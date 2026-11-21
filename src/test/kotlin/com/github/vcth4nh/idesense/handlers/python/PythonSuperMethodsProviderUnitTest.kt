package com.github.vcth4nh.idesense.handlers.python

import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.search.PySuperMethodsSearch
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

class PythonSuperMethodsProviderUnitTest : TestCase() {

    override fun tearDown() {
        PySuperMethodsSearch.onSearch = { throw UnsupportedOperationException("no search in this test") }
        super.tearDown()
    }

    // The Python plugin is not on the unit-test classpath. The test tree has stubs for PyFunction,
    // PyClass, TypeEvalContext and PySuperMethodsSearch only, and the mock is no PyFunction. The
    // strict mock fails on each call, thus the test also proves that the method does not read the
    // element.
    fun testNoBaseDeclarationsWhenThePythonPluginIsAbsent() {
        assertTrue(PythonSuperMethodsProvider().findBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }

    fun testNoSkippedBaseDeclarationsWhenThePythonPluginIsAbsent() {
        assertTrue(PythonSuperMethodsProvider().skippedBaseDeclarations(mockk<PsiElement>()).isEmpty())
    }

    // A cancellation in the reflective search leaves the walk, so that the read action starts
    // again. The provider returned an empty list (#210).
    fun testACancellationOfTheSearchLeavesFindBaseDeclarations() {
        PySuperMethodsSearch.onSearch = { throw ProcessCanceledException() }

        assertCancellation { PythonSuperMethodsProvider().findBaseDeclarations(pyFunction()) }
    }

    fun testACancellationOfTheSearchLeavesSkippedBaseDeclarations() {
        PySuperMethodsSearch.onSearch = { throw ProcessCanceledException() }

        assertCancellation { PythonSuperMethodsProvider().skippedBaseDeclarations(pyFunction()) }
    }

    fun testACancellationOfFindAllLeavesFindBaseDeclarations() {
        PySuperMethodsSearch.onSearch = { CancelledQuery() }

        assertCancellation { PythonSuperMethodsProvider().findBaseDeclarations(pyFunction()) }
    }

    /** The query of a search that a write action interrupts. */
    class CancelledQuery {
        fun findAll(): Collection<PsiElement> = throw ProcessCanceledException()
    }

    private fun pyFunction(): PyFunction = mockk {
        every { project } returns mockk<Project>()
        every { containingFile } returns null
    }

    private fun assertCancellation(call: () -> List<PsiElement>) {
        try {
            val result = call()
            fail("The cancellation must leave the provider, got $result")
        } catch (_: ProcessCanceledException) {
        }
    }
}
