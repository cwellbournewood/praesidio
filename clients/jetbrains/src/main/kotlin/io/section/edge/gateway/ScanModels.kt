package io.section.edge.gateway

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Data transfer objects mirroring the Pydantic models in
 * `services/gateway/section_gateway/api/v1/scan.py`.
 *
 * Wire compatibility notes:
 *  - Snake-case is the gateway's JSON style. We use [SerialName] rather
 *    than a global naming strategy because some fields (e.g.
 *    `request_id`) are repeated under different camel-cased Kotlin
 *    names elsewhere in the codebase.
 *  - Unknown fields are ignored on deserialization — see
 *    [GatewayClient.json] — so the gateway can add fields without
 *    forcing a plugin update.
 *  - The `decision` block is left as a raw [JsonObject] because its
 *    shape is policy-dependent and the plugin only needs the action
 *    summary, which is duplicated in [ScanResponse.action] /
 *    [ScanResponse.reason] / [ScanResponse.severity].
 */

@Serializable
data class ScanRequest(
    val text: String,
    val client: String = "jetbrains",
    val url: String? = null,
    val model: String? = null,
    @SerialName("session_id") val sessionId: String? = null,
)

@Serializable
data class ScanTransform(
    val label: String,
    val placeholder: String,
    /** "tokenise" | "fpe" | "redact" */
    val method: String,
    val scope: String,
)

@Serializable
data class ScanFinding(
    val label: String,
    val detector: String,
    val confidence: Double,
    val start: Int,
    val end: Int,
)

@Serializable
data class ScanResponse(
    @SerialName("request_id") val requestId: String,
    /** "allow" | "mask" | "block" */
    val action: String,
    val sanitised: String? = null,
    val transforms: List<ScanTransform> = emptyList(),
    val findings: List<ScanFinding> = emptyList(),
    /** Policy decision block — opaque from the plugin's perspective. */
    val decision: JsonObject = JsonObject(emptyMap()),
    @SerialName("bundle_digest") val bundleDigest: String = "",
    val reason: String? = null,
    val severity: String? = null,
) {
    val isAllow: Boolean get() = action == "allow"
    val isMask: Boolean get() = action == "mask"
    val isBlock: Boolean get() = action == "block"
}

@Serializable
data class RestoreRequest(
    @SerialName("request_id") val requestId: String,
    val text: String,
)

@Serializable
data class RestoreResponse(
    @SerialName("request_id") val requestId: String,
    val text: String,
    val restored: Int = 0,
    val missing: List<String> = emptyList(),
)

/**
 * Standard error envelope used by the gateway. The handler may also
 * raise a bare FastAPI `HTTPException` whose body is `{"detail": "..."}`
 * — [GatewayClient] tolerates both shapes.
 */
@Serializable
data class GatewayError(
    val detail: String? = null,
    val message: String? = null,
    val code: String? = null,
) {
    fun bestMessage(): String =
        detail ?: message ?: code ?: "unknown gateway error"
}

/** Result wrapper that callers branch on instead of catching exceptions. */
sealed interface GatewayResult<out T> {
    data class Ok<T>(val value: T) : GatewayResult<T>
    data class Err(
        val status: Int,
        val message: String,
        val retryAfterSeconds: Long? = null,
    ) : GatewayResult<Nothing>
}
