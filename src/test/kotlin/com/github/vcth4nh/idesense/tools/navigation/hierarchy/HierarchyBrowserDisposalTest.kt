package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.github.vcth4nh.idesense.tools.McpTool
import com.github.vcth4nh.idesense.tools.navigation.CallHierarchyTool
import com.github.vcth4nh.idesense.tools.navigation.TypeHierarchyTool
import com.intellij.ide.hierarchy.HierarchyBrowserBaseEx
import com.intellij.testFramework.LeakHunter
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Platform test for GH #26: every hierarchy call constructs a per-call
 * [HierarchyBrowserBaseEx] (whose ctor registers a `SingleAlarm` under it in the
 * Disposer tree). The tools must dispose that browser once the walk result is
 * consumed, so no browser stays reachable from the platform's roots afterwards.
 */
class HierarchyBrowserDisposalTest : BasePlatformTestCase() {

    private fun addFixture() {
        myFixture.addFileToProject(
            "Service.java",
            """
            public class Service {
                public void doWork() {}
            }
            """.trimIndent()
        )
        myFixture.addFileToProject(
            "Caller.java",
            """
            public class Caller extends Service {
                public void call() { doWork(); }
            }
            """.trimIndent()
        )
    }

    /** Runs the tool and fails (does not skip) on an error: a walk that never built a browser proves nothing. */
    private fun runOk(tool: McpTool, args: JsonObject): String = runBlocking {
        val result = tool.execute(project, args)
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("${tool.name} must build a hierarchy for the leak check to be meaningful: $text", result.isError)
        text
    }

    fun testHierarchyToolsLeaveNoBrowserReachable() {
        addFixture()

        val typeText = runOk(TypeHierarchyTool(), buildJsonObject { put("className", "Caller") })
        assertTrue("type hierarchy should list Service as a supertype: $typeText", typeText.contains("Service"))

        val callText = runOk(CallHierarchyTool(), buildJsonObject {
            put("symbol", "Service#doWork")
            put("direction", "callers")
        })
        assertTrue("call hierarchy should list Caller.call as a caller: $callText", callText.contains("call"))

        LeakHunter.checkLeak(LeakHunter.allRoots(), HierarchyBrowserBaseEx::class.java) { true }
    }
}
