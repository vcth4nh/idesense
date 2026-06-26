package com.github.vcth4nh.idesense.util

import com.intellij.openapi.application.ReadAction
import com.intellij.psi.PsiClass
import com.intellij.psi.PsiElement
import com.intellij.testFramework.fixtures.BasePlatformTestCase

class ClassResolverTest : BasePlatformTestCase() {

    fun testResolvesJavaClassByFqn() {
        myFixture.configureByText(
            "MyService.java",
            """
            package com.example;
            public class MyService {}
            """.trimIndent()
        )

        val resolved = ReadAction.compute<com.intellij.psi.PsiElement?, Throwable> {
            ClassResolver.findClassByName(project, "com.example.MyService")
        }

        assertNotNull(resolved)
        assertTrue("Expected PsiClass", resolved is PsiClass)
        assertEquals("MyService", (resolved as PsiClass).name)
    }

    fun testReturnsNullForUnknownFqn() {
        val resolved = ReadAction.compute<com.intellij.psi.PsiElement?, Throwable> {
            ClassResolver.findClassByName(project, "com.example.DoesNotExist")
        }
        assertNull(resolved)
    }

    fun testResolvesPythonClassByFqnWhenPythonPluginPresent() {
        // Skip if Python plugin isn't actually active. Class.forName alone is insufficient —
        // the headless gradle test runtime can have the class on the classpath without the
        // language extensions being registered. Verify the registered Language by ID.
        if (com.intellij.lang.Language.findLanguageByID("Python") == null) return
        try {
            Class.forName("com.jetbrains.python.psi.PyClass")
        } catch (_: ClassNotFoundException) {
            return
        }

        val pyFile = myFixture.configureByText(
            "noise.py",
            """
            class MyParser:
                pass
            """.trimIndent()
        )
        // Final guard: if the fixture didn't actually parse as Python, the language services
        // aren't initialized for this test run.
        if (pyFile.language.id != "Python") return

        val resolved = ReadAction.compute<com.intellij.psi.PsiElement?, Throwable> {
            ClassResolver.findClassByName(project, "noise.MyParser")
        }

        assertNotNull("Python class should resolve via EP iteration", resolved)
        // The returned element should at least have name "MyParser".
        val nameMethod = resolved!!.javaClass.methods.firstOrNull { it.name == "getName" && it.parameterCount == 0 }
        assertEquals("MyParser", nameMethod?.invoke(resolved))
    }

    fun testResolvesPhpInterfaceByFqnWhenPhpPluginPresent() {
        try {
            Class.forName("com.jetbrains.php.PhpIndex")
        } catch (_: ClassNotFoundException) {
            return
        }

        myFixture.configureByText(
            "Greeter.php",
            """
            <?php
            interface Greeter {
                public function greet(): string;
            }
            """.trimIndent()
        )

        val resolved = ReadAction.compute<PsiElement?, Throwable> {
            ClassResolver.findClassByName(project, "\\Greeter")
        }

        assertNotNull("PHP interface should resolve via PhpIndex.getInterfacesByFQN fallback", resolved)
    }

    fun testResolvesPhpTraitByFqnWhenPhpPluginPresent() {
        try {
            Class.forName("com.jetbrains.php.PhpIndex")
        } catch (_: ClassNotFoundException) {
            return
        }

        myFixture.configureByText(
            "Loggable.php",
            """
            <?php
            trait Loggable {
                public function log(${'$'}message): void {}
            }
            """.trimIndent()
        )

        val resolved = ReadAction.compute<PsiElement?, Throwable> {
            ClassResolver.findClassByName(project, "\\Loggable")
        }

        assertNotNull("PHP trait should resolve via PhpIndex.getTraitsByFQN fallback", resolved)
    }
}
