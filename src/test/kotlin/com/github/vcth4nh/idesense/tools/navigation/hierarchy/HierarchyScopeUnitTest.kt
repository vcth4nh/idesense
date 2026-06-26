package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.intellij.ide.hierarchy.HierarchyBrowserBaseEx
import junit.framework.TestCase
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class HierarchyScopeUnitTest : TestCase() {

    fun testWireValuesAndIdeScopeMapping() {
        assertEquals(HierarchyBrowserBaseEx.SCOPE_ALL, HierarchyScope.ALL.ideScopeType)
        assertEquals(HierarchyBrowserBaseEx.SCOPE_PROJECT, HierarchyScope.PRODUCTION.ideScopeType)
        assertEquals(HierarchyBrowserBaseEx.SCOPE_TEST, HierarchyScope.TEST.ideScopeType)
        assertEquals(HierarchyBrowserBaseEx.SCOPE_CLASS, HierarchyScope.THIS_CLASS.ideScopeType)
        assertEquals(HierarchyBrowserBaseEx.SCOPE_MODULE, HierarchyScope.THIS_MODULE.ideScopeType)
        assertEquals("all", HierarchyScope.ALL.wireValue)
        assertEquals("production", HierarchyScope.PRODUCTION.wireValue)
        assertEquals("this_class", HierarchyScope.THIS_CLASS.wireValue)
        assertEquals("this_module", HierarchyScope.THIS_MODULE.wireValue)
    }

    fun testScopeSets() {
        assertEquals(
            listOf("all", "production", "test", "this_class", "this_module"),
            HierarchyScope.wireValues(HierarchyScope.CALL_HIERARCHY_SCOPES)
        )
        assertEquals(
            listOf("all", "production", "test"),
            HierarchyScope.wireValues(HierarchyScope.TYPE_HIERARCHY_SCOPES)
        )
    }

    fun testFromWireValue() {
        assertEquals(HierarchyScope.PRODUCTION, HierarchyScope.fromWireValue("production"))
        assertNull(HierarchyScope.fromWireValue("project_files"))
        assertNull(HierarchyScope.fromWireValue("nonsense"))
    }

    fun testParseDefaultsToAll() {
        assertEquals(HierarchyScope.ALL, HierarchyScope.parse(buildJsonObject {}))
    }

    fun testParseReadsScope() {
        val args: JsonObject = buildJsonObject { put("scope", JsonPrimitive("test")) }
        assertEquals(HierarchyScope.TEST, HierarchyScope.parse(args))
    }

    fun testParseThrowsOnUnknown() {
        val args: JsonObject = buildJsonObject { put("scope", JsonPrimitive("project_files")) }
        try {
            HierarchyScope.parse(args)
            fail("Expected IllegalArgumentException for unknown scope")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message!!.contains("project_files"))
        }
    }
}
