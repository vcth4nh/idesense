package com.github.vcth4nh.idesense.util

import com.github.vcth4nh.idesense.tools.models.StructureNode

/**
 * Renders a tree of [StructureNode]s as a 2-space-indented text tree.
 *
 * Per-line format: `<modifiers...> <name>[ <signature>] (line N)`.
 * Empty fields are silently omitted; the order is preserved for readability.
 */
object TreeFormatter {

    fun format(nodes: List<StructureNode>, fileName: String): String {
        val lines = mutableListOf<String>()
        lines.add(fileName)
        lines.add("")
        nodes.forEach { formatNode(it, indent = 0, output = lines) }
        return lines.joinToString("\n")
    }

    private fun formatNode(node: StructureNode, indent: Int, output: MutableList<String>) {
        val indentStr = "  ".repeat(indent)
        val parts = mutableListOf<String>()
        parts.addAll(node.modifiers)
        parts.add(node.name)
        node.signature?.takeIf { it.isNotBlank() }?.let { parts.add(it) }
        output.add("$indentStr${parts.joinToString(" ")} (line ${node.line})")
        node.children.forEach { formatNode(it, indent + 1, output) }
    }
}
