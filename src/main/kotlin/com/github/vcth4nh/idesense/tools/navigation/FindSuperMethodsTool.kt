package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.constants.ErrorMessages
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.MethodInfo
import com.github.vcth4nh.idesense.tools.models.SuperMethodInfo
import com.github.vcth4nh.idesense.tools.models.SuperMethodsResult
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.intellij.openapi.project.Project
import kotlinx.serialization.json.JsonObject

/**
 * Tool for finding super methods across multiple languages.
 *
 * Supports: Java, Kotlin, Python, JavaScript, TypeScript, PHP, Go (interface satisfaction — methods and types), Rust (trait fn/const/type alias overrides).
 *
 * Delegates to language-specific providers via the [SuperMethodsProvider] extension point.
 */
class FindSuperMethodsTool : AbstractMcpTool() {

    override val name = ToolNames.FIND_SUPER_METHODS

    override val description = """
        Navigate UP the hierarchy from a code element — the IDE's Go to Super (Ctrl+U). Use when you
        need what a method overrides, what interfaces a class/type extends, or what abstract method a
        lambda implements. Prefer this over ide_type_hierarchy when you only need the direct super
        of a single element (cheaper); use ide_type_hierarchy for the full ancestor tree.

        Anchor on: a method (→ super-methods, transitive chain), a class/interface/struct/trait
        (→ direct supertypes), a lambda (→ the SAM it implements), or a field/constant (→ overridden
        member).

        Returns: the source element info and the matching super(s) with file locations, qualified
        names, and kinds. Empty hierarchy when the element has no super.

        Gotchas: requires smart mode. Languages: Java, Kotlin, Python, JS/TS, PHP, Go, Rust.
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

            // Anchor resolution is delegated entirely to the language provider: it returns null
            // only when the caret is not on a super-navigable element (method, class, field/const,
            // or lambda), and an empty hierarchy when the element is valid but has no super.
            val superMethodsData = LanguageServices.findSuperMethods(element, project)
            if (superMethodsData == null) {
                return@suspendingReadAction createErrorResult(
                    "No super-navigable element at position. Place the caret on a method, class, field/const, or lambda."
                )
            }

            // Convert handler result to tool result
            createJsonResult(SuperMethodsResult(
                method = MethodInfo(
                    name = superMethodsData.method.name,
                    qualifiedName = superMethodsData.method.qualifiedName,
                    kind = superMethodsData.method.kind,
                    file = superMethodsData.method.file,
                    line = superMethodsData.method.line,
                    column = superMethodsData.method.column,
                ),
                hierarchy = superMethodsData.hierarchy.map { superMethod ->
                    SuperMethodInfo(
                        name = superMethod.name,
                        qualifiedName = superMethod.qualifiedName,
                        kind = superMethod.kind,
                        file = superMethod.file,
                        line = superMethod.line,
                        column = superMethod.column,
                    )
                },
            ))
        }
    }
}
