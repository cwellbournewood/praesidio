package io.section.edge

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import io.section.edge.proxy.ProxyController
import io.section.edge.settings.SectionSettings
import io.section.edge.util.logger
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Application-level coordinator. Registered as a service so the
 * platform owns its lifecycle; the actual init runs from
 * [SectionStartupActivity] post-IDE-init so we can read settings
 * (which require the application to be ready).
 *
 * Single responsibility: wire the proxy autostart toggle. Everything
 * else hangs off its own service.
 */
@Service(Service.Level.APP)
class SectionApp {

    private val log: Logger = logger<SectionApp>()
    private val started = AtomicBoolean(false)

    fun onStartup() {
        if (!started.compareAndSet(false, true)) return
        log.info("Section plugin starting; gateway=${SectionSettings.getInstance().gatewayUrl}")
        maybeAutostartProxy()
    }

    private fun maybeAutostartProxy() {
        val settings = SectionSettings.getInstance()
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
        fun getInstance(): SectionApp =
            ApplicationManager.getApplication().getService(SectionApp::class.java)
    }
}
