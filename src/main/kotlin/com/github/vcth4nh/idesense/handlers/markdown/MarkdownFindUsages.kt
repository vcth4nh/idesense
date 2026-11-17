package com.github.vcth4nh.idesense.handlers.markdown

import com.intellij.psi.PsiReference

/**
 * The Markdown part of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch] (#196): the
 * rule of the Markdown plugin for a dynamic usage. The plugin does not compile against the Markdown
 * plugin: the Markdown classes are known by name.
 */
internal object MarkdownFindUsages {

    private const val MARKDOWN_CODE_SPAN = "org.intellij.plugins.markdown.lang.psi.impl.MarkdownCodeSpan"
    private const val BACKTICK_REFERENCE = "org.intellij.plugins.markdown.lang.references.backtick.BacktickReference"

    /**
     * The rule of `BacktickUsageViewElementsListener`: true when the element of [reference] is a
     * `MarkdownCodeSpan` and one of the references of the element is a `BacktickReference`. A
     * `BacktickReference` does not resolve: its `isReferenceTo` accepts each element with the same
     * name.
     *
     * Source: `org.intellij.plugins.markdown.lang.references.backtick.BacktickUsageViewElementsListener`
     * (`plugins/markdown/lib/intellij.markdown.jar`, build 262.8665). In `beforeUsageAdded` it
     * calls `UsageInfo.setDynamicUsage(true)` on such a usage. In the six IDEs of build 262, the
     * extension point `com.intellij.usageViewElementsListener` has only two registered listeners:
     * this listener and `JSUsageViewElementsListener` (see
     * [com.github.vcth4nh.idesense.handlers.javascript.JavaScriptFindUsages]).
     *
     * The check reads `element.references` only after the code span check, because the call runs
     * the reference providers. The caller catches the exceptions.
     */
    fun isDynamicUsage(reference: PsiReference): Boolean {
        val element = reference.element
        if (!isInstanceByName(element, MARKDOWN_CODE_SPAN)) return false
        return element.references.any { isInstanceByName(it, BACKTICK_REFERENCE) }
    }

    /** True when [className] is the name of the class of [value] or of one of its superclasses. */
    private fun isInstanceByName(value: Any, className: String): Boolean =
        generateSequence<Class<*>>(value.javaClass) { it.superclass }.any { it.name == className }
}
