package com.github.vcth4nh.idesense.tools.navigation.structure

import com.github.vcth4nh.idesense.tools.navigation.hierarchy.rethrowIfCancellation
import com.intellij.psi.PsiComment
import com.intellij.psi.PsiElement

/**
 * Language-agnostic modifier extraction for the file-structure tree.
 *
 * Most languages we care about expose modifier text via a single sub-element on the
 * declaration (e.g. `PsiModifierList`, `KtModifierList`, `PhpModifierList`,
 * `JSAttributeList`, `RsVis`). Despite the type names differing per language, the
 * accessor methods are conventionally one of `getModifierList`, `getAttributeList`,
 * or `getVis`, and the returned PSI element's `getText()` yields the source-order
 * keyword list. We probe those accessors reflectively, remove the text of each
 * annotation, decorator or comment child (see [withoutAnnotationsAndComments]), and split
 * the resulting text on whitespace, dropping anything that looks like an annotation (`@...`).
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
 * A Java class initializer also returns empty. Its only keyword is `static`, and the IDE already
 * writes it into the name of the node (`static class initializer`, #326).
 *
 * Caveat: Kotlin's `KtModifierList` includes declaration-shape keywords like `data`,
 * `sealed`, `enum`, `annotation` — those will surface as modifiers. That's
 * grammatically correct in Kotlin and we accept it rather than maintaining a
 * per-language filter list.
 */
internal object UniversalModifiers {

    private val GETTERS = listOf("getModifierList", "getAttributeList", "getVis")

    private val classInitializerClass: Class<*>? by lazy {
        try { Class.forName("com.intellij.psi.PsiClassInitializer") } catch (_: ClassNotFoundException) { null }
    }

    fun extract(value: Any?): List<String> {
        if (value !is PsiElement || classInitializerClass?.isInstance(value) == true) return emptyList()
        for (getter in GETTERS) {
            val sub = invokeNoArg(value, getter) ?: continue
            val text = invokeString(sub, "getText") ?: continue
            return splitKeywords(withoutAnnotationsAndComments(sub, text))
        }
        invokeNoArg(value, "getModifier")?.let { mod ->
            val text = mod.toString()
            if (text.isNotBlank() && '@' !in text) return splitKeywords(text)
        }
        return emptyList()
    }

    /**
     * Puts a space in place of each child of [modifierList] whose text starts with `@`: a Java or
     * Kotlin annotation, or a JavaScript or TypeScript decorator. The arguments of such a child
     * can hold white space, so the `@` filter of [splitKeywords] alone left parts of them (#173).
     * With the space, two keywords next to the child stay apart (`static@A(x)final`).
     *
     * A comment between two keywords is also a child, and it gets a space too (#282). A comment
     * is a leaf, and `getChildren()` of a Kotlin modifier list gives only the composite children,
     * so the comments come from the walk over the siblings.
     *
     * The offsets come from the PSI, so a string or a parenthesis in the arguments has no effect.
     * In a compiled Java class the annotations are the only children, and the text and the
     * offsets come from the decompiled text. The loop goes from the end, so that each
     * replacement keeps the offsets of the children before it.
     *
     * A light modifier list has no children. An example is the modifier list of a Kotlin member
     * that a Java class inherits. Its text is the text of its navigation element, so the children
     * come from that element when the two texts are the same.
     */
    private fun withoutAnnotationsAndComments(modifierList: Any, text: String): String {
        if (modifierList !is PsiElement) return text
        val source = modifierList.navigationElement.takeIf { it.text == text } ?: modifierList
        val annotations = source.children.filter { it.text.startsWith("@") }
        val comments = generateSequence(source.firstChild) { it.nextSibling }.filterIsInstance<PsiComment>()
        val result = StringBuilder(text)
        for (child in (annotations + comments).sortedByDescending { it.startOffsetInParent }) {
            val start = child.startOffsetInParent
            if (start < 0) continue
            result.replace(start, start + child.textLength, " ")
        }
        return result.toString()
    }

    private fun splitKeywords(text: String): List<String> =
        text.trim().split(Regex("\\s+"))
            .filter { it.isNotEmpty() && !it.startsWith("@") }

    private fun invokeNoArg(target: Any, method: String): Any? = runCatching {
        target.javaClass.getMethod(method).invoke(target)
    }.onFailure(::rethrowIfCancellation).getOrNull()

    private fun invokeString(target: Any, method: String): String? = runCatching {
        target.javaClass.getMethod(method).invoke(target) as? String
    }.onFailure(::rethrowIfCancellation).getOrNull()?.takeIf { it.isNotBlank() }
}
