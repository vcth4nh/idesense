package com.github.vcth4nh.idesense.tools.navigation.structure

import com.github.vcth4nh.idesense.testutil.JAVA_PROJECT_DESCRIPTOR
import com.intellij.ide.structureView.StructureViewTreeElement
import com.intellij.ide.structureView.TreeBasedStructureViewBuilder
import com.intellij.ide.structureView.newStructureView.TreeActionsOwner
import com.intellij.ide.structureView.newStructureView.TreeModelWrapper
import com.intellij.ide.util.treeView.AbstractTreeNode
import com.intellij.ide.util.treeView.smartTree.ProvidingTreeModel
import com.intellij.ide.util.treeView.smartTree.SmartTreeStructure
import com.intellij.lang.LanguageStructureViewBuilder
import com.intellij.openapi.util.Disposer
import com.intellij.psi.JavaPsiFacade
import com.intellij.psi.PsiMethod
import com.intellij.psi.PsiNameIdentifierOwner
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.LightProjectDescriptor
import com.intellij.testFramework.fixtures.BasePlatformTestCase

/**
 * [UniversalModifiers.extract] on the PSI of Java and Kotlin declarations. The modifiers hold
 * keywords only: an annotation with white space in its arguments left parts of its text (#173).
 */
class UniversalModifiersTest : BasePlatformTestCase() {

    // The compiled-class case needs `java.lang.Thread` from the mock JDK.
    override fun getProjectDescriptor(): LightProjectDescriptor = JAVA_PROJECT_DESCRIPTOR

    // region Java: no text of an annotation stays

    fun testJavaMethodWithNamedAnnotationArgument() {
        java(
            """
            class A {
                @Deprecated(since = "1.0") public static void m() {}
            }
            """
        )
        assertEquals(listOf("public", "static"), modifiersOf("m"))
    }

    fun testJavaClassAndFieldWithNamedAnnotationArgument() {
        java(
            """
            @Deprecated(since = "1.0") public final class A {
                @Deprecated(since = "1.0") private int f;
            }
            """
        )
        assertEquals(listOf("public", "final"), modifiersOf("A"))
        assertEquals(listOf("private"), modifiersOf("f"))
    }

    fun testJavaArrayArgumentWithWhiteSpace() {
        java(
            """
            class A {
                @SuppressWarnings({"unchecked", "rawtypes"}) public void a() {}
            }
            """
        )
        assertEquals(listOf("public"), modifiersOf("a"))
    }

    fun testJavaAnnotationOverSeveralLines() {
        java(
            """
            @SuppressWarnings({
                "",
                "PMD",
                "all"
            })
            public class A {}
            """
        )
        assertEquals(listOf("public"), modifiersOf("A"))
    }

    fun testJavaNestedParenthesesAndStringsWithAtSignAndParenthesis() {
        java(
            """
            class A {
                @Ann(text = "a @b ) c", inner = @Inner(x = (1 + 2)))
                protected static void n() {}
            }
            """
        )
        assertEquals(listOf("protected", "static"), modifiersOf("n"))
    }

    fun testJavaAnnotationBetweenKeywords() {
        java(
            """
            class A {
                public @Deprecated(since = "1.0") static void k() {}
                static@Ann(x)final int g = 1;
            }
            """
        )
        assertEquals(listOf("public", "static"), modifiersOf("k"))
        assertEquals(listOf("static", "final"), modifiersOf("g"))
    }

    // The modifier list of a compiled class has the annotations as its only children. The
    // keywords come from the text of the decompiled class.
    fun testJavaCompiledMethodWithNamedAnnotationArguments() {
        val thread = JavaPsiFacade.getInstance(project)
            .findClass("java.lang.Thread", GlobalSearchScope.allScope(project))!!
        val stop = thread.findMethodsByName("stop", false).single()
        assertEquals(listOf("public", "final"), UniversalModifiers.extract(stop))
    }

    // With the inherited members on, the Java structure view shows a member of a Kotlin superclass
    // as a light method. Its modifier list has no children, and its text is the text of the Kotlin
    // modifier list.
    fun testJavaInheritedMemberOfKotlinClass() {
        myFixture.addFileToProject(
            "K.kt",
            """
            open class K {
                @Deprecated("a b") open fun r() {}
                open fun plain() {}
            }
            """.trimIndent()
        )
        java("class B extends K {}")
        val inherited = inheritedMethodsInStructureView()
        assertEquals(listOf("open"), UniversalModifiers.extract(inherited.getValue("r")))
        assertEquals(listOf("open"), UniversalModifiers.extract(inherited.getValue("plain")))
    }

    // endregion

    // region Java: the keywords of a declaration with no annotation text in them do not change

    fun testJavaKeywordsInSourceOrder() {
        java(
            """
            abstract class A {
                public static final int X = 1;
                private transient volatile int tv;
                static public void sp() {}
                protected abstract void ab();
                synchronized void sy() {}
                void none() {}
                @Override public String toString() { return ""; }
                @SuppressWarnings("unchecked") private void u() {}
            }
            """
        )
        assertEquals(listOf("abstract"), modifiersOf("A"))
        assertEquals(listOf("public", "static", "final"), modifiersOf("X"))
        assertEquals(listOf("private", "transient", "volatile"), modifiersOf("tv"))
        assertEquals(listOf("static", "public"), modifiersOf("sp"))
        assertEquals(listOf("protected", "abstract"), modifiersOf("ab"))
        assertEquals(listOf("synchronized"), modifiersOf("sy"))
        assertEquals(emptyList<String>(), modifiersOf("none"))
        assertEquals(listOf("public"), modifiersOf("toString"))
        assertEquals(listOf("private"), modifiersOf("u"))
    }

    // endregion

    // region Kotlin: no text of an annotation stays

    fun testKotlinFunctionWithNamedAnnotationArgument() {
        kotlin(
            """
            @Deprecated("old", level = DeprecationLevel.WARNING) public fun m() {}
            """
        )
        assertEquals(listOf("public"), modifiersOf("m"))
    }

    fun testKotlinClassWithAnnotationArguments() {
        kotlin(
            """
            @Suppress("UNCHECKED_CAST", "UNUSED") internal data class D(val a: Int)
            """
        )
        assertEquals(listOf("internal", "data"), modifiersOf("D"))
    }

    fun testKotlinArrayArgumentAndBracketedAnnotationsWithWhiteSpace() {
        kotlin(
            """
            @Suppress(names = ["a", "b"]) private val p = 1
            @[Suppress("x") JvmName("y z")] internal fun br() {}
            """
        )
        assertEquals(listOf("private"), modifiersOf("p"))
        assertEquals(listOf("internal"), modifiersOf("br"))
    }

    fun testKotlinAnnotationOverSeveralLines() {
        kotlin(
            """
            @Deprecated(
                message = "old",
                replaceWith = ReplaceWith("n()"),
            )
            internal fun o() {}
            """
        )
        assertEquals(listOf("internal"), modifiersOf("o"))
    }

    fun testKotlinUseSiteTargetAndStringWithAtSignAndParenthesis() {
        kotlin(
            """
            class K {
                @field:Ann(text = "a @b ) c", inner = Inner(x = (1 + 2))) lateinit var q: String
            }
            """
        )
        assertEquals(listOf("lateinit"), modifiersOf("q"))
    }

    fun testKotlinAnnotationBetweenKeywords() {
        kotlin(
            """
            open class K {
                public @Deprecated("a b") open fun r() {}
            }
            """
        )
        assertEquals(listOf("public", "open"), modifiersOf("r"))
    }

    // endregion

    // region Kotlin: the keywords of a declaration with no annotation text in them do not change

    fun testKotlinKeywordsInSourceOrder() {
        kotlin(
            """
            data class D(val a: Int)
            sealed class S
            enum class E { ONE }
            annotation class Ann
            abstract class K {
                companion object Factory { const val C = 1 }
                private inline fun il() {}
                abstract suspend fun su()
                open fun op() {}
                internal lateinit var lv: String
                @JvmField val jf = 1
                fun none() {}
            }
            context(String) fun cx() {}
            """
        )
        assertEquals(listOf("data"), modifiersOf("D"))
        assertEquals(listOf("sealed"), modifiersOf("S"))
        assertEquals(listOf("enum"), modifiersOf("E"))
        assertEquals(listOf("annotation"), modifiersOf("Ann"))
        assertEquals(listOf("abstract"), modifiersOf("K"))
        assertEquals(listOf("companion"), modifiersOf("Factory"))
        assertEquals(listOf("const"), modifiersOf("C"))
        assertEquals(listOf("private", "inline"), modifiersOf("il"))
        assertEquals(listOf("abstract", "suspend"), modifiersOf("su"))
        assertEquals(listOf("open"), modifiersOf("op"))
        assertEquals(listOf("internal", "lateinit"), modifiersOf("lv"))
        assertEquals(emptyList<String>(), modifiersOf("jf"))
        assertEquals(emptyList<String>(), modifiersOf("none"))
        // The context receiver list is a child of the modifier list, and it stays.
        assertEquals(listOf("context(String)"), modifiersOf("cx"))
    }

    // endregion

    private fun java(text: String) {
        myFixture.configureByText("A.java", text.trimIndent())
    }

    private fun kotlin(text: String) {
        myFixture.configureByText("A.kt", text.trimIndent())
    }

    // The first declaration with the name in source order. A Kotlin primary constructor has the
    // name of its class and comes after the class.
    private fun modifiersOf(name: String): List<String> {
        val declaration = PsiTreeUtil.findChildrenOfType(myFixture.file, PsiNameIdentifierOwner::class.java)
            .first { it.name == name }
        return UniversalModifiers.extract(declaration)
    }

    // The methods of the Java structure view of the file with the inherited members on. These are
    // the elements that `ide_file_structure` gives to `UniversalModifiers.extract` for
    // `show: ["inherited"]`.
    private fun inheritedMethodsInStructureView(): Map<String, PsiMethod> {
        val builder = LanguageStructureViewBuilder.getInstance()
            .getStructureViewBuilder(myFixture.file) as TreeBasedStructureViewBuilder
        val model = builder.createStructureViewModel(null)
        try {
            val inherited = (model as ProvidingTreeModel).nodeProviders
                .single { it.name.contains("INHERITED", ignoreCase = true) }.name
            val owner = object : TreeActionsOwner {
                override fun isActionActive(name: String): Boolean = name == inherited
                override fun setActionActive(name: String, state: Boolean) {}
            }
            val root = SmartTreeStructure(project, TreeModelWrapper(model, owner)).rootElement as AbstractTreeNode<*>
            return generateSequence(listOf(root)) { level -> level.flatMap { it.children }.ifEmpty { null } }
                .flatten()
                .mapNotNull { (it.value as? StructureViewTreeElement)?.value as? PsiMethod }
                .associateBy { it.name }
        } finally {
            Disposer.dispose(model)
        }
    }
}
