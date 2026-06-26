package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.intellij.ide.hierarchy.HierarchyNodeDescriptor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement

/**
 * Reflection-based introspection of "class-like" PSI elements across languages.
 *
 * The IdeSense plugin runs in any JetBrains IDE (PyCharm, WebStorm, GoLand,
 * PhpStorm, RustRover, etc.) — not all of them ship the Java plugin. Direct
 * `is PsiClass` / `is PsiMethod` checks emit bytecode references that crash
 * with `NoClassDefFoundError` at first invocation when the Java plugin isn't
 * on the classpath. Use these helpers instead — class lookups are cached and
 * silently absent when a plugin isn't installed.
 *
 * Recognised "class-like" types (returns kind string + extracts qualifiedName):
 * - Java: PsiClass (with isInterface/isEnum/isRecord/isAnnotationType)
 * - Kotlin: KtClassOrObject
 * - Python: PyClass
 * - JavaScript/TypeScript: JSClass
 * - PHP: PhpClass
 * - Go: GoTypeSpec
 * - Rust: RsTraitItem, RsStructItem, RsEnumItem, RsImplItem
 *
 * Recognised "method-like" types:
 * - Java: PsiMethod
 * - Kotlin: KtNamedFunction, KtConstructor, KtProperty (accessors)
 * - Python: PyFunction
 * - JavaScript/TypeScript: JSFunction
 * - PHP: Function (interface, parent of Method)
 * - Go: GoFunctionOrMethodDeclaration (or GoNamedSignatureOwner)
 * - Rust: RsFunction
 */
internal object ClassLikePsi {

    private fun loadClass(fqn: String): Class<*>? = runCatching { Class.forName(fqn) }.getOrNull()

    // Class-like types
    private val PSI_CLASS by lazy { loadClass("com.intellij.psi.PsiClass") }
    private val KT_CLASS_OR_OBJECT by lazy { loadClass("org.jetbrains.kotlin.psi.KtClassOrObject") }
    private val PY_CLASS by lazy { loadClass("com.jetbrains.python.psi.PyClass") }
    private val JS_CLASS by lazy { loadClass("com.intellij.lang.javascript.psi.ecmal4.JSClass") }
    private val PHP_CLASS by lazy { loadClass("com.jetbrains.php.lang.psi.elements.PhpClass") }
    private val GO_TYPE_SPEC by lazy { loadClass("com.goide.psi.GoTypeSpec") }
    private val RS_TRAIT_ITEM by lazy { loadClass("org.rust.lang.core.psi.RsTraitItem") }
    private val RS_STRUCT_ITEM by lazy { loadClass("org.rust.lang.core.psi.RsStructItem") }
    private val RS_ENUM_ITEM by lazy { loadClass("org.rust.lang.core.psi.RsEnumItem") }
    private val RS_IMPL_ITEM by lazy { loadClass("org.rust.lang.core.psi.RsImplItem") }

    private val classLikeTypes: List<Class<*>> by lazy {
        listOfNotNull(
            PSI_CLASS, KT_CLASS_OR_OBJECT, PY_CLASS, JS_CLASS, PHP_CLASS, GO_TYPE_SPEC,
            RS_TRAIT_ITEM, RS_STRUCT_ITEM, RS_ENUM_ITEM, RS_IMPL_ITEM
        )
    }

    fun isClassLike(element: PsiElement): Boolean =
        classLikeTypes.any { it.isInstance(element) }

    /**
     * Extracts the primary display name from a [HierarchyNodeDescriptor]'s
     * highlighted text, stripping the grayed-out suffix (file path, module,
     * package) that the IDE appends for its tree-view UI.
     *
     * The IDE's `CompositeAppearance` is built from multiple `TextSection`s,
     * each with its own `TextAttributes`. The main symbol name uses the first
     * section's attributes; subsequent sections with *different* attributes
     * are the grayed suffix (e.g. " in path/file.go", " (module)"). We
     * collect only sections sharing the first section's attributes.
     *
     * Falls back to `PsiNamedElement.name` when the descriptor has no
     * highlighted text (e.g. synthetic descriptors from the Rust fallback).
     */
    fun descriptorDisplayName(descriptor: HierarchyNodeDescriptor, psi: PsiElement): String {
        val name = runCatching { extractPrimaryText(descriptor) }.getOrNull()
        if (!name.isNullOrBlank()) return name.trim()
        return (psi as? PsiNamedElement)?.name ?: psi.text.take(60)
    }

    private fun extractPrimaryText(descriptor: HierarchyNodeDescriptor): String? {
        val appearance = descriptor.getHighlightedText() ?: return null
        val sections = appearance.getSectionsIterator() ?: return null
        if (!sections.hasNext()) return null
        val first = sections.next()
        val primaryAttrs = first.getTextAttributes()
        val sb = StringBuilder(first.getText())
        while (sections.hasNext()) {
            val section = sections.next()
            if (section.getTextAttributes() != primaryAttrs) break
            sb.append(section.getText())
        }
        return sb.toString()
    }

    /**
     * Walks up the PSI tree from [element] looking for the smallest enclosing
     * class-like ancestor. Returns null if none found.
     */
    fun walkUpToClassLike(element: PsiElement): PsiElement? {
        var current: PsiElement? = element
        while (current != null) {
            if (isClassLike(current)) return current
            current = current.parent
        }
        return null
    }

    /**
     * Returns a kind string for a class-like element (UPPERCASE per legacy
     * convention) or `"class"` when the element isn't class-like and we can't
     * tell — preserves wire-format compatibility.
     */
    fun describeKind(element: PsiElement): String {
        return LanguageServices.getKind(element)
    }

    /**
     * Returns the qualifiedName for a class-like element, or null if not extractable.
     * Delegates to [com.github.vcth4nh.idesense.util.QualifiedNameUtil]
     * which knows per-language conventions (Rust `crate::Foo`, Go `pkg.Foo`,
     * PHP `\Ns\Foo`, Java FQN, Kotlin FqName via the platform's QualifiedNameProvider EP).
     */
    fun describeQualifiedName(element: PsiElement): String? =
        com.github.vcth4nh.idesense.util.QualifiedNameUtil.getQualifiedName(element)

    // -------------------- method-like helpers --------------------

    private val PSI_METHOD by lazy { loadClass("com.intellij.psi.PsiMethod") }
    private val KT_NAMED_FUNCTION by lazy { loadClass("org.jetbrains.kotlin.psi.KtNamedFunction") }
    private val KT_CONSTRUCTOR by lazy { loadClass("org.jetbrains.kotlin.psi.KtConstructor") }
    private val PY_FUNCTION by lazy { loadClass("com.jetbrains.python.psi.PyFunction") }
    private val JS_FUNCTION by lazy { loadClass("com.intellij.lang.javascript.psi.JSFunction") }
    private val PHP_FUNCTION by lazy { loadClass("com.jetbrains.php.lang.psi.elements.Function") }
    private val GO_NAMED_SIGNATURE_OWNER by lazy { loadClass("com.goide.psi.GoNamedSignatureOwner") }
    private val RS_FUNCTION by lazy { loadClass("org.rust.lang.core.psi.RsFunction") }

    private val methodLikeTypes: List<Class<*>> by lazy {
        listOfNotNull(
            PSI_METHOD, KT_NAMED_FUNCTION, KT_CONSTRUCTOR, PY_FUNCTION,
            JS_FUNCTION, PHP_FUNCTION, GO_NAMED_SIGNATURE_OWNER, RS_FUNCTION
        )
    }

    fun isMethodLike(element: PsiElement): Boolean =
        methodLikeTypes.any { it.isInstance(element) }

    fun walkUpToMethodLike(element: PsiElement): PsiElement? {
        var current: PsiElement? = element
        while (current != null) {
            if (isMethodLike(current)) return current
            current = current.parent
        }
        return null
    }
}
