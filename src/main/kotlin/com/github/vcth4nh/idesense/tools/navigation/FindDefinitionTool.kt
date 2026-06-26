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
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.search.GlobalSearchScope
import kotlinx.serialization.json.JsonObject

class FindDefinitionTool : AbstractMcpTool() {

    override val name = ToolNames.FIND_DEFINITION

    override val description = """
        Jump to the declaration of the symbol under the caret — the IDE's Go to Definition (F4 / Ctrl+B).
        Use when you have a reference and need to see the declaration; prefer this over ide_search_text
        or ide_find_class when you already know where the usage is.

        Returns: file path, 1-based line/column of the declaration, code preview, symbol name, kind,
        and qualified name.

        Gotchas: requires smart mode. Works for all languages and library sources (jar://…).
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

            // Prefer source files (.java) over compiled files (.class) for library classes
            val targetElement = PsiUtils.getNavigationElement(resolvedElement)

            // Try the target element first, then its navigationElement (for Kotlin light classes
            // and import directives where the resolved element may be a compiled class without a virtual file)
            val effectiveTarget = if (targetElement.containingFile?.virtualFile != null) {
                targetElement
            } else {
                val navElement = targetElement.navigationElement
                if (navElement != targetElement && navElement.containingFile?.virtualFile != null) {
                    navElement
                } else {
                    targetElement
                }
            }

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
