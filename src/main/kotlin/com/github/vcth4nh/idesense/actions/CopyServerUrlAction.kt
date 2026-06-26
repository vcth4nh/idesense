package com.github.vcth4nh.idesense.actions

import com.github.vcth4nh.idesense.McpBundle
import com.github.vcth4nh.idesense.McpConstants
import com.github.vcth4nh.idesense.server.McpServerService
import com.intellij.icons.AllIcons
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ide.CopyPasteManager
import java.awt.datatransfer.StringSelection

class CopyServerUrlAction : AnAction(
    McpBundle.message("toolWindow.copyUrl"),
    "Copy the MCP server URL to clipboard",
    AllIcons.Actions.Copy
) {
    override fun actionPerformed(e: AnActionEvent) {
        val url = McpServerService.getInstance().getServerUrl()
        CopyPasteManager.getInstance().setContents(StringSelection(url))

        NotificationGroupManager.getInstance()
            .getNotificationGroup(McpConstants.NOTIFICATION_GROUP_ID)
            .createNotification(
                McpBundle.message("notification.urlCopied"),
                NotificationType.INFORMATION
            )
            .notify(e.project)
    }
}
