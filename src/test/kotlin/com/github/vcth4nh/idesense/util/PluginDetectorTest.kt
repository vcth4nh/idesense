package com.github.vcth4nh.idesense.util

import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * A detector answers from the `languageKindResolver` extension point. The test platform has the
 * Java plugin, so `java-features.xml` is loaded; it has no PHP plugin, so
 * `php-features.xml` is not loaded.
 */
class PluginDetectorTest : BasePlatformTestCase() {

    fun testDetectorOfALanguageWithALoadedConfigFileAnswersTrue() {
        assertTrue(PluginDetector("Java", "JAVA").isAvailable)
    }

    fun testPhpDetectorAnswersFalseWithoutItsPlugin() {
        assertFalse(PluginDetectors.php.isAvailable)
    }

    fun testIfAvailableReturnsNullWhenUnavailable() {
        val detector = PluginDetector("Test", "NoSuchLanguage")
        assertNull(detector.ifAvailable { "found" })
    }

    fun testIfAvailableOrElseReturnsFallbackWhenUnavailable() {
        val detector = PluginDetector("Test", "NoSuchLanguage")
        assertEquals("default", detector.ifAvailableOrElse("default") { "found" })
    }
}
