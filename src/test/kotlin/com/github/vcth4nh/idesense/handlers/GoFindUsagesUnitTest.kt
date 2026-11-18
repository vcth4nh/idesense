package com.github.vcth4nh.idesense.handlers

import com.github.vcth4nh.idesense.handlers.go.GoFindUsages
import com.intellij.psi.PsiElement
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

class GoFindUsagesUnitTest : TestCase() {

    // Stands for com.goide.usages.GoMethodFindUsagesOptions: a public boolean field `findBaseMethods`.
    class WithFlag { @JvmField var findBaseMethods: Boolean = true }
    class WithoutFlag
    class WrongType { @JvmField var findBaseMethods: String = "yes" }

    // GoMethodFindUsagesOptions is package-private: the field is public, its class is not.
    // This test is not in the package of GoFindUsages, so a write needs `isAccessible`.
    private class PrivateWithFlag { @JvmField var findBaseMethods: Boolean = true }

    fun testSetFindBaseMethodsSetsThePublicField() {
        val options = WithFlag()

        assertTrue(GoFindUsages.setFindBaseMethods(options, false))
        assertFalse(options.findBaseMethods)
    }

    fun testSetFindBaseMethodsIsFalseWithoutTheField() {
        assertFalse(GoFindUsages.setFindBaseMethods(WithoutFlag(), false))
        assertFalse(GoFindUsages.setFindBaseMethods(WrongType(), false))
    }

    fun testSetFindBaseMethodsSetsTheFieldOfANonPublicClass() {
        val options = PrivateWithFlag()

        assertTrue(GoFindUsages.setFindBaseMethods(options, false))
        assertFalse(options.findBaseMethods)
    }

    // Stand for com.goide.psi.GoKey and com.goide.psi.GoFieldName: the field name is a child of the key.
    private interface Key : PsiElement
    private interface FieldName : PsiElement

    private fun element(parent: PsiElement?): PsiElement {
        val element = mockk<PsiElement>()
        every { element.parent } returns parent
        return element
    }

    private fun key(): Key {
        val key = mockk<Key>()
        every { key.parent } returns null
        return key
    }

    private fun fieldName(parent: PsiElement?): FieldName {
        val name = mockk<FieldName>()
        every { name.parent } returns parent
        return name
    }

    private fun keyFieldName(usageElement: PsiElement): PsiElement? =
        GoFindUsages.keyFieldName(usageElement, Key::class.java, FieldName::class.java)

    // UsageInfo.element of a key: the field name, the element of its multi reference.
    fun testTheFieldNameOfAKeyIsItsOwnFieldName() {
        val name = fieldName(key())

        assertSame(name, keyFieldName(name))
    }

    fun testTheIdentifierOfAFieldNameGivesTheFieldName() {
        val name = fieldName(key())

        assertSame(name, keyFieldName(element(name)))
    }

    // A field name in a selector or a struct type is no key.
    fun testAFieldNameOutsideAKeyIsNoKey() {
        assertNull(keyFieldName(fieldName(element(null))))
        assertNull(keyFieldName(element(fieldName(element(null)))))
    }

    fun testAnotherChildOfAKeyIsNoFieldName() {
        assertNull(keyFieldName(element(key())))
    }

    fun testAnElementOutsideAKeyIsNoKey() {
        assertNull(keyFieldName(element(element(null))))
        assertNull(keyFieldName(element(null)))
    }

    // The Go plugin is not on the unit-test classpath. The strict mocks fail on each call, thus the
    // test also proves that the rule does not read the elements.
    fun testNoFieldKeyWhenTheGoPluginIsAbsent() {
        assertFalse(GoFindUsages.isFieldKeyOfType(mockk(), mockk()))
    }
}
