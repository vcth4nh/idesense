package com.github.vcth4nh.idesense.util

import com.intellij.codeInsight.navigation.actions.GotoDeclarationHandler
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.OrderEnumerator
import com.intellij.openapi.util.SystemInfo
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.toNioPathOrNull
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiFileSystemItem
import com.intellij.psi.PsiManager
import com.intellij.psi.PsiNameIdentifierOwner
import com.intellij.psi.PsiNamedElement
import com.intellij.psi.PsiReference
import java.nio.file.InvalidPathException
import java.nio.file.Path

object PsiUtils {

    private val LOG = logger<PsiUtils>()

    /**
     * Default depth for searching parent chain for references.
     * 3 levels covers common cases: identifier -> expression -> call expression.
     */
    private const val DEFAULT_PARENT_SEARCH_DEPTH = 3

    /**
     * Resolves the target element from a position, mirroring what the IDE's Ctrl+Click does
     * (see `GotoDeclarationAction.findTargetElementsNoVS`).
     *
     * Order of attempts:
     * 1. Iterate `GotoDeclarationHandler.EP_NAME.extensionList`. Languages register handlers
     *    here for special navigation rules (e.g. constructor calls → class declaration in
     *    Java, or `int(x)` → `int.__new__` in Python). Use the first non-empty result.
     * 2. Fall back to [resolveReferenceTarget] — pure reference-system resolution.
     *
     * Use this for `find_definition` (Ctrl+Click semantics). For `find_usages` use
     * [resolveReferenceTarget] instead, so the search anchor is the user-intuitive entity
     * rather than the navigation target (which can differ per language).
     *
     * @param element The leaf PSI element at a position (from `psiFile.findElementAt(offset)`)
     * @return The resolved target element (declaration), or null if resolution fails
     */
    fun resolveTargetElement(element: PsiElement): PsiElement? {
        // 1. Ask each registered GotoDeclarationHandler — same EP the IDE's Ctrl+Click iterates.
        val gotoTarget = resolveViaGotoDeclarationHandler(element)
        if (gotoTarget != null) {
            val refined = PythonDefinitionResolver.refineResolvedTarget(element, gotoTarget)
            if (refined != null) return refined
        }

        // 2. Reference-system fallback (the chain `find_usages` uses directly).
        return resolveReferenceTarget(element)
    }

    /**
     * Resolves the target element from a position using reference-system semantics ONLY,
     * skipping the [GotoDeclarationHandler] step that [resolveTargetElement] tries first.
     *
     * Used by `find_usages` so the search anchor is the user-intuitive entity (the class for
     * `new Foo()`, the variable for `fn = int`, etc.) rather than the navigation target
     * (constructor / `__init__` / class declaration — different per language). This mirrors
     * the IDE's Find Usages action (Alt+F7), which uses different element-resolution flags
     * than Ctrl+Click — `TargetElementUtil.FIND_TARGET_FLAGS` does not invoke
     * `GotoDeclarationHandler` extensions.
     *
     * Order:
     * 1. `element.reference?.resolve()` — direct reference resolution.
     * 2. Walk the parent chain looking for a reference (some PSI structures put the reference
     *    on a parent rather than the leaf identifier).
     * 3. Python refinement with no resolved target (handles edge cases inside
     *    [PythonDefinitionResolver]).
     * 4. As a last resort, [findNamedElement] when the caret is actually on a declaration's
     *    name identifier. For comments/whitespace/literals, return null.
     *
     * Each attempt's result goes through [PythonDefinitionResolver.refineResolvedTarget].
     */
    fun resolveReferenceTarget(element: PsiElement): PsiElement? {
        // 1. Direct reference on the leaf.
        val reference = element.reference
        if (reference != null) {
            val resolved = reference.resolve()
            val refined = PythonDefinitionResolver.refineResolvedTarget(element, resolved)
            if (refined != null) return refined
        }

        // 2. Walk up parent chain looking for references.
        val parentReference = findReferenceInParent(element)
        if (parentReference != null) {
            val resolved = parentReference.resolve()
            val refined = PythonDefinitionResolver.refineResolvedTarget(element, resolved)
            if (refined != null) return refined
        }

        PythonDefinitionResolver.refineResolvedTarget(element, null)?.let { return it }

        // 3. Cursor-on-declaration-identifier fallback only — bug B.1 fix.
        if (!isOnDeclarationIdentifier(element)) return null
        return findNamedElement(element)
    }

    /**
     * Iterates `GotoDeclarationHandler.EP_NAME.extensionList` and returns the first non-empty
     * target list's first element. Returns null if no handler claims the element. Handler
     * exceptions are logged at debug and treated as "no result" so a single misbehaving plugin
     * doesn't block the whole resolution chain.
     *
     * Editor is passed as null — most handlers tolerate this for headless usage.
     */
    private fun resolveViaGotoDeclarationHandler(element: PsiElement): PsiElement? {
        val offset = element.textOffset
        for (handler in GotoDeclarationHandler.EP_NAME.extensionList) {
            val targets = try {
                handler.getGotoDeclarationTargets(element, offset, null)
            } catch (_: Throwable) {
                LOG.debug("GotoDeclarationHandler ${handler.javaClass.simpleName} threw; skipping")
                continue
            }
            if (!targets.isNullOrEmpty()) {
                return targets.first()
            }
        }
        return null
    }

    /**
     * Searches up the parent chain for a reference.
     *
     * Some PSI structures place the reference on a parent element rather than
     * the leaf identifier. This walks up a few levels to find it.
     *
     * @param element Starting element
     * @param maxDepth Maximum parent levels to check (default: [DEFAULT_PARENT_SEARCH_DEPTH])
     * @return The first reference found, or null
     * @see resolveTargetElement
     */
    fun findReferenceInParent(element: PsiElement, maxDepth: Int = DEFAULT_PARENT_SEARCH_DEPTH): PsiReference? {
        var current: PsiElement? = element
        repeat(maxDepth) {
            current = current?.parent ?: return null
            current?.reference?.let { return it }
        }
        return null
    }

    /**
     * Returns true if [element] is the name identifier token of its parent declaration.
     *
     * Used as a precondition for "cursor-on-declaration" fallbacks. When false, callers
     * should NOT walk up the PSI tree to find an enclosing named ancestor — the caret
     * is on a comment, whitespace, literal, or unrelated token.
     *
     * This is the canonical IntelliJ platform pattern: every language's declaration PSI
     * type implements [PsiNameIdentifierOwner] (PsiMethod, PsiClass, KtNamedFunction,
     * KtClassOrObject, PyFunction, RsFunction, etc.) and exposes
     * [PsiNameIdentifierOwner.getNameIdentifier] as its name token.
     */
    fun isOnDeclarationIdentifier(element: PsiElement): Boolean {
        var current: PsiElement? = element.parent
        while (current != null && current !is PsiFile) {
            if (current is PsiNameIdentifierOwner && current.nameIdentifier === element) return true
            if (current is PsiNamedElement && current.name == element.text) return true
            current = current.parent
        }
        return false
    }

    fun getVirtualFile(project: Project, relativePath: String): VirtualFile? {
        val basePath = project.basePath ?: return null
        return resolveLocalFile(relativePath, sequenceOf(basePath))
    }

    fun resolveVirtualFileAnywhere(project: Project, path: String): VirtualFile? {
        // On Windows, \ is a path separator (and is forbidden in filenames), so normalizing is
        // always safe and necessary. On POSIX, \ is a valid filename character and must not be
        // treated as a separator.
        val normalizedPath = if (SystemInfo.isWindows) path.replace('\\', '/') else path
        val virtualFileManager = VirtualFileManager.getInstance()

        // Handle already-formatted jar:// URLs
        if (normalizedPath.startsWith("jar://")) {
            val jarPath = normalizedPath.removePrefix("jar://").substringBefore("!/")
            val projectLibraryJars = project.getProjectLibraryJars()
            if (projectLibraryJars.none { isPathPrefixOf(it, jarPath) }) return null
            return virtualFileManager.findFileByUrl(normalizedPath)
        }

        // Handle jar path format: /path/to/file.jar!/internal/path
        if (normalizedPath.contains(".jar!/")) {
            val parts = normalizedPath.split("!/", limit = 2)
            if (parts.size == 2) {
                val jarPath = parts[0]
                val internalPath = parts[1]

                val homeExpandedJarPath = expandHome(jarPath)
                val absoluteJarPath = resolveAbsolutePathString(homeExpandedJarPath, listOfNotNull(project.basePath).asSequence())
                    ?: homeExpandedJarPath

                val projectLibraryJars = project.getProjectLibraryJars()

                if (projectLibraryJars.none { isPathPrefixOf(it, absoluteJarPath) }) {
                    return null
                }
                
                // Construct the jar URL: jar://absolute/path/to/file.jar!/internal/path
                val jarUrl = "jar://$absoluteJarPath!/$internalPath"
                val findFileByUrl = virtualFileManager.findFileByUrl(jarUrl)
                return findFileByUrl
            }
        }

        return getVirtualFile(project, normalizedPath)
    }

    fun resolveNavigableVirtualFile(project: Project, path: String): VirtualFile? {
        // Match resolveVirtualFileAnywhere() semantics for path normalization.
        val normalizedPath = if (SystemInfo.isWindows) path.replace('\\', '/') else path
        val virtualFileManager = VirtualFileManager.getInstance()
        val rootCandidates = sequence {
            project.basePath?.let { yield(it) }
            for (root in ProjectUtils.getModuleContentRoots(project)) {
                yield(root)
            }
        }

        val resolved = when {
            normalizedPath.startsWith("jar://") -> virtualFileManager.findFileByUrl(normalizedPath)
            normalizedPath.contains(".jar!/") -> {
                val parts = normalizedPath.split("!/", limit = 2)
                if (parts.size != 2) {
                    null
                } else {
                    val jarPath = parts[0]
                    val internalPath = parts[1]
                    val homeExpandedJarPath = expandHome(jarPath)
                    val absoluteJarPath = resolveAbsolutePathString(homeExpandedJarPath, rootCandidates)
                        ?: homeExpandedJarPath
                    virtualFileManager.findFileByUrl("jar://$absoluteJarPath!/$internalPath")
                }
            }
            else -> resolveLocalFile(normalizedPath, rootCandidates)
        } ?: return null

        return resolved.takeIf { ProjectUtils.isAccessibleFile(project, it) }
    }

    fun resolveLocalFile(path: String, rootCandidates: Sequence<String>): VirtualFile? {
        val expandedPath = expandHome(path)
        // resolveAbsolutePath handles both absolute paths and relative paths against each root candidate.
        val absolutePath = resolveAbsolutePath(expandedPath, rootCandidates) ?: return null
        return LocalFileSystem.getInstance().findFileByNioFile(absolutePath)
    }

    fun resolveAbsolutePath(path: String, rootCandidates: Sequence<String> = emptySequence()): Path? {
        val candidate = toPathOrNull(path) ?: return null
        if (candidate.isAbsolute) return candidate.normalize()

        for (root in rootCandidates) {
            val resolved = resolveAgainstRoot(path, root)
            if (resolved != null) return resolved
        }
        return null
    }

    fun resolveAbsolutePathString(path: String, rootCandidates: Sequence<String> = emptySequence()): String? =
        resolveAbsolutePath(path, rootCandidates)?.toString()?.replace('\\', '/')

    private fun resolveAgainstRoot(path: String, root: String?): Path? {
        val rootPath = toPathOrNull(root) ?: return null
        val relativePath = toPathOrNull(path) ?: return null
        return rootPath.resolve(relativePath).normalize()
    }

    private fun toPathOrNull(path: String?): Path? {
        if (path.isNullOrBlank()) return null
        return try {
            Path.of(path)
        } catch (_: InvalidPathException) {
            null
        }
    }

    private fun expandHome(path: String): String {
        if (!path.startsWith("~")) return path
        val homeDir = System.getProperty("user.home") ?: return path
        return path.replaceFirst("~", homeDir)
    }

    fun getFileContent(project: Project, virtualFile: VirtualFile): String? {
        val psiFile = PsiManager.getInstance(project).findFile(virtualFile)
        val document = psiFile?.let { PsiDocumentManager.getInstance(project).getDocument(it) }
        return document?.text ?: runCatching { VfsUtil.loadText(virtualFile) }.getOrNull()
    }

    fun getFileContentByLines(
        project: Project,
        virtualFile: VirtualFile,
        startLine: Int,
        endLine: Int
    ): String? {
        val psiFile = PsiManager.getInstance(project).findFile(virtualFile)
        val document = psiFile?.let { PsiDocumentManager.getInstance(project).getDocument(it) }

        if (document != null) {
            val clampedStart = (startLine - 1).coerceAtLeast(0)
            val clampedEnd = (endLine - 1).coerceAtMost(document.lineCount - 1)
            if (clampedStart > clampedEnd) return ""
            val startOffset = document.getLineStartOffset(clampedStart)
            val endOffset = document.getLineEndOffset(clampedEnd)
            return document.getText(com.intellij.openapi.util.TextRange(startOffset, endOffset))
        }

        val text = runCatching { VfsUtil.loadText(virtualFile) }.getOrNull() ?: return null
        val lines = text.lines()
        val clampedStart = (startLine - 1).coerceAtLeast(0)
        val clampedEnd = (endLine - 1).coerceAtMost(lines.size - 1)
        if (clampedStart > clampedEnd) return ""
        return lines.subList(clampedStart, clampedEnd + 1).joinToString("\n")
    }

    /**
     * Returns the chain of named PSI ancestors enclosing [element], ordered from the
     * outermost (closest to file root) to the innermost (immediate named parent).
     * The [element] itself is never included, nor are anonymous (unnamed) nodes.
     */
    fun getEnclosingScope(element: PsiElement): List<String> {
        val ancestors = mutableListOf<String>()
        var current: PsiElement? = element.parent
        while (current != null && current !is PsiFile) {
            if (current is PsiNamedElement) {
                val name = current.name
                if (!name.isNullOrEmpty()) {
                    ancestors.add(name)
                }
            }
            current = current.parent
        }
        return ancestors.asReversed()
    }

    /**
     * Offset of [element]'s name identifier — the position the IDE's "Go to Declaration"
     * navigates to.
     *
     * Uses the name identifier's `textRange`, which resolves the decompiled-class mirror
     * the same way it does for source PSI. `element.textOffset` is deliberately avoided:
     * it returns -1 for some decompiled `.class` stubs (the compiled-PSI mirror can be
     * soft-collected between calls). Anonymous elements have no name identifier — they
     * are never hierarchy nodes, so the element's own range start is used.
     */
    fun identifierOffset(element: PsiElement): Int {
        val anchor = (element as? PsiNameIdentifierOwner)?.nameIdentifier ?: element
        return anchor.textRange?.startOffset ?: 0
    }

    fun findNamedElement(element: PsiElement): PsiNamedElement? {
        var current: PsiElement? = element
        while (current != null) {
            // Exclude PsiFile (too high-level; a file-level match would make callers act on the
            // whole file) and PsiFileSystemItem (parent chain continues past PsiFile to PsiDirectory,
            // which is a PsiNamedElement; returning it leaks the containing directory as
            // "Package directory: …" from find_definition — bug B.2).
            if (current is PsiNamedElement
                && current !is PsiFile
                && current !is PsiFileSystemItem
                && current.name != null) {
                return current
            }
            current = current.parent
        }
        return null
    }

    /**
     * Gets the navigation element for a PSI element, preferring source files over compiled files.
     *
     * This is crucial for library classes where we want to navigate to `.java` source files
     * instead of `.class` bytecode files when sources are available.
     *
     * **Why this matters:**
     * When you have a library with attached sources (e.g., via Maven or Gradle), IntelliJ
     * stores both the compiled `.class` files and the source `.java` files. By default,
     * PSI elements may point to the `.class` file, but `navigationElement` provides the
     * source file if available, which is much more useful for reading code.
     *
     * @param element The PSI element to get the navigation target for
     * @return The navigation element (preferably source), or the original element if no navigation target exists
     */
    fun getNavigationElement(element: PsiElement): PsiElement {
        return element.navigationElement ?: element
    }
}

/**
 * Checks whether [prefix] is a path prefix of [child], using NIO Path semantics.
 * On Windows, NIO Path comparison is case-insensitive, matching the OS file system behavior.
 */
private fun isPathPrefixOf(prefix: String, child: String): Boolean {
    return try {
        Path.of(child).startsWith(Path.of(prefix))
    } catch (_: InvalidPathException) {
        child.startsWith(prefix)
    }
}

private fun Project.getProjectLibraryJars(): List<String> = OrderEnumerator.orderEntries(this)
    .librariesOnly()
    .classes()
    .roots
    .mapNotNull { root ->
        root.toNioPathOrNull()?.toString()?.replace('\\', '/')
            ?: root.path.takeIf { it.contains("!/") }
                ?.substringBefore("!/")
                ?.replace('\\', '/')
                ?.let { p ->
                    // On Windows, JarFileSystem paths start with /C:/ — normalize to C:/
                    if (p.length >= 3 && p[0] == '/' && p[2] == ':') p.substring(1) else p
                }
    }
