package io.praesidio.edge.actions

import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import io.praesidio.edge.gateway.GatewayResult
import io.praesidio.edge.gateway.GatewayService
import io.praesidio.edge.gateway.RecentDecisionsService
import io.praesidio.edge.gateway.ScanRequest
import io.praesidio.edge.gateway.ScanResponse
import io.praesidio.edge.util.PraesidioBundle.message

/**
 * "Praesidio: Scan Selection" — sends the current editor selection
 * to the gateway's `/v1/scan` endpoint and surfaces the decision as a
 * notification.
 *
 * Pure inspection: no edits to the document. For replacement, use
 * [TokeniseSelectionAction] instead. Splitting the two actions makes
 * the semantics obvious from the menu and avoids accidental
 * mutations from a curious "scan this" invocation.
 */
class ScanSelectionAction : AnAction() {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun update(e: AnActionEvent) {
        val editor = e.getData(CommonDataKeys.EDITOR)
        e.presentation.isEnabled = editor?.selectionModel?.hasSelection() == true
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val selection = editor.selectionModel.selectedText
        if (selection.isNullOrEmpty()) {
            notify(
                project,
                message("praesidio.action.scan.empty"),
                NotificationType.WARNING,
            )
            return
        }

        // Kick the scan off on a background progress task so the EDT
        // stays responsive even against a slow gateway. The
        // ProgressIndicator is cancellable; users can hit Escape to
        // abort if they realise they didn't mean to share this.
        object : Task.Backgroundable(project, message("praesidio.action.scan.title"), true) {
            override fun run(indicator: ProgressIndicator) {
                runScan(project, selection)
            }
        }.queue()
    }

    private fun runScan(project: Project?, selection: String) {
        val client = GatewayService.getInstance().client()
        val req = ScanRequest(
            text = selection,
            client = "jetbrains",
            model = null,
            sessionId = null,
        )
        when (val result = client.scan(req)) {
            is GatewayResult.Ok -> {
                RecentDecisionsService.getInstance().record(
                    RecentDecisionsService.fromScan(result.value, "jetbrains"),
                )
                notifyScan(project, result.value)
            }
            is GatewayResult.Err ->
                notify(
                    project,
                    message("praesidio.action.scan.error", result.message),
                    NotificationType.ERROR,
                )
        }
    }

    private fun notifyScan(project: Project?, resp: ScanResponse) {
        when {
            resp.isBlock ->
                notify(
                    project,
                    message(
                        "praesidio.action.scan.block",
                        resp.reason ?: "policy enforcement",
                    ),
                    NotificationType.ERROR,
                )
            resp.isMask ->
                notify(
                    project,
                    message("praesidio.action.scan.mask", resp.findings.size),
                    NotificationType.WARNING,
                )
            else ->
                notify(
                    project,
                    message("praesidio.action.scan.allow"),
                    NotificationType.INFORMATION,
                )
        }
    }

    companion object {
        internal fun notify(
            project: Project?,
            text: String,
            type: NotificationType,
        ) {
            val group = NotificationGroupManager.getInstance()
                .getNotificationGroup(NOTIFY_GROUP)
                ?: return
            group.createNotification(text, type).notify(project)
        }

        const val NOTIFY_GROUP: String = "Praesidio"
    }
}
