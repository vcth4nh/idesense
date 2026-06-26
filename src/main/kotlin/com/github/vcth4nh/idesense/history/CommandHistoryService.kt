package com.github.vcth4nh.idesense.history

import com.github.vcth4nh.idesense.settings.McpSettings
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.diagnostic.logger
import com.intellij.openapi.project.Project
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.util.ArrayDeque
import java.util.concurrent.CopyOnWriteArrayList

@Service(Service.Level.PROJECT)
class CommandHistoryService(private val project: Project) {

    companion object {
        private val LOG = logger<CommandHistoryService>()

        fun getInstance(project: Project): CommandHistoryService = project.service()
    }

    private val historyLock = Any()
    private val history = ArrayDeque<CommandEntry>()
    private val listeners = CopyOnWriteArrayList<CommandHistoryListener>()

    private val json = Json {
        prettyPrint = true
        encodeDefaults = true
    }

    val entries: List<CommandEntry>
        get() = synchronized(historyLock) {
            trimHistoryLocked(configuredMaxSize())
            history.toList()
        }

    fun recordCommand(entry: CommandEntry) {
        val event = synchronized(historyLock) {
            val maxSize = configuredMaxSize()
            if (maxSize == 0) {
                val hadEntries = history.isNotEmpty()
                history.clear()
                if (hadEntries) CommandHistoryEvent.HistoryCleared else null
            } else {
                history.addFirst(entry)
                trimHistoryLocked(maxSize)
                CommandHistoryEvent.CommandAdded(entry)
            }
        }

        event?.let { notifyListeners(it) }
        LOG.debug("Recorded command: ${entry.toolName}")
    }

    fun updateCommandStatus(
        id: String,
        status: CommandStatus,
        result: String?,
        durationMs: Long? = null,
        affectedFiles: List<String>? = null
    ) {
        val updatedEntry = synchronized(historyLock) {
            trimHistoryLocked(configuredMaxSize())

            val entry = history.firstOrNull { it.id == id } ?: return

            entry.status = status
            entry.durationMs = durationMs
            entry.affectedFiles = affectedFiles

            // Store result in appropriate field based on status
            if (status == CommandStatus.ERROR) {
                entry.error = result
                entry.result = null
            } else {
                entry.result = result
                entry.error = null
            }

            entry
        }

        notifyListeners(CommandHistoryEvent.CommandUpdated(updatedEntry))
        LOG.debug("Updated command status: ${updatedEntry.toolName} -> $status")
    }

    fun clearHistory() {
        val shouldNotify = synchronized(historyLock) {
            val hadEntries = history.isNotEmpty()
            history.clear()
            hadEntries
        }

        if (shouldNotify) {
            notifyListeners(CommandHistoryEvent.HistoryCleared)
        }
        LOG.info("Command history cleared")
    }

    fun getFilteredHistory(filter: CommandFilter): List<CommandEntry> {
        return synchronized(historyLock) {
            trimHistoryLocked(configuredMaxSize())

            history.filter { entry ->
                val matchesTool = filter.toolName == null || entry.toolName == filter.toolName
                val matchesStatus = filter.status == null || entry.status == filter.status
                val matchesSearch = filter.searchText == null ||
                    entry.toolName.contains(filter.searchText, ignoreCase = true) ||
                    entry.parameters.toString().contains(filter.searchText, ignoreCase = true) ||
                    entry.result?.contains(filter.searchText, ignoreCase = true) == true

                matchesTool && matchesStatus && matchesSearch
            }
        }
    }

    fun getUniqueToolNames(): List<String> {
        return synchronized(historyLock) {
            trimHistoryLocked(configuredMaxSize())
            history.map { it.toolName }.distinct().sorted()
        }
    }

    fun exportToJson(): String {
        val exports = synchronized(historyLock) {
            trimHistoryLocked(configuredMaxSize())
            history.map { it.toExport() }
        }
        return json.encodeToString(exports)
    }

    fun exportToCsv(): String {
        val header = "ID,Timestamp,Tool,Status,Duration(ms),Result,Error"
        val rows = synchronized(historyLock) {
            trimHistoryLocked(configuredMaxSize())
            history.map { entry ->
                listOf(
                    entry.id,
                    entry.timestamp.toString(),
                    entry.toolName,
                    entry.status.name,
                    entry.durationMs?.toString() ?: "",
                    entry.result?.replace(",", ";")?.replace("\n", " ")?.take(100) ?: "",
                    entry.error?.replace(",", ";")?.replace("\n", " ") ?: ""
                ).joinToString(",") { "\"$it\"" }
            }
        }

        return (listOf(header) + rows).joinToString("\n")
    }

    fun addListener(listener: CommandHistoryListener) {
        listeners.add(listener)
    }

    fun removeListener(listener: CommandHistoryListener) {
        listeners.remove(listener)
    }

    private fun configuredMaxSize(): Int {
        return try {
            McpSettings.getInstance().maxHistorySize.coerceAtLeast(0)
        } catch (_: Exception) {
            100
        }
    }

    private fun trimHistoryLocked(maxSize: Int) {
        if (maxSize == 0) {
            history.clear()
            return
        }

        while (history.size > maxSize) {
            history.removeLast()
        }
    }

    private fun notifyListeners(event: CommandHistoryEvent) {
        ApplicationManager.getApplication().invokeLater({
            when (event) {
                is CommandHistoryEvent.CommandAdded -> {
                    listeners.forEach { it.onCommandAdded(event.entry) }
                }
                is CommandHistoryEvent.CommandUpdated -> {
                    listeners.forEach { it.onCommandUpdated(event.entry) }
                }
                is CommandHistoryEvent.HistoryCleared -> {
                    listeners.forEach { it.onHistoryCleared() }
                }
            }
        }, ModalityState.any())
    }
}
