package com.github.vcth4nh.idesense.server.transport

import com.github.vcth4nh.idesense.testutil.LogRecorder
import junit.framework.TestCase
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.job
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlin.coroutines.coroutineContext

class KtorSseSessionUnitTest : TestCase() {

    /** A session whose channel reports "open" at the check, but is closed at the send. */
    @OptIn(DelicateCoroutinesApi::class, ExperimentalCoroutinesApi::class)
    private fun racedSession(): KtorSseSession {
        val closed = Channel<String>(Channel.UNLIMITED).apply { close() }
        val standIn = object : Channel<String> by closed {
            override val isClosedForSend: Boolean get() = false
        }
        return KtorSseSession("s5").apply { channel = standIn }
    }

    fun testCancellationLeavesSendEventWithoutLogEntry() {
        val session = racedSession()
        val log = LogRecorder()
        var thrown: Throwable? = null
        log.record {
            runBlocking {
                launch {
                    coroutineContext.job.cancel()
                    try {
                        session.sendEvent("message", "x")
                    } catch (e: CancellationException) {
                        thrown = e
                    }
                }.join()
            }
        }
        assertTrue("sendEvent did not pass the cancellation on", thrown is CancellationException)
        assertEquals(emptyList<String>(), log.errorsAndThrowables())
    }

    fun testClosedChannelAtSendGivesFalseWithNoError() {
        val session = racedSession()
        val log = LogRecorder()
        var result: Boolean? = null
        log.record { runBlocking { result = session.sendEvent("message", "x") } }
        assertEquals(false, result)
        assertEquals(emptyList<String>(), log.errorsAndThrowables())
    }
}
