package io.praesidio.edge.gateway

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import io.praesidio.edge.settings.PraesidioCredentialStore
import io.praesidio.edge.settings.PraesidioSettings

/**
 * Application-level service that hands out [GatewayClient] instances
 * configured from the current settings + credential store.
 *
 * Why a service: callers (actions, inspection, tool window) all need a
 * client wired with the same authentication; cluttering each call site
 * with the same wiring code makes refactors harder. Services also let
 * us swap in a mock client during testing — see [GatewayClientTest].
 */
@Service(Service.Level.APP)
class GatewayService {

    /** Build a fresh client snapshot — never cache across requests. */
    fun client(): GatewayClient {
        val settings = PraesidioSettings.getInstance()
        val store = PraesidioCredentialStore(settings.gatewayUrl)

        // Prefer OIDC access token when present; fall back to API key;
        // fall back to header-only mode if neither is configured (dev
        // installs against a `--auth-mode dev` gateway).
        val auth: GatewayClient.Auth = run {
            val bearer = store.oidcAccessToken()
            if (!bearer.isNullOrEmpty()) return@run GatewayClient.Auth.Bearer(bearer)
            val apiKey = store.apiKey()
            if (!apiKey.isNullOrEmpty()) return@run GatewayClient.Auth.ApiKey(apiKey)
            GatewayClient.Auth.None
        }

        return GatewayClient(
            baseUrl = settings.gatewayUrl,
            auth = auth,
            tenant = settings.tenant.ifEmpty { null },
            userId = settings.userId.ifEmpty { null },
            groups = settings.groups,
        )
    }

    companion object {
        @JvmStatic
        fun getInstance(): GatewayService =
            ApplicationManager.getApplication().getService(GatewayService::class.java)
    }
}
