package com.github.vcth4nh.idesense.server

import com.github.vcth4nh.idesense.McpConstants

/**
 * Decides which host the MCP server may actually bind to.
 *
 * Binding anywhere other than loopback exposes every enabled tool — including full read
 * access to the workspace — to any machine that can reach the port, and there is no auth on
 * any transport. So a non-loopback host is honored only when the user has explicitly
 * acknowledged that exposure in settings; otherwise the server quietly falls back to loopback
 * and the caller reports why.
 */
object ServerHostPolicy {

    data class Resolution(
        /** The host to actually bind. */
        val effectiveHost: String,
        /** True when a non-loopback host was requested without acknowledgement and was refused. */
        val blocked: Boolean,
    )

    fun isLoopback(host: String): Boolean {
        val h = host.trim().lowercase().removeSurrounding("[", "]")
        return h == "localhost" ||
            h == "::1" ||
            h == "0:0:0:0:0:0:0:1" ||
            h.startsWith("127.")
    }

    fun resolve(configuredHost: String, acknowledged: Boolean): Resolution {
        val host = configuredHost.trim()
        return when {
            host.isEmpty() -> Resolution(McpConstants.DEFAULT_SERVER_HOST, blocked = false)
            isLoopback(host) || acknowledged -> Resolution(host, blocked = false)
            else -> Resolution(McpConstants.DEFAULT_SERVER_HOST, blocked = true)
        }
    }
}
