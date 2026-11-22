package com.github.vcth4nh.idesense.tools.navigation.structure

import com.github.vcth4nh.idesense.tools.navigation.structure.hidden.hiddenModifierHolder
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.psi.PsiElement
import junit.framework.TestCase
import java.lang.reflect.Proxy
import java.util.concurrent.CancellationException

/** A public stand-in for a PSI element: the getter of the modifier list is public. */
interface ModifierHolder : PsiElement {
    fun getModifierList(): Any?
}

/** The text of the modifier list of the stand-ins. */
interface TextHolder {
    fun getText(): String
}

/**
 * [UniversalModifiers.extract] and the failure of a reflective getter: a cancellation leaves the
 * call, each other failure gives the empty result.
 */
class UniversalModifiersUnitTest : TestCase() {

    private inline fun <reified T : PsiElement> element(crossinline getter: () -> Any?): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, method, _ ->
            if (method.name == "getModifierList") getter() else null
        } as T

    private fun textHolder(text: String): TextHolder =
        Proxy.newProxyInstance(TextHolder::class.java.classLoader, arrayOf(TextHolder::class.java)) { _, _, _ ->
            text
        } as TextHolder

    fun testProcessCanceledExceptionLeavesExtract() {
        val holder = element<ModifierHolder> { throw ProcessCanceledException() }
        assertThrows(ProcessCanceledException::class.java) { UniversalModifiers.extract(holder) }
    }

    fun testCancellationExceptionLeavesExtract() {
        val holder = element<ModifierHolder> { throw CancellationException("cancelled") }
        assertThrows(CancellationException::class.java) { UniversalModifiers.extract(holder) }
    }

    fun testPublicGetterGivesModifiers() {
        val holder = element<ModifierHolder> { textHolder("public static") }
        assertEquals(listOf("public", "static"), UniversalModifiers.extract(holder))
    }

    /** Passes on the old code and on the new code: the result for a non-public class does not change. */
    fun testNonPublicClassGivesEmptyResult() {
        val holder = hiddenModifierHolder(textHolder("public static"))
        try {
            holder.javaClass.getMethod("getModifierList").invoke(holder)
            fail("The reflective call must throw IllegalAccessException for a non-public class")
        } catch (e: IllegalAccessException) {
            // This is the case that the test names.
        }
        assertEquals(emptyList<String>(), UniversalModifiers.extract(holder))
    }

    /** Passes on the old code and on the new code. */
    fun testPlainExceptionGivesEmptyResult() {
        val holder = element<ModifierHolder> { throw IllegalStateException("broken") }
        assertEquals(emptyList<String>(), UniversalModifiers.extract(holder))
    }

    private fun assertThrows(type: Class<out Throwable>, block: () -> Unit) {
        try {
            block()
        } catch (t: Throwable) {
            if (type.isInstance(t)) return
            throw t
        }
        fail("Expected ${type.simpleName}, but nothing was thrown")
    }
}
