package com.github.vcth4nh.idesense.handlers.java

import com.intellij.psi.PsiElement
import com.intellij.psi.search.SearchScope
import io.mockk.mockk
import junit.framework.TestCase

class JavaSuperMethodsProviderUnitTest : TestCase() {

    // The mock is no PsiMethod. The strict mocks fail on each call, thus the tests also prove that
    // the methods do not read the element or the scope.
    fun testNoBaseDeclarationsForAnElementThatIsNotAMethod() {
        assertTrue(JavaSuperMethodsProvider().findBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }

    fun testNoDirectReferencesForAnElementThatIsNotAMethod() {
        assertNull(JavaSuperMethodsProvider().findDirectReferences(mockk<PsiElement>(), mockk<SearchScope>()))
    }
}
