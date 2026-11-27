package com.github.vcth4nh.idesense

import com.github.vcth4nh.idesense.util.IdeProductInfo
import com.intellij.util.messages.Topic

object McpConstants {
    const val PLUGIN_NAME = "IdeSense"
    const val TOOL_WINDOW_ID = PLUGIN_NAME
    const val NOTIFICATION_GROUP_ID = PLUGIN_NAME
    const val SETTINGS_DISPLAY_NAME = PLUGIN_NAME

    // Server configuration - IDE-specific defaults
    const val DEFAULT_SERVER_HOST = "127.0.0.1"

    /**
     * Returns the IDE-specific default server port.
     * Each IDE has a unique default port to avoid conflicts when multiple IDEs run simultaneously.
     */
    @JvmStatic
    fun getDefaultServerPort(): Int = IdeProductInfo.getDefaultPort()

    /**
     * Legacy constant for backwards compatibility.
     * New code should use getDefaultServerPort() for IDE-specific ports.
     */
    const val DEFAULT_SERVER_PORT = 29170

    // MCP Endpoint paths
    const val MCP_ENDPOINT_PATH = "/mcp"
    const val SSE_ENDPOINT_PATH = "$MCP_ENDPOINT_PATH/sse"
    const val STREAMABLE_HTTP_ENDPOINT_PATH = "$MCP_ENDPOINT_PATH/streamable-http"
    const val SESSION_ID_PARAM = "sessionId"

    // JSON-RPC version
    const val JSON_RPC_VERSION = "2.0"

    // MCP Protocol versions
    const val LEGACY_MCP_PROTOCOL_VERSION = "2024-11-05"
    const val STREAMABLE_HTTP_MCP_PROTOCOL_VERSION = "2025-11-25"
    const val MCP_PROTOCOL_VERSION = STREAMABLE_HTTP_MCP_PROTOCOL_VERSION

    /** Protocol versions this server can speak, newest first. Used for initialize negotiation. */
    val SUPPORTED_PROTOCOL_VERSIONS = listOf("2025-11-25", "2025-03-26", "2024-11-05")

    // Server identification - IDE-specific
    /**
     * Returns the IDE-specific server name (e.g., "intellij-idesense", "pycharm-idesense").
     */
    @JvmStatic
    fun getServerName(): String = IdeProductInfo.getServerName()

    /**
     * Legacy constant for backwards compatibility.
     */
    const val SERVER_NAME = "idesense"

    /**
     * Plugin version, read from the resource `idesense-version.txt`. The Gradle task
     * `processResources` writes it from the Gradle property `pluginVersion`, the same property
     * that gives `plugin.xml` its version, so a build with `-PpluginVersion=<x>` reports `<x>`.
     * Lazy, so the resource is read on the first use.
     */
    val SERVER_VERSION: String by lazy {
        McpConstants::class.java.getResource("/idesense-version.txt")!!.readText().trim()
    }

    const val SERVER_DESCRIPTION = "Code intelligence server for JetBrains IDEs (IntelliJ, PyCharm, WebStorm, GoLand, PhpStorm, RustRover). Use this instead of grep/ripgrep for semantic code understanding. Capabilities: find usages, go to definition, type/call hierarchies, find implementations, symbol search, rename refactoring, diagnostics. Languages: Java, Kotlin, Python, JavaScript, TypeScript, Go, PHP, Rust. Prerequisite: project must be open in IDE. Note: refactoring tools modify source files."

    /**
     * Topic for server status change notifications.
     * Used to notify UI components when the server restarts or encounters errors.
     */
    @JvmField
    val SERVER_STATUS_TOPIC: Topic<ServerStatusListener> = Topic.create(
        "MCP Server Status",
        ServerStatusListener::class.java
    )
}

/**
 * Listener interface for server status changes.
 */
interface ServerStatusListener {
    fun serverStatusChanged()
}
