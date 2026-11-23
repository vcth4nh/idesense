package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.tools.navigation.hierarchy.rethrowIfCancellation
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive

/**
 * Tells the two cases of a cancellation apart in a catch block of a request path (#127). A
 * cancellation is a `CancellationException` or a `ControlFlowException`, also inside an
 * `InvocationTargetException`: the set of [rethrowIfCancellation].
 *
 * - [e] is no cancellation: returns null. The caller handles [e] as before.
 * - The coroutine of the call is cancelled, for example because the server stops: throws the
 *   cancellation. It leaves the block with no log entry and no answer. Before it leaves,
 *   `processToolCall` sets the status CANCELLED on the history entry of the call (#284).
 * - The coroutine of the call is still active, so the client still waits: returns the
 *   cancellation. Examples are the `ServiceNotReadyException` of an index that is not ready and
 *   the `AlreadyDisposedException` of a disposed service. The caller gives its usual answer and
 *   logs one line with no throwable, because the platform logger replaces a logged cancellation
 *   with the text "Control-flow exceptions ... should never be logged".
 */
internal suspend fun cancellationInActiveCall(e: Throwable): Throwable? {
    try {
        rethrowIfCancellation(e)
    } catch (cancellation: Throwable) {
        if (!currentCoroutineContext().isActive) throw cancellation
        return cancellation
    }
    return null
}
