package com.github.vcth4nh.idesense.tools.navigation.hierarchy

import com.intellij.codeWithMe.ClientId
import com.intellij.ide.hierarchy.CallHierarchyBrowserBase
import com.intellij.ide.hierarchy.HierarchyBrowserBaseEx
import com.intellij.ide.hierarchy.HierarchyNodeDescriptor
import com.intellij.ide.hierarchy.HierarchyTreeStructure
import com.intellij.ide.hierarchy.LanguageCallHierarchy
import com.intellij.ide.hierarchy.LanguageTypeHierarchy
import com.intellij.ide.hierarchy.TypeHierarchyBrowserBase
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.client.ClientKind
import com.intellij.openapi.client.ClientSessionsManager
import com.intellij.openapi.diagnostic.ControlFlowException
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.util.concurrency.annotations.RequiresReadLock
import java.lang.reflect.InvocationTargetException
import java.lang.reflect.Method
import java.util.concurrent.CancellationException

enum class HierarchyKind {
    CALLERS,
    CALLEES,
    SUPERTYPES,
    SUBTYPES;

    val isCall: Boolean get() = this == CALLERS || this == CALLEES
    val isType: Boolean get() = this == SUPERTYPES || this == SUBTYPES
}

/**
 * Rethrows cooperative cancellation so the enclosing cancellable read action can
 * perform its automatic write-pending restart.
 *
 * The hierarchy tools run inside `com.intellij.openapi.application.readAction { }`
 * (see `AbstractMcpTool.suspendingReadAction`). When a write action becomes pending
 * mid-read, the platform throws `ReadAction.CannotReadException` (a
 * `ProcessCanceledException`) out of the action block; the coroutine read loop
 * (`InternalReadAction.tryReadCancellable`) catches exactly that, maps it to
 * `ReadResult.WritePending`, yields to the write, and re-runs the block. The
 * walker's broad `runCatching {}` blocks would otherwise swallow that signal —
 * reflection wraps it in [InvocationTargetException] — and mislabel it as a genuine
 * failure (e.g. "Browser refused element ..."), turning a retryable race into a
 * spurious tool error.
 *
 * No-op for every non-cancellation throwable, which keeps flowing through the
 * caller's normal failure handling.
 */
internal fun rethrowIfCancellation(t: Throwable) {
    val cause = (t as? InvocationTargetException)?.targetException ?: t
    if (cause is CancellationException || cause is ControlFlowException) throw cause
}

/**
 * Classifies the outcome of reflectively invoking
 * `HierarchyProvider.createHierarchyBrowser(PsiElement)` (#30).
 *
 * - **Cooperative cancellation** — a cold-start [com.intellij.openapi.application.ReadAction.CannotReadException]
 *   / [com.intellij.openapi.progress.ProcessCanceledException], wrapped by reflection in
 *   [InvocationTargetException] — is **rethrown** via [rethrowIfCancellation] so the enclosing
 *   coroutine `readAction { }` performs its write-pending restart instead of surfacing a spurious
 *   hard failure. This is the sibling of the tree-build retry sites fixed in #141: the one
 *   construction site that previously swallowed the signal to `null`, mislabeling a retryable
 *   cold-start race as "createHierarchyBrowser returned non-HierarchyBrowserBaseEx".
 * - A **genuine ctor failure** is surfaced as a [Result.failure] with the real cause attached, so
 *   a permanent problem is diagnosable from the tool response instead of being hidden in idea.log
 *   at WARN.
 * - A **non-null wrong-type** browser (or `null`) is a permanent mismatch: a descriptive
 *   [Result.failure] naming the actual type.
 */
internal fun classifyBrowserConstruction(invokeResult: Result<Any?>): Result<HierarchyBrowserBaseEx> =
    invokeResult.fold(
        onSuccess = { raw ->
            if (raw is HierarchyBrowserBaseEx) {
                Result.success(raw)
            } else {
                Result.failure(
                    IllegalStateException(
                        "createHierarchyBrowser returned ${raw?.javaClass?.name ?: "null"}, not HierarchyBrowserBaseEx"
                    )
                )
            }
        },
        onFailure = { t ->
            rethrowIfCancellation(t) // transient cold-start cancellation -> escape for the readAction retry
            val cause = (t as? InvocationTargetException)?.targetException ?: t
            Result.failure(
                IllegalStateException("createHierarchyBrowser threw ${cause.javaClass.simpleName}: ${cause.message}", cause)
            )
        }
    )

/**
 * Resolves the "logical element" represented by a [HierarchyNodeDescriptor].
 * This abstraction is needed because `HierarchyNodeDescriptor.psiElement` may
 * point at the call site (e.g. a `PsiReferenceExpression`) rather than the
 * containing method — the IDE's per-language browsers expose
 * `getElementFromDescriptor(descriptor)` for this. See [BrowserBackedResolver].
 */
internal interface LogicalElementResolver {
    fun resolve(descriptor: HierarchyNodeDescriptor): PsiElement?
}

/** Walker output: the populated descriptor tree plus a resolver to extract logical elements. */
internal class HierarchyWalkResult(
    val root: HierarchyNodeDescriptor,
    val resolver: LogicalElementResolver
)

/**
 * [LogicalElementResolver] used for the IDE-driven path. Resolution order:
 *
 * 1. `descriptor.getEnclosingElement()` — the IDE's own notion of the
 *    "logical owner" of a hierarchy node (e.g. Java/Rust/JS call-hierarchy
 *    descriptors expose this). Returns the enclosing method/class regardless
 *    of whether the descriptor's `psiElement` points at a call-site reference.
 *
 * 2. Browser's `protected getElementFromDescriptor(descriptor)` — fallback for
 *    descriptors that don't expose getEnclosingElement directly (e.g. Java's
 *    type-hierarchy descriptor uses `getPsiClass()` which the browser routes
 *    to). Each language's browser knows how to extract the logical element
 *    from its own descriptor type.
 *
 * 3. `descriptor.psiElement` — last-resort fallback.
 *
 * Rationale: Rust's `RsCallHierarchyBrowser.getElementFromDescriptor()` returns
 * `descriptor.psiElement` (the call-site reference), while Java's returns
 * `descriptor.getEnclosingElement()` (the calling method). Preferring
 * `getEnclosingElement` directly normalises this — Rust callers now point at
 * the calling fn, matching Java/Kotlin/Python/PHP/Go semantics.
 */
internal class BrowserBackedResolver(private val browser: HierarchyBrowserBaseEx) : LogicalElementResolver {
    private val getElementMethod: java.lang.reflect.Method? = run {
        var c: Class<*>? = browser.javaClass
        while (c != null) {
            try {
                return@run c.getDeclaredMethod("getElementFromDescriptor", HierarchyNodeDescriptor::class.java)
                    .apply { isAccessible = true }
            } catch (_: NoSuchMethodException) {
                c = c.superclass
            }
        }
        null
    }

    override fun resolve(descriptor: HierarchyNodeDescriptor): PsiElement? {
        // Prefer descriptor.getEnclosingElement() — uniform "logical owner" across languages.
        val enclosing = runCatching {
            descriptor.javaClass.getMethod("getEnclosingElement").invoke(descriptor) as? PsiElement
        }.getOrNull()
        if (enclosing != null) return enclosing

        // Fallback: ask the browser.
        val method = getElementMethod ?: return descriptor.psiElement
        return runCatching { method.invoke(browser, descriptor) as? PsiElement }
            .getOrNull() ?: descriptor.psiElement
    }
}

/** Resolver that just reads `descriptor.psiElement` — used by the Rust fallback which builds synthetic descriptors with the right element. */
internal object IdentityElementResolver : LogicalElementResolver {
    override fun resolve(descriptor: HierarchyNodeDescriptor): PsiElement? = descriptor.psiElement
}

/**
 * Generic hierarchy-tree walker that dispatches via the IDE's
 * `LanguageCallHierarchy` / `LanguageTypeHierarchy` extension points,
 * uses `provider.getTarget()` for language-specific pre-coercion (e.g.
 * Kotlin K1 light-class conversion), constructs the language's
 * `HierarchyBrowserBaseEx` headlessly on EDT, and reflectively invokes
 * the `protected createHierarchyTreeStructure(typeName, element)` to
 * obtain a walkable `HierarchyTreeStructure`. The walk is depth-limited
 * with cycle dedupe via PSI element identity. Type strings are sourced
 * from the localized `CallHierarchyBrowserBase.getCallerType()` etc. —
 * NEVER `getTypeHierarchyType()` (combined view) since multiple languages
 * either return null or call EDT-only modal-window analysis for it.
 */
internal object HierarchyTreeWalker {

    private val LOG = logger<HierarchyTreeWalker>()

    /**
     * Walks the IDE's hierarchy tree for [element] in the [kind] direction.
     * Returns the root [HierarchyNodeDescriptor] with all children populated
     * via [HierarchyNodeDescriptor.setCachedChildren] up to [maxDepth].
     *
     * MUST be called from a read action.
     */
    @RequiresReadLock
    fun walk(
        project: Project,
        element: PsiElement,
        kind: HierarchyKind,
        scope: HierarchyScope,
        maxDepth: Int
    ): Result<HierarchyWalkResult> {
        // Pin the whole walk to the IDE GUI's client session (GH #17). The platform
        // hierarchy browser ctor (reached via createBrowserHeadless) force-inits the
        // `HierarchyBrowserManager` project service, which is registered client="all"
        // (one instance PER client session) and whose ctor registers the global
        // "Hierarchy" tool window. Our MCP server runs on a background thread with no
        // ClientId, so `getService` resolves to the LOCAL session and creates a SECOND
        // instance; in serverMode / remote-dev (Gateway) the GUI's interactive hierarchy
        // runs under a remote (CONTROLLER) client session, so the two collide ->
        // "Conflicting component name 'HierarchyBrowserManager'" + "window with
        // id=\"Hierarchy\" is already registered" -> getInstance() returns null -> the
        // interactive Hierarchy tool window NPEs on update and stops appearing. Running
        // under the connected remote session makes us reuse the GUI's single instance.
        // No remote client (plain local IDE / pure-headless agent use) -> localId, where
        // there is only one session, so this is a no-op.
        //
        // Flatten: walkInner returns Result<...>; runCatching wraps any unexpected
        // throw as Result.failure; combine so callers always see a single Result.
        val result = ClientId.withExplicitClientId(guiClientId(project)) {
            runCatching { walkInner(project, element, kind, scope, maxDepth) }
                .getOrElse { Result.failure(it) }
        }
        // Never swallow a read-action cancellation — rethrow it so the enclosing
        // readAction{} can perform its write-pending restart. Covers both a thrown
        // CannotReadException and one surfaced via Result.failure (e.g. Rust fallback).
        result.exceptionOrNull()?.let(::rethrowIfCancellation)
        return result
    }

    /**
     * The ClientId whose session our hierarchy work should run under so it shares the IDE
     * GUI's single `HierarchyBrowserManager` instance instead of creating a second one in
     * the LOCAL session (see [walk]). In remote-dev / serverMode the connected thin client
     * is a remote (non-local) project session — pin to it. With no remote client connected
     * (plain local IDE or pure-headless agent use) there is only one session and nothing to
     * collide with, so fall back to the local id. Best-effort: any failure falls back to local.
     */
    private fun guiClientId(project: Project): ClientId =
        runCatching {
            val local = ClientId.localId
            ClientSessionsManager.getProjectSessions(project, ClientKind.ALL)
                .firstOrNull { session -> session.clientId != local }
                ?.clientId
        }.getOrNull() ?: ClientId.localId

    private fun walkInner(
        project: Project,
        element: PsiElement,
        kind: HierarchyKind,
        scope: HierarchyScope,
        maxDepth: Int
    ): Result<HierarchyWalkResult> {
        val language = element.language
        val provider = when {
            kind.isCall -> LanguageCallHierarchy.INSTANCE.forLanguage(language)
            else -> LanguageTypeHierarchy.INSTANCE.forLanguage(language)
        }
        if (provider == null) {
            // Strategy II fallback: Rust type hierarchy has no IDE provider.
            if (kind.isType && language.id.equals("Rust", ignoreCase = true)) {
                return runCatching { RustTypeHierarchyFallback.walk(project, element, kind, scope, maxDepth) }
                    .getOrElse { Result.failure(it) }
            }
            return Result.failure(
                IllegalStateException(
                    "No ${if (kind.isCall) "call" else "type"} hierarchy provider for language: ${language.id}"
                )
            )
        }

        // Walk up the leaf to the natural target type FIRST (each language's
        // provider.getTarget walks up only when an Editor is in the DataContext;
        // we're headless, so we have to do it ourselves). This avoids Class
        // Cast failures inside provider.createHierarchyBrowser when it tries
        // (PsiClass)leafToken etc.
        val coercedElement = if (kind.isCall) {
            ClassLikePsi.walkUpToMethodLike(element) ?: element
        } else {
            ClassLikePsi.walkUpToClassLike(element) ?: element
        }

        val target = resolveTarget(provider, project, coercedElement)
            ?: return Result.failure(IllegalStateException("Provider rejected element for $kind"))

        // createBrowserHeadless rethrows a cold-start read cancellation (caught by walk()'s
        // runCatching and re-rethrown there for the readAction retry); a genuine failure is
        // surfaced here with its real cause attached (#30).
        val browser = createBrowserHeadless(provider, target)
            .getOrElse { return Result.failure(it) }

        val typeName = typeStringFor(kind)

        // Per-language tree structures read scope-type via `browser.getCurrentScopeType()`,
        // which itself reads `myCurrentSheet.get().myScope`. A freshly-constructed browser
        // has no current sheet, so the scope would default to SCOPE_ALL. Reflectively poke
        // the sheet for our `typeName` to install our chosen scope before invoking
        // createHierarchyTreeStructure.
        applyBrowserScope(browser, typeName, scope.ideScopeType)

        val structure = invokeCreateHierarchyTreeStructure(browser, typeName, target)
            ?: return Result.failure(IllegalStateException("Browser refused element ${element.text} for $kind"))

        runCatching { structure.baseDescriptor.update() }.onFailure(::rethrowIfCancellation)
        walkRecursive(structure, structure.baseDescriptor, maxDepth, mutableSetOf())
        return Result.success(HierarchyWalkResult(structure.baseDescriptor, BrowserBackedResolver(browser)))
    }

    private fun resolveTarget(provider: Any, project: Project, element: PsiElement): PsiElement? {
        // Build a synthetic DataContext with PSI_ELEMENT + PROJECT, then call
        // provider.getTarget(ctx). This delegates per-language pre-coercion (e.g.
        // walking up to the enclosing function, light-class conversion in Kotlin K1)
        // to the IDE's own logic. Falls back to the raw element if getTarget returns
        // null (rare, but defensive).
        val ctx = SimpleDataContext.builder()
            .add(CommonDataKeys.PROJECT, project)
            .add(CommonDataKeys.PSI_ELEMENT, element)
            .build()
        // HierarchyProvider.getTarget(DataContext): PsiElement?
        val getTarget = runCatching {
            provider.javaClass.getMethod("getTarget", com.intellij.openapi.actionSystem.DataContext::class.java)
        }.getOrNull() ?: return element
        val coerced = runCatching { getTarget.invoke(provider, ctx) as? PsiElement }.getOrNull()
        return coerced ?: element
    }

    private fun createBrowserHeadless(provider: Any, target: PsiElement): Result<HierarchyBrowserBaseEx> {
        // HierarchyProvider.createHierarchyBrowser(PsiElement): HierarchyBrowser
        //
        // Called from inside a read action. The IDE's deadlock-prevention guard rejects
        // `invokeAndWait` from a read action, so we cannot switch to EDT here. Instead
        // we construct the browser on the calling thread. This works in practice because
        // (a) the per-language browser ctors just call super(project, element); (b) the
        // platform `HierarchyBrowserBaseEx` ctor allocates Swing components but does not
        // display them — Swing tolerates off-EDT construction of unmounted JComponents.
        // The reflective `createHierarchyTreeStructure` call later is read-action-safe.
        //
        // [classifyBrowserConstruction] rethrows a cold-start read cancellation (so the
        // readAction{} retries — #30) and surfaces a genuine failure's real cause.
        val createBrowser = runCatching {
            provider.javaClass.getMethod("createHierarchyBrowser", PsiElement::class.java)
        }.getOrElse {
            return Result.failure(
                IllegalStateException("createHierarchyBrowser method not found on ${provider.javaClass.name}", it)
            )
        }
        return classifyBrowserConstruction(runCatching { createBrowser.invoke(provider, target) })
    }

    /**
     * Reflectively configures the browser's "current sheet" with the requested
     * scope type-string so per-language tree structures read it via
     * [HierarchyBrowserBaseEx.getCurrentScopeType] when their constructor runs.
     *
     * Best-effort: silently no-ops if the IDE's private field shape changes.
     * The fallback is the browser's default scope (SCOPE_ALL).
     */
    private fun applyBrowserScope(
        browser: HierarchyBrowserBaseEx,
        typeName: String,
        scopeStr: String
    ) {
        runCatching {
            val baseClass = generateSequence(browser.javaClass as Class<*>) { it.superclass }
                .firstOrNull { it.simpleName == "HierarchyBrowserBaseEx" } ?: return
            val sheetMapField = baseClass.getDeclaredField("myType2Sheet").apply { isAccessible = true }
            @Suppress("UNCHECKED_CAST")
            val sheets = sheetMapField.get(browser) as? Map<String, Any> ?: return
            val sheet = sheets[typeName] ?: return
            // (1) Base browsers (Java/Kotlin/Python/PHP/JS/TS) read scope from the sheet:
            //     HierarchyBrowserBaseEx.getCurrentScopeType() = myType2Sheet[currentViewType].myScope.
            sheet.javaClass.getDeclaredField("myScope").apply { isAccessible = true }.set(sheet, scopeStr)
            // (2) getCurrentViewType() = myCurrentSheet.get().myType — install our sheet as current so
            //     the view type is non-null (both base and overriding browsers gate scope on it).
            val currentSheetField = baseClass.getDeclaredField("myCurrentSheet").apply { isAccessible = true }
            @Suppress("UNCHECKED_CAST")
            val currentSheetRef = currentSheetField.get(browser) as? java.util.concurrent.atomic.AtomicReference<Any>
            currentSheetRef?.set(sheet)
            // (3) Some language browsers (e.g. Go's GoCallHierarchyBrowser) OVERRIDE
            //     getCurrentScopeType() to read their OWN `myScope` field on the browser rather than
            //     the sheet's. Without setting it the persisted scope masks our value and scope
            //     filtering silently no-ops. No-op for browsers that don't declare such a field.
            var browserClass: Class<*>? = browser.javaClass
            while (browserClass != null && browserClass.simpleName != "HierarchyBrowserBaseEx") {
                val ownScopeField = runCatching { browserClass.getDeclaredField("myScope") }.getOrNull()
                if (ownScopeField != null) {
                    ownScopeField.isAccessible = true
                    ownScopeField.set(browser, scopeStr)
                    break
                }
                browserClass = browserClass.superclass
            }
        }.onFailure { LOG.warn("Failed to set hierarchy browser scope reflectively (typeName=$typeName, scope=$scopeStr)", it) }
    }

    private fun typeStringFor(kind: HierarchyKind): String = when (kind) {
        HierarchyKind.CALLERS -> CallHierarchyBrowserBase.getCallerType()
        HierarchyKind.CALLEES -> CallHierarchyBrowserBase.getCalleeType()
        HierarchyKind.SUPERTYPES -> TypeHierarchyBrowserBase.getSupertypesHierarchyType()
        HierarchyKind.SUBTYPES -> TypeHierarchyBrowserBase.getSubtypesHierarchyType()
    }

    private fun invokeCreateHierarchyTreeStructure(
        browser: HierarchyBrowserBaseEx,
        typeName: String,
        element: PsiElement
    ): HierarchyTreeStructure? {
        val method = findCreateMethod(browser.javaClass) ?: run {
            LOG.warn("createHierarchyTreeStructure(String, PsiElement) not found on ${browser.javaClass.name}")
            return null
        }
        method.isAccessible = true
        return runCatching { method.invoke(browser, typeName, element) as? HierarchyTreeStructure }
            .onFailure(::rethrowIfCancellation)
            .onFailure { LOG.warn("createHierarchyTreeStructure invocation failed", it) }
            .getOrNull()
    }

    private fun findCreateMethod(clazz: Class<*>): Method? {
        var c: Class<*>? = clazz
        while (c != null) {
            try {
                return c.getDeclaredMethod(
                    "createHierarchyTreeStructure",
                    String::class.java,
                    PsiElement::class.java
                )
            } catch (_: NoSuchMethodException) {
                c = c.superclass
            }
        }
        return null
    }

    private fun walkRecursive(
        structure: HierarchyTreeStructure,
        node: HierarchyNodeDescriptor,
        depthLeft: Int,
        visited: MutableSet<PsiElement>
    ) {
        if (depthLeft <= 0) {
            node.cachedChildren = emptyArray()
            return
        }
        val psi = node.psiElement
        if (psi != null) {
            if (psi in visited) {
                node.cachedChildren = emptyArray()
                return
            }
            visited.add(psi)
        }
        val descriptorChildren = runCatching { structure.getChildElements(node) }
            .onFailure(::rethrowIfCancellation)
            .getOrDefault(emptyArray<Any>())
            .filterIsInstance<HierarchyNodeDescriptor>()
        node.cachedChildren = descriptorChildren.toTypedArray<Any>()
        for (child in descriptorChildren) {
            // Trigger the descriptor's presentation update so getHighlightedText()
            // is populated — the IDE normally does this in the UI tree renderer.
            runCatching { child.update() }.onFailure(::rethrowIfCancellation)
            walkRecursive(structure, child, depthLeft - 1, visited)
        }
    }
}
