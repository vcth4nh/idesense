package com.github.vcth4nh.idesense.handlers.go

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.search.searches.DefinitionsScopedSearch
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.Processor

class GoSuperMethodsProvider : SuperMethodsProvider {

    private val goMethodDeclarationClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoMethodDeclaration") } catch (_: ClassNotFoundException) { null }
    }

    /**
     * GoSuperMethodSearch is NOT registered under DefinitionsScopedSearch EP — only
     * GoMethodInheritorsSearch and GoInheritorsSearch are (go-plugin/lib/go-plugin.jar plugin.xml).
     * We must call GoSuperMethodSearch.GO_SUPER_METHOD_SEARCH directly via reflection.
     *
     * GoGotoSuperHandler.showPopup(GoMethodDeclaration) uses:
     *   GoSuperMethodSearch.GO_SUPER_METHOD_SEARCH.processQuery(
     *       GoGotoUtil.param(goMethod), processor)
     *
     * GoGotoUtil.param(element) = new DefinitionsScopedSearch.SearchParameters(element)
     * Single-arg constructor sets checkDeep=true internally.
     */
    private val goSuperMethodSearch: Any? by lazy {
        try {
            val searchClass = Class.forName("com.goide.go.GoSuperMethodSearch")
            searchClass.getDeclaredField("GO_SUPER_METHOD_SEARCH").get(null)
        } catch (_: Exception) { null }
    }

    private val processQueryMethod: java.lang.reflect.Method? by lazy {
        try {
            goSuperMethodSearch?.javaClass?.getMethod("processQuery", Any::class.java, Processor::class.java)
        } catch (_: Exception) { null }
    }

    private val goTypeSpecClass: Class<*>? by lazy {
        try { Class.forName("com.goide.psi.GoTypeSpec") } catch (_: ClassNotFoundException) { null }
    }

    /**
     * Type anchor (caret on an interface/struct declaration). GoGotoSuperHandler.SUPER_SEARCH is the
     * GoSuperSearch instance behind BOTH Ctrl+U and the "implementing" gutter for types
     * (GoSuperMarkerProvider.hasSuperType calls the same field). It emits GoTypeSpec for every
     * interface the type structurally satisfies, transitively; embedded structs are never emitted.
     * Distinct from GO_SUPER_METHOD_SEARCH above, which is the method-anchor path.
     */
    private val goSuperTypeSearch: Any? by lazy {
        try {
            Class.forName("com.goide.go.GoGotoSuperHandler")
                .getDeclaredField("SUPER_SEARCH").get(null)
        } catch (_: Exception) { null }
    }

    private val processTypeQueryMethod: java.lang.reflect.Method? by lazy {
        try {
            goSuperTypeSearch?.javaClass?.getMethod("processQuery", Any::class.java, Processor::class.java)
        } catch (_: Exception) { null }
    }

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? =
        tryMethodAnchor(element, project) ?: tryTypeAnchor(element, project)

    /**
     * Method anchor: caret on a Go method declaration -> the interface method spec(s) it satisfies.
     * Uses GoSuperMethodSearch.GO_SUPER_METHOD_SEARCH (the GotoSuper method path).
     */
    private fun tryMethodAnchor(element: PsiElement, project: Project): SuperMethodsData? {
        val goMethodClass = goMethodDeclarationClass ?: return null
        val search = goSuperMethodSearch ?: return null
        val method = processQueryMethod ?: return null

        @Suppress("UNCHECKED_CAST")
        val goMethod = if (goMethodClass.isInstance(element)) element
        else PsiTreeUtil.getParentOfType(element, goMethodClass as Class<out PsiElement>)
            ?: return null

        // A resolved Go method that satisfies no interface is a valid result with an
        // empty hierarchy (mirrors Java/Kotlin/Python), not "no method found".
        val results = runSuperSearch(search, method, goMethod, project)
        val file = goMethod.containingFile?.virtualFile
        val methodData = MethodData(
            name = getName(goMethod) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(goMethod),
            kind = LanguageServices.getKind(goMethod),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, goMethod) ?: 0,
            column = getColumnNumber(project, goMethod) ?: 0,
        )
        return SuperMethodsData(method = methodData, hierarchy = results.map { toSuperMethodData(it, project) })
    }

    /**
     * Type anchor: caret on an interface/struct declaration -> the interfaces it structurally
     * satisfies (transitive; embedded structs excluded). Uses GoGotoSuperHandler.SUPER_SEARCH — the
     * GoSuperSearch instance behind both Ctrl+U and the "implementing" gutter for types.
     */
    private fun tryTypeAnchor(element: PsiElement, project: Project): SuperMethodsData? {
        val typeSpecClass = goTypeSpecClass ?: return null
        val search = goSuperTypeSearch ?: return null
        val method = processTypeQueryMethod ?: return null

        @Suppress("UNCHECKED_CAST")
        val goType = if (typeSpecClass.isInstance(element)) element
        else PsiTreeUtil.getParentOfType(element, typeSpecClass as Class<out PsiElement>)
            ?: return null

        val results = runSuperSearch(search, method, goType, project)
        val file = goType.containingFile?.virtualFile
        val typeData = MethodData(
            name = getName(goType) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(goType),
            kind = LanguageServices.getKind(goType),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, goType) ?: 0,
            column = getColumnNumber(project, goType) ?: 0,
        )
        return SuperMethodsData(method = typeData, hierarchy = results.map { toSuperMethodData(it, project) })
    }

    /**
     * Runs a Go super-search field's processQuery(SearchParameters, Processor) via reflection and
     * returns the deduped PsiElement results. The single-arg DefinitionsScopedSearch.SearchParameters
     * constructor sets checkDeep=true, matching GoGotoUtil.param() used by the IDE's GotoSuper.
     *
     * Dedup: when a type/method is reachable via multiple inheritance paths the same super
     * declaration fires through the processor more than once (e.g. an interface embedded along
     * several paths). Collapse on (qname or identityHashCode) + file:line, matching the sibling providers.
     */
    private fun runSuperSearch(
        search: Any,
        method: java.lang.reflect.Method,
        anchor: PsiElement,
        project: Project,
    ): List<PsiElement> {
        val params = DefinitionsScopedSearch.SearchParameters(anchor)
        val results = mutableListOf<PsiElement>()
        val visited = mutableSetOf<String>()
        val processor = Processor<Any> { result ->
            if (result is PsiElement) {
                val qname = QualifiedNameUtil.getQualifiedName(result)
                    ?: "${result.javaClass.simpleName}@${System.identityHashCode(result)}"
                val file = result.containingFile?.virtualFile?.let { getRelativePath(project, it) } ?: "?"
                val line = getLineNumber(project, result)?.toString() ?: "?"
                val key = "$qname@$file:$line"
                if (visited.add(key)) results.add(result)
            }
            true
        }
        runCatching { method.invoke(search, params, processor) }
        return results
    }

    private fun toSuperMethodData(resultElement: PsiElement, project: Project): SuperMethodData {
        val file = resultElement.containingFile?.virtualFile
        return SuperMethodData(
            name = getName(resultElement) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(resultElement),
            kind = LanguageServices.getKind(resultElement),
            file = file?.let { getRelativePath(project, it) },
            line = getLineNumber(project, resultElement),
            column = getColumnNumber(project, resultElement),
        )
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
