package com.github.vcth4nh.idesense.tools.models

import kotlinx.serialization.Serializable

@Serializable
data class PositionInput(
    val file: String,
    val line: Int,
    val column: Int
)

// find_usages output
@Serializable
data class UsageLocation(
    val file: String,
    val line: Int,
    val column: Int,
    val preview: String,
    val usageType: String,
    val enclosingScope: List<String>,
)

@Serializable
data class FindUsagesResult(
    val usages: List<UsageLocation>,
    val totalCount: Int,
    val truncated: Boolean = false,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    val totalCollected: Int = 0,
    val offset: Int = 0,
    val pageSize: Int = 0,
    val stale: Boolean = false
)

// find_definition output
@Serializable
data class DefinitionResult(
    val file: String,
    val line: Int,
    val column: Int,
    val name: String,
    val kind: String,
    val preview: String,
    val qualifiedName: String? = null,
    val enclosingScope: List<String>? = null,
)

// ide_read_file output
@Serializable
data class ReadFileResult(
    val file: String,
    val content: String,
    val language: String?,
    val lineCount: Int,
    val startLine: Int?,
    val endLine: Int?,
    val isLibraryFile: Boolean
)


// type_hierarchy output
@Serializable
data class TypeHierarchyResult(
    val element: TypeElement,
    val supertypes: List<TypeElement>,
    val subtypes: List<TypeElement>
)

@Serializable
data class TypeElement(
    val name: String,
    val qualifiedName: String? = null,
    val enclosingScope: List<String>? = null,
    val kind: String,
    val file: String? = null,
    val line: Int? = null,
    val column: Int? = null,
    val supertypes: List<TypeElement>? = null
)

// call_hierarchy output
@Serializable
data class CallHierarchyResult(
    val element: CallElement,
    val calls: List<CallElement>
)

@Serializable
data class CallElement(
    val name: String,
    val qualifiedName: String? = null,
    val enclosingScope: List<String>? = null,
    val kind: String,
    val file: String,
    val line: Int,
    val column: Int,
    val children: List<CallElement>? = null
)

// find_implementations output
@Serializable
data class ImplementationResult(
    val implementations: List<ImplementationLocation>,
    val totalCount: Int,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    val totalCollected: Int = 0,
    val offset: Int = 0,
    val pageSize: Int = 0,
    val stale: Boolean = false
)

@Serializable
data class ImplementationLocation(
    val name: String,
    val file: String,
    val line: Int,
    val column: Int,
    val kind: String,
    val qualifiedName: String? = null
)


// ide_diagnostics output
@Serializable
data class DiagnosticsResult(
    val problems: List<ProblemInfo>? = null,
    val intentions: List<IntentionInfo>? = null,
    val problemCount: Int? = null,
    val intentionCount: Int? = null,
    val analysisFresh: Boolean? = null,
    val analysisTimedOut: Boolean? = null,
    val analysisMessage: String? = null,
    val buildErrors: List<BuildMessage>? = null,
    val buildErrorCount: Int? = null,
    val buildWarningCount: Int? = null,
    val buildErrorsTruncated: Boolean? = null,
    val buildTimestamp: Long? = null,
    val testResults: List<TestResultInfo>? = null,
    val testSummary: TestSummary? = null,
    val testResultsTruncated: Boolean? = null
)

@Serializable
data class ProblemInfo(
    val message: String,
    val severity: String,
    val file: String,
    val line: Int,
    val column: Int,
    val endLine: Int?,
    val endColumn: Int?
)

@Serializable
data class IntentionInfo(
    val name: String,
    val description: String?
)

// ide_diagnostics test results output
@Serializable
data class TestResultInfo(
    val name: String,
    val suite: String?,
    val status: String,
    val durationMs: Long?,
    val errorMessage: String?,
    val stacktrace: String?,
    val file: String?,
    val line: Int?
)

@Serializable
data class TestSummary(
    val total: Int,
    val passed: Int,
    val failed: Int,
    val ignored: Int,
    val runConfigName: String?
)

// Refactoring result
@Serializable
data class RefactoringResult(
    val success: Boolean,
    val affectedFiles: List<String>,
    val changesCount: Int,
    val message: String
)


// get_index_status output
@Serializable
data class IndexStatusResult(
    val isDumbMode: Boolean,
    val isIndexing: Boolean,
    val indexingProgress: Double?
)

// ide_sync_files output
@Serializable
data class SyncFilesResult(
    val syncedPaths: List<String>,
    val syncedAll: Boolean,
    val message: String
)

// Build diagnostics message — captured passively by BuildDiagnosticsCacheService, surfaced by ide_diagnostics
@Serializable
data class BuildMessage(
    val category: String,
    val message: String,
    val file: String? = null,
    val line: Int? = null,
    val column: Int? = null
)

// ide_install_plugin output
@Serializable
data class InstallPluginResult(
    val installed: Boolean,
    val source: String,
    val pluginDir: String,
    val pluginId: String? = null,
    val pluginVersion: String? = null,
    val restartRequired: Boolean = true,
    val message: String
)

// ide_restart output
@Serializable
data class RestartIdeResult(
    val restarting: Boolean,
    val delaySeconds: Int,
    val message: String
)

// ide_find_symbol output
@Serializable
data class FindSymbolResult(
    val symbols: List<SymbolMatch>,
    val totalCount: Int,
    val query: String,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    val totalCollected: Int = 0,
    val offset: Int = 0,
    val pageSize: Int = 0,
    val stale: Boolean = false
)

@Serializable
data class SymbolMatch(
    val name: String,
    val qualifiedName: String?,
    val kind: String,
    val file: String,
    val line: Int,
    val column: Int,
)

// ide_find_super_methods output
@Serializable
data class SuperMethodsResult(
    val method: MethodInfo,
    val hierarchy: List<SuperMethodInfo>,
)

@Serializable
data class MethodInfo(
    val name: String,
    val qualifiedName: String? = null,
    val kind: String,
    val file: String,
    val line: Int,
    val column: Int,
)

@Serializable
data class SuperMethodInfo(
    val name: String,
    val qualifiedName: String? = null,
    val kind: String,
    val file: String?,
    val line: Int?,
    val column: Int?,
)

// ide_find_class output (reuses SymbolMatch)
@Serializable
data class FindClassResult(
    val classes: List<SymbolMatch>,
    val totalCount: Int,
    val query: String,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    val totalCollected: Int = 0,
    val offset: Int = 0,
    val pageSize: Int = 0,
    val stale: Boolean = false
)

// ide_find_file output
@Serializable
data class FindFileResult(
    val files: List<FileMatch>,
    val totalCount: Int,
    val query: String,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    val totalCollected: Int = 0,
    val offset: Int = 0,
    val pageSize: Int = 0,
    val stale: Boolean = false
)

@Serializable
data class FileMatch(
    val name: String,
    val path: String,
    val directory: String
)

// ide_search_text output
@Serializable
data class SearchTextResult(
    val matches: List<TextMatch>,
    val totalCount: Int,
    val query: String,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    val totalCollected: Int = 0,
    val offset: Int = 0,
    val pageSize: Int = 0,
    val stale: Boolean = false
)

@Serializable
data class TextMatch(
    val file: String,
    val line: Int,
    val column: Int,
    val context: String,       // line content
    val contextType: String    // "CODE", "COMMENT", "STRING_LITERAL"
)
