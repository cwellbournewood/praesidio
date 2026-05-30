package io.section.edge.settings

import com.intellij.credentialStore.CredentialAttributes
import com.intellij.credentialStore.Credentials
import com.intellij.credentialStore.generateServiceName
import com.intellij.ide.passwordSafe.PasswordSafe

/**
 * Secret storage for the plugin. Wraps [PasswordSafe] so the rest of
 * the code never touches a credential string directly — easier to
 * stub in unit tests and easier to audit ("who reads the API key?").
 *
 * Two slots, both keyed on `Section` service name:
 *  - `apiKey`         — the per-gateway API key.
 *  - `oidcRefresh`    — refresh token from the device-code flow.
 *  - `oidcAccess`     — short-lived bearer used for `/v1/scan` calls.
 *
 * The slots are scoped by gateway URL because a developer who has two
 * gateways configured (e.g. dev + prod) would otherwise end up using
 * the wrong key for the wrong target. The URL is hashed into the
 * `userName` field of the credential attribute, not the service name,
 * so the OS credential manager UI groups all Section entries
 * together.
 *
 * On macOS this lands in Keychain, on Windows in the Credential
 * Manager (DPAPI), on Linux in libsecret / KeePassXC / a local
 * encrypted file depending on the user's IDE PasswordSafe configuration.
 */
class SectionCredentialStore(private val gatewayUrl: String) {

    fun setApiKey(value: String?) = store(SLOT_API_KEY, value)
    fun apiKey(): String? = read(SLOT_API_KEY)

    fun setOidcAccessToken(value: String?) = store(SLOT_OIDC_ACCESS, value)
    fun oidcAccessToken(): String? = read(SLOT_OIDC_ACCESS)

    fun setOidcRefreshToken(value: String?) = store(SLOT_OIDC_REFRESH, value)
    fun oidcRefreshToken(): String? = read(SLOT_OIDC_REFRESH)

    /** Wipe everything — invoked on sign-out and on store rotation. */
    fun clearAll() {
        store(SLOT_API_KEY, null)
        store(SLOT_OIDC_ACCESS, null)
        store(SLOT_OIDC_REFRESH, null)
    }

    /**
     * `userName` field of the [CredentialAttributes] encodes which
     * gateway URL the secret applies to, so a single PasswordSafe can
     * hold credentials for multiple gateways.
     */
    private fun attributes(slot: String): CredentialAttributes =
        CredentialAttributes(
            generateServiceName(SERVICE_BASE, slot),
            scopeKey(),
        )

    private fun scopeKey(): String =
        // URL canonicalisation lives here so callers don't have to be
        // careful about trailing slashes. We intentionally keep the
        // scheme so http://localhost:8080 and https://gw.example.com
        // are distinct credentials.
        gatewayUrl.trim().trimEnd('/').lowercase()

    private fun read(slot: String): String? {
        val safe = PasswordSafe.instance
        val creds = safe.get(attributes(slot)) ?: return null
        return creds.password?.toString()?.takeIf(String::isNotEmpty)
    }

    private fun store(slot: String, value: String?) {
        val safe = PasswordSafe.instance
        val attrs = attributes(slot)
        if (value.isNullOrEmpty()) {
            safe.set(attrs, null)
        } else {
            safe.set(attrs, Credentials(scopeKey(), value))
        }
    }

    companion object {
        const val SERVICE_BASE: String = "Section"
        const val SLOT_API_KEY: String = "apiKey"
        const val SLOT_OIDC_ACCESS: String = "oidcAccessToken"
        const val SLOT_OIDC_REFRESH: String = "oidcRefreshToken"

        /** Convenience accessor for the current settings' gateway URL. */
        @JvmStatic
        fun forCurrent(): SectionCredentialStore =
            SectionCredentialStore(SectionSettings.getInstance().gatewayUrl)
    }
}
