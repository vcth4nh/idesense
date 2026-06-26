package com.github.vcth4nh.idesense.util

import com.intellij.psi.PsiDirectory
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiPolyVariantReference
import com.intellij.psi.ResolveResult
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyElement
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PyReferenceExpression
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

class PsiUtilsPythonFallbackUnitTest : TestCase() {

    fun testResolveTargetElementPrefersPythonCalleeOverDirectoryTarget() {
        val directoryTarget = mockk<PsiDirectory>(relaxed = true)
        val resolvedFunction = mockk<PyElement>(relaxed = true)
        val genericReference = mockk<PsiPolyVariantReference>(relaxed = true)
        val qualifiedReference = mockk<PyReferenceExpression>(relaxed = true)
        val callExpression = mockk<PyCallExpression>(relaxed = true)
        val qualifier = mockk<PyExpression>(relaxed = true)

        every { genericReference.resolve() } returns directoryTarget
        every { qualifiedReference.getReference() } returns genericReference
        every { qualifiedReference.getQualifier() } returns qualifier
        every { qualifiedReference.parent } returns callExpression
        every { callExpression.parent } returns null
        every { callExpression.getCallee() } returns qualifiedReference
        every { callExpression.multiResolveCalleeFunction(any()) } returns listOf(resolvedFunction)

        val resolved = PsiUtils.resolveTargetElement(qualifiedReference)

        assertSame("Qualified Python calls should resolve to the callable target", resolvedFunction, resolved)
    }

    fun testResolveTargetElementPrefersQualifiedPythonReferenceOverDirectoryTarget() {
        val directoryTarget = mockk<PsiDirectory>(relaxed = true)
        val resolvedFunction = mockk<PyElement>(relaxed = true)
        val genericReference = mockk<PsiPolyVariantReference>(relaxed = true)
        val qualifiedReference = mockk<PyReferenceExpression>(relaxed = true)
        val qualifier = mockk<PyExpression>(relaxed = true)
        val resolveResult = mockk<ResolveResult>(relaxed = true)

        every { genericReference.resolve() } returns directoryTarget
        every { genericReference.multiResolve(false) } returns arrayOf(resolveResult)
        every { resolveResult.element } returns resolvedFunction
        every { qualifiedReference.getReference() } returns genericReference
        every { qualifiedReference.getQualifier() } returns qualifier
        every { qualifiedReference.parent } returns null

        val resolved = PsiUtils.resolveTargetElement(qualifiedReference)

        assertSame("Qualified Python references should prefer the referenced member over a package directory", resolvedFunction, resolved)
    }

    fun testResolveTargetElementKeepsQualifierNavigationWhenCaretIsOnQualifierToken() {
        val directoryTarget = mockk<PsiDirectory>(relaxed = true)
        val qualifierReference = mockk<PyReferenceExpression>(relaxed = true)
        val qualifiedReference = mockk<PyReferenceExpression>(relaxed = true)
        val qualifierReferenceLookup = mockk<PsiPolyVariantReference>(relaxed = true)
        val qualifiedReferenceLookup = mockk<PsiPolyVariantReference>(relaxed = true)
        val callExpression = mockk<PyCallExpression>(relaxed = true)

        every { qualifierReferenceLookup.resolve() } returns directoryTarget
        every { qualifierReference.getReference() } returns qualifierReferenceLookup
        every { qualifierReference.getQualifier() } returns null
        every { qualifierReference.parent } returns qualifiedReference

        every { qualifiedReference.getReference() } returns qualifiedReferenceLookup
        every { qualifiedReference.getQualifier() } returns qualifierReference
        every { qualifiedReference.parent } returns callExpression

        every { callExpression.parent } returns null
        every { callExpression.getCallee() } returns qualifiedReference
        every { callExpression.multiResolveCalleeFunction(any()) } returns emptyList()

        val resolved = PsiUtils.resolveTargetElement(qualifierReference)

        assertSame(
            "Caret on the qualifier token should keep qualifier/module navigation semantics",
            directoryTarget,
            resolved
        )
    }

    fun testResolveTargetElementReturnsNullForNonDeclarationIdentifierFallback() {
        // Regression guard for the precondition gate added in the navigation walk-to-enclosing
        // fix: resolveTargetElement's findNamedElement fallback now fires only when the caret is
        // actually on a declaration's name identifier (PsiNameIdentifierOwner.nameIdentifier ===
        // element). A raw PsiNamedElement with no parent chain fails the precondition — which
        // reflects real PSI behavior, since production callers always pass leaf tokens from
        // psiFile.findElementAt(offset), never PsiNamedElement instances directly. Positive
        // coverage for the "caret IS on a declaration identifier" path lives in
        // NavigationPrecisionTest.testResolveTarget_onJavaDeclarationIdentifier_resolves.
        val namedElement = mockk<com.intellij.psi.PsiNamedElement>(relaxed = true)
        every { namedElement.reference } returns null
        every { namedElement.parent } returns null
        every { namedElement.name } returns "localName"

        val resolved = PsiUtils.resolveTargetElement(namedElement)

        assertNull(
            "Precondition gate rejects fallback when element has no PsiNameIdentifierOwner parent",
            resolved
        )
    }
}
