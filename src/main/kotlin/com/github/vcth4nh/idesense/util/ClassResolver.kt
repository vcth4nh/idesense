package com.github.vcth4nh.idesense.util

import com.intellij.ide.actions.QualifiedNameProvider
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement

/**
 * Resolves any element by its qualified name using IntelliJ's QualifiedNameProvider
 * extension point. Symmetric reverse of [QualifiedNameUtil.getQualifiedName] — every
 * language plugin's QualifiedNameProvider implements both forward and reverse direction.
 *
 * Works for any language whose plugin registers a QualifiedNameProvider (Java, Kotlin,
 * Python, PHP, JS/TS, Rust, Go, etc.).
 */
object ClassResolver {

    private val LOG = logger<ClassResolver>()

    /**
     * Reflectively-loaded PhpIndex helper. Null when the PHP plugin isn't loaded.
     * Used as a PHP-specific fallback for interface and trait FQNs, which the
     * upstream PhpQualifiedNameProvider.qualifiedNameToElement does not resolve.
     */
    private val phpIndexClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpIndex") } catch (_: ClassNotFoundException) { null }
    }

    /**
     * Finds an element by its fully qualified name. Returns null if no provider matches.
     *
     * Resolution order:
     * 1. Iterate `QualifiedNameProvider.EP_NAME` calling `qualifiedNameToElement` —
     *    handles Java, Kotlin, Python, PHP classes, JS/TS, Rust, Go, etc.
     * 2. If the result is from a `.class`/decompiled wrapper, unwrap to its
     *    `navigationElement` so callers see the source-attached element.
     * 3. PHP-specific fallback: if EP iteration returns null and the PHP plugin is
     *    loaded, query `PhpIndex.getInterfacesByFQN` and `PhpIndex.getTraitsByFQN`
     *    (the upstream `PhpQualifiedNameProvider.qualifiedNameToElement` only
     *    resolves classes — interface and trait stub indexes are separate).
     *
     * @param project The project context.
     * @param qualifiedName Fully qualified name in the language's natural format
     *   (e.g., `com.example.MyClass`, `\App\Models\User`, `noise.MyParser`).
     * @return The resolved [PsiElement], or null. Caller is responsible for instanceof checks
     *   if a specific element kind is required (e.g., `PsiClass` / `PyClass`).
     */
    fun findClassByName(project: Project, qualifiedName: String): PsiElement? {
        for (provider in QualifiedNameProvider.EP_NAME.extensionList) {
            try {
                val resolved = provider.qualifiedNameToElement(qualifiedName, project)
                if (resolved != null) return resolved.navigationElement ?: resolved
            } catch (e: Exception) {
                LOG.debug(
                    "QualifiedNameProvider ${provider.javaClass.simpleName} threw for FQN " +
                        "$qualifiedName: ${e.message}"
                )
            }
        }

        // PHP-specific fallback: interface or trait FQNs.
        phpIndexClass?.let { return resolvePhpInterfaceOrTrait(it, project, qualifiedName) }
        return null
    }

    private fun resolvePhpInterfaceOrTrait(
        phpIndexCls: Class<*>,
        project: Project,
        qualifiedName: String
    ): PsiElement? {
        return try {
            val instance = phpIndexCls.getMethod("getInstance", Project::class.java).invoke(null, project)

            // Normalize FQN: handle double-escaped backslashes and ensure leading backslash.
            val cleanedFqn = qualifiedName.replace("\\\\", "\\")
            val normalizedFqn = if (cleanedFqn.startsWith("\\")) cleanedFqn else "\\$cleanedFqn"

            val getInterfacesByFqn = phpIndexCls.getMethod("getInterfacesByFQN", String::class.java)
            val getTraitsByFqn = try {
                phpIndexCls.getMethod("getTraitsByFQN", String::class.java)
            } catch (_: NoSuchMethodException) {
                null
            }

            @Suppress("UNCHECKED_CAST")
            (getInterfacesByFqn.invoke(instance, normalizedFqn) as? Collection<PsiElement>)
                ?.firstOrNull()
                ?.let { return it.navigationElement ?: it }

            @Suppress("UNCHECKED_CAST")
            (getTraitsByFqn?.invoke(instance, normalizedFqn) as? Collection<PsiElement>)
                ?.firstOrNull()
                ?.let { return it.navigationElement ?: it }

            null
        } catch (e: Exception) {
            LOG.debug("PHP interface/trait fallback threw for FQN $qualifiedName: ${e.message}")
            null
        }
    }
}
