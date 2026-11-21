package com.github.vcth4nh.idesense.handlers

import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.psi.PsiManager
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.testFramework.IndexingTestUtil
import com.intellij.testFramework.PsiTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import java.nio.file.Files
import java.nio.file.Path

class BuiltInSearchScopeResolverTest : BasePlatformTestCase() {

    fun testResolveGlobalScopeFiltersProductionAndTestRoots() {
        val prod = createSourceRoot("prod", isTestSource = false)
        val test = createSourceRoot("test", isTestSource = true)

        val prodFile = createProjectFile(prod, "sample/ProdOnly.kt", "class ProdOnly")
        val testFile = createProjectFile(test, "sample/TestOnly.kt", "class TestOnly")

        val productionScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, BuiltInSearchScope.PROJECT_PRODUCTION_FILES)
        val testScope = BuiltInSearchScopeResolver.resolveGlobalScope(project, BuiltInSearchScope.PROJECT_TEST_FILES)

        assertTrue(productionScope.contains(prodFile.virtualFile))
        assertFalse(productionScope.contains(testFile.virtualFile))
        assertFalse(testScope.contains(prodFile.virtualFile))
        assertTrue(testScope.contains(testFile.virtualFile))
    }

    fun testResolveSearchScopeReturnsGlobalScopeForBuiltInValues() {
        val prod = createSourceRoot("prod-search", isTestSource = false)
        val prodFile = createProjectFile(prod, "sample/Searchable.kt", "class Searchable")

        val scope = BuiltInSearchScopeResolver.resolveSearchScope(project, BuiltInSearchScope.PROJECT_FILES)

        assertTrue(scope is GlobalSearchScope)
        assertTrue((scope as GlobalSearchScope).contains(prodFile.virtualFile))
    }

    private fun createSourceRoot(name: String, isTestSource: Boolean): Path {
        val path = Path.of(project.basePath ?: error("Project base path is required")).resolve(name)
        Files.createDirectories(path)
        val virtualFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(path)
            ?: error("Failed to refresh $name source root")
        PsiTestUtil.addSourceRoot(module, virtualFile, isTestSource)
        return path
    }

    private fun createProjectFile(root: Path, relativePath: String, content: String) = run {
        val filePath = root.resolve(relativePath)
        Files.createDirectories(filePath.parent)
        Files.writeString(filePath, content)

        val virtualFile = LocalFileSystem.getInstance().refreshAndFindFileByNioFile(filePath)
            ?: error("Failed to refresh $relativePath")
        IndexingTestUtil.waitUntilIndexesAreReady(project)
        PsiManager.getInstance(project).findFile(virtualFile)
            ?: error("Failed to create PSI for $relativePath")
    }
}
