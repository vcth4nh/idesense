package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.javascript.JavaScriptFindUsages
import com.intellij.psi.PsiReference
import io.mockk.mockk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class JavaScriptFindUsagesUnitTest {

    @Test fun dynamicWhenTheResolveIsDynamic() = assertEquals(true, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = true, strictEnough = true))
    @Test fun dynamicWhenTheReferenceIsNotStrict() = assertEquals(true, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = false, strictEnough = false))
    @Test fun notDynamicWhenBothChecksPass() = assertEquals(false, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = false, strictEnough = true))
    @Test fun unknownWhenNoCheckRan() = assertNull(JavaScriptFindUsages.isDynamicUsage(resolveDynamic = null, strictEnough = null))
    @Test fun oneCheckIsSufficientForTrue() = assertEquals(true, JavaScriptFindUsages.isDynamicUsage(resolveDynamic = true, strictEnough = null))
    @Test fun oneCheckAloneCannotSayFalse() = assertNull(JavaScriptFindUsages.isDynamicUsage(resolveDynamic = false, strictEnough = null))

    // The JavaScript plugin is not on the unit-test classpath. A strict mock fails when the check reads the reference.
    @Test fun unknownWhenTheJavaScriptPluginIsAbsent() = assertNull(JavaScriptFindUsages.isDynamicUsage(mockk<PsiReference>(), emptyList()))
}
