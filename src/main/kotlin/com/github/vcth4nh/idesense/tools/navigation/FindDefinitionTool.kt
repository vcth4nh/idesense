package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.DefinitionResult
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.util.PsiUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiDirectory
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.search.GlobalSearchScope
import kotlinx.serialization.json.JsonObject

class FindDefinitionTool : AbstractMcpTool() {

    companion object {
        // Kotlin PSI is only present when the Kotlin plugin is installed; resolve reflectively
        // so this class loads in non-IntelliJ IDEs (same approach as the PsiPackage guard below).
        private val ktConstructorClass: Class<*>? by lazy {
            try {
                Class.forName("org.jetbrains.kotlin.psi.KtConstructor")
            } catch (_: ClassNotFoundException) {
                null
            }
        }

        /**
         * Maps a resolved element to the declaration the IDE presents: prefers source files over
         * compiled ones, falls back to the navigationElement when the direct target has no virtual
         * file (Kotlin light classes, import directives), then remaps Kotlin constructors to their
         * class (#17). Shared with ide_explain_symbol so both report the same declaration identity.
         */
        internal fun effectiveDeclarationTarget(resolved: PsiElement): PsiElement {
            val targetElement = PsiUtils.getNavigationElement(resolved)
            val navigationTarget = if (targetElement.containingFile?.virtualFile != null) {
                targetElement
            } else {
                val navElement = targetElement.navigationElement
                if (navElement != targetElement && navElement.containingFile?.virtualFile != null) {
                    navElement
                } else {
                    targetElement
                }
            }
            return adjustConstructorTarget(navigationTarget)
        }

        /**
         * Kotlin resolves a constructor call to the KtPrimaryConstructor/KtSecondaryConstructor
         * element. Report the class being constructed instead, matching the declaration-site
         * result and Java's behavior for `new Foo()` (#17).
         */
        private fun adjustConstructorTarget(element: PsiElement): PsiElement {
            val ctorClass = ktConstructorClass ?: return element
            if (!ctorClass.isInstance(element)) return element
            return try {
                ctorClass.getMethod("getContainingClassOrObject").invoke(element) as? PsiElement ?: element
            } catch (_: Exception) {
                element
            }
        }
    }

    override val name = ToolNames.FIND_DEFINITION

    override val description = """
        Jump to the declaration of the symbol under the caret — the IDE's Go to Definition (F4 / Ctrl+B).
        Use when you have a reference and need to see the declaration; prefer this over ide_search_text
        or ide_find_class when you already know where the usage is.

        Returns: file path, 1-based line/column of the declaration, code preview, symbol name, kind,
        and qualified name when available (otherwise an enclosing-scope path).

        Gotchas: requires smart mode. Works for any language whose JetBrains plugin provides Go to Declaration/reference resolution (Java, Kotlin, Python, JS/TS, Go, PHP, Rust in live coverage), and library sources (jar://…).
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .file(description = "Project-relative file path, or a dependency/library absolute path or jar:// URL previously returned by the plugin.")
        .lineAndColumn()
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        requireSmartMode(project)

        return suspendingReadAction {
            val element = resolveElementFromArguments(project, arguments, allowLibraryFilesForPosition = true).getOrElse {
                return@suspendingReadAction createErrorResult(it.message ?: ErrorMessages.COULD_NOT_RESOLVE_SYMBOL)
            }

            // Symbol-based resolution returns the declaration directly (PsiNamedElement).
            // Position-based resolution returns a leaf token that needs reference resolution.
            val resolvedElement = element as? PsiNamedElement
                ?: (PsiUtils.resolveTargetElement(element)
                    ?: return@suspendingReadAction createErrorResult(ErrorMessages.SYMBOL_NOT_RESOLVED))

            val effectiveTarget = effectiveDeclarationTarget(resolvedElement)

            // Handle package/directory references (e.g., cursor on package segment in import statement)
            if (effectiveTarget is PsiDirectory) {
                val dirPath = getRelativePath(project, effectiveTarget.virtualFile)
                return@suspendingReadAction createJsonResult(DefinitionResult(
                    file = dirPath,
                    line = 1,
                    column = 1,
                    name = effectiveTarget.name ?: dirPath,
                    kind = "PACKAGE",
                    preview = "Package directory: $dirPath",
                ))
            }
            // PsiPackage is Java-plugin-only; guard with Class.forName / isInstance to avoid NoClassDefFoundError in non-Java IDEs.
            // getDirectories remains reflective (loading package directories is out of scope for the QualifiedNameProvider migration).
            try {
                val psiPackageClass = Class.forName("com.intellij.psi.PsiPackage")
                if (psiPackageClass.isInstance(effectiveTarget)) {
                    val qualifiedName = QualifiedNameUtil.getQualifiedName(effectiveTarget) ?: "unknown"
                    val dirs = psiPackageClass
                        .getMethod("getDirectories", GlobalSearchScope::class.java)
                        .invoke(effectiveTarget, GlobalSearchScope.projectScope(project)) as Array<*>
                    val dir = dirs.firstOrNull() as? PsiDirectory
                    if (dir != null) {
                        val dirPath = getRelativePath(project, dir.virtualFile)
                        return@suspendingReadAction createJsonResult(DefinitionResult(
                            file = dirPath,
                            line = 1,
                            column = 1,
                            name = qualifiedName,
                            kind = "PACKAGE",
                            preview = "Package: $qualifiedName",
                        ))
                    }
                }
            } catch (_: ClassNotFoundException) {
                // Java plugin not available — skip PsiPackage handling
            }

            val targetFile = effectiveTarget.containingFile?.virtualFile
                ?: return@suspendingReadAction createErrorResult(ErrorMessages.DEFINITION_FILE_NOT_FOUND)

            val document = PsiDocumentManager.getInstance(project)
                .getDocument(effectiveTarget.containingFile)
                ?: return@suspendingReadAction createErrorResult(ErrorMessages.DEFINITION_DOCUMENT_NOT_FOUND)

            val targetLine = document.getLineNumber(effectiveTarget.textOffset) + 1
            val targetColumn = effectiveTarget.textOffset -
                document.getLineStartOffset(targetLine - 1) + 1

            val preview = document.getText(
                TextRange(document.getLineStartOffset(targetLine - 1), document.getLineEndOffset(targetLine - 1))
            ).trim()

            val name = if (effectiveTarget is PsiNamedElement) {
                effectiveTarget.name ?: "unknown"
            } else {
                effectiveTarget.text.take(50)
            }
            val qualifiedName = QualifiedNameUtil.getQualifiedName(effectiveTarget)
            val kind = LanguageServices.getKind(effectiveTarget)
            val enclosingScope = if (qualifiedName == null) PsiUtils.getEnclosingScope(effectiveTarget) else null

            createJsonResult(DefinitionResult(
                file = getRelativePath(project, targetFile),
                line = targetLine,
                column = targetColumn,
                name = name,
                kind = kind,
                preview = preview,
                qualifiedName = qualifiedName,
                enclosingScope = enclosingScope
            ))
        }
    }
}
