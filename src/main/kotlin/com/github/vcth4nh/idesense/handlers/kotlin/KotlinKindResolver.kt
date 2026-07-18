package com.github.vcth4nh.idesense.handlers.kotlin

import com.github.vcth4nh.idesense.handlers.LanguageKindResolver
import com.intellij.psi.PsiElement
import org.jetbrains.kotlin.lexer.KtTokens
import org.jetbrains.kotlin.psi.KtClass
import org.jetbrains.kotlin.psi.KtConstructor
import org.jetbrains.kotlin.psi.KtObjectDeclaration

class KotlinKindResolver : LanguageKindResolver {
    override fun resolveKind(element: PsiElement): String? {
        // A constructor call resolves to the KtPrimaryConstructor/KtSecondaryConstructor
        // element; report the kind of the class it constructs (#17).
        if (element is KtConstructor<*>) return resolveKind(element.getContainingClassOrObject())
        if (element is KtClass) {
            return when {
                element.isAnnotation() -> "ANNOTATION"
                element.isInterface() -> "INTERFACE"
                element.isEnum() -> "ENUM"
                element.isData() -> "DATA_CLASS"
                element.isSealed() -> "SEALED_CLASS"
                element.modifierList?.hasModifier(KtTokens.ABSTRACT_KEYWORD) == true -> "ABSTRACT_CLASS"
                else -> "CLASS"
            }
        }
        if (element is KtObjectDeclaration) return "OBJECT"
        return null
    }
}
