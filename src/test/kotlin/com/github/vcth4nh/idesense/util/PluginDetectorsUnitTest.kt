package com.github.vcth4nh.idesense.util

import junit.framework.TestCase

class PluginDetectorsUnitTest : TestCase() {

    fun testPluginDetectorBasicProperties() {
        val detector = PluginDetector("Test", "TestLanguage")
        assertEquals("Test", detector.name)
    }

    fun testPluginDetectorsRegistryHasAllLanguages() {
        assertNotNull(PluginDetectors.php)
        assertNotNull(PluginDetectors.rust)
    }

    fun testPluginDetectorsHaveCorrectNames() {
        assertEquals("PHP", PluginDetectors.php.name)
        assertEquals("Rust", PluginDetectors.rust.name)
    }
}
