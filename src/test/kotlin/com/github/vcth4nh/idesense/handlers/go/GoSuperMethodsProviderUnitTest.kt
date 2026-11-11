package com.github.vcth4nh.idesense.handlers.go

import com.intellij.psi.PsiElement
import io.mockk.every
import io.mockk.mockk
import junit.framework.TestCase

class GoSuperMethodsProviderUnitTest : TestCase() {

    // Stands for com.goide.psi.GoMethodSpec: one line in the body of a Go interface.
    private interface MethodSpec : PsiElement

    private val withSignature = mutableSetOf<PsiElement>()

    private fun methodSpec(hasSignature: Boolean): MethodSpec {
        val spec = mockk<MethodSpec>()
        every { spec.parent } returns null
        if (hasSignature) withSignature += spec
        return spec
    }

    private fun childOf(parent: PsiElement?): PsiElement {
        val element = mockk<PsiElement>()
        every { element.parent } returns parent
        return element
    }

    private fun interfaceMethodAt(element: PsiElement): PsiElement? =
        GoSuperMethodsProvider.interfaceMethodAt(element, MethodSpec::class.java) { spec -> spec in withSignature }

    // `Full() string` in an interface: the caret is on the name or on the result type.
    fun testAPositionInsideAnInterfaceMethodGivesThatMethod() {
        val method = methodSpec(hasSignature = true)

        assertSame(method, interfaceMethodAt(childOf(childOf(method))))
    }

    fun testAnInterfaceMethodIsItsOwnAnchor() {
        val method = methodSpec(hasSignature = true)

        assertSame(method, interfaceMethodAt(method))
    }

    // An embedded interface is a method spec with no signature. The type anchor handles it.
    fun testAnEmbeddedTypeIsNoInterfaceMethod() {
        val embeddedType = methodSpec(hasSignature = false)

        assertNull(interfaceMethodAt(childOf(embeddedType)))
    }

    fun testAPositionOutsideAnInterfaceBodyIsNoInterfaceMethod() {
        assertNull(interfaceMethodAt(childOf(childOf(null))))
    }
}
