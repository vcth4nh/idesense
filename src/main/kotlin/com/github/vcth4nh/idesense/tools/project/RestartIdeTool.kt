package com.github.vcth4nh.idesense.tools.project

import com.github.vcth4nh.idesense.constants.ParamNames
import com.github.vcth4nh.idesense.constants.ToolNames
import com.github.vcth4nh.idesense.server.models.ToolCallResult
import com.github.vcth4nh.idesense.tools.AbstractMcpTool
import com.github.vcth4nh.idesense.tools.models.RestartIdeResult
import com.github.vcth4nh.idesense.tools.schema.SchemaBuilder
import com.github.vcth4nh.idesense.util.ThreadingUtils
import com.intellij.openapi.application.ex.ApplicationManagerEx
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import com.intellij.util.concurrency.AppExecutorUtil
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive
import java.util.concurrent.TimeUnit

/**
 * Restarts THIS IDE. The other half of the local plugin dev loop — call after
 * [InstallPluginTool] (`ide_install_plugin`) to load the freshly staged build.
 *
 * The restart is **scheduled after this tool returns**, not invoked inline. The MCP
 * response is only flushed once `doExecute` returns (see `KtorMcpServer`'s streamable-HTTP
 * handler), and this plugin's own MCP server dies with the IDE. Scheduling the restart on a
 * delay lets the client receive the result before the connection drops.
 */
class RestartIdeTool : AbstractMcpTool() {

    companion object {
        private val LOG = logger<RestartIdeTool>()
        private const val DEFAULT_DELAY_SECONDS = 2
        private const val MAX_DELAY_SECONDS = 60
    }

    override val requiresPsiSync: Boolean = false

    override val name = ToolNames.RESTART_IDE

    override val description = """
        Restart this IDE. Use as the second half of the plugin dev loop after ide_install_plugin —
        the plugin is not dynamically reloadable, so restart is required to pick up new code.

        The restart fires after a short delay (default 2 s) so this response reaches the client
        before the connection drops. The MCP server goes down with the IDE; reconnect once the IDE
        is back. In remote-dev / serverMode, the backend relaunches and the thin client reconnects
        automatically.

        Returns: restarting flag and effective delaySeconds.

        Gotchas: disabled by default — must be enabled in Settings → IdeSense. Unsaved
        in-memory state is lost on restart.
    """.trimIndent()

    override val inputSchema: JsonObject = SchemaBuilder.tool()
        .projectPath()
        .intProperty(
            ParamNames.DELAY_SECONDS,
            "Seconds to wait before restarting (lets the response flush to the client). Default: 2. Range: 0-60."
        )
        .build()

    override suspend fun doExecute(project: Project, arguments: JsonObject): ToolCallResult {
        val requested = arguments[ParamNames.DELAY_SECONDS]?.jsonPrimitive?.intOrNull ?: DEFAULT_DELAY_SECONDS
        val delaySeconds = requested.coerceIn(0, MAX_DELAY_SECONDS)

        AppExecutorUtil.getAppScheduledExecutorService().schedule({
            try {
                ThreadingUtils.runOnEdt {
                    ApplicationManagerEx.getApplicationEx().restart(true)
                }
            } catch (e: Throwable) {
                LOG.error("IDE restart failed", e)
            }
        }, delaySeconds.toLong(), TimeUnit.SECONDS)

        return createJsonResult(
            RestartIdeResult(
                restarting = true,
                delaySeconds = delaySeconds,
                message = "IDE will restart in ${delaySeconds}s. The MCP server stops during restart — reconnect after the IDE is back (serverMode backends relaunch and the thin client reconnects automatically)."
            )
        )
    }
}
