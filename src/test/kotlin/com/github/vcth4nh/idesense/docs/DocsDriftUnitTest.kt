package com.github.vcth4nh.idesense.docs

import com.github.vcth4nh.idesense.constants.SchemaConstants
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.settings.McpSettings
import com.github.vcth4nh.idesense.tools.McpTool
import com.github.vcth4nh.idesense.tools.intelligence.GetDiagnosticsTool
import com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.FileStructureTool
import com.github.vcth4nh.idesense.tools.navigation.FindClassTool
import com.github.vcth4nh.idesense.tools.navigation.FindDefinitionTool
import com.github.vcth4nh.idesense.tools.navigation.FindFileTool
import com.github.vcth4nh.idesense.tools.navigation.FindImplementationsTool
import com.github.vcth4nh.idesense.tools.navigation.FindSuperMethodsTool
import com.github.vcth4nh.idesense.tools.navigation.FindSymbolTool
import com.github.vcth4nh.idesense.tools.navigation.FindUsagesTool
import com.github.vcth4nh.idesense.tools.navigation.ReadFileTool
import com.github.vcth4nh.idesense.tools.navigation.SearchTextTool
import com.github.vcth4nh.idesense.tools.navigation.TypeHierarchyTool
import com.github.vcth4nh.idesense.tools.project.GetIndexStatusTool
import com.github.vcth4nh.idesense.tools.project.InstallPluginTool
import com.github.vcth4nh.idesense.tools.project.RestartIdeTool
import com.github.vcth4nh.idesense.tools.project.SyncFilesTool
import com.github.vcth4nh.idesense.tools.refactoring.MoveFileTool
import com.github.vcth4nh.idesense.tools.refactoring.RenameSymbolTool
import junit.framework.TestCase
import kotlinx.serialization.json.jsonObject
import java.io.File

/**
 * Pure unit test (no platform) that pins the docs to code-derived facts.
 * SSOT: ToolNames.ALL (names), McpSettings disabledTools (enabled-state), inputSchema (params).
 * Parsing is STRUCTURAL (one uniform locus per catalog); prose mentions are ignored by construction,
 * so this test needs NO per-token exclusion allowlist.
 */
class DocsDriftUnitTest : TestCase() {

    private val repoRoot: File = locateRepoRoot()
    private val skillDir = File(repoRoot, "src/main/resources/skill/idesense")

    private fun locateRepoRoot(): File {
        var dir = File(System.getProperty("user.dir")).absoluteFile
        while (dir.parentFile != null && !File(dir, "settings.gradle.kts").exists()) {
            dir = dir.parentFile
        }
        check(File(dir, "settings.gradle.kts").exists()) {
            "Could not locate repo root from user.dir=${System.getProperty("user.dir")}"
        }
        return dir
    }

    private fun read(relPath: String): String {
        val f = File(repoRoot, relPath)
        check(f.exists()) { "Doc not found: ${f.absolutePath}" }
        return f.readText()
    }

    private fun readSkill(name: String): String {
        val f = File(skillDir, name)
        check(f.exists()) { "Skill doc not found: ${f.absolutePath}" }
        return f.readText()
    }

    private val allTools: Set<String> = ToolNames.ALL.toSet()
    private val disabled: Set<String> = McpSettings.State().disabledTools.toSet()
    private val enabled: Set<String> = allTools - disabled

    private fun allToolInstances(): List<McpTool> = listOf(
        FindUsagesTool(), FindDefinitionTool(), TypeHierarchyTool(), CallHierarchyTool(),
        FindImplementationsTool(), FindSymbolTool(), FindSuperMethodsTool(), FileStructureTool(),
        FindClassTool(), FindFileTool(), SearchTextTool(), ReadFileTool(), GetDiagnosticsTool(),
        GetIndexStatusTool(), SyncFilesTool(), InstallPluginTool(), RestartIdeTool(),
        RenameSymbolTool(), MoveFileTool()
    )

    private fun schemaProps(tool: McpTool): Set<String> =
        tool.inputSchema[SchemaConstants.PROPERTIES]?.jsonObject?.keys ?: emptySet()

    private val headingToken = Regex("""(?m)^#{2,}\s+(ide_[a-z_]+)""")
    private val tableCol1Tool = Regex("""(?m)^\|\s*`(ide_[a-z_]+)`""")
    private val paramRow = Regex("""(?m)^\|\s*`([A-Za-z_][A-Za-z0-9_]*)`\s*\|""")
    private val paramAliases = setOf("limit", "maxResults", "cursor")

    private fun headingSet(md: String) = headingToken.findAll(md).map { it.groupValues[1] }.toSet()
    private fun tableToolSet(md: String) = tableCol1Tool.findAll(md).map { it.groupValues[1] }.toSet()

    fun testCanonicalCounts() {
        assertEquals("Expected 19 tools in ToolNames.ALL", 19, allTools.size)
        assertEquals(
            "Default-disabled set must be exactly the mutating tools plus ide_read_file (analysis-only default, #72)",
            setOf(
                ToolNames.INSTALL_PLUGIN, ToolNames.RESTART_IDE, ToolNames.READ_FILE,
                ToolNames.REFACTOR_RENAME, ToolNames.REFACTOR_MOVE
            ),
            disabled
        )
        assertEquals("Every tool must be instantiable for schema introspection",
            allTools, allToolInstances().map { it.name }.toSet())
    }

    fun testUsageDocumentsEveryTool() {
        assertEquals("USAGE.md per-tool headings must equal the canonical tool set",
            allTools, headingSet(read("docs/USAGE.md")))
    }

    fun testReadmeCuratedSubset() {
        val readme = tableToolSet(read("README.md"))
        assertTrue("README table lists unknown tool(s): ${readme - allTools}", (readme - allTools).isEmpty())
        assertTrue("README table missing enabled tool(s): ${enabled - readme}", (enabled - readme).isEmpty())
    }

    fun testToolsReferenceCuratedSubset() {
        val ref = headingSet(readSkill("references/tools-reference.md"))
        assertTrue("tools-reference lists unknown tool(s): ${ref - allTools}", (ref - allTools).isEmpty())
        assertTrue("tools-reference missing enabled tool(s): ${enabled - ref}", (enabled - ref).isEmpty())
    }

    fun testSkillTriggerEqualsEnabled() {
        val skill = readSkill("SKILL.md")
        val frontmatter = skill.substringAfter("---").substringBefore("---")
        val triggerTokens = Regex("""ide_[a-z_]+""").findAll(frontmatter).map { it.value }.toSet()
        assertEquals("SKILL.md frontmatter trigger list must equal the enabled tool set",
            enabled, triggerTokens)
    }

    fun testArchitectureMechanismRowPerTool() {
        assertEquals("ARCHITECTURE.md mechanism table must have one row per tool",
            allTools, tableToolSet(read("docs/ARCHITECTURE.md")))
    }

    fun testUsageParamsSubsetOfSchema() {
        val usage = read("docs/USAGE.md")
        val byName = allToolInstances().associateBy { it.name }
        val sections = headingToken.findAll(usage).toList()
        val problems = mutableListOf<String>()
        for (i in sections.indices) {
            val name = sections[i].groupValues[1]
            val tool = byName[name] ?: continue
            val start = sections[i].range.last + 1
            val end = if (i + 1 < sections.size) sections[i + 1].range.first else usage.length
            val body = usage.substring(start, end)
            val documented = paramRow.findAll(body).map { it.groupValues[1] }.toSet()
            val allowed = schemaProps(tool) + paramAliases
            val phantom = documented - allowed
            if (phantom.isNotEmpty()) problems += "$name documents non-schema params: $phantom"
        }
        assertTrue(problems.joinToString("\n"), problems.isEmpty())
    }

    fun testUsageDocumentsEverySchemaParam() {
        // COMMON: params documented in a shared section of USAGE.md that are not repeated in
        // per-tool tables, so their absence from a tool's per-tool section is expected.
        //
        // Only "project_path" qualifies: USAGE.md has a dedicated "Common Parameters" section
        // (before the per-tool headings) that documents it as applying to *all* tools, and
        // indeed every tool schema includes it.  The "Position Parameters" subsection documents
        // file/line/column, but those are NOT present in every tool's schema (e.g.
        // ide_index_status, ide_restart have no positional params), so they
        // cannot be excluded — the per-tool section for tools that *do* have them must list them.
        val COMMON = setOf("project_path")

        val usage = read("docs/USAGE.md")
        val byName = allToolInstances().associateBy { it.name }
        val sections = headingToken.findAll(usage).toList()
        val problems = mutableListOf<String>()
        for (i in sections.indices) {
            val name = sections[i].groupValues[1]
            val tool = byName[name] ?: continue
            val start = sections[i].range.last + 1
            val end = if (i + 1 < sections.size) sections[i + 1].range.first else usage.length
            val body = usage.substring(start, end)
            val documented = paramRow.findAll(body).map { it.groupValues[1] }.toSet()
            val missing = schemaProps(tool) - documented - COMMON
            if (missing.isNotEmpty()) problems += "$name missing documented params: $missing"
        }
        assertTrue(problems.joinToString("\n"), problems.isEmpty())
    }

    fun testToolsReferenceHasReturnsPerTool() {
        val ref = readSkill("references/tools-reference.md")
        val sections = headingToken.findAll(ref).toList()
        val missing = mutableListOf<String>()
        for (i in sections.indices) {
            val name = sections[i].groupValues[1]
            if (name !in allTools) continue
            val start = sections[i].range.last + 1
            val end = if (i + 1 < sections.size) sections[i + 1].range.first else ref.length
            val body = ref.substring(start, end)
            if (!body.contains("Returns", ignoreCase = true)) missing += name
        }
        assertTrue("tools-reference.md tools missing a Returns block: $missing", missing.isEmpty())
    }
}
