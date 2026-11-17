package com.github.vcth4nh.idesense.handlers.java

import com.intellij.lang.Language
import com.intellij.lang.java.JavaLanguage
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiMethod
import com.intellij.psi.search.SearchScope
import io.mockk.every
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

    // The strict mock has no navigationElement, so the test also proves that the method does not read it.
    fun testASuperMethodOfTheJavaLanguageIsItsOwnBaseDeclaration() {
        val superMethod = mockk<PsiMethod>()
        every { superMethod.language } returns JavaLanguage.INSTANCE

        assertSame(superMethod, JavaSuperMethodsProvider().baseDeclarationOf(superMethod))
    }

    // For example a Kotlin light method: its navigation element is the Kotlin declaration.
    fun testASuperMethodOfAnotherLanguageGivesItsNavigationElement() {
        val declaration = mockk<PsiElement>()
        val superMethod = mockk<PsiMethod>()
        every { superMethod.language } returns mockk<Language>()
        every { superMethod.navigationElement } returns declaration

        assertSame(declaration, JavaSuperMethodsProvider().baseDeclarationOf(superMethod))
    }
}
