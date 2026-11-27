package com.github.vcth4nh.idesense

import junit.framework.TestCase

class McpConstantsUnitTest : TestCase() {

    fun testServerVersionIsTheVersionOfTheBuild() {
        val buildVersion = System.getProperty("idesense.pluginVersion")
        assertNotNull("the test task sets idesense.pluginVersion", buildVersion)
        assertFalse("placeholder in SERVER_VERSION: ${McpConstants.SERVER_VERSION}", McpConstants.SERVER_VERSION.contains("\${"))
        assertEquals(buildVersion, McpConstants.SERVER_VERSION)
    }
}
