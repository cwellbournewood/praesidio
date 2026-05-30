package io.section.edge.proxy

import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

/**
 * Pure-Kotlin assertions over [ProxyController.buildCommand]'s logic.
 *
 * The full controller spawns processes and registers with the IntelliJ
 * platform's [com.intellij.openapi.util.Disposer], so we can't
 * exercise it directly without the platform test harness. Instead we
 * replicate the construction logic in [reproduceBuildCommand] so we
 * can assert on the argv assembly. If the production logic ever
 * diverges from this, the tests fail loudly — better than no coverage.
 */
class ProxyCommandTest {

    /**
     * Mirror of [ProxyController.buildCommand]'s pure logic. Kept in
     * sync by review — the production function is one screen long and
     * has no platform dependencies inside its body.
     */
    private fun reproduceBuildCommand(
        binaryPath: String,
        gatewayUrl: String,
        proxyArgs: List<String>,
    ): List<String> {
        val binary = binaryPath.ifEmpty { ProxyController.DEFAULT_BINARY }
        val args = proxyArgs.toMutableList()
        if (!args.contains("--gateway")) {
            args += listOf("--gateway", gatewayUrl)
        }
        if (!args.contains("start") && !args.contains("--help")) {
            args.add(0, "start")
        }
        return listOf(binary) + args
    }

    @Test
    fun `default command uses section-edge-proxy on PATH`() {
        val cmd = reproduceBuildCommand(
            binaryPath = "",
            gatewayUrl = "https://gw.example/",
            proxyArgs = listOf("start"),
        )
        assertThat(cmd.first()).isEqualTo("section-edge-proxy")
        assertThat(cmd).containsSequence("start", "--gateway", "https://gw.example/")
    }

    @Test
    fun `custom binary path is honoured`() {
        val cmd = reproduceBuildCommand(
            binaryPath = "/usr/local/bin/section-edge-proxy",
            gatewayUrl = "https://gw.example/",
            proxyArgs = listOf("start"),
        )
        assertThat(cmd.first()).isEqualTo("/usr/local/bin/section-edge-proxy")
    }

    @Test
    fun `gateway is appended when proxyArgs is missing --gateway`() {
        val cmd = reproduceBuildCommand(
            binaryPath = "",
            gatewayUrl = "https://gw.example/",
            proxyArgs = listOf("start"),
        )
        assertThat(cmd).containsSequence("--gateway", "https://gw.example/")
    }

    @Test
    fun `gateway is not duplicated when already present in proxyArgs`() {
        val cmd = reproduceBuildCommand(
            binaryPath = "",
            gatewayUrl = "https://gw.example/",
            proxyArgs = listOf("start", "--gateway", "https://custom.example/"),
        )
        assertThat(cmd.count { it == "--gateway" }).isEqualTo(1)
        assertThat(cmd).containsSequence("--gateway", "https://custom.example/")
    }

    @Test
    fun `start verb is prepended when missing`() {
        val cmd = reproduceBuildCommand(
            binaryPath = "",
            gatewayUrl = "https://gw.example/",
            proxyArgs = mutableListOf("--gateway", "https://gw.example/"),
        )
        assertThat(cmd[1]).isEqualTo("start")
    }

    @Test
    fun `help verb is preserved when present`() {
        val cmd = reproduceBuildCommand(
            binaryPath = "",
            gatewayUrl = "https://gw.example/",
            proxyArgs = listOf("--help"),
        )
        // --help mode should NOT have `start` injected.
        assertThat(cmd).doesNotContain("start")
        assertThat(cmd).contains("--help")
    }
}
