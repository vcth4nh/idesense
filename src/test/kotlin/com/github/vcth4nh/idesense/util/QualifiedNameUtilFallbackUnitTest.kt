package com.github.vcth4nh.idesense.util

import junit.framework.TestCase

class QualifiedNameUtilFallbackUnitTest : TestCase() {

    fun testFormatGoQualifiedName_topLevelFunction() {
        // package.Function — e.g. main.MakeDefaultShapes
        val result = QualifiedNameUtil.formatGoQualifiedName(
            packageName = "main",
            receiverType = null,
            name = "MakeDefaultShapes"
        )
        assertEquals("main.MakeDefaultShapes", result)
    }

    fun testFormatGoQualifiedName_methodOnReceiver() {
        // package.Receiver.Method — e.g. main.Circle.Area
        val result = QualifiedNameUtil.formatGoQualifiedName(
            packageName = "main",
            receiverType = "Circle",
            name = "Area"
        )
        assertEquals("main.Circle.Area", result)
    }

    fun testFormatGoQualifiedName_methodOnPointerReceiver() {
        // Pointer receiver text "*ShapeCollection" → strip leading *
        val result = QualifiedNameUtil.formatGoQualifiedName(
            packageName = "main",
            receiverType = "*ShapeCollection",
            name = "Add"
        )
        assertEquals("main.ShapeCollection.Add", result)
    }

    fun testFormatGoQualifiedName_emptyPackageOmitsPrefix() {
        // Defensive: package empty → just the name
        val result = QualifiedNameUtil.formatGoQualifiedName(
            packageName = "",
            receiverType = null,
            name = "Foo"
        )
        assertEquals("Foo", result)
    }

    fun testFormatRustQualifiedName_traitMethod() {
        // crate::quirks::IntCoercer::coerce
        val result = QualifiedNameUtil.formatRustQualifiedName(
            ancestorChain = listOf("crate", "quirks", "IntCoercer"),
            name = "coerce"
        )
        assertEquals("crate::quirks::IntCoercer::coerce", result)
    }

    fun testFormatRustQualifiedName_topLevelFunction_excludesFilename() {
        // Top-level function: ancestor chain should be just ["crate"], NOT ["crate", "main.rs"].
        // This documents the rustFallback PSI-walk contract: file boundaries do NOT contribute
        // to the chain. RsFile extends RsMod (a RsNamedElement) so a naive walk would otherwise
        // emit "crate::main.rs::make_default_shapes". See rustFallback() in QualifiedNameUtil.kt.
        val result = QualifiedNameUtil.formatRustQualifiedName(
            ancestorChain = listOf("crate"),
            name = "make_default_shapes"
        )
        assertEquals("crate::make_default_shapes", result)
    }

    fun testFormatRustQualifiedName_emptyAncestors() {
        val result = QualifiedNameUtil.formatRustQualifiedName(
            ancestorChain = emptyList(),
            name = "foo"
        )
        assertEquals("foo", result)
    }
}
