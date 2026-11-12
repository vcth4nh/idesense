package com.github.vcth4nh.idesense.handlers.go

import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.psi.PsiElement

/**
 * The Go part of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch] (#130, #132).
 * The plugin does not compile against the Go plugin: the Go classes are known by name and
 * read by reflection.
 */
internal object GoFindUsages {

    /**
     * The `notes` entry when the options of the Go handler search the interface methods too and
     * the method has a super method ([hasSuperMethod]). In the mode of the Find Usages action,
     * `GoFindUsagesHandlerFactory` sets `findBaseMethods` for every Go method (registry key
     * `go.find.usages.always.use.top.hierarchy.methods`), also for a method that implements no
     * interface, so the flag alone does not decide the note. When the check cannot run, the note
     * comes, because the handler did search the base methods. The text does not say that usages
     * of the interface methods exist.
     */
    const val BASE_METHODS_NOTE =
        "Usages of the interface methods that this method implements are included (the default of Find Usages in GoLand)."

    private const val GO_FIND_USAGES_HANDLER = "com.goide.usages.GoFindUsagesHandler"

    /** True when `com.goide.usages.GoFindUsagesHandler` is the class of [handler] or one of its superclasses (compare class NAMES; the plugin does not compile against the Go plugin). */
    fun isGoHandler(handler: FindUsagesHandler): Boolean =
        generateSequence<Class<*>>(handler.javaClass) { it.superclass }.any { it.name == GO_FIND_USAGES_HANDLER }

    /** Reads the public boolean field `findBaseMethods` of [options] by reflection (the declaring class is package-private: set `isAccessible`). False when the field is absent or not a boolean. */
    fun searchesBaseMethods(options: Any): Boolean {
        val field = try {
            options.javaClass.getField("findBaseMethods")
        } catch (_: NoSuchFieldException) {
            return false
        }
        if (field.type != java.lang.Boolean.TYPE) return false
        field.isAccessible = true
        return field.getBoolean(options)
    }

    /**
     * True when [element], a Go method declaration, has at least one super method; the search of
     * [GoSuperMethodsProvider.hasSuperMethod]. Null when the check cannot run.
     */
    fun hasSuperMethod(element: PsiElement): Boolean? =
        (SuperMethodsProvider.EP.forLanguage(element.language) as? GoSuperMethodsProvider)?.hasSuperMethod(element)
}
