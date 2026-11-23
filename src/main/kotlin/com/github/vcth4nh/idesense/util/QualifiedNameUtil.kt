package com.github.vcth4nh.idesense.util

import com.intellij.ide.actions.QualifiedNameProvider
import com.intellij.openapi.diagnostic.logger
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil

object QualifiedNameUtil {
    private val LOG = logger<QualifiedNameUtil>()

    private val pyQualifiedNameOwnerClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.python.psi.PyQualifiedNameOwner") } catch (_: ClassNotFoundException) { null }
    }

    private val goNamedElementClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoNamedElement") } catch (_: ClassNotFoundException) { null }
    }

    private val goFileClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoFile") } catch (_: ClassNotFoundException) { null }
    }

    private val goMethodDeclarationClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoMethodDeclaration") } catch (_: ClassNotFoundException) { null }
    }

    private val goMethodSpecClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoMethodSpec") } catch (_: ClassNotFoundException) { null }
    }

    private val goTypeSpecClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoTypeSpec") } catch (_: ClassNotFoundException) { null }
    }

    private val goFieldDefinitionClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoFieldDefinition") } catch (_: ClassNotFoundException) { null }
    }

    private val goAnonymousFieldDefinitionClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoAnonymousFieldDefinition") } catch (_: ClassNotFoundException) { null }
    }

    private val ktTypeAliasClass: Class<*>? by lazy {
        try { Class.forName("org.jetbrains.kotlin.psi.KtTypeAlias") } catch (_: ClassNotFoundException) { null }
    }

    private val rsNamedElementClass: Class<*>? by lazy {
        try { Class.forName("org.rust.lang.core.psi.ext.RsNamedElement") } catch (_: ClassNotFoundException) { null }
    }

    /**
     * Returns the qualified name of [element] using the IDE's QualifiedNameProvider extension point.
     * Falls back (in order) to:
     *  - PyCharm's PyQualifiedNameOwner (covers PyTargetExpression cases the upstream provider misses)
     *  - Go: builds package.Function / package.Receiver.Method via reflection on GoFile + GoMethodDeclaration
     *  - Rust: walks PSI ancestors joining names with ::
     *  - Kotlin type alias: the fully qualified name of the Kotlin PSI (#278)
     *
     * Must be called inside a read action.
     *
     * @return qualified name, or null when no provider or fallback handles the element.
     */
    fun getQualifiedName(element: PsiElement): String? {
        // A file element goes to the providers too, but not its directory (#187).
        // A Kotlin type alias gets no name from the providers. The walk over the parents would give
        // the name of its class when the alias is nested (#278), so the walk does not run for it.
        val isTypeAlias = ktTypeAliasClass?.isInstance(element) == true
        val candidates = if (element is PsiFile || isTypeAlias) sequenceOf(element)
            else generateSequence(element) { it.parent }.takeWhile { it !is PsiFile }
        for (candidate in candidates) {
            for (provider in QualifiedNameProvider.EP_NAME.extensionList) {
                try {
                    val adjusted = provider.adjustElementToCopy(candidate) ?: candidate
                    val result = provider.getQualifiedName(adjusted)
                    if (!result.isNullOrBlank()) return result
                } catch (e: Exception) {
                    LOG.debug(
                        "QualifiedNameProvider ${provider.javaClass.simpleName} threw for " +
                            "${candidate.javaClass.simpleName}: ${e.message}"
                    )
                }
            }
        }

        // Fallback 0: Kotlin type alias. The IDE gives no name (KotlinQualifiedNameProvider has no case
        // for KtTypeAlias); the tool gives package + name, as KtNamedDeclaration.getFqName does (#278).
        if (isTypeAlias) return kotlinTypeAliasFqName(element)

        // Fallback 1: PyTargetExpression and similar implement PyQualifiedNameOwner directly.
        val pyOwner = pyQualifiedNameOwnerClass
        if (pyOwner != null && pyOwner.isInstance(element)) {
            try {
                val result = pyOwner.getMethod("getQualifiedName").invoke(element) as? String
                if (!result.isNullOrBlank()) return result
            } catch (e: Exception) {
                LOG.debug("PyQualifiedNameOwner fallback threw for ${element.javaClass.simpleName}: ${e.message}")
            }
        }

        // Fallback 2: Go (no upstream provider exists in GoLand)
        if (element.language.id == "go") {
            goFallback(element)?.let { return it }
        }

        // Fallback 3: Rust (the provider of the Rust plugin returns null for some elements)
        if (element.language.id == "Rust") {
            rustFallback(element)?.let { return it }
        }

        return null
    }

    /**
     * Build a Go-style qualified name. Pure-logic so it's unit-testable without a PSI mock.
     *
     *  - Top-level function: `package.Function`
     *  - Method (with receiver): `package.Receiver.Method` (pointer receiver `*Foo` strips the *)
     *  - If [packageName] is blank, returns just [name] (or `Receiver.name` for methods).
     */
    fun formatGoQualifiedName(packageName: String, receiverType: String?, name: String): String {
        val cleanReceiver = receiverType?.trim()?.removePrefix("*")?.trim()
        val tail = if (!cleanReceiver.isNullOrBlank()) "$cleanReceiver.$name" else name
        return if (packageName.isBlank()) tail else "$packageName.$tail"
    }

    /**
     * Build a Rust-style qualified name. Pure-logic.
     * Joins [ancestorChain] (e.g. ["crate", "quirks", "IntCoercer"]) with `::` then appends `::name`.
     * Empty ancestor chain returns just [name].
     */
    fun formatRustQualifiedName(ancestorChain: List<String>, name: String): String {
        return if (ancestorChain.isEmpty()) name else ancestorChain.joinToString("::") + "::" + name
    }

    private fun kotlinTypeAliasFqName(element: PsiElement): String? = try {
        // getFqName is null for an alias with no name (broken code)
        element.javaClass.getMethod("getFqName").invoke(element)?.toString()
    } catch (e: Exception) {
        LOG.debug("Kotlin type alias fqName threw for ${element.javaClass.simpleName}: ${e.message}")
        null
    }

    private fun goFallback(element: PsiElement): String? {
        val namedElementClass = goNamedElementClass ?: return null
        if (!namedElementClass.isInstance(element)) return null
        return try {
            val name = namedElementClass.getMethod("getName").invoke(element) as? String ?: return null
            val packageName = run {
                val file = element.containingFile ?: return@run ""
                val goFile = goFileClass ?: return@run ""
                if (!goFile.isInstance(file)) "" else (goFile.getMethod("getPackageName").invoke(file) as? String).orEmpty()
            }
            val receiverType = run {
                val methodDecl = goMethodDeclarationClass ?: return@run null
                if (!methodDecl.isInstance(element)) return@run null
                val receiver = methodDecl.getMethod("getReceiver").invoke(element) ?: return@run null
                val type = receiver.javaClass.getMethod("getType").invoke(receiver) as? PsiElement ?: return@run null
                type.text?.trim()
            }
            // Interface method specs (GoMethodSpec) and struct fields (GoFieldDefinition,
            // GoAnonymousFieldDefinition) have no receiver; qualify them by the nearest enclosing
            // type (GoTypeSpec) so they read `package.Type.name` instead of `package.name`.
            // Otherwise a method spec reads as a top-level function, and the fields of one name in
            // two structs of one package get one name (#136). GoLand gives `package.field`.
            val typeName = run {
                val members = listOfNotNull(goMethodSpecClass, goFieldDefinitionClass, goAnonymousFieldDefinitionClass)
                if (members.none { it.isInstance(element) }) return@run null
                val typeSpecCls = goTypeSpecClass ?: return@run null
                @Suppress("UNCHECKED_CAST")
                val enclosing = PsiTreeUtil.getParentOfType(element, typeSpecCls as Class<out PsiElement>) ?: return@run null
                enclosing.javaClass.getMethod("getName").invoke(enclosing) as? String
            }
            formatGoQualifiedName(packageName, receiverType ?: typeName, name)
        } catch (e: Exception) {
            LOG.debug("Go qualified-name fallback threw for ${element.javaClass.simpleName}: ${e.message}")
            null
        }
    }

    private fun rustFallback(element: PsiElement): String? {
        // The name of a file element is its file name ("pathutil.rs"), so no module path can be
        // built from it. Only the provider knows the path of a module file (#187).
        if (element is PsiFile) return null
        val namedElementClass = rsNamedElementClass ?: return null
        if (!namedElementClass.isInstance(element)) return null
        return try {
            val getName = namedElementClass.getMethod("getName")
            val name = getName.invoke(element) as? String ?: return null
            val ancestors = mutableListOf<String>()
            var current: PsiElement? = element.parent
            // Stop the walk at PsiFile boundary: RsFile extends RsMod (a RsNamedElement)
            // and its getName() returns the source file name (e.g. "main.rs"), which would
            // otherwise leak into the qualified name as "crate::main.rs::foo".
            while (current != null && current !is PsiFile) {
                if (namedElementClass.isInstance(current)) {
                    val n = getName.invoke(current) as? String
                    if (!n.isNullOrBlank()) ancestors.add(0, n)
                }
                current = current.parent
            }
            // Prepend "crate" so root-level elements emit `crate::name`.
            ancestors.add(0, "crate")
            formatRustQualifiedName(ancestors, name)
        } catch (e: Exception) {
            LOG.debug("Rust qualified-name fallback threw for ${element.javaClass.simpleName}: ${e.message}")
            null
        }
    }
}
