package com.github.vcth4nh.idesense.testutil

import com.intellij.testFramework.LoggedErrorProcessor
import java.util.Collections

/**
 * Records each warning and each error that a logger writes during [record], from each thread. The
 * entries do not go to the test log, and an error does not fail the test.
 */
class LogRecorder : LoggedErrorProcessor() {
    val entries: MutableList<String> = Collections.synchronizedList(mutableListOf())

    override fun processWarn(category: String, message: String, t: Throwable?): Boolean {
        entries += "WARN $category: $message"
        return false
    }

    override fun processError(category: String, message: String, details: Array<String>, t: Throwable?): Set<Action> {
        entries += "ERROR $category: $message"
        return Action.NONE
    }

    fun record(block: () -> Unit) {
        LoggedErrorProcessor.executeWith<Throwable>(this) { block() }
    }
}
