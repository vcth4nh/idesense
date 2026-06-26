package com.github.vcth4nh.idesense.handlers.python

import com.github.vcth4nh.idesense.handlers.LanguageServices
import com.github.vcth4nh.idesense.handlers.MethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodData
import com.github.vcth4nh.idesense.handlers.SuperMethodsData
import com.github.vcth4nh.idesense.handlers.SuperMethodsProvider
import com.github.vcth4nh.idesense.util.ProjectUtils
import com.github.vcth4nh.idesense.util.QualifiedNameUtil
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil

/**
 * Python super-methods provider. Delegates to
 * `com.jetbrains.python.psi.search.PySuperMethodsSearch.search(...)` — the
 * data layer the IDE's `PyLineMarkerProvider` uses for the `I↑` gutter icon.
 *
 * `deepSearch=true` walks the full C3 MRO chain; `@property` getter/setter
 * direction handled by the search's executor.
 */
class PythonSuperMethodsProvider : SuperMethodsProvider {

    companion object {
        private val LOG = logger<PythonSuperMethodsProvider>()
    }

    private val pyFunctionClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.python.psi.PyFunction") } catch (_: ClassNotFoundException) { null }
    }

    private val pyClassClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.python.psi.PyClass") } catch (_: ClassNotFoundException) { null }
    }

    private val pySuperMethodsSearchClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.python.psi.search.PySuperMethodsSearch") } catch (_: ClassNotFoundException) { null }
    }

    private val typeEvalContextClass: Class<*>? by lazy {
        try { Class.forName("com.jetbrains.python.psi.types.TypeEvalContext") } catch (_: ClassNotFoundException) { null }
    }

    private val searchMethod: java.lang.reflect.Method? by lazy {
        try {
            val py = pyFunctionClass ?: return@lazy null
            val tec = typeEvalContextClass ?: return@lazy null
            pySuperMethodsSearchClass?.getMethod("search", py, java.lang.Boolean.TYPE, tec)
        } catch (_: Throwable) { null }
    }

    private val userInitiatedFactory: java.lang.reflect.Method? by lazy {
        try {
            typeEvalContextClass?.getMethod("userInitiated", Project::class.java, PsiFile::class.java)
        } catch (_: Throwable) { null }
    }

    private val getSuperClassesMethod: java.lang.reflect.Method? by lazy {
        try {
            val pyc = pyClassClass ?: return@lazy null
            val tec = typeEvalContextClass ?: return@lazy null
            pyc.getMethod("getSuperClasses", tec)
        } catch (_: Throwable) { null }
    }

    override fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        // Member path: try PyFunction first (unchanged).
        val pyFunction = findContainingPyFunction(element)
        if (pyFunction != null) {
            val file = pyFunction.containingFile?.virtualFile
            val methodData = MethodData(
                name = getName(pyFunction) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(pyFunction),
                kind = LanguageServices.getKind(pyFunction),
                file = file?.let { getRelativePath(project, it) } ?: "unknown",
                line = getLineNumber(project, pyFunction) ?: 0,
                column = getColumnNumber(project, pyFunction) ?: 0,
            )
            return SuperMethodsData(method = methodData, hierarchy = buildHierarchy(project, pyFunction))
        }

        // Class anchor path: walk up to nearest PyClass and return direct base classes.
        val pyClass = findContainingPyClass(element) ?: return null
        val file = pyClass.containingFile?.virtualFile
        val classData = MethodData(
            name = getName(pyClass) ?: "unknown",
            qualifiedName = QualifiedNameUtil.getQualifiedName(pyClass),
            kind = LanguageServices.getKind(pyClass),
            file = file?.let { getRelativePath(project, it) } ?: "unknown",
            line = getLineNumber(project, pyClass) ?: 0,
            column = getColumnNumber(project, pyClass) ?: 0,
        )
        return SuperMethodsData(method = classData, hierarchy = buildClassHierarchy(project, pyClass))
    }

    private fun buildHierarchy(project: Project, pyFunction: PsiElement): List<SuperMethodData> {
        val search = searchMethod ?: return emptyList()
        val ctx = createUserInitiatedContext(project, pyFunction.containingFile) ?: return emptyList()

        val query = try {
            search.invoke(null, pyFunction, true, ctx)
        } catch (t: Throwable) {
            LOG.debug("PySuperMethodsSearch.search invocation failed", t)
            return emptyList()
        }

        val findAllMethod = runCatching { query.javaClass.getMethod("findAll") }.getOrNull()
            ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val results = try {
            findAllMethod.invoke(query) as? Collection<PsiElement> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("Query.findAll invocation failed", t)
            return emptyList()
        }

        val visited = mutableSetOf<String>()
        val out = mutableListOf<SuperMethodData>()
        for (superMethod in results) {
            val key = QualifiedNameUtil.getQualifiedName(superMethod)
                ?: "${superMethod.javaClass.simpleName}@${System.identityHashCode(superMethod)}"
            if (!visited.add(key)) continue
            val file = superMethod.containingFile?.virtualFile
            out.add(SuperMethodData(
                name = getName(superMethod) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(superMethod),
                kind = LanguageServices.getKind(superMethod),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, superMethod),
                column = getColumnNumber(project, superMethod),
            ))
        }
        return out
    }

    private fun findContainingPyFunction(element: PsiElement): PsiElement? {
        val pyFunc = pyFunctionClass ?: return null
        if (pyFunc.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, pyFunc as Class<out PsiElement>)
    }

    private fun findContainingPyClass(element: PsiElement): PsiElement? {
        val pyc = pyClassClass ?: return null
        if (pyc.isInstance(element)) return element
        @Suppress("UNCHECKED_CAST")
        return PsiTreeUtil.getParentOfType(element, pyc as Class<out PsiElement>)
    }

    private fun buildClassHierarchy(project: Project, pyClass: PsiElement): List<SuperMethodData> {
        val method = getSuperClassesMethod ?: return emptyList()
        val ctx = createUserInitiatedContext(project, pyClass.containingFile) ?: return emptyList()

        @Suppress("UNCHECKED_CAST")
        val superClasses: Array<PsiElement> = try {
            method.invoke(pyClass, ctx) as? Array<PsiElement> ?: return emptyList()
        } catch (t: Throwable) {
            LOG.debug("PyClass.getSuperClasses invocation failed", t)
            return emptyList()
        }

        val out = mutableListOf<SuperMethodData>()
        for (base in superClasses) {
            val file = base.containingFile?.virtualFile
            out.add(SuperMethodData(
                name = getName(base) ?: "unknown",
                qualifiedName = QualifiedNameUtil.getQualifiedName(base),
                kind = LanguageServices.getKind(base),
                file = file?.let { getRelativePath(project, it) },
                line = getLineNumber(project, base),
                column = getColumnNumber(project, base),
            ))
        }
        return out
    }

    private fun getName(element: PsiElement): String? = runCatching {
        element.javaClass.getMethod("getName").invoke(element) as? String
    }.getOrNull()

    private fun createUserInitiatedContext(project: Project, origin: PsiFile?): Any? {
        val factory = userInitiatedFactory ?: return null
        return try {
            factory.invoke(null, project, origin)
        } catch (t: Throwable) {
            LOG.debug("TypeEvalContext.userInitiated invocation failed", t)
            null
        }
    }

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
