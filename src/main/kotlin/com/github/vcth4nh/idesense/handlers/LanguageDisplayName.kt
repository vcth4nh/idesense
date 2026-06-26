package com.github.vcth4nh.idesense.handlers

/**
 * Maps an IntelliJ Language ID (e.g. `"JAVA"`, `"kotlin"`, `"go"`) to the display name
 * used in our wire format and tool responses (e.g. `"Java"`, `"Kotlin"`, `"Go"`).
 * Unknown IDs are returned as-is.
 *
 * Shared with FileStructureTool so file_structure responses don't expose lowercase
 * "kotlin" while every other tool reports "Kotlin".
 */
internal fun displayLanguageName(languageId: String): String {
    return when (languageId) {
        "JAVA" -> "Java"
        "kotlin" -> "Kotlin"
        "Python" -> "Python"
        "JavaScript", "ECMAScript 6", "JSX Harmony" -> "JavaScript"
        "TypeScript", "TypeScript JSX" -> "TypeScript"
        "go" -> "Go"
        "PHP" -> "PHP"
        "Rust" -> "Rust"
        else -> languageId
    }
}
