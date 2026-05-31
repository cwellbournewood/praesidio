package io.section.edge

import com.intellij.ide.AppLifecycleListener
import io.section.edge.proxy.ProxyController
import io.section.edge.util.logger

/**
 * Hooks IDE-wide shutdown so the edge proxy doesn't outlive the IDE.
 * [ProxyController] is also registered as a [com.intellij.openapi.Disposable]
 * off the application root, so this listener is belt-and-braces — the
 * platform will dispose us in the normal path, and this listener is
 * the fast-path on graceful shutdown.
 */
class SectionAppLifecycleListener : AppLifecycleListener {

    private val log = logger<SectionAppLifecycleListener>()

    override fun appWillBeClosed(isRestart: Boolean) {
        log.info("Section: app shutting down (restart=$isRestart) — stopping edge proxy")
        try {
            ProxyController.getInstance().stop()
        } catch (t: Throwable) {
            log.warn("error stopping proxy on shutdown: ${t.message}")
        }
    }
}
