package io.praesidio.edge.inspections

import com.intellij.codeHighlighting.HighlightDisplayLevel
import com.intellij.codeInspection.InspectionManager
import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.ProblemDescriptor
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.editor.Document
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import io.praesidio.edge.gateway.GatewayResult
import io.praesidio.edge.gateway.GatewayService
import io.praesidio.edge.gateway.RecentDecisionsService
import io.praesidio.edge.gateway.ScanRequest
import io.praesidio.edge.gateway.ScanResponse
import io.praesidio.edge.settings.PraesidioSettings
import io.praesidio.edge.util.Chunker
import io.praesidio.edge.util.PraesidioBundle.message
import io.praesidio.edge.util.logger
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap
import kotlin.math.roundToInt

/**
 * Local inspection that surfaces Praesidio gateway findings as IDE
 * warnings on any opened text file.
 *
 * Why "any text file" and not just specific languages: AI prompts are
 * crafted in `.md`, `.txt`, source files of every language, JSON
 * scratch buffers, and even `.http` requests. The cost of running the
 * scan per file is bounded by the debounce + chunking logic below, so
 * the broad scope is affordable.
 *
 * Two layers of work-avoidance keep the gateway pressure manageable:
 *
 *  1. **Per-file caching by content hash.** A document whose body
 *     hasn't changed since the last scan re-uses the cached findings.
 *     This is the dominant savings on idle files — IntelliJ re-runs
 *     inspections whenever the user opens any tool window, switches
 *     editors, or even hovers a problem.
 *  2. **Inflight de-dup.** If a scan is already running for a given
 *     content hash, concurrent invocations return the cached "no
 *     findings yet" snapshot rather than queueing another HTTP call.
 *
 * The 500ms quiescence requirement from the RFP is implemented by
 * IntelliJ's own inspection scheduler: inspections only fire after
 * editor edits settle. The cache makes any earlier triggers cheap.
 */
class SensitiveDataInspection : LocalInspectionTool() {

    private val log = logger<SensitiveDataInspection>()
    private val cache = ConcurrentHashMap<String, ScanResponse>()
    private val inflight = ConcurrentHashMap<String, Boolean>()

    override fun getDefaultLevel(): HighlightDisplayLevel = HighlightDisplayLevel.WARNING

    override fun isEnabledByDefault(): Boolean = true

    override fun getGroupDisplayName(): String =
        message("praesidio.inspection.group")

    override fun getDisplayName(): String =
        message("praesidio.inspection.displayName")

    override fun getShortName(): String = SHORT_NAME

    override fun runForWholeFile(): Boolean = true

    /**
     * IntelliJ calls [checkFile] per inspection pass with a
     * de-batched, post-quiescence document. We return an array of
     * [ProblemDescriptor]s — one per finding.
     */
    override fun checkFile(
        file: PsiFile,
        manager: InspectionManager,
        isOnTheFly: Boolean,
    ): Array<ProblemDescriptor>? {
        val settings = PraesidioSettings.getInstance()
        if (!settings.enableInspections) return null

        val document = file.viewProvider.document ?: return null
        val text = document.charsSequence.toString()
        if (text.isBlank()) return null
        // Skip very small docs — nothing for the scanner to bite on
        // and we don't want to spam the audit trail.
        if (text.length < MIN_INSPECTION_CHARS) return null

        val hash = contentHash(text)
        val cached = cache[hash]
        if (cached != null) {
            return cached.toProblems(manager, file, document, text)
        }
        // Avoid duplicating an in-flight scan. Subsequent re-runs of
        // the inspection while we wait will read the cache as soon as
        // the scan returns.
        if (inflight.putIfAbsent(hash, true) == null) {
            ApplicationManager.getApplication().executeOnPooledThread {
                scanAsync(hash, text)
            }
        }
        return null
    }

    private fun scanAsync(hash: String, text: String) {
        try {
            // Chunk to stay under the gateway's per-call limit and to
            // give the user something rather than nothing on very
            // large documents.
            val chunks = Chunker.split(text)
            if (chunks.isEmpty()) return
            val client = GatewayService.getInstance().client()
            val merged = ScanResponse(requestId = "merged", action = "allow")
            var head = merged
            for (chunk in chunks) {
                val req = ScanRequest(
                    text = chunk.text,
                    client = "jetbrains",
                )
                when (val result = client.scan(req)) {
                    is GatewayResult.Ok -> {
                        head = mergeChunkResult(head, result.value, chunk.start)
                        RecentDecisionsService.getInstance().record(
                            RecentDecisionsService.fromScan(result.value, "jetbrains-inspection"),
                        )
                        // Block decisions short-circuit further chunks
                        // — the file already has a finding we should
                        // surface and we don't need to keep paying for
                        // the rest.
                        if (result.value.isBlock) break
                    }
                    is GatewayResult.Err -> {
                        log.debug("inspection scan failed: ${result.message}")
                        return
                    }
                }
            }
            cache[hash] = head
            // Best-effort: keep the cache bounded so a long-lived IDE
            // session doesn't accumulate megabytes of scan responses.
            if (cache.size > CACHE_MAX_ENTRIES) {
                val toEvict = cache.size - CACHE_MAX_ENTRIES + CACHE_EVICT_BATCH
                cache.keys.take(toEvict).forEach { cache.remove(it) }
            }
        } finally {
            inflight.remove(hash)
        }
    }

    /**
     * Merge a per-chunk [ScanResponse] into the accumulator, offsetting
     * finding positions back into the original document's coordinate
     * space.
     */
    private fun mergeChunkResult(
        acc: ScanResponse,
        next: ScanResponse,
        offset: Int,
    ): ScanResponse {
        val rebased = next.findings.map { f ->
            f.copy(start = f.start + offset, end = f.end + offset)
        }
        // Promote action: block > mask > allow.
        val action = when {
            acc.action == "block" || next.action == "block" -> "block"
            acc.action == "mask" || next.action == "mask" -> "mask"
            else -> "allow"
        }
        return acc.copy(
            action = action,
            findings = acc.findings + rebased,
            transforms = acc.transforms + next.transforms,
            reason = acc.reason ?: next.reason,
            severity = acc.severity ?: next.severity,
        )
    }

    private fun ScanResponse.toProblems(
        manager: InspectionManager,
        file: PsiFile,
        document: Document,
        text: String,
    ): Array<ProblemDescriptor>? {
        if (findings.isEmpty()) return null
        val docLen = document.textLength
        val out = ArrayList<ProblemDescriptor>(findings.size)
        for (finding in findings) {
            // Clamp to document bounds in case the buffer shrank since
            // the scan ran. A racy edit shouldn't crash the inspection.
            val start = finding.start.coerceIn(0, docLen)
            val end = finding.end.coerceIn(start, docLen)
            if (end <= start) continue
            val element: PsiElement = file.findElementAt(start) ?: file
            val highlightRange = TextRange(
                start - element.textRange.startOffset,
                end - element.textRange.startOffset,
            ).takeIf { it.startOffset >= 0 && it.endOffset <= element.textLength }
            val pct = (finding.confidence * 100).roundToInt()
            val problemMessage = message(
                "praesidio.inspection.problem",
                finding.label,
                finding.detector,
                pct,
            )
            val descriptor = manager.createProblemDescriptor(
                element,
                highlightRange,
                problemMessage,
                ProblemHighlightType.GENERIC_ERROR_OR_WARNING,
                true,
                TokeniseQuickFix(start, end, text.substring(start, end)),
            )
            out.add(descriptor)
        }
        return out.toTypedArray()
    }

    private fun contentHash(text: String): String {
        val md = MessageDigest.getInstance("SHA-256")
        return md.digest(text.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    /**
     * Quick-fix: replace the offending range with the placeholder the
     * gateway minted for it. We re-issue `/v1/scan` on just the
     * sensitive span so the placeholder is bound to a fresh request
     * id and won't leak vault entries from the parent inspection's
     * audit row.
     */
    internal class TokeniseQuickFix(
        private val start: Int,
        private val end: Int,
        private val original: String,
    ) : LocalQuickFix {
        override fun getName(): String =
            message("praesidio.inspection.quickfix.tokenise")

        override fun getFamilyName(): String =
            message("praesidio.inspection.quickfix.tokenise.familyName")

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val element = descriptor.psiElement ?: return
            val file = element.containingFile ?: return
            val document = file.viewProvider.document ?: return
            ApplicationManager.getApplication().executeOnPooledThread {
                val client = GatewayService.getInstance().client()
                val req = ScanRequest(text = original, client = "jetbrains")
                val result = client.scan(req)
                if (result !is GatewayResult.Ok) return@executeOnPooledThread
                val sanitised = result.value.sanitised ?: return@executeOnPooledThread
                if (sanitised == original) return@executeOnPooledThread
                ApplicationManager.getApplication().invokeLater {
                    WriteCommandAction.runWriteCommandAction(project, "Praesidio: Tokenise", null, {
                        val docLen = document.textLength
                        if (start in 0..docLen && end in start..docLen) {
                            document.replaceString(start, end, sanitised)
                        }
                    })
                }
            }
        }

        override fun startInWriteAction(): Boolean = false
    }

    companion object {
        const val SHORT_NAME: String = "PraesidioSensitiveData"
        const val MIN_INSPECTION_CHARS: Int = 16
        const val CACHE_MAX_ENTRIES: Int = 128
        const val CACHE_EVICT_BATCH: Int = 16
    }
}
