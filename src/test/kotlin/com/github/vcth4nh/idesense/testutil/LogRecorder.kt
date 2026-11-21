package com.github.vcth4nh.idesense.testutil

import com.intellij.testFramework.LoggedErrorProcessor
import java.util.Collections

/**
 * Records each warning and each error that a logger of the plugin writes during [record], from
 * each thread. The entries do not go to the test log, and an error does not fail the test. An
 * entry with a throwable ends with the text [THROWABLE] and the throwable.
 *
 * [LoggedErrorProcessor.executeWith] sets one processor for the full JVM. Thus an entry of another
 * category, for example of a background task of the platform, gets the usual processing.
 */
class LogRecorder : LoggedErrorProcessor() {
    val entries: MutableList<String> = Collections.synchronizedList(mutableListOf())

    override fun processWarn(category: String, message: String, t: Throwable?): Boolean {
        if (!category.startsWith(PLUGIN_CATEGORY)) return super.processWarn(category, message, t)
        entries += "WARN $category: $message" + throwableText(t)
        return false
    }

    override fun processError(category: String, message: String, details: Array<String>, t: Throwable?): Set<Action> {
        if (!category.startsWith(PLUGIN_CATEGORY)) return super.processError(category, message, details, t)
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

        /** The category of a logger of the plugin (`logger<T>()` gives `#` and the class name). */
        private const val PLUGIN_CATEGORY = "#com.github.vcth4nh.idesense"
    }
}
