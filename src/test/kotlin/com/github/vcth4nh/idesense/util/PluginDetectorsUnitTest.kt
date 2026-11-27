package com.github.vcth4nh.idesense.util

import junit.framework.TestCase
import org.w3c.dom.Element
import javax.xml.parsers.DocumentBuilderFactory

class PluginDetectorsUnitTest : TestCase() {

    fun testPluginDetectorBasicProperties() {
        val detector = PluginDetector("Test", "TestLanguage")
        assertEquals("Test", detector.name)
    }

    fun testPluginDetectorsRegistryHasAllLanguages() {
        assertNotNull(PluginDetectors.php)
    }

    fun testPluginDetectorsHaveCorrectNames() {
        assertEquals("PHP", PluginDetectors.php.name)
    }

    /** A detector finds its plugin only when its key is the language of the config file. */
    fun testDetectorLanguagesAreTheLanguagesOfTheirConfigFiles() {
        assertEquals(listOf(PluginDetectors.php.language), kindResolverLanguages("META-INF/php-features.xml"))
    }

    private fun kindResolverLanguages(resource: String): List<String> {
        val document = javaClass.classLoader.getResourceAsStream(resource)!!.use {
            DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(it)
        }
        val resolvers = document.getElementsByTagName("languageKindResolver")
        return (0 until resolvers.length).map { (resolvers.item(it) as Element).getAttribute("language") }
    }
}
