package io.praesidio.edge.proxy

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.util.Disposer
import com.intellij.util.messages.Topic
import com.intellij.util.messages.Topic.AppLevel
import io.praesidio.edge.settings.PraesidioSettings
import io.praesidio.edge.util.logger
import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/**
 * Spawns and manages a single child process running the
 * `praesidio-edge-proxy` CLI (Lane E). One process per IDE — multiple
 * IDE windows share the same proxy via the loopback port.
 *
 * Lifecycle:
 *  - Start: builds the argv from settings, forks via [ProcessBuilder].
 *    Inherits stdout/stderr to a discard sink and pumps them on a
 *    daemon thread to avoid the pipe buffer filling and stalling the
 *    child.
 *  - Stop: sends SIGTERM (`destroy()`), waits up to 5s, force-kills
 *    if necessary.
 *  - Shutdown: registered as a [Disposable] off the application root
 *    so IDE close → proxy kill happens automatically.
 *
 * State changes publish to a message-bus topic the tool window
 * subscribes to.
 */
@Service(Service.Level.APP)
class ProxyController : Disposable {

    private val log: Logger = logger<ProxyController>()
    private val processRef = AtomicReference<Process?>()
    private val stateRef = AtomicReference(ProxyState.STOPPED)

    init {
        // Register so app-level shutdown disposes us and kills the child.
        Disposer.register(ApplicationManager.getApplication(), this)
    }

    enum class ProxyState { STOPPED, STARTING, RUNNING, FAILED }

    /** Listener for tool-window status badges. */
    fun interface Listener {
        fun onProxyStateChanged(state: ProxyState, message: String?)
    }

    val state: ProxyState get() = stateRef.get()
    val isRunning: Boolean get() = stateRef.get() == ProxyState.RUNNING

    /** Start or restart the proxy. Returns the new state. */
    fun start(): ProxyState {
        if (stateRef.get() == ProxyState.RUNNING) return ProxyState.RUNNING
        val settings = PraesidioSettings.getInstance()
        val cmd = buildCommand(settings)
        return try {
            log.info("starting edge proxy: ${cmd.joinToString(" ")}")
            transition(ProxyState.STARTING, null)
            val pb = ProcessBuilder(cmd)
                .redirectErrorStream(true)
                .redirectOutput(ProcessBuilder.Redirect.PIPE)
            val proc = pb.start()
            processRef.set(proc)
            pumpOutput(proc)
            // Quick liveness check — if the binary is missing or crashes
            // immediately, `isAlive` flips to false within a few ms.
            // We wait 250 ms to give a fast-crashing child a chance to
            // report failure, then assume "running".
            Thread.sleep(LIVENESS_PROBE_MS)
            if (!proc.isAlive && proc.exitValue() != 0) {
                transition(ProxyState.FAILED, "exit code ${proc.exitValue()}")
                processRef.set(null)
                return ProxyState.FAILED
            }
            transition(ProxyState.RUNNING, null)
            ProxyState.RUNNING
        } catch (ex: IOException) {
            log.warn("failed to start edge proxy: ${ex.message}")
            transition(ProxyState.FAILED, ex.message)
            ProxyState.FAILED
        } catch (ex: InterruptedException) {
            Thread.currentThread().interrupt()
            transition(ProxyState.FAILED, "interrupted")
            ProxyState.FAILED
        }
    }

    /** Stop the proxy. Idempotent. */
    fun stop() {
        val proc = processRef.getAndSet(null) ?: run {
            transition(ProxyState.STOPPED, null)
            return
        }
        try {
            proc.destroy()
            if (!proc.waitFor(GRACEFUL_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
                log.warn("edge proxy did not exit gracefully — forcing")
                proc.destroyForcibly()
            }
        } catch (ex: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        transition(ProxyState.STOPPED, null)
    }

    /** Toggle. Returns the resulting state. */
    fun toggle(): ProxyState {
        return if (isRunning) {
            stop()
            ProxyState.STOPPED
        } else {
            start()
        }
    }

    override fun dispose() {
        stop()
    }

    /**
     * Build the proxy argv. The first element is either the explicit
     * binary path from settings or the bare CLI name (which relies on
     * PATH resolution). Subsequent args come from `proxyArgs` but we
     * always append `--gateway <url>` if it isn't already present.
     */
    internal fun buildCommand(settings: PraesidioSettings): List<String> {
        val binary = settings.proxyBinaryPath.ifEmpty { DEFAULT_BINARY }
        val args = settings.proxyArgs.toMutableList()
        if (!args.contains("--gateway")) {
            args += listOf("--gateway", settings.gatewayUrl)
        }
        if (!args.contains("start") && !args.contains("--help")) {
            args.add(0, "start")
        }
        return listOf(binary) + args
    }

    private fun pumpOutput(proc: Process) {
        // Daemon thread reads the merged stdout+stderr stream so the
        // child's pipe doesn't block when verbose. We forward each
        // line to the IDE log — proxy CLI output is therefore
        // discoverable via Help → Show Log in Finder/Explorer.
        Thread({
            try {
                proc.inputStream.bufferedReader().useLines { lines ->
                    for (line in lines) log.info("[edge-proxy] $line")
                }
            } catch (ex: IOException) {
                log.debug("edge-proxy stream closed: ${ex.message}")
            }
            // When the stream closes the process is on its way out;
            // reflect that in state.
            if (processRef.get() == proc) {
                val exit = runCatching { proc.exitValue() }.getOrElse { -1 }
                processRef.set(null)
                if (exit == 0) {
                    transition(ProxyState.STOPPED, null)
                } else {
                    transition(ProxyState.FAILED, "exit code $exit")
                }
            }
        }, "praesidio-edge-proxy-output").apply { isDaemon = true }.start()
    }

    private fun transition(next: ProxyState, message: String?) {
        stateRef.set(next)
        ApplicationManager.getApplication().messageBus
            .syncPublisher(TOPIC)
            .onProxyStateChanged(next, message)
    }

    companion object {
        const val DEFAULT_BINARY: String = "praesidio-edge-proxy"
        const val GRACEFUL_TIMEOUT_MS: Long = 5_000
        const val LIVENESS_PROBE_MS: Long = 250

        @AppLevel
        @JvmField
        val TOPIC: Topic<Listener> =
            Topic.create("Praesidio.ProxyState", Listener::class.java)

        @JvmStatic
        fun getInstance(): ProxyController =
            ApplicationManager.getApplication().getService(ProxyController::class.java)
    }
}
