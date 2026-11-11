package com.github.vcth4nh.idesense.tools.navigation

import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiMethod
import com.intellij.psi.search.GlobalSearchScope
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

class FindImplementationsToolUnitTest : TestCase() {

    private val scope = mockk<GlobalSearchScope>()
    private val project = mockk<Project>()

    private fun methodWhoseClassLookupThrows(failure: Throwable): PsiMethod {
        val method = mockk<PsiMethod>()
        every { method.containingClass } throws failure
        return method
    }

    // A cancelled read action must leave its block: the platform then runs the block again. The
    // reflective call gives the cancellation inside an InvocationTargetException.
    fun testACancellationInTheFunctionalExpressionSearchLeavesTheSearch() {
        val method = methodWhoseClassLookupThrows(ProcessCanceledException())

        try {
            FindImplementationsTool().addFunctionalExpressionImpls(method, scope, ImplementationLocations.Collector(limit = 10), project)
            fail("The cancellation must leave the search")
        } catch (_: ProcessCanceledException) {
        }
    }

    // The search for lambdas is an addition to the implementation search. A failure of the
    // search itself does not fail the tool.
    fun testAnotherFailureOfTheFunctionalExpressionSearchIsNotThrown() {
        val method = methodWhoseClassLookupThrows(IllegalStateException("no containing class"))
        val collector = ImplementationLocations.Collector(limit = 10)

        FindImplementationsTool().addFunctionalExpressionImpls(method, scope, collector, project)

        assertTrue(collector.results.isEmpty())
    }
}
