package com.github.vcth4nh.idesense.handlers.rust

import com.intellij.psi.PsiElement
import io.mockk.mockk
import junit.framework.TestCase

class RustSuperMethodsProviderUnitTest : TestCase() {

    // The Rust plugin is not on the unit-test classpath. The strict mock fails on each call, thus
    // the test also proves that the method does not read the element.
    fun testNoBaseDeclarationsWhenTheRustPluginIsAbsent() {
        assertTrue(RustSuperMethodsProvider().findBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }
}
