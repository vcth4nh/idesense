package com.github.vcth4nh.idesense.handlers.kotlin

import com.intellij.psi.PsiElement
import com.intellij.psi.search.SearchScope
import io.mockk.mockk
import junit.framework.TestCase

class KotlinSuperMethodsProviderUnitTest : TestCase() {

    // The mock is no KtCallableDeclaration. The strict mocks fail on each call, thus the tests also
    // prove that the methods do not read the element or the scope.
    fun testNoBaseDeclarationsForAnElementThatIsNotACallable() {
        assertTrue(KotlinSuperMethodsProvider().findBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }

    fun testNoDirectReferencesForAnElementThatIsNotACallable() {
        assertNull(KotlinSuperMethodsProvider().findDirectReferences(mockk<PsiElement>(), mockk<SearchScope>()))
    }
}
