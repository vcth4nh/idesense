package com.github.vcth4nh.idesense.handlers

import com.intellij.openapi.progress.ProcessCanceledException
import junit.framework.TestCase

class LanguageServicesKindUnitTest : TestCase() {

    fun testTheTypeOfTheFindUsagesProviderGivesTheKind() {
        val kind = LanguageServices.kindFromIdeTypeOrClassName("GoMethodDeclarationImpl") { "method" }

        assertEquals("METHOD", kind)
    }

    fun testAnEmptyProviderTypeFallsBackToTheClassName() {
        val kind = LanguageServices.kindFromIdeTypeOrClassName("JSFunctionImpl") { "" }

        assertEquals("FUNCTION", kind)
    }

    // XmlFindUsagesProvider.getType throws IllegalArgumentException("Cannot get type for ...") for
    // an element it does not know, for example an HTML file node of a call hierarchy (#126).
    fun testAProviderThatThrowsFallsBackToTheClassName() {
        val kind = LanguageServices.kindFromIdeTypeOrClassName("HtmlFileImpl") {
            throw IllegalArgumentException("Cannot get type for HtmlFile:index.html")
        }

        assertEquals("SYMBOL", kind)
    }

    // PhpFindUsagesProvider.getType gives "Class constant" for a class constant and "Constant" for a
    // constant outside a class. The substring test for "class" gave CLASS to the class constant (#180).
    fun testAPhpClassConstantGetsTheKindOfAPhpConstant() {
        val classConstant = LanguageServices.kindFromIdeTypeOrClassName("ClassConstImpl") { "Class constant" }
        val constant = LanguageServices.kindFromIdeTypeOrClassName("ConstantImpl") { "Constant" }

        assertEquals("CONSTANT", classConstant)
        assertEquals(constant, classConstant)
    }

    fun testACancellationOfTheProviderIsRethrown() {
        try {
            LanguageServices.kindFromIdeTypeOrClassName("HtmlFileImpl") { throw ProcessCanceledException() }
            fail("The cancellation must reach the caller")
        } catch (_: ProcessCanceledException) {
        }
    }
}
