package com.github.hechtcarmel.jetbrainsindexmcpplugin.tools.navigation.hierarchy

import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.diagnostic.ControlFlowException
import com.intellij.openapi.progress.ProcessCanceledException
import junit.framework.TestCase
import java.lang.reflect.InvocationTargetException

class HierarchyTreeWalkerUnitTest : TestCase() {

    fun testHierarchyKindIsCallTrueForCallers() {
        assertTrue(HierarchyKind.CALLERS.isCall)
        assertFalse(HierarchyKind.CALLERS.isType)
    }

    fun testHierarchyKindIsCallTrueForCallees() {
        assertTrue(HierarchyKind.CALLEES.isCall)
        assertFalse(HierarchyKind.CALLEES.isType)
    }

    fun testHierarchyKindIsTypeTrueForSupertypes() {
        assertTrue(HierarchyKind.SUPERTYPES.isType)
        assertFalse(HierarchyKind.SUPERTYPES.isCall)
    }

    fun testHierarchyKindIsTypeTrueForSubtypes() {
        assertTrue(HierarchyKind.SUBTYPES.isType)
        assertFalse(HierarchyKind.SUBTYPES.isCall)
    }

    // --- rethrowIfCancellation (#141): never swallow a read-action cancellation -------------
    // The platform's coroutine readAction{} retries the block when a CannotReadException
    // (a ProcessCanceledException) escapes it; the walker must let that signal through.

    /** Runs the helper and returns whatever it rethrew, or null if it was a no-op. */
    private fun caught(t: Throwable): Throwable? = try {
        rethrowIfCancellation(t)
        null
    } catch (e: Throwable) {
        e
    }

    /** Marker-only ControlFlowException that is NOT a CancellationException. */
    private class FakeControlFlow : RuntimeException(), ControlFlowException

    fun testRethrowsCannotReadExceptionDirectly() {
        val pce = ReadAction.CannotReadException()
        assertSame(pce, caught(pce))
    }

    fun testUnwrapsAndRethrowsCancellationFromInvocationTargetException() {
        // Reflection (Method.invoke) wraps the cancellation; the helper must unwrap and
        // rethrow the ORIGINAL CannotReadException, not the InvocationTargetException.
        val pce = ReadAction.CannotReadException()
        assertSame(pce, caught(InvocationTargetException(pce)))
    }

    fun testRethrowsProcessCanceledException() {
        val pce = ProcessCanceledException()
        assertSame(pce, caught(pce))
    }

    fun testRethrowsControlFlowException() {
        val cf = FakeControlFlow()
        assertSame(cf, caught(cf))
    }

    fun testIgnoresOrdinaryThrowable() {
        // Genuine failures keep flowing through the caller's normal failure handling.
        assertNull(caught(IllegalStateException("genuine failure")))
    }

    fun testIgnoresOrdinaryThrowableWrappedInInvocationTargetException() {
        assertNull(caught(InvocationTargetException(IllegalStateException("genuine failure"))))
    }

    // --- classifyBrowserConstruction (#30): browser construction must self-heal on a --------
    // cold-start read cancellation (rethrow for the readAction retry) and surface the REAL
    // cause of a genuine failure instead of masking everything as "non-HierarchyBrowserBaseEx".
    // #141 added rethrowIfCancellation at the tree-BUILD sites but not this construction site.

    /** Runs the classifier and returns whatever it rethrew, or null if it returned normally. */
    private fun rethrownByClassify(invokeResult: Result<Any?>): Throwable? = try {
        classifyBrowserConstruction(invokeResult)
        null
    } catch (e: Throwable) {
        e
    }

    fun testClassifyRethrowsReadCancellationForRetry() {
        // The cold-start race: createHierarchyBrowser throws CannotReadException. It MUST
        // escape so the enclosing coroutine readAction{} performs its write-pending restart,
        // not be flattened to a hard "non-HierarchyBrowserBaseEx" failure (#30).
        val pce = ReadAction.CannotReadException()
        assertSame(pce, rethrownByClassify(Result.failure(pce)))
    }

    fun testClassifyRethrowsReflectionWrappedCancellation() {
        // The exact #30 shape: Method.invoke wraps the cancellation in InvocationTargetException.
        val pce = ProcessCanceledException()
        assertSame(pce, rethrownByClassify(Result.failure(InvocationTargetException(pce))))
    }

    fun testClassifySurfacesGenuineCtorFailureWithCause() {
        // A real ctor failure must be surfaced with its cause attached, not swallowed to a
        // WARN-only log, so a permanent failure is diagnosable from the tool response.
        val boom = IllegalStateException("ctor boom")
        val result = classifyBrowserConstruction(Result.failure(InvocationTargetException(boom)))
        assertTrue(result.isFailure)
        val error = result.exceptionOrNull()!!
        assertSame(boom, error.cause)
        assertTrue(error.message!!.contains("ctor boom"))
    }

    fun testClassifyReportsWrongTypeWithActualClassName() {
        // A non-null, wrong-type return is a genuine (permanent) mismatch: keep it a failure
        // but name the actual type so it is diagnosable.
        val result = classifyBrowserConstruction(Result.success("definitely not a browser"))
        assertTrue(result.isFailure)
        val msg = result.exceptionOrNull()!!.message!!
        assertTrue(msg.contains("not HierarchyBrowserBaseEx"))
        assertTrue(msg.contains("String"))
    }

    fun testClassifyReportsNullReturn() {
        val result = classifyBrowserConstruction(Result.success(null))
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()!!.message!!.contains("null"))
    }
}
