package com.github.vcth4nh.idesense.handlers.markdown

import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.psi.PsiElement

/**
 * The Markdown part of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch] (#196): the
 * rule of the Markdown plugin for a dynamic usage. The plugin does not compile against the Markdown
 * plugin: the Markdown classes are known by name.
 */
internal object MarkdownFindUsages {

    private const val MARKDOWN_CODE_SPAN = "org.intellij.plugins.markdown.lang.psi.impl.MarkdownCodeSpan"
    private const val BACKTICK_REFERENCE = "org.intellij.plugins.markdown.lang.references.backtick.BacktickReference"

    /**
     * The rule of `BacktickUsageViewElementsListener`: true when [element] is a `MarkdownCodeSpan`
     * and one of the references of [element] is a `BacktickReference`. The listener reads the
     * element of the usage (`usageInfo.getElement()`), not the reference, so the check takes the
     * element. Both search paths of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch]
     * call it.
     *
     * A `BacktickReference` can resolve by name: its `multiResolve` asks the Go to Class and Go to
     * Symbol contributors (`ChooseByNameContributorEx.CLASS_EP_NAME` and `SYMBOL_EP_NAME`). But
     * `BacktickReference.isReferenceTo` does not resolve; it accepts each element with the same
     * name. Thus such a usage is a name match only. (`isReferenceTo` compares only the name when
     * the name has at least `markdown.backtick.reference.symbol.length` characters, default 10, or
     * more than one word. For a shorter name it calls the `isReferenceTo` of its superclass, which
     * resolves.)
     *
     * Source: `org.intellij.plugins.markdown.lang.references.backtick.BacktickUsageViewElementsListener`
     * (`plugins/markdown/lib/intellij.markdown.jar`, build 262.8665). In `beforeUsageAdded` it
     * calls `UsageInfo.setDynamicUsage(true)` on such a usage. In the six IDEs of build 262, the
     * extension point `com.intellij.usageViewElementsListener` has only two registered listeners:
     * this listener and `JSUsageViewElementsListener` (see
     * [com.github.vcth4nh.idesense.handlers.javascript.JavaScriptFindUsages]).
     *
     * The check reads `element.references` only after the code span check, because the call runs
     * the reference providers. [ProcessCanceledException] and [LinkageError] pass through. Each
     * other exception gives false.
     */
    fun isDynamicUsage(element: PsiElement): Boolean =
        try {
            isInstanceByName(element, MARKDOWN_CODE_SPAN) &&
                element.references.any { isInstanceByName(it, BACKTICK_REFERENCE) }
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (_: Throwable) {
            false
        }

    /** True when [className] is the name of the class of [value] or of one of its superclasses. */
    private fun isInstanceByName(value: Any, className: String): Boolean =
        generateSequence<Class<*>>(value.javaClass) { it.superclass }.any { it.name == className }
}
