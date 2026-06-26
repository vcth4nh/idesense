package com.github.vcth4nh.idesense.handlers.rust

import com.github.vcth4nh.idesense.handlers.LanguageKindResolver
import com.intellij.psi.PsiElement

class RustKindResolver : LanguageKindResolver {

    private val rsStructItem: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsStructItem") }
    private val rsTraitItem: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsTraitItem") }
    private val rsEnumItem: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsEnumItem") }
    private val rsFunction: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsFunction") }
    private val rsImplItem: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsImplItem") }
    private val rsModItem: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsModItem") }
    private val rsConstant: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsConstant") }
    private val rsTypeAlias: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsTypeAlias") }
    private val rsEnumVariant: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsEnumVariant") }
    private val rsNamedFieldDecl: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsNamedFieldDecl") }
    private val rsMacro: Class<*>? by lazy { loadClass("org.rust.lang.core.psi.RsMacro") }

    private fun loadClass(name: String): Class<*>? =
        try { Class.forName(name) } catch (_: ClassNotFoundException) { null }

    override fun resolveKind(element: PsiElement): String? {
        return when {
            rsStructItem?.isInstance(element) == true -> "STRUCT"
            rsTraitItem?.isInstance(element) == true -> "TRAIT"
            rsEnumItem?.isInstance(element) == true -> "ENUM"
            rsEnumVariant?.isInstance(element) == true -> "ENUM_VARIANT"
            rsFunction?.isInstance(element) == true -> resolveRustFunction(element)
            rsImplItem?.isInstance(element) == true -> "IMPL"
            rsModItem?.isInstance(element) == true -> "MODULE"
            rsConstant?.isInstance(element) == true -> "CONSTANT"
            rsTypeAlias?.isInstance(element) == true -> "TYPE_ALIAS"
            rsNamedFieldDecl?.isInstance(element) == true -> "FIELD"
            rsMacro?.isInstance(element) == true -> "MACRO"
            else -> null
        }
    }

    private fun resolveRustFunction(element: PsiElement): String {
        return try {
            val parent = element.parent
            val grandparent = parent?.parent
            if (rsImplItem?.isInstance(parent) == true || rsTraitItem?.isInstance(parent) == true ||
                rsImplItem?.isInstance(grandparent) == true || rsTraitItem?.isInstance(grandparent) == true) {
                "METHOD"
            } else {
                "FUNCTION"
            }
        } catch (_: Exception) { "FUNCTION" }
    }
}
