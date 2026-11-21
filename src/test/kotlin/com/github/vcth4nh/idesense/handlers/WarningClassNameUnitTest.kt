package com.github.vcth4nh.idesense.handlers

import com.intellij.find.findUsages.FindUsagesHandlerFactory
import junit.framework.TestCase

// The name of a handler class or of a handler factory class in a warning of the find usages
// search (#206).
class WarningClassNameUnitTest : TestCase() {

    private val anonymous = object : Any() {}

    fun testAnAnonymousClassGivesItsNameWithoutThePackage() {
        val type = anonymous.javaClass
        assertEquals("", type.simpleName)
        assertEquals("WarningClassNameUnitTest\$anonymous\$1", FindUsagesHandlerSearch.warningClassName(type))
    }

    fun testATopLevelClassGivesItsSimpleName() {
        assertEquals("FindUsagesHandlerFactory", FindUsagesHandlerSearch.warningClassName(FindUsagesHandlerFactory::class.java))
    }

    fun testANamedNestedClassGivesItsSimpleName() {
        val type = FindUsagesHandlerFactory.OperationMode::class.java
        assertEquals("OperationMode", FindUsagesHandlerSearch.warningClassName(type))
    }
}
