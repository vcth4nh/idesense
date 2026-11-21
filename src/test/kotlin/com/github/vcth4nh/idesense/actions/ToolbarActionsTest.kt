package com.github.vcth4nh.idesense.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.testFramework.fixtures.BasePlatformTestCase

class ToolbarActionsTest : BasePlatformTestCase() {

    // An action that overrides update() and not getActionUpdateThread() updates on the EDT, and
    // each update of the toolbar then waits for the EDT (#128).
    fun testTheToolbarActionsUpdateOnABackgroundThread() {
        for (action in listOf(ClearHistoryAction(), ExportHistoryAction(), RefreshAction())) {
            assertEquals(action.javaClass.simpleName, ActionUpdateThread.BGT, action.actionUpdateThread)
        }
    }
}
