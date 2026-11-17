package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.javascript.JavaScriptFindUsages
import com.intellij.psi.PsiReference
import io.mockk.mockk
import junit.framework.TestCase

class JavaScriptFindUsagesUnitTest : TestCase() {

    fun testDynamicWhenTheResolveIsDynamic() = assertEquals(true, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = true, strictEnough = true))
    fun testDynamicWhenTheReferenceIsNotStrict() = assertEquals(true, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = false, strictEnough = false))
    fun testNotDynamicWhenBothChecksPass() = assertEquals(false, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = false, strictEnough = true))
    fun testUnknownWhenNoCheckRan() = assertNull(JavaScriptFindUsages.isDynamicUsage(resolveDynamic = null, strictEnough = null))
    fun testOneCheckIsSufficientForTrue() = assertEquals(true, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = true, strictEnough = null))
    fun testOneCheckAloneCannotSayFalse() = assertNull(JavaScriptFindUsages.isDynamicUsage(resolveDynamic = false, strictEnough = null))

    // The JavaScript plugin is not on the unit-test classpath. A strict mock fails when the check reads the reference.
    fun testUnknownWhenTheJavaScriptPluginIsAbsent() = assertNull(JavaScriptFindUsages.isDynamicUsage(mockk<PsiReference>(), emptyList()))
}
