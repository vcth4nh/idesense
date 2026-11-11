package com.github.vcth4nh.idesense.handlers

import com.intellij.lang.findUsages.LanguageFindUsages
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement

object LanguageServices {
    private val LOG = logger<LanguageServices>()

    fun getKind(element: PsiElement): String {
        // Tier 1: per-language EP-registered kind resolver
        LanguageKindResolver.EP.forLanguage(element.language)?.resolveKind(element)?.let { return it }
        element.language.baseLanguage?.let { base ->
            LanguageKindResolver.EP.forLanguage(base)?.resolveKind(element)?.let { return it }
        }
        return kindFromIdeTypeOrClassName(element.javaClass.simpleName) { LanguageFindUsages.getType(element) }
    }

    /**
     * Tier 2, the platform FindUsagesProvider ([ideType]), then tier 3, the class name. A provider
     * can throw for an element that it does not know: `XmlFindUsagesProvider.getType` throws
     * IllegalArgumentException for an HTML file (#126). Then the class name gives the kind.
     */
    internal fun kindFromIdeTypeOrClassName(simpleName: String, ideType: () -> String): String {
        val type = try {
            ideType()
        } catch (e: ProcessCanceledException) {
            throw e
        } catch (e: Exception) {
            LOG.debug("FindUsagesProvider.getType threw for $simpleName: ${e.message}")
            ""
        }
        return if (type.isNotEmpty()) normalizeKind(type) else fallbackKindFromClassName(simpleName)
    }

    fun findSuperMethods(element: PsiElement, project: Project): SuperMethodsData? {
        SuperMethodsProvider.EP.forLanguage(element.language)?.findSuperMethods(element, project)?.let { return it }
        return element.language.baseLanguage?.let {
            SuperMethodsProvider.EP.forLanguage(it)?.findSuperMethods(element, project)
        }
    }

    fun hasAnySuperMethodsProvider(): Boolean =
        SuperMethodsProvider.EP_NAME.extensionList.isNotEmpty()

    private fun normalizeKind(ideType: String): String {
        val lower = ideType.lowercase()
        return when {
            lower == "method" -> "METHOD"
            lower == "function" -> "FUNCTION"
            lower == "class" -> "CLASS"
            lower == "interface" -> "INTERFACE"
            lower == "enum" -> "ENUM"
            lower == "trait" -> "TRAIT"
            lower == "struct" -> "STRUCT"
            lower == "object" -> "OBJECT"
            lower == "field" -> "FIELD"
            lower == "variable" -> "VARIABLE"
            lower == "property" -> "PROPERTY"
            lower == "constant" -> "CONSTANT"
            lower == "type alias" || lower == "typealias" -> "TYPE_ALIAS"
            lower == "type" -> "TYPE"
            lower == "record" -> "RECORD"
            lower == "annotation" -> "ANNOTATION"
            lower == "parameter" -> "PARAMETER"
            lower == "constructor" -> "CONSTRUCTOR"
            lower == "module" -> "MODULE"
            lower == "package" -> "PACKAGE"
            lower == "label" -> "LABEL"
            lower.contains("interface") -> "INTERFACE"
            lower.contains("method") -> "METHOD"
            lower.contains("function") -> "FUNCTION"
            lower.contains("class") -> "CLASS"
            else -> ideType.uppercase().replace(" ", "_")
        }
    }

    private fun fallbackKindFromClassName(simpleName: String): String {
        val lower = simpleName.lowercase()
        return when {
            lower.contains("interface") -> "INTERFACE"
            lower.contains("trait") -> "TRAIT"
            lower.contains("annotation") -> "ANNOTATION"
            lower.contains("enum") -> "ENUM"
            lower.contains("record") -> "RECORD"
            // before the struct checks: "constructor" contains "struct" as a substring
            lower.contains("constructor") -> "CONSTRUCTOR"
            lower.contains("structitem") -> "STRUCT"
            lower.contains("implitem") -> "IMPL"
            lower.contains("moditem") -> "MODULE"
            lower.contains("struct") -> "STRUCT"
            lower.contains("objectdeclaration") -> "OBJECT"
            lower.contains("method") -> "METHOD"
            lower.contains("function") -> "FUNCTION"
            lower.contains("field") -> "FIELD"
            lower.contains("variable") -> "VARIABLE"
            lower.contains("property") -> "PROPERTY"
            lower.contains("constant") -> "CONSTANT"
            lower.contains("class") -> "CLASS"
            else -> "SYMBOL"
        }
    }
}
