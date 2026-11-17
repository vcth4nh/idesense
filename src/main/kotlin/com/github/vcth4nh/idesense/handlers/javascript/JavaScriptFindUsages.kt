package com.github.vcth4nh.idesense.handlers.javascript

import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiReference
import java.lang.reflect.InvocationTargetException
import java.lang.reflect.Method

/**
 * The JavaScript part of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch] (#171, #196):
 * the rule of WebStorm for a dynamic usage. The plugin does not compile against the JavaScript
 * plugin: the JavaScript classes are known by name and read by reflection.
 *
 * The rule of WebStorm (build 262.8665):
 * - `JSUsageViewElementsListener.isJavaScriptDynamicUsage` is `usageInfo.isDynamicUsage() &&
 *   JSResolveUtil.isResolveDynamic(reference, targets) || reference != null &&
 *   !JSDefaultRenameProcessor.isStrictEnoughReference(reference)`.
 * - Before the listener adds a usage, it calls `setDynamicUsage(true)` on the usage when
 *   `JSResolveUtil.isResolveDynamic(reference, targets)` is true. Thus the first term of the rule
 *   is true when `isResolveDynamic` is true.
 * - `targets` are the elements that the handler searches.
 *
 * `JSUsageViewElementsListener` and `JSDefaultRenameProcessor` are in
 * `plugins/javascript-plugin/lib/modules/intellij.javascript.backend.jar`. `JSResolveUtil` is in
 * `plugins/javascript-plugin/lib/modules/intellij.javascript.psi.impl.jar`. Both checks are
 * public static methods: `com.intellij.lang.javascript.psi.resolve.JSResolveUtil.isResolveDynamic(PsiReference, Collection)`
 * and `com.intellij.lang.javascript.refactoring.JSDefaultRenameProcessor.isStrictEnoughReference(PsiReference)`
 * (a `@JvmStatic` bridge to the method of its companion).
 */
internal object JavaScriptFindUsages {

    private val jsLanguageDialectClass: Class<*>? by lazy {
        try { Class.forName("com.intellij.lang.javascript.JSLanguageDialect") } catch (_: ClassNotFoundException) { null }
    }

    private val isResolveDynamicMethod: Method? by lazy {
        staticMethod(
            "com.intellij.lang.javascript.psi.resolve.JSResolveUtil", "isResolveDynamic",
            PsiReference::class.java, Collection::class.java,
        )
    }

    private val isStrictEnoughReferenceMethod: Method? by lazy {
        staticMethod(
            "com.intellij.lang.javascript.refactoring.JSDefaultRenameProcessor", "isStrictEnoughReference",
            PsiReference::class.java,
        )
    }

    /**
     * WebStorm's rule for a dynamic usage. Null when the JavaScript plugin is absent, when
     * [reference] is not in a JavaScript dialect file, or when the check cannot run.
     *
     * A JavaScript dialect file is a file of which the language is a
     * `com.intellij.lang.javascript.JSLanguageDialect` (JavaScript, TypeScript and their dialects).
     * A file of a host language, for example Vue or HTML, gives null. A check gives null when its
     * method is absent or throws. [ProcessCanceledException] and [LinkageError] pass through.
     */
    fun isDynamicUsage(reference: PsiReference, targets: Collection<PsiElement>): Boolean? {
        val dialectClass = jsLanguageDialectClass ?: return null
        if (!dialectClass.isInstance(reference.element.containingFile?.language)) return null
        return isDynamicUsage(
            resolveDynamic = runCheck(isResolveDynamicMethod, reference, targets),
            strictEnough = runCheck(isStrictEnoughReferenceMethod, reference),
        )
    }

    /**
     * The rule itself, with the two checks as parameters, for the unit test. True when
     * [resolveDynamic] is true or [strictEnough] is false. False when [resolveDynamic] is false
     * and [strictEnough] is true. Else null: one check alone cannot say false.
     */
    internal fun isDynamicUsage(resolveDynamic: Boolean?, strictEnough: Boolean?): Boolean? = when {
        resolveDynamic == true || strictEnough == false -> true
        resolveDynamic == false && strictEnough == true -> false
        else -> null
    }

    /** The public method [name] of the class [className]; null when the class or the method is absent. */
    private fun staticMethod(className: String, name: String, vararg parameterTypes: Class<*>): Method? =
        try {
            Class.forName(className).getMethod(name, *parameterTypes)
        } catch (_: ClassNotFoundException) {
            null
        } catch (_: NoSuchMethodException) {
            null
        }

    /**
     * Calls the static [method] with [args]. Null when [method] is null, when it does not return a
     * boolean, or when it throws. A cancellation or a [LinkageError] passes through, also when the
     * reflective call wraps it in an [InvocationTargetException].
     */
    private fun runCheck(method: Method?, vararg args: Any): Boolean? {
        if (method == null) return null
        return try {
            method.invoke(null, *args) as? Boolean
        } catch (e: InvocationTargetException) {
            val cause = e.cause
            if (cause is ProcessCanceledException) throw cause
            if (cause is LinkageError) throw cause
            null
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (_: Throwable) {
            null
        }
    }
}
