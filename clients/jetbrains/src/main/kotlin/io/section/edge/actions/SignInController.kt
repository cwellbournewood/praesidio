package io.section.edge.actions

import com.intellij.ide.BrowserUtil
import com.intellij.notification.NotificationType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.util.NlsContexts
import io.section.edge.actions.ScanSelectionAction.Companion.notify
import io.section.edge.settings.SectionCredentialStore
import io.section.edge.settings.SectionSettings
import io.section.edge.util.SectionBundle.message
import io.section.edge.util.logger
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.IOException
import java.time.Duration
import java.util.Base64

/**
 * Orchestrates the RFC 8628 OAuth 2.0 Device Authorization Grant flow
 * against the gateway. The gateway is expected to expose:
 *
 *   POST {issuer}/device_authorization
 *   POST {issuer}/token (grant_type=urn:ietf:params:oauth:grant-type:device_code)
 *
 * Both endpoints are documented in `docs/auth/oidc.md`. The OIDC
 * issuer is discovered from `{gateway}/.well-known/section-edge`.
 *
 * On success:
 *  - access token → keychain (slot `oidcAccessToken`)
 *  - refresh token → keychain (slot `oidcRefreshToken`)
 *  - displayable identity (`preferred_username` claim, if present) →
 *    settings.signedInAs
 *
 * On failure: notification, no state mutation.
 *
 * The `onComplete` callback runs on a pooled thread and receives
 * `true` if the flow ended with credentials in the keychain. Callers
 * that update UI on success must hop to the EDT themselves.
 */
class SignInController(
    private val httpClient: OkHttpClient = defaultHttpClient(),
    private val json: Json = Json { ignoreUnknownKeys = true; isLenient = true },
) {

    private val log = logger<SignInController>()

    fun start(onComplete: (Boolean) -> Unit = {}) {
        ProgressManager.getInstance().run(
            object : Task.Backgroundable(
                null,
                @Suppress("DialogTitleCapitalization") title(),
                true,
            ) {
                override fun run(indicator: ProgressIndicator) {
                    val ok = runFlow(indicator)
                    onComplete(ok)
                }
            },
        )
    }

    @NlsContexts.DialogTitle
    private fun title(): String = message("section.action.signin.title")

    private fun runFlow(indicator: ProgressIndicator): Boolean {
        val settings = SectionSettings.getInstance()
        val gateway = settings.gatewayUrl.trimEnd('/')

        // 1) Discover OIDC config.
        val discovery = try {
            fetchDiscovery(gateway)
        } catch (ex: IOException) {
            notifyError(ex.message)
            return false
        }
        indicator.text = "Requesting device code…"

        // 2) Request device + user codes.
        val auth = try {
            requestDeviceCode(discovery)
        } catch (ex: IOException) {
            notifyError(ex.message)
            return false
        }

        // 3) Open the browser and show the user-friendly code in a
        //    modal dialog. We do this on the EDT because Swing.
        ApplicationManager.getApplication().invokeLater {
            BrowserUtil.browse(auth.verificationUriComplete ?: auth.verificationUri)
            Messages.showInfoMessage(
                message(
                    "section.action.signin.deviceCode",
                    auth.verificationUri,
                    auth.userCode,
                ),
                title(),
            )
        }

        // 4) Poll for token. Per RFC 8628 we honour `interval` and
        //    re-poll on `authorization_pending`; back off on
        //    `slow_down`; abort on anything else.
        var interval = (auth.interval ?: 5).coerceAtLeast(1)
        val deadline = System.currentTimeMillis() + (auth.expiresIn ?: 600).coerceAtLeast(60) * 1000L
        while (System.currentTimeMillis() < deadline) {
            indicator.checkCanceled()
            indicator.text = "Waiting for browser approval…"
            Thread.sleep(interval * 1000L)
            val token = pollToken(discovery, auth.deviceCode)
            when (token) {
                is TokenPollResult.Success -> {
                    storeCredentials(settings, gateway, token, discovery)
                    notify(
                        null,
                        message(
                            "section.action.signin.success",
                            SectionSettings.getInstance().signedInAs,
                        ),
                        NotificationType.INFORMATION,
                    )
                    return true
                }
                TokenPollResult.AuthorizationPending -> continue
                TokenPollResult.SlowDown -> interval += 5
                is TokenPollResult.Failed -> {
                    notifyError(token.message)
                    return false
                }
            }
        }
        notifyError("device-code flow timed out")
        return false
    }

    private fun fetchDiscovery(gateway: String): Discovery {
        val req = Request.Builder()
            .url("$gateway/.well-known/section-edge")
            .get()
            .header("Accept", "application/json")
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) {
                throw IOException("OIDC discovery failed: HTTP ${resp.code}")
            }
            return json.decodeFromString(Discovery.serializer(), body)
        }
    }

    private fun requestDeviceCode(d: Discovery): DeviceAuthResponse {
        val body = FormBody.Builder()
            .add("client_id", d.clientId ?: "section-edge")
            .add("scope", d.scope ?: "openid profile email")
            .build()
        val req = Request.Builder()
            .url(d.deviceAuthorizationEndpoint)
            .post(body)
            .header("Accept", "application/json")
            .build()
        httpClient.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) {
                throw IOException("device_authorization failed: HTTP ${resp.code} $text")
            }
            return json.decodeFromString(DeviceAuthResponse.serializer(), text)
        }
    }

    private fun pollToken(d: Discovery, deviceCode: String): TokenPollResult {
        val body = FormBody.Builder()
            .add("client_id", d.clientId ?: "section-edge")
            .add("grant_type", "urn:ietf:params:oauth:grant-type:device_code")
            .add("device_code", deviceCode)
            .build()
        val req = Request.Builder()
            .url(d.tokenEndpoint)
            .post(body)
            .header("Accept", "application/json")
            .build()
        return try {
            httpClient.newCall(req).execute().use { resp ->
                val text = resp.body?.string().orEmpty()
                if (resp.isSuccessful) {
                    val parsed = json.decodeFromString(TokenResponse.serializer(), text)
                    TokenPollResult.Success(parsed)
                } else {
                    // Try to parse an RFC 6749 error envelope.
                    val err = runCatching {
                        json.decodeFromString(TokenError.serializer(), text)
                    }.getOrNull()
                    when (err?.error) {
                        "authorization_pending" -> TokenPollResult.AuthorizationPending
                        "slow_down" -> TokenPollResult.SlowDown
                        else -> TokenPollResult.Failed(
                            err?.errorDescription ?: err?.error ?: "HTTP ${resp.code}",
                        )
                    }
                }
            }
        } catch (ex: IOException) {
            TokenPollResult.Failed(ex.message ?: "network error")
        }
    }

    private fun storeCredentials(
        settings: SectionSettings,
        gateway: String,
        token: TokenPollResult.Success,
        d: Discovery,
    ) {
        val store = SectionCredentialStore(gateway)
        store.setOidcAccessToken(token.token.accessToken)
        token.token.refreshToken?.let { store.setOidcRefreshToken(it) }
        // Best-effort identity from the ID-token claims. We do not
        // validate the signature here — gateway does that on every
        // call — but we do extract `preferred_username` for the UI.
        val display = extractUsername(token.token.idToken)
            ?: token.token.accessToken.take(8) + "…"
        settings.update {
            it.signedInAs = display
            it.oidcIssuer = d.issuer ?: gateway
        }
        log.info("OIDC sign-in complete; identity=$display")
    }

    private fun extractUsername(idToken: String?): String? {
        if (idToken.isNullOrEmpty()) return null
        // JWT body is `header.payload.signature` (base64url-encoded JSON).
        // We only need the payload's `preferred_username` (or `email`,
        // or `sub`) claim to populate the "Signed in as" label — full
        // signature verification is the gateway's job.
        val parts = idToken.split('.')
        if (parts.size < 2) return null
        return try {
            val payload = Base64.getUrlDecoder().decode(parts[1])
            val parsed = json.parseToJsonElement(payload.toString(Charsets.UTF_8))
            val obj = parsed as? JsonObject ?: return null
            val candidate = obj["preferred_username"] ?: obj["email"] ?: obj["sub"]
            (candidate as? JsonPrimitive)?.content
        } catch (_: Throwable) {
            null
        }
    }

    private fun notifyError(text: String?) {
        notify(
            null,
            message("section.action.signin.error", text ?: "unknown error"),
            NotificationType.ERROR,
        )
    }

    // -------- DTOs --------

    @Serializable
    data class Discovery(
        val issuer: String? = null,
        @SerialName("device_authorization_endpoint") val deviceAuthorizationEndpoint: String,
        @SerialName("token_endpoint") val tokenEndpoint: String,
        @SerialName("client_id") val clientId: String? = null,
        val scope: String? = null,
    )

    @Serializable
    data class DeviceAuthResponse(
        @SerialName("device_code") val deviceCode: String,
        @SerialName("user_code") val userCode: String,
        @SerialName("verification_uri") val verificationUri: String,
        @SerialName("verification_uri_complete") val verificationUriComplete: String? = null,
        @SerialName("expires_in") val expiresIn: Int? = 600,
        val interval: Int? = 5,
    )

    @Serializable
    data class TokenResponse(
        @SerialName("access_token") val accessToken: String,
        @SerialName("refresh_token") val refreshToken: String? = null,
        @SerialName("id_token") val idToken: String? = null,
        @SerialName("token_type") val tokenType: String? = null,
        @SerialName("expires_in") val expiresIn: Int? = null,
        val scope: String? = null,
    )

    @Serializable
    data class TokenError(
        val error: String,
        @SerialName("error_description") val errorDescription: String? = null,
    )

    sealed interface TokenPollResult {
        data class Success(val token: TokenResponse) : TokenPollResult
        object AuthorizationPending : TokenPollResult
        object SlowDown : TokenPollResult
        data class Failed(val message: String) : TokenPollResult
    }

    companion object {
        internal fun defaultHttpClient(): OkHttpClient =
            OkHttpClient.Builder()
                .connectTimeout(Duration.ofSeconds(5))
                .readTimeout(Duration.ofSeconds(15))
                .writeTimeout(Duration.ofSeconds(10))
                .build()
    }
}
