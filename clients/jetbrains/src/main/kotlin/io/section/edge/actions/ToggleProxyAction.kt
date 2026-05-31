package io.section.edge.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import io.section.edge.actions.ScanSelectionAction.Companion.notify
import io.section.edge.proxy.ProxyController
import io.section.edge.util.SectionBundle.message

/**
 * "Section: Toggle Edge Proxy" — starts the proxy if stopped, stops
 * it if running. The actual work is delegated to [ProxyController];
 * this action exists so the gesture is discoverable from the main
 * menu / "Find Action" / keyboard shortcuts.
 */
class ToggleProxyAction : AnAction() {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun update(e: AnActionEvent) {
        val running = ProxyController.getInstance().isRunning
        e.presentation.text = if (running) {
            "Stop Edge Proxy"
        } else {
            "Start Edge Proxy"
        }
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project
        ApplicationManager.getApplication().executeOnPooledThread {
            val wasRunning = ProxyController.getInstance().isRunning
            if (!wasRunning) {
                notify(
                    project,
                    message("section.action.proxy.starting"),
                    NotificationType.INFORMATION,
                )
            }
            val newState = ProxyController.getInstance().toggle()
            ApplicationManager.getApplication().invokeLater {
                when (newState) {
                    ProxyController.ProxyState.RUNNING ->
                        notify(
                            project,
                            message(
                                "section.action.proxy.started",
                                ProxyController.DEFAULT_BINARY,
                            ),
                            NotificationType.INFORMATION,
                        )
                    ProxyController.ProxyState.STOPPED ->
                        notify(
                            project,
                            message("section.action.proxy.stopped"),
                            NotificationType.INFORMATION,
                        )
                    ProxyController.ProxyState.FAILED ->
                        notify(
                            project,
                            message(
                                "section.action.proxy.error",
                                "proxy failed to start (see idea.log)",
                            ),
                            NotificationType.ERROR,
                        )
                    ProxyController.ProxyState.STARTING -> Unit
                }
            }
        }
    }
}
