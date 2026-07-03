package com.github.vcth4nh.idesense.util

import junit.framework.TestCase

class PluginDetectorsUnitTest : TestCase() {

    fun testPluginDetectorBasicProperties() {
        val detector = PluginDetector("Test", listOf("com.test.plugin"))
        assertEquals("Test", detector.name)
    }

    fun testPluginDetectorWithFallbackClass() {
        val detector = PluginDetector("Test", listOf("com.test.plugin"), fallbackClass = "com.nonexistent.Class")
        assertFalse(detector.isAvailable)
    }

    fun testIfAvailableReturnsNullWhenUnavailable() {
        val detector = PluginDetector("Test", listOf("com.nonexistent.plugin"))
        val result = detector.ifAvailable { "found" }
        assertNull(result)
    }

    fun testIfAvailableOrElseReturnsFallbackWhenUnavailable() {
        val detector = PluginDetector("Test", listOf("com.nonexistent.plugin"))
        val result = detector.ifAvailableOrElse("default") { "found" }
        assertEquals("default", result)
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
