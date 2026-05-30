package io.section.edge.gateway

import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.time.Duration

/**
 * Black-box tests against a [MockWebServer] — no IntelliJ Platform
 * dependencies, so this suite runs under plain `./gradlew test`
 * without booting the heavy platform test harness.
 *
 * The contract we're protecting:
 *  - Outbound JSON matches the gateway's Pydantic schema.
 *  - Auth + tenant headers go on every request.
 *  - 4xx/5xx are surfaced as [GatewayResult.Err] with a useful
 *    message and the Retry-After header parsed when present.
 *  - Unknown JSON fields don't break parsing (forwards compat).
 */
class GatewayClientTest {

    private lateinit var server: MockWebServer

    @BeforeEach
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @AfterEach
    fun tearDown() {
        server.shutdown()
    }

    private fun client(
        auth: GatewayClient.Auth = GatewayClient.Auth.None,
        tenant: String? = "acme",
        userId: String? = "alice@acme.example",
        groups: List<String> = listOf("dev", "security"),
    ): GatewayClient = GatewayClient(
        baseUrl = server.url("/").toString().trimEnd('/'),
        auth = auth,
        tenant = tenant,
        userId = userId,
        groups = groups,
        httpClient = OkHttpClient.Builder()
            .callTimeout(Duration.ofSeconds(5))
            .build(),
    )

    @Test
    fun `scan with mask decision parses fully`() {
        val body = """
            {
              "request_id": "9b2c-abc",
              "action": "mask",
              "sanitised": "send to <ACCOUNT_NUMBER_A4F2>",
              "transforms": [
                {
                  "label": "regex.account_number",
                  "placeholder": "<ACCOUNT_NUMBER_A4F2>",
                  "method": "tokenise",
                  "scope": "request"
                }
              ],
              "findings": [
                {
                  "label": "ACCOUNT_NUMBER",
                  "detector": "regex.account_number",
                  "confidence": 0.95,
                  "start": 8,
                  "end": 13
                }
              ],
              "decision": {"action":"transform","effective_action":"transform"},
              "bundle_digest": "deadbeef"
            }
        """.trimIndent()
        server.enqueue(MockResponse().setBody(body).setHeader("Content-Type", "application/json"))

        val result = client(GatewayClient.Auth.ApiKey("k1")).scan(
            ScanRequest(text = "send to 12345", client = "jetbrains"),
        )

        assertThat(result).isInstanceOf(GatewayResult.Ok::class.java)
        val resp = (result as GatewayResult.Ok).value
        assertThat(resp.action).isEqualTo("mask")
        assertThat(resp.isMask).isTrue()
        assertThat(resp.transforms).hasSize(1)
        assertThat(resp.transforms[0].placeholder).isEqualTo("<ACCOUNT_NUMBER_A4F2>")
        assertThat(resp.findings[0].label).isEqualTo("ACCOUNT_NUMBER")
        assertThat(resp.bundleDigest).isEqualTo("deadbeef")
    }

    @Test
    fun `scan sends API key, tenant, and groups headers`() {
        server.enqueue(MockResponse().setBody(allowResponse()))

        client(GatewayClient.Auth.ApiKey("test-key-xyz")).scan(
            ScanRequest(text = "hello", client = "jetbrains"),
        )

        val recorded = server.takeRequest()
        assertThat(recorded.method).isEqualTo("POST")
        assertThat(recorded.path).isEqualTo("/v1/scan")
        assertThat(recorded.getHeader("X-API-Key")).isEqualTo("test-key-xyz")
        assertThat(recorded.getHeader("Authorization")).isNull()
        assertThat(recorded.getHeader("X-Section-Tenant")).isEqualTo("acme")
        assertThat(recorded.getHeader("X-Section-User")).isEqualTo("alice@acme.example")
        assertThat(recorded.getHeader("X-Section-Groups")).isEqualTo("dev,security")
        assertThat(recorded.getHeader("Content-Type")).contains("application/json")
        assertThat(recorded.getHeader("User-Agent"))
            .startsWith(GatewayClient.USER_AGENT.substringBefore('/'))
    }

    @Test
    fun `scan with bearer token uses Authorization header instead of X-API-Key`() {
        server.enqueue(MockResponse().setBody(allowResponse()))

        client(GatewayClient.Auth.Bearer("opaque.access.token")).scan(
            ScanRequest(text = "hello"),
        )

        val recorded = server.takeRequest()
        assertThat(recorded.getHeader("Authorization")).isEqualTo("Bearer opaque.access.token")
        assertThat(recorded.getHeader("X-API-Key")).isNull()
    }

    @Test
    fun `scan body uses snake_case session_id field`() {
        server.enqueue(MockResponse().setBody(allowResponse()))

        client().scan(
            ScanRequest(
                text = "x",
                client = "jetbrains",
                sessionId = "sess-1",
                model = "gpt-4o",
                url = "https://chatgpt.com/c/abc",
            ),
        )

        val recorded = server.takeRequest()
        val body = recorded.body.readUtf8()
        assertThat(body).contains("\"session_id\":\"sess-1\"")
        assertThat(body).contains("\"model\":\"gpt-4o\"")
        assertThat(body).contains("\"client\":\"jetbrains\"")
        assertThat(body).contains("\"url\":\"https://chatgpt.com/c/abc\"")
    }

    @Test
    fun `scan with null model omits the field entirely`() {
        // Pydantic accepts model=null, but cleaner audit rows want the
        // field absent so the gateway uses its own default "section-edge".
        server.enqueue(MockResponse().setBody(allowResponse()))

        client().scan(ScanRequest(text = "y"))

        val body = server.takeRequest().body.readUtf8()
        assertThat(body).doesNotContain("\"model\":null")
        assertThat(body).doesNotContain("\"url\":null")
    }

    @Test
    fun `scan returns Err with retry-after on 429`() {
        server.enqueue(
            MockResponse()
                .setResponseCode(429)
                .setHeader("Retry-After", "30")
                .setBody("""{"detail":"rate limited"}"""),
        )

        val result = client().scan(ScanRequest(text = "z"))

        assertThat(result).isInstanceOf(GatewayResult.Err::class.java)
        val err = result as GatewayResult.Err
        assertThat(err.status).isEqualTo(429)
        assertThat(err.message).contains("rate limited")
        assertThat(err.retryAfterSeconds).isEqualTo(30)
    }

    @Test
    fun `scan tolerates unknown response fields`() {
        // Gateway adds a new field — we must not crash.
        val body = """
            {
              "request_id": "abc",
              "action": "allow",
              "sanitised": "z",
              "transforms": [],
              "findings": [],
              "decision": {},
              "bundle_digest": "x",
              "future_field_added_in_v2": {"some":"shape"}
            }
        """.trimIndent()
        server.enqueue(MockResponse().setBody(body))

        val result = client().scan(ScanRequest(text = "z"))

        assertThat(result).isInstanceOf(GatewayResult.Ok::class.java)
        assertThat((result as GatewayResult.Ok).value.isAllow).isTrue()
    }

    @Test
    fun `scan surfaces network errors as Err`() {
        // No response enqueued + immediate shutdown → connection refused.
        server.shutdown()
        val result = client().scan(ScanRequest(text = "w"))
        assertThat(result).isInstanceOf(GatewayResult.Err::class.java)
        assertThat((result as GatewayResult.Err).status).isEqualTo(0)
    }

    @Test
    fun `scan returns Err for malformed JSON success body`() {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setBody("this is not json"),
        )
        val result = client().scan(ScanRequest(text = "x"))
        assertThat(result).isInstanceOf(GatewayResult.Err::class.java)
        assertThat((result as GatewayResult.Err).message).contains("malformed")
    }

    @Test
    fun `restore round-trips placeholders to original text`() {
        val body = """
            {
              "request_id": "9b2c",
              "text": "I'll send the wire to 12345 on Tuesday.",
              "restored": 1,
              "missing": []
            }
        """.trimIndent()
        server.enqueue(MockResponse().setBody(body))

        val result = client().restore(
            RestoreRequest(
                requestId = "9b2c",
                text = "I'll send the wire to <ACCOUNT_NUMBER_A4F2> on Tuesday.",
            ),
        )

        assertThat(result).isInstanceOf(GatewayResult.Ok::class.java)
        val resp = (result as GatewayResult.Ok).value
        assertThat(resp.restored).isEqualTo(1)
        assertThat(resp.text).contains("12345")
        assertThat(resp.missing).isEmpty()
    }

    @Test
    fun `restore sends request_id in snake_case`() {
        server.enqueue(MockResponse().setBody("""{"request_id":"x","text":"x","restored":0,"missing":[]}"""))
        client().restore(RestoreRequest(requestId = "abc-123", text = ""))
        val sent = server.takeRequest().body.readUtf8()
        assertThat(sent).contains("\"request_id\":\"abc-123\"")
    }

    @Test
    fun `restore reports missing placeholders without failing`() {
        val body = """
            {
              "request_id": "9b2c",
              "text": "got <EMAIL_K7M2>",
              "restored": 0,
              "missing": ["<EMAIL_K7M2>"]
            }
        """.trimIndent()
        server.enqueue(MockResponse().setBody(body))

        val result = client().restore(RestoreRequest(requestId = "9b2c", text = "got <EMAIL_K7M2>"))

        val resp = (result as GatewayResult.Ok).value
        assertThat(resp.restored).isZero
        assertThat(resp.missing).containsExactly("<EMAIL_K7M2>")
    }

    @Test
    fun `ping returns the HTTP status code on reachable gateway`() {
        server.enqueue(MockResponse().setResponseCode(200).setBody("ok"))
        val result = client().ping()
        assertThat(result).isInstanceOf(GatewayResult.Ok::class.java)
        assertThat((result as GatewayResult.Ok).value).isEqualTo(200)
    }

    @Test
    fun `ping returns Ok even on 401 because gateway is reachable`() {
        server.enqueue(MockResponse().setResponseCode(401))
        val result = client().ping()
        assertThat(result).isInstanceOf(GatewayResult.Ok::class.java)
        assertThat((result as GatewayResult.Ok).value).isEqualTo(401)
    }

    @Test
    fun `client header marks edge source`() {
        server.enqueue(MockResponse().setBody(allowResponse()))
        client().scan(ScanRequest(text = "x"))
        val recorded: RecordedRequest = server.takeRequest()
        assertThat(recorded.getHeader("X-Section-Client")).isEqualTo("jetbrains")
    }

    private fun allowResponse(): String = """
        {
          "request_id": "r",
          "action": "allow",
          "sanitised": "x",
          "transforms": [],
          "findings": [],
          "decision": {"action":"allow"},
          "bundle_digest": "z"
        }
    """.trimIndent()
}
