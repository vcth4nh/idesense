package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.go.GoFindUsages
import junit.framework.TestCase

class GoFindUsagesUnitTest : TestCase() {

    // Stands for com.goide.usages.GoMethodFindUsagesOptions: a public boolean field `findBaseMethods`.
    class WithFlag { @JvmField var findBaseMethods: Boolean = true }
    class WithoutFlag
    class WrongType { @JvmField var findBaseMethods: String = "yes" }

    // GoMethodFindUsagesOptions is package-private: the field is public, its class is not.
    // This test is not in the package of GoFindUsages, so a read needs `isAccessible`.
    private class PrivateWithFlag { @JvmField var findBaseMethods: Boolean = true }

    fun testSearchesBaseMethodsReadsThePublicField() {
        assertTrue(GoFindUsages.searchesBaseMethods(WithFlag()))
        assertFalse(GoFindUsages.searchesBaseMethods(WithFlag().apply { findBaseMethods = false }))
    }

    fun testSearchesBaseMethodsIsFalseWithoutTheField() {
        assertFalse(GoFindUsages.searchesBaseMethods(WithoutFlag()))
        assertFalse(GoFindUsages.searchesBaseMethods(WrongType()))
    }

    fun testSearchesBaseMethodsReadsTheFieldOfANonPublicClass() {
        assertTrue(GoFindUsages.searchesBaseMethods(PrivateWithFlag()))
        assertFalse(GoFindUsages.searchesBaseMethods(PrivateWithFlag().apply { findBaseMethods = false }))
    }

    fun testSetFindBaseMethodsSetsThePublicField() {
        val options = WithFlag()

        assertTrue(GoFindUsages.setFindBaseMethods(options, false))
        assertFalse(options.findBaseMethods)
    }

    fun testSetFindBaseMethodsIsFalseWithoutTheField() {
        assertFalse(GoFindUsages.setFindBaseMethods(WithoutFlag(), false))
        assertFalse(GoFindUsages.setFindBaseMethods(WrongType(), false))
    }

    fun testSetFindBaseMethodsSetsTheFieldOfANonPublicClass() {
        val options = PrivateWithFlag()

        assertTrue(GoFindUsages.setFindBaseMethods(options, false))
        assertFalse(options.findBaseMethods)
    }
}
