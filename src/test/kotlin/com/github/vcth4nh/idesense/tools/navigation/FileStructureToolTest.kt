package com.github.vcth4nh.idesense.tools.navigation

import com.github.vcth4nh.idesense.server.models.ContentBlock
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiMethod
import com.intellij.psi.impl.FakePsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import java.nio.file.Files
import java.nio.file.Path
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The line of a node in the outline of ide_file_structure is the line of its navigation element:
 * the Structure window goes there (#197). An example is the node `default` of a JavaScript
 * `export default { ... }` object: its element is not physical, its text offset is 0, and its
 * navigation element is the first member of the object. [NavigatesTo] has the same form.
 */
class FileStructureToolTest : BasePlatformTestCase() {

    fun testLineIsTheLineOfTheNavigationElement() {
        val file = myFixture.configureByText("A.java", "class A {\n\n    void m() {}\n}\n")
        val m = PsiTreeUtil.findChildOfType(file, PsiMethod::class.java)!!

        assertEquals(3, FileStructureTool.lineOf(project, NavigatesTo(target = m, parent = m), file))
    }

    // For example a compiled class and its source: the line stays a line of the file of the outline.
    fun testLineStaysTheLineOfTheElementWhenTheNavigationElementIsInAnotherFile() {
        val other = myFixture.addFileToProject("B.java", "class B {\n\n\n\n    void n() {}\n}\n")
        val n = PsiTreeUtil.findChildOfType(other, PsiMethod::class.java)!!
        val file = myFixture.configureByText("A.java", "class A {\n    void m() {}\n}\n")
        val m = PsiTreeUtil.findChildOfType(file, PsiMethod::class.java)!!

        assertEquals(2, FileStructureTool.lineOf(project, NavigatesTo(target = n, parent = m, offset = m.textOffset), file))
    }

    // The Structure tool window hides the lambdas in its default state, so the default set of Java has
    // no `lambdas` (#341). The category stays: `show` can ask for it.
    fun testJavaLambdaIsNotInTheDefaultResult() {
        val text = structureOfLambdaClass(null)
        assertTrue("The method is missing in: $text", text.contains("run(): void"))
        assertFalse("A lambda node is in the default result: $text", text.contains("lambda$"))
    }

    fun testJavaLambdaIsInTheResultWhenShowNamesLambdas() {
        val text = structureOfLambdaClass(listOf("non_public", "fields", "lambdas"))
        assertTrue("No lambda node in: $text", text.contains("lambda$"))
    }

    private fun structureOfLambdaClass(show: List<String>?): String = runBlocking {
        // The tool resolves the path on the disk below the project base path.
        val path = Files.createDirectories(Path.of(project.basePath!!)).resolve("Lam.java")
        Files.writeString(path, "class Lam {\n    void run() {\n        Runnable r = () -> {};\n    }\n}\n")
        LocalFileSystem.getInstance().refreshAndFindFileByNioFile(path)!!
        val result = FileStructureTool().execute(project, buildJsonObject {
            put("file", "Lam.java")
            if (show != null) put("show", buildJsonArray { show.forEach { add(JsonPrimitive(it)) } })
        })
        val text = (result.content.first() as ContentBlock.Text).text
        assertFalse("The call must succeed: $text", result.isError)
        text
    }

    private class NavigatesTo(
        private val target: PsiElement,
        private val parent: PsiElement,
        private val offset: Int = 0,
    ) : FakePsiElement() {
        override fun getParent(): PsiElement = parent
        override fun getNavigationElement(): PsiElement = target
        override fun getTextOffset(): Int = offset
    }
}
