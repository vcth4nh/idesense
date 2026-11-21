package com.github.vcth4nh.idesense.server

import com.intellij.testFramework.fixtures.BasePlatformTestCase

class McpServerServiceTest : BasePlatformTestCase() {

    fun testInitializeStartsNoServerInUnitTestMode() {
        val service = McpServerService.getInstance()
        // The constructor starts the initialization in a coroutine. initialize() is synchronized
        // and returns at once after the first run, so this call returns only when the
        // initialization is complete.
        service.initialize()

        assertTrue("The service must be initialized", service.isInitialized)
        assertTrue(
            "The tool registry must keep the built-in tools in unit test mode",
            service.getToolRegistry().getAllTools().isNotEmpty()
        )
        assertFalse("No MCP server may run in unit test mode", service.isServerRunning())
        assertNull("No server start may happen in unit test mode, so no server error", service.getServerError())
    }
}
