package com.github.vcth4nh.idesense

import junit.framework.TestCase

class McpConstantsUnitTest : TestCase() {

    fun testServerVersionIsTheVersionOfTheBuild() {
        val buildVersion = System.getProperty("idesense.pluginVersion")
        assertNotNull("the test task sets idesense.pluginVersion", buildVersion)
        assertEquals(
            "SERVER_VERSION is not the version of the build (also when it is the placeholder \${version})",
            buildVersion,
            McpConstants.SERVER_VERSION,
        )
    }
}
