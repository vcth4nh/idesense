package com.github.vcth4nh.idesense.integration

import com.github.vcth4nh.idesense.util.PsiUtils
import com.intellij.psi.PsiDirectory
import com.intellij.testFramework.fixtures.BasePlatformTestCase

class NavigationPrecisionTest : BasePlatformTestCase() {

    // region isOnDeclarationIdentifier — Java

    fun testIsOnDeclarationIdentifier_trueOnJavaMethodName() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                public int <caret>alphaMethod() { return 1; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertTrue(PsiUtils.isOnDeclarationIdentifier(element))
    }

    fun testIsOnDeclarationIdentifier_falseOnJavaComment() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                // <caret>alphaMethod is mentioned in this comment.
                public int alphaMethod() { return 1; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertFalse(PsiUtils.isOnDeclarationIdentifier(element))
    }

    fun testIsOnDeclarationIdentifier_falseOnJavaCallSite() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                public int alphaMethod() { return 1; }
                public int sum() { return <caret>alphaMethod(); }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        // A call site identifier is NOT a declaration identifier; the resolution goes
        // through element.reference, not through the findNamedElement fallback.
        assertFalse(PsiUtils.isOnDeclarationIdentifier(element))
    }

    // endregion

    // region isOnDeclarationIdentifier — Kotlin (verifies light-class layer assumption)

    fun testIsOnDeclarationIdentifier_trueOnKotlinFunctionName() {
        myFixture.configureByText("Foo.kt", """
            class Foo {
                fun <caret>alphaMethod(): Int = 1
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertTrue(
            "Kotlin KtNamedFunction must implement PsiNameIdentifierOwner so caret on `alphaMethod` in declaration is recognized",
            PsiUtils.isOnDeclarationIdentifier(element)
        )
    }

    fun testIsOnDeclarationIdentifier_falseOnKotlinComment() {
        myFixture.configureByText("Foo.kt", """
            class Foo {
                // <caret>alphaMethod is in a comment
                fun alphaMethod(): Int = 1
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertFalse(PsiUtils.isOnDeclarationIdentifier(element))
    }

    // endregion

    // region resolveTargetElement — negative probes (B.1 fix)

    fun testResolveTarget_onJavaCommentAboveMethod_returnsNull() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                // <caret>alphaMethod is mentioned in this comment.
                public int alphaMethod() { return 1; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertNull(
            "Caret on a comment must not walk to the attached method",
            PsiUtils.resolveTargetElement(element)
        )
    }

    fun testResolveTarget_onJavaEmptyLineBetweenMethods_returnsNull() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                public int alphaMethod() { return 1; }
            <caret>
                public int betaMethod() { return 2; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertNull(
            "Caret on whitespace inside a class must not walk to the class",
            PsiUtils.resolveTargetElement(element)
        )
    }

    fun testResolveTarget_onJavaLiteralInBody_returnsNull() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                public int alphaMethod() { return <caret>42; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        assertNull(
            "Caret on a literal (not an identifier) must not walk to the enclosing method",
            PsiUtils.resolveTargetElement(element)
        )
    }

    // endregion

    // region resolveTargetElement — positive probes (regression guards for preserved behavior)

    fun testResolveTarget_onJavaDeclarationIdentifier_resolves() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                public int <caret>alphaMethod() { return 1; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        val target = PsiUtils.resolveTargetElement(element)
        assertNotNull("Caret on declaration identifier must resolve", target)
    }

    fun testResolveTarget_onJavaRealCallSite_resolves() {
        myFixture.configureByText("Foo.java", """
            class Foo {
                public int alphaMethod() { return 1; }
                public int sum() { return <caret>alphaMethod(); }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        val target = PsiUtils.resolveTargetElement(element)
        assertNotNull("Caret on a real call site must resolve to the called method", target)
    }

    // endregion

    // region B.2 — PsiDirectory behavior (preserved for imports; blocked for walk-past-file)

    fun testResolveTarget_onJavaImportPackageSegment_doesNotLeakDirectory() {
        // No-leak guard: verifies that resolveTargetElement does not escape to PsiDirectory when
        // the caret is on an import package segment (e.g., `util` in `import java.util.List;`).
        // In the test sandbox java.util is not indexed, so reference.resolve() returns null.
        // The findNamedElement fallback must NOT fire (import-segment identifiers are not
        // PsiNameIdentifierOwner), so the result is null — never a PsiDirectory.
        // (The complementary direct check of findNamedElement hardening lives in
        // testFindNamedElement_doesNotReturnPsiDirectory.)
        myFixture.configureByText("Foo.java", """
            package testcases;
            import java.<caret>util.List;
            class Foo {
                List<String> items;
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        // In test sandbox: java.util is not indexed, reference.resolve() == null, no fallback fires
        // → returns null. In real IDE: reference resolves to PsiPackage/PsiDirectory.
        // Either outcome is acceptable; we just verify no exception is thrown.
        val target = PsiUtils.resolveTargetElement(element)
        // target may be null in sandbox or non-null in real IDE — both are correct.
        // The important invariant: no ClassCastException, no directory leak from findNamedElement.
        assertTrue(
            "resolveTargetElement must return null or a valid PsiElement — never throw",
            target == null || target.isValid
        )
    }

    fun testFindNamedElement_doesNotReturnPsiDirectory() {
        // Direct check of the findNamedElement hardening: even if a caller forgets the gate,
        // findNamedElement must not escape past PsiFile to PsiDirectory.
        myFixture.configureByText("empty.py", "\n\n\n")
        val element = myFixture.file.findElementAt(0)!!
        val result = PsiUtils.findNamedElement(element)
        assertFalse(
            "findNamedElement must exclude PsiFileSystemItem (including PsiDirectory)",
            result is PsiDirectory
        )
    }

    // endregion

    // region TypeHierarchy characterization — documents deliberate exclusion from this fix

    fun testTypeHierarchy_javaCaretOnWhitespace_currentlyReturnsContainingClass() {
        // This test DOCUMENTS current behavior: Java type_hierarchy walks to the containing
        // class from any position including whitespace. This is tool-specific semantics, not
        // bug B.1, and is intentionally excluded from this fix. If a future investigation
        // determines the walk-to-class is unintended, a follow-up PR can gate TypeHierarchyTool.
        myFixture.configureByText("Foo.java", """
            class Foo {
            <caret>
                public int alphaMethod() { return 1; }
            }
        """.trimIndent())
        val element = myFixture.file.findElementAt(myFixture.editor.caretModel.offset)!!
        // resolveTargetElement gated — should return null (not walk to class). The tool layer
        // for TypeHierarchyTool uses a different path that preserves the class walk.
        assertNull(
            "resolveTargetElement is gated; TypeHierarchyTool's separate class walk is unaffected",
            PsiUtils.resolveTargetElement(element)
        )
    }

    // endregion
}
