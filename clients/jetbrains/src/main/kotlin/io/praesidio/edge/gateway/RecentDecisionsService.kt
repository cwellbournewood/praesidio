package io.praesidio.edge.gateway

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.util.messages.Topic
import com.intellij.util.messages.Topic.AppLevel
import io.praesidio.edge.settings.PraesidioSettings
import java.time.Instant
import java.util.ArrayDeque
import java.util.concurrent.locks.ReentrantReadWriteLock
import kotlin.concurrent.read
import kotlin.concurrent.write

/**
 * Thread-safe ring buffer of recent gateway decisions, plus a message
 * bus topic so the tool window can refresh without polling.
 *
 * Capacity is taken from [PraesidioSettings.recentDecisionsLimit] (1
 * to 200). When the buffer is full the oldest entry is dropped.
 *
 * Decisions are kept **in memory only**. Persisting them would
 * duplicate the audit trail (the gateway owns that record) and would
 * be PII-adjacent on the developer's machine, so we deliberately keep
 * this as ephemeral state.
 */
@Service(Service.Level.APP)
class RecentDecisionsService {

    /** One row of the tool window's recent-decisions list. */
    data class Decision(
        val occurredAt: Instant,
        val action: String,
        val client: String,
        val findings: Int,
        val transforms: Int,
        val reason: String? = null,
        val requestId: String? = null,
    )

    /** Listener interface for tool-window refresh. */
    fun interface Listener {
        fun onDecisionRecorded(decision: Decision)
    }

    private val lock = ReentrantReadWriteLock()
    private val buffer = ArrayDeque<Decision>()

    fun record(decision: Decision) {
        val cap = PraesidioSettings.getInstance().recentDecisionsLimit
        lock.write {
            while (buffer.size >= cap) buffer.pollLast()
            buffer.addFirst(decision)
        }
        ApplicationManager.getApplication().messageBus
            .syncPublisher(TOPIC)
            .onDecisionRecorded(decision)
    }

    fun snapshot(): List<Decision> = lock.read { buffer.toList() }

    fun clear() {
        lock.write { buffer.clear() }
    }

    companion object {
        @AppLevel
        @JvmField
        val TOPIC: Topic<Listener> =
            Topic.create("Praesidio.RecentDecisions", Listener::class.java)

        @JvmStatic
        fun getInstance(): RecentDecisionsService =
            ApplicationManager.getApplication().getService(RecentDecisionsService::class.java)

        /**
         * Helper used by actions / inspection. Builds a [Decision]
         * from a [ScanResponse] and the originating client tag.
         */
        fun fromScan(resp: ScanResponse, client: String): Decision =
            Decision(
                occurredAt = Instant.now(),
                action = resp.action,
                client = client,
                findings = resp.findings.size,
                transforms = resp.transforms.size,
                reason = resp.reason,
                requestId = resp.requestId,
            )
    }
}
