package io.praesidio.edge

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import io.praesidio.edge.proxy.ProxyController
import io.praesidio.edge.settings.PraesidioSettings
import io.praesidio.edge.util.logger
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Application-level coordinator. Registered as a service so the
 * platform owns its lifecycle; the actual init runs from
 * [PraesidioStartupActivity] post-IDE-init so we can read settings
 * (which require the application to be ready).
 *
 * Single responsibility: wire the proxy autostart toggle. Everything
 * else hangs off its own service.
 */
@Service(Service.Level.APP)
class PraesidioApp {

    private val log: Logger = logger<PraesidioApp>()
    private val started = AtomicBoolean(false)

    fun onStartup() {
        if (!started.compareAndSet(false, true)) return
        log.info("Praesidio plugin starting; gateway=${PraesidioSettings.getInstance().gatewayUrl}")
        maybeAutostartProxy()
    }

    private fun maybeAutostartProxy() {
        val settings = PraesidioSettings.getInstance()
        if (!settings.proxyAutostart) return
        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                ProxyController.getInstance().start()
            } catch (t: Throwable) {
                log.warn("proxy autostart failed: ${t.message}")
            }
        }
    }

    companion object {
        @JvmStatic
        fun getInstance(): PraesidioApp =
            ApplicationManager.getApplication().getService(PraesidioApp::class.java)
    }
}
