package io.praesidio.edge.actions

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent

/**
 * "Praesidio: Sign In…" — kicks off the OIDC device-code flow via
 * [SignInController]. Surfaced from the Tools → Praesidio menu and
 * from the tool window button. The action does no work itself; it
 * delegates to the controller so the same flow can be invoked from
 * the settings panel without code duplication.
 */
class SignInAction : AnAction() {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun actionPerformed(e: AnActionEvent) {
        SignInController().start()
    }
}
