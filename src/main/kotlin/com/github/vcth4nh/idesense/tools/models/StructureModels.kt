package com.github.vcth4nh.idesense.tools.models

import kotlinx.serialization.Serializable

// One node in the file structure tree.
//
// TreeFormatter renders each node as: modifiers name signature (line N).
// modifiers   source-order tokens from the element's modifier list (e.g. public, private,
//             abstract, final, override, suspend, data, sealed). Empty when the language
//             has no modifier concept (Go) or the element carries none.
// name        IDE's ItemPresentation.presentableText for the element, as one line of at most
//             80 characters; `{}` for a JavaScript or TypeScript object literal with no text.
// signature   IDE's ItemPresentation.locationString (return type, qualifier, etc.).
// line        1-based source line of the element's navigation element, where the Structure
//             window goes; of the element itself when that is in another file.
// children    nested nodes, recursively decorated.
@Serializable
data class StructureNode(
    val name: String,
    val modifiers: List<String> = emptyList(),
    val signature: String? = null,
    val line: Int,
    val children: List<StructureNode> = emptyList()
)

// Output model returned by the file_structure tool.
@Serializable
data class FileStructureResult(
    val file: String,
    val language: String,
    val structure: String
)
