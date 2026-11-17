package com.github.vcth4nh.idesense.handlers.python

import com.intellij.psi.PsiElement
import io.mockk.mockk
import junit.framework.TestCase

class PythonSuperMethodsProviderUnitTest : TestCase() {

    // The Python plugin is not on the unit-test classpath. The test tree has stubs for PyFunction,
    // PyClass and TypeEvalContext only, and the mock is no PyFunction. The strict mock fails on
    // each call, thus the test also proves that the method does not read the element.
    fun testNoBaseDeclarationsWhenThePythonPluginIsAbsent() {
        assertTrue(PythonSuperMethodsProvider().findBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }
}
