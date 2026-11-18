package com.github.vcth4nh.idesense.handlers.php

import com.github.vcth4nh.idesense.constants.UsageDrop
import com.github.vcth4nh.idesense.constants.UsageMatch
import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Key
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiPolyVariantReference
import com.intellij.psi.PsiReference
import com.intellij.psi.search.SearchScope
import com.intellij.psi.search.searches.ReferencesSearch
import com.intellij.psi.util.CachedValue
import com.intellij.psi.util.CachedValueProvider
import com.intellij.psi.util.CachedValuesManager
import com.intellij.psi.util.PsiModificationTracker
import com.intellij.psi.util.PsiTreeUtil
import java.lang.reflect.InvocationHandler
import java.lang.reflect.InvocationTargetException
import java.lang.reflect.Proxy

/**
 * PHP super-methods provider. Delegates to
 * `com.jetbrains.php.PhpClassHierarchyUtils.processSuperMembers(PhpClassMember, HierarchyClassMemberProcessor)`
 * — the broader API that internally dispatches to `processSuperMethods` for
 * `Method` and `processSuperFields` for `Field`. In the PHP plugin's PSI,
 * `const X = "y"` inside a class is a `Field` with `isConstant() == true`,
 * so this single call covers methods, fields/properties, AND class constants.
 *
 * Matches the data path `PhpLineMarkerProvider.findParents` uses for the
 * `↑` gutter marker (which also accepts both Method and Field).
 *
 * The `HierarchyClassMemberProcessor` is a `@FunctionalInterface` callback;
 * we implement it via `java.lang.reflect.Proxy.newProxyInstance` to avoid a
 * compile-time PHP-plugin dep.
 *
 * Covers (gain over previous walker): trait sources, `insteadof` conflict
 * resolution, `@mixin`, constant overrides, field overrides, correct
 * private-method handling.
 *
 * Find usages (#179, #182, #183). The PHP classes below are in `plugins/php-impl/lib/php.jar`
 * and `plugins/php-impl/lib/php-openapi.jar` of PhpStorm (build 262.8665), read with `javap`:
 * - `PhpFindUsagesHandlerFactory.createFindUsagesHandler(PsiElement, OperationMode)` (php.jar):
 *   for a `Method` in each mode except `HIGHLIGHT_USAGES`, it calls the private
 *   `checkSuperMethods(Method, String)`. That method collects the super methods with
 *   `PhpClassHierarchyUtils.processSuperMethods(Method, HierarchyMethodProcessor)`. With a super
 *   method, it calls `isFindUsagesOfBaseMethod(Project, String, String)`, which shows
 *   `Messages.showYesNoCancelDialog` (the question "find usages of base method?") unless the
 *   stored answer of `PhpSmartKeysConfiguration` applies. Off the EDT the dialog throws (#182).
 *   [findDirectReferences] gives the references of each PHP method, thus the search asks the
 *   factory for no method, and the question cannot occur.
 * - `PhpFindUsagesHandler.processElementUsages(PsiElement, Processor, FindUsagesOptions)`
 *   (php.jar), the search of the Find Usages action: for a `Method`, it runs
 *   `ReferencesSearch.search(m, options.searchScope, false)` for the method and for each method of
 *   the private `checkImplementedMethods(PsiElement)`, which collects the overriding methods with
 *   `PhpClassHierarchyUtils.processOverridingMethods(Method, TypedHierarchyMemberProcessor)` (#183).
 *   It gives the declaration of an overriding method only when `PhpFindUsagesOptions.isIncludeChildMethods`
 *   is on; the tool never gives these declarations ([findOverridingDeclarations]).
 * - `PhpThisOrSelfFilteringRule.isVisible(Usage, UsageTarget[])` (php.jar): the rule that the
 *   Usage View applies by default (#179); see [droppedUsageKind].
 * - `PhpClassHierarchyUtils` and its processor interfaces are in php-openapi.jar.
 *   `PhpLangUtil` is in php.jar.
 *
 * The tool searches a PHP method in up to three passes: the method itself, each base method
 * ([findBaseDeclarations], mark `BASE`) and each overriding method ([findOverridingDeclarations],
 * mark `OVERRIDE`). For a method with a base method, this is the approved deviation of a marked
 * false positive: PhpStorm searches either the base methods and their overriding methods (the
 * answer Base Method) or the method and its overriding methods (the answer Current Method), with
 * no mark. The tool does not search the other overriding methods of a base method.
 * [usageMark] decides the mark of each usage from the declarations that its reference resolves
 * to, not from its pass: in PhpStorm 2026.2, both answers at `Circle::area` of the PHP fixture
 * list the same 4 calls on a value of the type `Shape`, so the references of an overriding method
 * also hold the calls through its base method.
 */
class PhpSuperMethodsProvider : SuperMethodsProvider {

    companion object {
        private val LOG = logger<PhpSuperMethodsProvider>()

        /** The overriding methods of a PHP method and whether it has a base method, kept until the next PSI change. */
        private val MARK_CONTEXT = Key.create<CachedValue<MarkContext>>("idesense.php.usageMarkContext")

        /**
         * The mark of a usage of the method [anchor] (the rule of [usageMark]). [targets] are the
         * declarations that the reference of the usage resolves to, [overrides] the overriding methods of
         * [anchor], [hasBase] true when [anchor] has a base method, [passMark] the mark of the pass, and
         * [same] the PSI equivalence. No mark when a target is [anchor]; `OVERRIDE` when a target is an
         * overriding method; [passMark] when there is no target or when [passMark] is not null; else
         * `BASE` when [anchor] has a base method, else `DYNAMIC`.
         */
        internal fun usageMarkOf(
            targets: List<PsiElement>,
            anchor: PsiElement,
            overrides: List<PsiElement>,
            hasBase: Boolean,
            passMark: String?,
            same: (PsiElement, PsiElement) -> Boolean,
        ): String? = when {
            targets.any { same(it, anchor) } -> null
            targets.any { target -> overrides.any { same(it, target) } } -> UsageMatch.OVERRIDE
            targets.isEmpty() || passMark != null -> passMark
            hasBase -> UsageMatch.BASE
            else -> UsageMatch.DYNAMIC
        }
    }

    /** See [MARK_CONTEXT]. */
    private class MarkContext(val overrides: List<PsiElement>, val hasBase: Boolean)

    private val phpClassMemberClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.PhpClassMember") } catch (_: ClassNotFoundException) { null }
    }

    private val phpClassClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.PhpClass") } catch (_: ClassNotFoundException) { null }
    }

    private val methodClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.Method") } catch (_: ClassNotFoundException) { null }
    }

    private val classReferenceClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.psi.elements.ClassReference") } catch (_: ClassNotFoundException) { null }
    }

    private val hierarchyUtilsClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpClassHierarchyUtils") } catch (_: ClassNotFoundException) { null }
    }

    private val hierarchyClassMemberProcessorClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpClassHierarchyUtils\$HierarchyClassMemberProcessor") } catch (_: ClassNotFoundException) { null }
    }

    private val hierarchyMethodProcessorClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpClassHierarchyUtils\$HierarchyMethodProcessor") } catch (_: ClassNotFoundException) { null }
    }

    private val typedHierarchyMemberProcessorClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.PhpClassHierarchyUtils\$TypedHierarchyMemberProcessor") } catch (_: ClassNotFoundException) { null }
    }

    private val phpLangUtilClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.php.lang.PhpLangUtil") } catch (_: ClassNotFoundException) { null }
    }

    /** `PhpClassHierarchyUtils.processSuperMethods(Method, HierarchyMethodProcessor)`. */
    private val processSuperMethodsMethod: java.lang.reflect.Method? by lazy {
        try {
            val util = hierarchyUtilsClass ?: return@lazy null
            util.getMethod("processSuperMethods", methodClass ?: return@lazy null, hierarchyMethodProcessorClass ?: return@lazy null)
        } catch (_: Throwable) { null }
    }

    /** `PhpClassHierarchyUtils.processOverridingMethods(Method, TypedHierarchyMemberProcessor)`. */
    private val processOverridingMethodsMethod: java.lang.reflect.Method? by lazy {
        try {
            val util = hierarchyUtilsClass ?: return@lazy null
            util.getMethod("processOverridingMethods", methodClass ?: return@lazy null, typedHierarchyMemberProcessorClass ?: return@lazy null)
        } catch (_: Throwable) { null }
    }

    /** `PhpLangUtil.isThisReference(PsiElement)`. */
    private val isThisReferenceMethod: java.lang.reflect.Method? by lazy {
        try { phpLangUtilClass?.getMethod("isThisReference", PsiElement::class.java) } catch (_: Throwable) { null }
    }

    /** `PhpLangUtil.isSelfReference(ClassReference)`. */
    private val isSelfReferenceMethod: java.lang.reflect.Method? by lazy {
        try { phpLangUtilClass?.getMethod("isSelfReference", classReferenceClass ?: return@lazy null) } catch (_: Throwable) { null }
    }

    /** `PhpLangUtil.isStaticReference(PsiElement)`. */
    private val isStaticReferenceMethod: java.lang.reflect.Method? by lazy {
        try { phpLangUtilClass?.getMethod("isStaticReference", PsiElement::class.java) } catch (_: Throwable) { null }
    }

    /** `PhpLangUtil.isObject(PhpClass)`. */
    private val isObjectMethod: java.lang.reflect.Method? by lazy {
        try { phpLangUtilClass?.getMethod("isObject", phpClassClass ?: return@lazy null) } catch (_: Throwable) { null }
    }

    private val processSuperMembersMethod: java.lang.reflect.Method? by lazy {
        try {
            val util = hierarchyUtilsClass ?: return@lazy null
            val member = phpClassMemberClass ?: return@lazy null
            val processor = hierarchyClassMemberProcessorClass ?: return@lazy null
            util.getMethod("processSuperMembers", member, processor)
        } catch (_: Throwable) { null }
    }

    private val getImmediateParentsMethod: java.lang.reflect.Method? by lazy {
        try {
            val util = hierarchyUtilsClass ?: return@lazy null
            val phpClass = phpClassClass ?: return@lazy null
            util.getMethod("getImmediateParents", phpClass)
        } catch (_: Throwable) { null }
    }

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        // Member anchor: existing full-chain behavior (unchanged)
        val member = findContainingMember(element)
        if (member != null) {
            val file = member.containingFile?.virtualFile
            val methodData = MethodData(
                name = getName(member) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(member),
                kind = LanguageServices.getKind(member),
                file = file?.let { getRelativePath(project, it) } ?: "unknown",
                line = getLineNumber(project, member) ?: 0,
                column = getColumnNumber(project, member) ?: 0,
            )
            return SuperMethodsData(method = methodData, hierarchy = buildHierarchy(project, member))
        }

        // Class anchor: direct supertypes only (one level up)
        val phpClass = findContainingPhpClass(element) ?: return null
        val file = phpClass.containingFile?.virtualFile
        val classData = MethodData(
            name = getName(phpClass) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(phpClass),
            kind = LanguageServices.getKind(phpClass),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, phpClass) ?: 0,
            column = getColumnNumber(project, phpClass) ?: 0,
        )
        return SuperMethodsData(method = classData, hierarchy = buildClassHierarchy(project, phpClass))
    }

    /**
     * The super methods of [element], when [element] itself is a PHP `Method`: all levels, the
     * nearest first. This is the list of `PhpFindUsagesHandlerFactory.checkSuperMethods`, the list
     * that the answer Base Method searches: `PhpClassHierarchyUtils.processSuperMethods` (a walk
     * of the parents, breadth first, in `processSuperMembersInternal`) with the processor of that
     * method (`lambda$checkSuperMethods$0`), which stops the walk without the method when the class
     * of the walk is the helper class `object` (`PhpLangUtil.isObject`). Empty for another element.
     */
    override fun findBaseDeclarations(element: PsiElement): List<PsiElement> {
        if (methodClass?.isInstance(element) != true) return emptyList()
        return walkMethods(processSuperMethodsMethod, hierarchyMethodProcessorClass, element) { subClass ->
            subClass == null || invokeCheck(isObjectMethod, subClass) != true
        }
    }

    /**
     * The references to [element] itself, when [element] is a PHP `Method`:
     * `ReferencesSearch.search(element, scope, false)`, the search that
     * `PhpFindUsagesHandler.processElementUsages` runs for each method. Null for another element:
     * the search then takes the handler, as before. Thus the search asks
     * `PhpFindUsagesHandlerFactory` for no method, and its question about the base method (#182)
     * cannot occur. The handler of a method has the method as its only primary element and no
     * secondary element (`PhpFindUsagesHandler(PsiElement, PhpFindUsagesHandlerFactory)`).
     */
    override fun findDirectReferences(element: PsiElement, scope: SearchScope): Collection<PsiReference>? {
        if (methodClass?.isInstance(element) != true) return null
        return ReferencesSearch.search(element, scope, false).findAll()
    }

    /**
     * The methods that override or implement [element], when [element] is a PHP `Method`: the
     * methods that `PhpClassHierarchyUtils.processOverridingMethods` gives, as
     * `PhpFindUsagesHandler.checkImplementedMethods` collects them (#183). The walk covers all
     * subclasses (`PhpIndex.processAllSubclasses`), the classes that use a trait and the traits of
     * the subclasses; a final class, a final method and a private method have none
     * (`methodCanHaveOverride`). A trait method that a class uses is an overriding method only when
     * this walk gives it. The list is kept until the next PSI change ([MARK_CONTEXT]).
     */
    override fun findOverridingDeclarations(element: PsiElement): List<PsiElement> {
        if (methodClass?.isInstance(element) != true) return emptyList()
        return markContext(element).overrides
    }

    /**
     * The mark of a usage of a PHP method [anchor] ([usageMarkOf]): the targets are the
     * declarations that [reference] resolves to (each result of `multiResolve(false)` for a
     * [PsiPolyVariantReference], else `resolve()`). The overriding methods and the base check come
     * one time for each anchor ([MARK_CONTEXT]). [passMark] for another anchor, and when the resolve
     * throws.
     */
    override fun usageMark(reference: PsiReference, anchor: PsiElement, passMark: String?): String? {
        if (methodClass?.isInstance(anchor) != true) return passMark
        val targets = try {
            if (reference is PsiPolyVariantReference) reference.multiResolve(false).mapNotNull { it.element }
            else listOfNotNull(reference.resolve())
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: LinkageError) {
            throw e
        } catch (e: Throwable) {
            LOG.debug("The resolve of a PHP reference threw; the usage keeps the mark of its pass", e)
            return passMark
        }
        val context = markContext(anchor)
        val manager = anchor.manager
        return usageMarkOf(targets, anchor, context.overrides, context.hasBase, passMark) { a, b -> manager.areElementsEquivalent(a, b) }
    }

    /**
     * [UsageDrop.PHP_SELF_REFERENCE] when [anchor] is a `PhpClass` (also an interface, a trait or an
     * enum) and [usageElement] is a row that Find Usages of PhpStorm hides by default (#179), else
     * null. The rule copies `PhpThisOrSelfFilteringRule.isVisible`: when each target is a `PhpClass`,
     * the rule hides a usage whose element is a `$this` reference (`PhpLangUtil.isThisReference`),
     * or a `ClassReference` that is `self` (`PhpLangUtil.isSelfReference(ClassReference)`) or
     * `static` (`PhpLangUtil.isStaticReference`). The element of the rule is the element of the
     * `UsageInfo` of the reference, the element of the reference. The setting
     * `PhpThisOrSelfImportFilteringUsageSetting.SHOW_THIS_OR_SELF_REFERENCES` is false by default,
     * so the rule is on. A usage of a method or a field keeps `$this->area()`.
     */
    override fun droppedUsageKind(usageElement: PsiElement, anchor: PsiElement): String? {
        if (phpClassClass?.isInstance(anchor) != true) return null
        val hidden = invokeCheck(isThisReferenceMethod, usageElement) == true ||
            (classReferenceClass?.isInstance(usageElement) == true &&
                (invokeCheck(isSelfReferenceMethod, usageElement) == true || invokeCheck(isStaticReferenceMethod, usageElement) == true))
        return if (hidden) UsageDrop.PHP_SELF_REFERENCE else null
    }

    /** The overriding methods and the base check of [method], computed one time until the next PSI change. */
    private fun markContext(method: PsiElement): MarkContext =
        CachedValuesManager.getCachedValue(method, MARK_CONTEXT) {
            val overrides = walkMethods(processOverridingMethodsMethod, typedHierarchyMemberProcessorClass, method) { true }
            CachedValueProvider.Result.create(
                MarkContext(overrides, findBaseDeclarations(method).isNotEmpty()),
                PsiModificationTracker.MODIFICATION_COUNT,
            )
        }

    /**
     * Calls the static [walk] of `PhpClassHierarchyUtils` with [method] and a processor of
     * [processorIface], and gives the methods of the calls `process(member, subClass, baseClass)`
     * for which [accept] of `subClass` is true, each one time. The processor returns the result of
     * [accept], so false stops the walk. Empty when the PHP plugin is absent or when the walk throws;
     * a cancellation passes through.
     */
    private fun walkMethods(
        walk: java.lang.reflect.Method?,
        processorIface: Class<*>?,
        method: PsiElement,
        accept: (subClass: PsiElement?) -> Boolean,
    ): List<PsiElement> {
        if (walk == null || processorIface == null) return emptyList()
        val collected = LinkedHashSet<PsiElement>()
        val handler = InvocationHandler { _, m, args ->
            when {
                m.name == "process" && args != null && args.size == 3 -> {
                    val keep = accept(args[1] as? PsiElement)
                    if (keep) (args[0] as? PsiElement)?.let(collected::add)
                    keep
                }
                m.name == "equals" && args?.size == 1 -> false
                m.name == "hashCode" -> 0
                m.name == "toString" -> "${processorIface.simpleName}\$Proxy"
                m.returnType == java.lang.Boolean.TYPE -> true
                else -> null
            }
        }
        val proxy = Proxy.newProxyInstance(processorIface.classLoader, arrayOf(processorIface), handler)
        try {
            walk.invoke(null, method, proxy)
        } catch (t: Throwable) {
            val cause = (t as? InvocationTargetException)?.targetException ?: t
            if (cause is ProcessCanceledException) throw cause
            LOG.debug("PhpClassHierarchyUtils.${walk.name} invocation failed", cause)
            return emptyList()
        }
        return collected.toList()
    }

    /** Calls the static boolean check [check] of `PhpLangUtil` with [element]. Null when it is absent or throws; a cancellation passes through. */
    private fun invokeCheck(check: java.lang.reflect.Method?, element: PsiElement): Boolean? {
        if (check == null) return null
        return try {
            check.invoke(null, element) as? Boolean
        } catch (t: Throwable) {
            val cause = (t as? InvocationTargetException)?.targetException ?: t
            if (cause is ProcessCanceledException) throw cause
            LOG.debug("PhpLangUtil.${check.name} invocation failed", cause)
            null
        }
    }

    private fun buildHierarchy(project: Project, member: PsiElement): List<SuperMethodData> {
        val invoker = processSuperMembersMethod ?: return emptyList()
        val processorIface = hierarchyClassMemberProcessorClass ?: return emptyList()

        val collected = mutableListOf<PsiElement>()
        val visited = mutableSetOf<String>()

        val handler = InvocationHandler { _, m, args ->
            if (m.name == "process" && args != null && args.isNotEmpty()) {
                val superMember = args[0] as? PsiElement
                if (superMember != null) {
                    val key = QualifiedNameUtil.getQualifiedName(superMember)
                        ?: "${superMember.javaClass.simpleName}@${System.identityHashCode(superMember)}"
                    if (visited.add(key)) collected.add(superMember)
                }
                return@InvocationHandler true  // keep processing
            }
            // Default returns for the Object methods (equals/hashCode/toString) and
            // any unexpected interface method. Defensive — the PHP plugin should
            // only ever call `process(...)` on our processor.
            when {
                m.name == "equals" && args?.size == 1 -> false
                m.name == "hashCode" -> 0
                m.name == "toString" -> "HierarchyClassMemberProcessor\$Proxy"
                m.returnType == java.lang.Boolean.TYPE -> true
                m.returnType == java.lang.Void.TYPE -> null
                else -> null
            }
        }

        val proxy = Proxy.newProxyInstance(
            processorIface.classLoader,
            arrayOf(processorIface),
            handler,
        )

        try {
            invoker.invoke(null, member, proxy)
        } catch (t: Throwable) {
            LOG.debug("PhpClassHierarchyUtils.processSuperMembers invocation failed", t)
            return emptyList()
        }

        return collected.map { superMember ->
            val file = superMember.containingFile?.virtualFile
            SuperMethodData(
                name = getName(superMember) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(superMember),
                kind = LanguageServices.getKind(superMember),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superMember),
                column = getColumnNumber(project, superMember),
            )
        }
    }

    private fun findContainingMember(element: PsiElement): PsiElement? {
        val cls = phpClassMemberClass ?: return null
        if (cls.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    private fun findContainingPhpClass(element: PsiElement): PsiElement? {
        val cls = phpClassClass ?: return null
        if (cls.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, cls as Class<out PsiElement>)
    }

    /**
     * Returns the DIRECT supertypes of [phpClass] — one level only, no transitive walk.
     * Mirrors `PhpGotoSuperMethodHandler`'s class branch, which calls
     * `PhpClassHierarchyUtils.getImmediateParents(PhpClass)` (super class + interfaces + traits).
     */
    private fun buildClassHierarchy(project: Project, phpClass: PsiElement): List<SuperMethodData> {
        val invoker = getImmediateParentsMethod ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val parents: List<PsiElement> = try {
            invoker.invoke(null, phpClass) as? List<PsiElement> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("PhpClassHierarchyUtils.getImmediateParents invocation failed", t)
            return emptyList()
        }

        return parents.mapNotNull { parent ->
            val file = parent.containingFile?.virtualFile
            SuperMethodData(
                name = getName(parent) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(parent),
                kind = LanguageServices.getKind(parent),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, parent),
                column = getColumnNumber(project, parent),
            )
        }
    }

    private fun getName(element: PsiElement): String? = runCatching {
        element.javaClass.getMethod("getName").invoke(element) as? String
    }.getOrNull()

    private fun getRelativePath(project: Project, file: VirtualFile): String =
        ProjectUtils.getToolFilePath(project, file)

    private fun getLineNumber(project: Project, element: PsiElement): Int? {
        val psiFile = element.containingFile ?: return null
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile) ?: return null
        return document.getLineNumber(element.textOffset) + 1
    }

    private fun getColumnNumber(project: Project, element: PsiElement): Int? {
        val psiFile = element.containingFile ?: return null
        val document = PsiDocumentManager.getInstance(project).getDocument(psiFile) ?: return null
        val lineNumber = document.getLineNumber(element.textOffset)
        return element.textOffset - document.getLineStartOffset(lineNumber) + 1
    }
}
