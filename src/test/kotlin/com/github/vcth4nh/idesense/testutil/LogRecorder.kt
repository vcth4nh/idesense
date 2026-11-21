package com.github.vcth4nh.idesense.testutil

import com.intellij.testFramework.LoggedErrorProcessor
import java.util.Collections

/**
 * Records each warning and each error that a logger writes during [record], from each thread. The
 * entries do not go to the test log, and an error does not fail the test. An entry with a
 * throwable ends with the text [THROWABLE] and the throwable.
 */
class LogRecorder : LoggedErrorProcessor() {
    val entries: MutableList<String> = Collections.synchronizedList(mutableListOf())

    override fun processWarn(category: String, message: String, t: Throwable?): Boolean {
        entries += "WARN $category: $message" + throwableText(t)
        return false
    }

    override fun processError(category: String, message: String, details: Array<String>, t: Throwable?): Set<Action> {
        entries += "ERROR $category: $message" + throwableText(t)
        return Action.NONE
    }

    fun record(block: () -> Unit) {
        LoggedErrorProcessor.executeWith<Throwable>(this) { block() }
    }

    /** The error entries and the entries with a throwable. */
    fun errorsAndThrowables(): List<String> =
        entries.filter { it.startsWith("ERROR ") || THROWABLE in it }

    private fun throwableText(t: Throwable?): String = if (t == null) "" else " $THROWABLE $t"

    companion object {
        const val THROWABLE = "| throwable:"
    }
}
