package com.github.vcth4nh.idesense.handlers

/**
 * Shared utilities for symbol/file search matching and path filtering.
 *
 * Used by the navigation tools (FindClassTool, FindFileTool) to avoid duplication.
 */

/**
 * Path prefixes that are excluded only when they appear at the project root.
 * These are common build output dirs or environment dirs that could legitimately appear
 * as nested source dirs (e.g. `src/config/env/`, `docker/env/`).
 */
internal val ROOT_ONLY_EXCLUDED_PREFIXES = listOf(
    "bin/", "build/", "out/", ".gradle/",
    ".env/", "env/"  // Python venv aliases — root-only to avoid false positives at depth
)

/**
 * Path segments that are excluded at any depth in the project tree.
 * Virtual environments and package manager directories should never contain source files
 * regardless of where they appear in the project hierarchy.
 */
internal val DEEP_EXCLUDED_SEGMENTS = listOf(
    ".venv/", "venv/",
    "node_modules/",
    ".worktrees/", ".claude/worktrees/"
)

/** Returns true if [path] matches any excluded directory rule. */
internal fun isExcludedPath(path: String): Boolean {
    if (ROOT_ONLY_EXCLUDED_PREFIXES.any { path.startsWith(it) }) return true
    if (DEEP_EXCLUDED_SEGMENTS.any { seg -> path.startsWith(seg) || path.contains("/$seg") }) return true
    return false
}
