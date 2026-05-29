package io.praesidio.edge.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.util.xmlb.XmlSerializerUtil

/**
 * Persistent, application-level settings for the Praesidio plugin.
 *
 * Stored in `<config-dir>/options/praesidio.xml`. Sensitive material
 * (API key, OIDC refresh token) lives in [PraesidioCredentialStore]
 * instead — this class only persists toggles, URLs, and non-secret
 * identifiers.
 *
 * Why application-level (not project-level): the gateway URL and
 * authentication are properties of the developer's machine, not of a
 * single project. Project-scoped settings would mean a developer
 * working on three repos has to re-authenticate three times. This
 * mirrors how IntelliJ's own VCS/HTTP proxy settings are scoped.
 */
@State(
    name = "PraesidioSettings",
    storages = [Storage("praesidio.xml")],
)
@Service(Service.Level.APP)
class PraesidioSettings : PersistentStateComponent<PraesidioSettings.State> {

    /** Serialised state. Keep field names stable — these end up in XML. */
    class State {
        /** Gateway base URL — e.g. `https://gateway.acme.example/`. */
        @JvmField
        var gatewayUrl: String = DEFAULT_GATEWAY_URL

        /** Tenant header — overridden by JWT claim when signed-in via OIDC. */
        @JvmField
        var tenant: String = ""

        /**
         * User id surfaced to the gateway as `X-Praesidio-User` when
         * not using a bearer token. Defaults to the operator's local
         * username on first launch so dev gateways auth out of the box.
         */
        @JvmField
        var userId: String = System.getProperty("user.name", "").trim()

        /** Comma-separated group claims. */
        @JvmField
        var groups: String = ""

        /** Friendly display string shown in the tool window after sign-in. */
        @JvmField
        var signedInAs: String = ""

        /** When non-empty, the [SignInAction] used OIDC and stored a token. */
        @JvmField
        var oidcIssuer: String = ""

        /** Whether the inspection should run on open documents. */
        @JvmField
        var enableInspections: Boolean = true

        /**
         * Debounce window between document changes before re-scanning
         * — must be >= 100ms to avoid hammering the gateway during
         * fast typing. UI clamps the input box too.
         */
        @JvmField
        var inspectionDebounceMs: Int = DEFAULT_DEBOUNCE_MS

        /** Auto-start the edge proxy when the IDE launches. */
        @JvmField
        var proxyAutostart: Boolean = false

        /** Edge-proxy binary path. Blank means "use PATH". */
        @JvmField
        var proxyBinaryPath: String = ""

        /**
         * Edge-proxy CLI args (excluding the binary name and the
         * `--gateway <url>` pair, which [ProxyController.buildCommand]
         * injects automatically based on [gatewayUrl]). Each token is
         * one element to avoid shell quoting issues.
         */
        @JvmField
        var proxyArgs: MutableList<String> = mutableListOf("start")

        /** Hard ceiling for the number of recent decisions to remember in memory. */
        @JvmField
        var recentDecisionsLimit: Int = DEFAULT_RECENT_LIMIT

        companion object {
            const val DEFAULT_GATEWAY_URL = "http://127.0.0.1:8080"
            const val DEFAULT_DEBOUNCE_MS = 750
            const val DEFAULT_RECENT_LIMIT = 25
            const val MIN_DEBOUNCE_MS = 100
            const val MAX_DEBOUNCE_MS = 30_000
        }
    }

    private var state: State = State()

    /** Read accessor — returned object is shared, callers must NOT mutate. */
    fun snapshot(): State {
        // Defensive copy — settings UI commits via setState which
        // installs a fresh State; consumers should never mutate the
        // live object lest they bypass [validate].
        return State().also { XmlSerializerUtil.copyBean(state, it) }
    }

    val gatewayUrl: String get() = state.gatewayUrl
    val tenant: String get() = state.tenant
    val userId: String get() = state.userId
    val groups: List<String>
        get() = state.groups
            .split(',')
            .map(String::trim)
            .filter(String::isNotEmpty)
    val signedInAs: String get() = state.signedInAs
    val oidcIssuer: String get() = state.oidcIssuer
    val enableInspections: Boolean get() = state.enableInspections
    val inspectionDebounceMs: Int
        get() = state.inspectionDebounceMs.coerceIn(
            State.MIN_DEBOUNCE_MS,
            State.MAX_DEBOUNCE_MS,
        )
    val proxyAutostart: Boolean get() = state.proxyAutostart
    val proxyBinaryPath: String get() = state.proxyBinaryPath
    val proxyArgs: List<String> get() = state.proxyArgs.toList()
    val recentDecisionsLimit: Int
        get() = state.recentDecisionsLimit.coerceIn(1, 200)

    /**
     * Commit fresh state — called by [PraesidioConfigurable.apply].
     * Validates and normalises before storing.
     */
    fun update(mutator: (State) -> Unit) {
        val draft = snapshot()
        mutator(draft)
        validate(draft)
        state = draft
    }

    override fun getState(): State = state

    override fun loadState(state: State) {
        validate(state)
        this.state = state
    }

    /** Defensive cleanup of values that survived bad migrations. */
    private fun validate(s: State) {
        if (s.gatewayUrl.isBlank()) s.gatewayUrl = State.DEFAULT_GATEWAY_URL
        s.gatewayUrl = s.gatewayUrl.trim()
        if (s.inspectionDebounceMs < State.MIN_DEBOUNCE_MS) {
            s.inspectionDebounceMs = State.MIN_DEBOUNCE_MS
        } else if (s.inspectionDebounceMs > State.MAX_DEBOUNCE_MS) {
            s.inspectionDebounceMs = State.MAX_DEBOUNCE_MS
        }
        if (s.recentDecisionsLimit < 1) s.recentDecisionsLimit = State.DEFAULT_RECENT_LIMIT
    }

    companion object {
        const val DEFAULT_GATEWAY_URL: String = State.DEFAULT_GATEWAY_URL

        /** Application-service accessor. */
        @JvmStatic
        fun getInstance(): PraesidioSettings =
            ApplicationManager.getApplication().getService(PraesidioSettings::class.java)
    }
}
