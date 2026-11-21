package com.github.vcth4nh.idesense.handlers.go

import com.intellij.find.findUsages.FindUsagesHandler
import com.intellij.psi.PsiElement

/**
 * The Go part of [com.github.vcth4nh.idesense.handlers.FindUsagesHandlerSearch] (#130, #132, #171).
 * The plugin does not compile against the Go plugin: the Go classes are known by name and
 * read by reflection.
 */
internal object GoFindUsages {

    private const val GO_FIND_USAGES_HANDLER = "com.goide.usages.GoFindUsagesHandler"

    private val goTypeSpecClass: Class<*>? by lazy { goClass("com.goide.psi.GoTypeSpec") }
    private val goKeyClass: Class<*>? by lazy { goClass("com.goide.psi.GoKey") }
    private val goFieldNameClass: Class<*>? by lazy { goClass("com.goide.psi.GoFieldName") }
    private val goFieldDefinitionClass: Class<*>? by lazy { goClass("com.goide.psi.GoFieldDefinition") }

    private fun goClass(name: String): Class<*>? =
        try { Class.forName(name) } catch (_: ClassNotFoundException) { null }

    /** True when `com.goide.usages.GoFindUsagesHandler` is the class of [handler] or one of its superclasses (compare class NAMES; the plugin does not compile against the Go plugin). */
    fun isGoHandler(handler: FindUsagesHandler): Boolean =
        generateSequence<Class<*>>(handler.javaClass) { it.superclass }.any { it.name == GO_FIND_USAGES_HANDLER }

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

    /**
     * True when [anchor] is a type (`com.goide.psi.GoTypeSpec`) and the usage at [usageElement] is
     * a key of a composite literal that resolves to a named struct field
     * (`com.goide.psi.GoFieldDefinition`): [usageElement] or its parent is a
     * `com.goide.psi.GoFieldName` whose parent is a `com.goide.psi.GoKey`. The find usages search
     * leaves out such a usage ([com.github.vcth4nh.idesense.constants.UsageDrop.GO_FIELD_KEY]).
     *
     * This is a deviation from GoLand, a decision of the owner (2026-11-17): Find Usages of GoLand
     * on a type lists a key with the name of the type also when the key names a field of the
     * literal's struct (in caddy v2.11.7, the key `CA` of `certmagic.ACMEIssuer{CA: iss.CA}` is a
     * usage of the interface `caddytls.CA`). Such a key refers to the field, not to the type.
     * A key of an embedded field (it resolves to a `com.goide.psi.GoAnonymousFieldDefinition`,
     * `Outer{Inner: v}`) names the type, and a key that does not resolve can name it: both stay.
     *
     * The facts of `plugins/go-plugin/lib/intellij.go.impl.jar` and the platform (build 262.8665):
     * - `GoKeyImpl.getFieldName()` is `GoParserPsiTreeUtil.getChildOfType(this, GoFieldName.class)`:
     *   the field name of a key is a child of the key.
     * - `GoFieldNameImpl.getReference()` gives `GoPsiImplUtil.getReference(GoFieldName)`: a
     *   `PsiMultiReference` (`GoPsiImplUtil$1`) on the field name with two references, a
     *   `GoFieldNameReference` (the fields of the struct type of the literal,
     *   `processStructLiteralKeys`) and `GoReference.create(fieldName)` (the name as an
     *   unqualified identifier). Its `multiResolve` gives the results of the `GoFieldNameReference`
     *   when it has some, else nothing when `GoFieldNameReference.inStructTypeKey()` is true, else
     *   the results of the identifier; its `resolve()` gives the one result, else null.
     * - `PsiMultiReference.isReferenceTo` is true when one of its references is a reference to the
     *   element (`lib/intellij.platform.core.impl.jar`). Thus the identifier part makes the key a
     *   reference to the type with the same name, although the key resolves to the field.
     * - `PsiElementBase.getReferences()` gives `[getReference()]` (`SharedPsiElementImplUtil`), so
     *   the search gets the multi reference itself. Find Usages wraps it in `UsageInfo(PsiReference)`
     *   (`FindUsagesHandlerBase$1.processInReadAction`, `lib/intellij.platform.analysis.impl.jar`),
     *   which keeps `reference.getElement()` (`lib/intellij.platform.core.jar`): `UsageInfo.element`
     *   is the field name.
     * - `GoAnonymousFieldDefinition` is no `GoFieldDefinition`: the two interfaces both extend
     *   `GoNamedElement`, and neither extends the other.
     */
    fun isFieldKeyOfType(usageElement: PsiElement, anchor: PsiElement): Boolean {
        val typeSpec = goTypeSpecClass ?: return false
        val key = goKeyClass ?: return false
        val fieldName = goFieldNameClass ?: return false
        val fieldDefinition = goFieldDefinitionClass ?: return false
        if (!typeSpec.isInstance(anchor)) return false
        val name = keyFieldName(usageElement, key, fieldName) ?: return false
        return fieldDefinition.isInstance(name.reference?.resolve())
    }

    /**
     * The field name of a composite literal key for [usageElement]: [usageElement] itself or its
     * parent, when it is of [fieldNameClass] and its parent is of [keyClass]. Else null.
     */
    internal fun keyFieldName(usageElement: PsiElement, keyClass: Class<*>, fieldNameClass: Class<*>): PsiElement? {
        val name = if (fieldNameClass.isInstance(usageElement)) usageElement
        else usageElement.parent?.takeIf { fieldNameClass.isInstance(it) } ?: return null
        return name.takeIf { keyClass.isInstance(it.parent) }
    }
}
