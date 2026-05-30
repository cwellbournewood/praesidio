package io.section.edge.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import io.section.edge.actions.SignInController
import io.section.edge.gateway.GatewayClient
import io.section.edge.gateway.GatewayResult
import io.section.edge.util.SectionBundle.message
import java.awt.BorderLayout
import java.awt.event.ActionListener
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JSpinner
import javax.swing.SpinnerNumberModel

/**
 * Section settings panel — surfaced under
 * `File → Settings → Tools → Section` on Windows/Linux and
 * `IntelliJ IDEA → Preferences → Tools → Section` on macOS.
 *
 * Layout uses [FormBuilder] for tidy two-column rows; the password
 * field is rendered as a [JBPasswordField] so the API key doesn't leak
 * via shoulder surfing or screenshot. The actual value is only ever
 * written to / read from [SectionCredentialStore]; the textual
 * settings file stores a placeholder.
 */
class SectionConfigurable : Configurable {

    private val urlField = JBTextField()
    private val apiKeyField = JBPasswordField().apply {
        emptyText.text = message("section.settings.apiKey.placeholder")
    }
    private val tenantField = JBTextField()
    private val groupsField = JBTextField()
    private val enableInspections = JBCheckBox(
        message("section.settings.enableInspections"),
    )
    private val debounceSpinner = JSpinner(
        SpinnerNumberModel(
            SectionSettings.State.DEFAULT_DEBOUNCE_MS,
            SectionSettings.State.MIN_DEBOUNCE_MS,
            SectionSettings.State.MAX_DEBOUNCE_MS,
            50,
        ),
    )
    private val proxyAutostart = JBCheckBox(
        message("section.settings.proxyAutostart"),
    )
    private val proxyBinaryPathField = TextFieldWithBrowseButton().apply {
        textField.let {
            if (it is JBTextField) {
                it.emptyText.text = message("section.settings.proxyBinaryPath.placeholder")
            }
        }
    }

    private val signedInLabel = JBLabel("")
    private val signInButton = JButton(message("section.settings.signIn"))
    private val signOutButton = JButton(message("section.settings.signOut"))
    private val testButton = JButton(message("section.settings.testConnection"))

    // Reference held during the panel's lifetime so apply() and reset()
    // share a single source of truth for "what was loaded".
    private var loaded: SectionSettings.State = SectionSettings.getInstance().snapshot()
    private var loadedApiKey: String = SectionCredentialStore(loaded.gatewayUrl).apiKey().orEmpty()

    private var panel: JPanel? = null

    override fun getDisplayName(): String =
        message("section.settings.displayName")

    override fun getHelpTopic(): String = "io.section.edge.settings"

    override fun createComponent(): JComponent {
        // Pre-populate from current settings.
        urlField.text = loaded.gatewayUrl
        apiKeyField.text = loadedApiKey
        tenantField.text = loaded.tenant
        groupsField.text = loaded.groups
        enableInspections.isSelected = loaded.enableInspections
        debounceSpinner.value = loaded.inspectionDebounceMs
        proxyAutostart.isSelected = loaded.proxyAutostart
        proxyBinaryPathField.text = loaded.proxyBinaryPath
        refreshSignInLabel()

        signInButton.addActionListener(handleSignIn())
        signOutButton.addActionListener(handleSignOut())
        testButton.addActionListener(handleTestConnection())

        val authRow = JPanel().apply {
            add(signInButton)
            add(signOutButton)
            add(signedInLabel)
        }

        val form = FormBuilder.createFormBuilder()
            .addLabeledComponent(message("section.settings.gatewayUrl"), urlField)
            .addTooltip(message("section.settings.gatewayUrl.help"))
            .addLabeledComponent(message("section.settings.apiKey"), apiKeyField)
            .addTooltip(message("section.settings.apiKey.help"))
            .addLabeledComponent(message("section.settings.tenant"), tenantField)
            .addLabeledComponent("Groups", groupsField)
            .addComponent(authRow)
            .addSeparator()
            .addComponent(enableInspections)
            .addTooltip(message("section.settings.enableInspections.help"))
            .addLabeledComponent(message("section.settings.inspectionDebounceMs"), debounceSpinner)
            .addTooltip(message("section.settings.inspectionDebounceMs.help"))
            .addSeparator()
            .addComponent(proxyAutostart)
            .addLabeledComponent(message("section.settings.proxyBinaryPath"), proxyBinaryPathField)
            .addTooltip(message("section.settings.proxyBinaryPath.help"))
            .addSeparator()
            .addComponent(testButton)
            .addComponentFillVertically(JPanel(), 0)
            .panel

        val root = JPanel().apply {
            border = JBUI.Borders.empty(10)
            layout = BorderLayout()
            add(form, BorderLayout.NORTH)
        }
        panel = root
        return root
    }

    override fun isModified(): Boolean {
        val current = SectionSettings.getInstance().snapshot()
        val currentApiKey = SectionCredentialStore(current.gatewayUrl).apiKey().orEmpty()
        return urlField.text.trim() != current.gatewayUrl ||
            String(apiKeyField.password) != currentApiKey ||
            tenantField.text.trim() != current.tenant ||
            groupsField.text.trim() != current.groups ||
            enableInspections.isSelected != current.enableInspections ||
            (debounceSpinner.value as Int) != current.inspectionDebounceMs ||
            proxyAutostart.isSelected != current.proxyAutostart ||
            proxyBinaryPathField.text.trim() != current.proxyBinaryPath
    }

    override fun apply() {
        val settings = SectionSettings.getInstance()
        val oldUrl = settings.gatewayUrl
        val newUrl = urlField.text.trim().ifBlank { SectionSettings.DEFAULT_GATEWAY_URL }
        settings.update {
            it.gatewayUrl = newUrl
            it.tenant = tenantField.text.trim()
            it.groups = groupsField.text.trim()
            it.enableInspections = enableInspections.isSelected
            it.inspectionDebounceMs = debounceSpinner.value as Int
            it.proxyAutostart = proxyAutostart.isSelected
            it.proxyBinaryPath = proxyBinaryPathField.text.trim()
        }
        // Persist API key under the new URL's scope. If the URL
        // changed, rotate: write to new, clear old (otherwise stale
        // credentials linger in the OS keychain).
        val key = String(apiKeyField.password)
        val store = SectionCredentialStore(newUrl)
        store.setApiKey(key.ifBlank { null })
        if (oldUrl != newUrl) {
            SectionCredentialStore(oldUrl).clearAll()
        }
        // Force a fresh load of the in-panel "loaded" snapshot so
        // isModified() reports the truth on the next compare.
        loaded = settings.snapshot()
        loadedApiKey = key
    }

    override fun reset() {
        loaded = SectionSettings.getInstance().snapshot()
        loadedApiKey = SectionCredentialStore(loaded.gatewayUrl).apiKey().orEmpty()
        urlField.text = loaded.gatewayUrl
        apiKeyField.text = loadedApiKey
        tenantField.text = loaded.tenant
        groupsField.text = loaded.groups
        enableInspections.isSelected = loaded.enableInspections
        debounceSpinner.value = loaded.inspectionDebounceMs
        proxyAutostart.isSelected = loaded.proxyAutostart
        proxyBinaryPathField.text = loaded.proxyBinaryPath
        refreshSignInLabel()
    }

    override fun disposeUIResources() {
        panel = null
    }

    private fun refreshSignInLabel() {
        val s = loaded
        signedInLabel.text = if (s.signedInAs.isNotEmpty()) {
            message("section.settings.signedInAs", s.signedInAs)
        } else {
            ""
        }
        signOutButton.isEnabled = s.signedInAs.isNotEmpty()
    }

    private fun handleSignIn(): ActionListener = ActionListener {
        // Persist any URL change first so the sign-in flow targets the
        // intended gateway.
        if (urlField.text.trim() != loaded.gatewayUrl) {
            apply()
        }
        val controller = SignInController()
        // The controller pops its own dialog with the device-code; we
        // just need to refresh on completion.
        controller.start { ok ->
            ApplicationManager.getApplication().invokeLater {
                if (ok) {
                    loaded = SectionSettings.getInstance().snapshot()
                    loadedApiKey = SectionCredentialStore(loaded.gatewayUrl).apiKey().orEmpty()
                    apiKeyField.text = loadedApiKey
                    refreshSignInLabel()
                }
            }
        }
    }

    private fun handleSignOut(): ActionListener = ActionListener {
        SectionSettings.getInstance().update {
            it.signedInAs = ""
            it.oidcIssuer = ""
        }
        SectionCredentialStore(urlField.text.trim()).let {
            it.setOidcAccessToken(null)
            it.setOidcRefreshToken(null)
        }
        loaded = SectionSettings.getInstance().snapshot()
        refreshSignInLabel()
    }

    private fun handleTestConnection(): ActionListener = ActionListener {
        val url = urlField.text.trim()
        if (url.isEmpty()) {
            Messages.showErrorDialog(panel, "Gateway URL is empty.", "Section")
            return@ActionListener
        }
        val apiKey = String(apiKeyField.password)
        val auth = when {
            apiKey.isNotEmpty() -> GatewayClient.Auth.ApiKey(apiKey)
            else -> GatewayClient.Auth.None
        }
        val client = GatewayClient(
            baseUrl = url,
            auth = auth,
            tenant = tenantField.text.trim().ifEmpty { null },
            userId = loaded.userId.ifEmpty { null },
            groups = groupsField.text
                .split(',')
                .map(String::trim)
                .filter(String::isNotEmpty),
        )
        // Run off the EDT — the test button is allowed to spin for a
        // few seconds without freezing settings.
        ApplicationManager.getApplication().executeOnPooledThread {
            val result = client.ping()
            ApplicationManager.getApplication().invokeLater {
                when (result) {
                    is GatewayResult.Ok -> Messages.showInfoMessage(
                        panel,
                        message("section.settings.testConnection.ok", result.value),
                        "Section",
                    )
                    is GatewayResult.Err -> Messages.showErrorDialog(
                        panel,
                        message("section.settings.testConnection.err", result.message),
                        "Section",
                    )
                }
            }
        }
    }
}
