package com.github.vcth4nh.idesense.tools.navigation.structure

import com.intellij.psi.PsiElement

/**
 * Language-agnostic modifier extraction for the file-structure tree.
 *
 * Most languages we care about expose modifier text via a single sub-element on the
 * declaration (e.g. `PsiModifierList`, `KtModifierList`, `PhpModifierList`,
 * `JSAttributeList`, `RsVis`). Despite the type names differing per language, the
 * accessor methods are conventionally one of `getModifierList`, `getAttributeList`,
 * or `getVis`, and the returned PSI element's `getText()` yields the source-order
 * keyword list. We probe those accessors reflectively and split the resulting text
 * on whitespace, dropping anything that looks like an annotation (`@...`).
 *
 * PHP class and field elements don't expose `getModifierList()` (only methods do).
 * As a fallback, we probe `getModifier()` — which returns a `PhpModifier` whose
 * `toString()` is overridden to yield source-form modifier text ("abstract public",
 * "private final static", etc., including PHP 8.4 `public(set)`). Guarded against
 * accidental matches in other languages by rejecting outputs containing `@`, since
 * Java's default `Object.toString()` returns `"ClassName@hashcode"`.
 *
 * Languages without a modifier concept (Python, Go) silently return empty.
 *
 * Caveat: Kotlin's `KtModifierList` includes declaration-shape keywords like `data`,
 * `sealed`, `enum`, `annotation` — those will surface as modifiers. That's
 * grammatically correct in Kotlin and we accept it rather than maintaining a
 * per-language filter list.
 */
internal object UniversalModifiers {

    private val GETTERS = listOf("getModifierList", "getAttributeList", "getVis")

    fun extract(value: Any?): List<String> {
        if (value !is PsiElement) return emptyList()
        for (getter in GETTERS) {
            val sub = invokeNoArg(value, getter) ?: continue
            val text = invokeString(sub, "getText") ?: continue
            return splitKeywords(text)
        }
        invokeNoArg(value, "getModifier")?.let { mod ->
            val text = mod.toString()
            if (text.isNotBlank() && '@' !in text) return splitKeywords(text)
        }
        return emptyList()
    }

    private fun splitKeywords(text: String): List<String> =
        text.trim().split(Regex("\\s+"))
            .filter { it.isNotEmpty() && !it.startsWith("@") }

    private fun invokeNoArg(target: Any, method: String): Any? = runCatching {
        target.javaClass.getMethod(method).invoke(target)
    }.getOrNull()

    private fun invokeString(target: Any, method: String): String? = runCatching {
        target.javaClass.getMethod(method).invoke(target) as? String
    }.getOrNull()?.takeIf { it.isNotBlank() }
}
