package io.praesidio.edge.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import io.praesidio.edge.actions.ScanSelectionAction.Companion.notify
import io.praesidio.edge.gateway.GatewayResult
import io.praesidio.edge.gateway.GatewayService
import io.praesidio.edge.gateway.RecentDecisionsService
import io.praesidio.edge.gateway.ScanRequest
import io.praesidio.edge.gateway.ScanResponse
import io.praesidio.edge.util.PraesidioBundle.message

/**
 * "Praesidio: Tokenise Selection" — scans the selection and, if the
 * gateway returns a `mask` decision, replaces the selection with the
 * sanitised string in a single undo-able edit.
 *
 * A block decision leaves the buffer untouched and shows an error.
 * An allow decision shows an "allowed" notification and also leaves
 * the buffer untouched — there's nothing to replace.
 *
 * The replacement runs inside a [WriteCommandAction] on the EDT so it
 * folds into one undo step and respects the project's read/write lock
 * protocol. The HTTP call itself happens on a pooled thread.
 */
class TokeniseSelectionAction : AnAction() {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun update(e: AnActionEvent) {
        val editor = e.getData(CommonDataKeys.EDITOR)
        e.presentation.isEnabled =
            editor != null &&
            !editor.isViewer &&
            editor.selectionModel.hasSelection()
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR) ?: return
        val selStart = editor.selectionModel.selectionStart
        val selEnd = editor.selectionModel.selectionEnd
        val selection = editor.selectionModel.selectedText
        if (selection.isNullOrEmpty()) {
            notify(
                project,
                message("praesidio.action.tokenise.nothing"),
                NotificationType.WARNING,
            )
            return
        }

        object : Task.Backgroundable(project, message("praesidio.action.scan.title"), true) {
            override fun run(indicator: ProgressIndicator) {
                runTokenise(project, editor, selStart, selEnd, selection)
            }
        }.queue()
    }

    private fun runTokenise(
        project: Project,
        editor: Editor,
        selStart: Int,
        selEnd: Int,
        selection: String,
    ) {
        val client = GatewayService.getInstance().client()
        val req = ScanRequest(text = selection, client = "jetbrains")
        when (val result = client.scan(req)) {
            is GatewayResult.Ok -> {
                RecentDecisionsService.getInstance().record(
                    RecentDecisionsService.fromScan(result.value, "jetbrains"),
                )
                applyResult(project, editor, selStart, selEnd, result.value)
            }
            is GatewayResult.Err ->
                notify(
                    project,
                    message("praesidio.action.scan.error", result.message),
                    NotificationType.ERROR,
                )
        }
    }

    private fun applyResult(
        project: Project,
        editor: Editor,
        selStart: Int,
        selEnd: Int,
        resp: ScanResponse,
    ) {
        if (resp.isBlock) {
            notify(
                project,
                message("praesidio.action.tokenise.blocked"),
                NotificationType.ERROR,
            )
            return
        }
        val sanitised = resp.sanitised
        if (resp.isAllow || sanitised == null ||
            sanitised == editor.document.getText(TextRange(selStart, selEnd))
        ) {
            notify(
                project,
                message("praesidio.action.scan.allow"),
                NotificationType.INFORMATION,
            )
            return
        }
        ApplicationManager.getApplication().invokeLater {
            WriteCommandAction.runWriteCommandAction(project, "Praesidio: Tokenise", null, {
                // Double-check the selection still aligns with the
                // document length — racy edits could have shrunk the
                // doc between scheduling and apply.
                val docLen = editor.document.textLength
                if (selStart in 0..docLen && selEnd in selStart..docLen) {
                    editor.document.replaceString(selStart, selEnd, sanitised)
                }
            })
            notify(
                project,
                message("praesidio.action.tokenise.replaced", resp.transforms.size),
                NotificationType.INFORMATION,
            )
        }
    }
}
