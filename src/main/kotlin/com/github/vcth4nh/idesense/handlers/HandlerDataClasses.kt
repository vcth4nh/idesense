package com.github.vcth4nh.idesense.handlers

import com.intellij.psi.PsiElement

/**
 * Result data for type hierarchy operations.
 */
data class TypeHierarchyData(
    val element: TypeElementData,
    val supertypes: List<TypeElementData>,
    val subtypes: List<TypeElementData>
)

/**
 * Represents a type element in a hierarchy.
 */
data class TypeElementData(
    val name: String,
    val qualifiedName: String?,
    val file: String?,
    val line: Int?,
    val kind: String,
    val language: String,
    val supertypes: List<TypeElementData>? = null,
    val psi: PsiElement? = null
)

/**
 * Result data for call hierarchy operations.
 */
data class CallHierarchyData(
    val element: CallElementData,
    val calls: List<CallElementData>
)

/**
 * Represents a method/function in a call hierarchy.
 */
data class CallElementData(
    val name: String,
    val file: String,
    val line: Int,
    val column: Int,
    val language: String,
    val children: List<CallElementData>? = null,
    val qualifiedName: String? = null
)

/**
 * Result data for symbol search.
 */
data class SymbolData(
    val name: String,
    val qualifiedName: String?,
    val kind: String,
    val file: String,
    val line: Int,
    val column: Int,
)

/**
 * Result data for super methods search.
 */
data class SuperMethodsData(
    val method: MethodData,
    val hierarchy: List<SuperMethodData>
)

/**
 * Represents a method in super methods results.
 */
data class MethodData(
    val name: String,
    val qualifiedName: String?,
    val kind: String,
    val file: String,
    val line: Int,
    val column: Int,
)

/**
 * Represents a super method in the inheritance chain.
 */
data class SuperMethodData(
    val name: String,
    val qualifiedName: String?,
    val kind: String,
    val file: String?,
    val line: Int?,
    val column: Int?,
)
