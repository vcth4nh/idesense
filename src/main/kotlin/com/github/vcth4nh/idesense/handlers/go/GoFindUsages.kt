package com.github.vcth4nh.idesense.handlers.go

import com.intellij.find.findUsages.FindUsagesHandler

/**
 * The Go part of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch] (#130, #132, #171).
 * The plugin does not compile against the Go plugin: the Go classes are known by name and
 * read by reflection.
 */
internal object GoFindUsages {

    private const val GO_FIND_USAGES_HANDLER = "com.goide.usages.GoFindUsagesHandler"

    /** True when `com.goide.usages.GoFindUsagesHandler` is the class of [handler] or one of its superclasses (compare class NAMES; the plugin does not compile against the Go plugin). */
    fun isGoHandler(handler: FindUsagesHandler): Boolean =
        generateSequence<Class<*>>(handler.javaClass) { it.superclass }.any { it.name == GO_FIND_USAGES_HANDLER }

    /** Reads the public boolean field `findBaseMethods` of [options] by reflection (the declaring class is package-private: set `isAccessible`). False when the field is absent or not a boolean. */
    fun searchesBaseMethods(options: Any): Boolean {
        val field = findBaseMethodsField(options) ?: return false
        return field.getBoolean(options)
    }

    /** Sets the public field `findBaseMethods` of GoLand's method options. False when [options] has no such field. */
    fun setFindBaseMethods(options: Any, value: Boolean): Boolean {
        val field = findBaseMethodsField(options) ?: return false
        field.setBoolean(options, value)
        return true
    }

    /** The boolean field `findBaseMethods` of [options], accessible; null when the field is absent or not a boolean. */
    private fun findBaseMethodsField(options: Any): java.lang.reflect.Field? {
        val field = try {
            options.javaClass.getField("findBaseMethods")
        } catch (_: NoSuchFieldException) {
            return null
        }
        if (field.type != java.lang.Boolean.TYPE) return null
        field.isAccessible = true
        return field
    }
}
