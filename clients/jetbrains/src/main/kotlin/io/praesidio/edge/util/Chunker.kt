package io.praesidio.edge.util

/**
 * Split text into chunks no larger than [maxBytes] **measured in UTF-8
 * bytes**. The gateway's `POST /v1/scan` accepts up to 512 kB per call;
 * we conservatively use 256 kB to leave headroom for the JSON envelope
 * and to keep latency per-call modest.
 *
 * Splitting rules — in order of preference:
 *  1. After a paragraph break (`\n\n`).
 *  2. After a line break (`\n`).
 *  3. After a sentence terminator (`. `, `? `, `! `).
 *  4. After any whitespace.
 *  5. Hard cut at byte budget.
 *
 * Chunks carry their original character offsets so the inspection can
 * project per-chunk findings back onto absolute editor positions.
 */
object Chunker {
    const val DEFAULT_MAX_BYTES: Int = 256 * 1024

    /** A single chunk with its `[start, end)` offsets into the source. */
    data class Chunk(val text: String, val start: Int, val end: Int) {
        init {
            require(start in 0..end) { "invalid chunk: start=$start end=$end" }
        }
    }

    fun split(text: String, maxBytes: Int = DEFAULT_MAX_BYTES): List<Chunk> {
        require(maxBytes > 0) { "maxBytes must be > 0" }
        if (text.isEmpty()) return emptyList()
        // Fast path: small inputs fit in a single chunk. We measure the
        // UTF-8 byte length lazily so ASCII-heavy text avoids the
        // allocation.
        if (text.length <= maxBytes / 4 ||
            text.toByteArray(Charsets.UTF_8).size <= maxBytes
        ) {
            return listOf(Chunk(text, 0, text.length))
        }

        val result = mutableListOf<Chunk>()
        var cursor = 0
        val n = text.length
        while (cursor < n) {
            val end = nextBoundary(text, cursor, maxBytes)
            result += Chunk(text.substring(cursor, end), cursor, end)
            cursor = end
        }
        return result
    }

    /**
     * Find the largest end-offset `e > start` such that
     * `text[start, e)` fits in [maxBytes] UTF-8 bytes AND ends on a
     * pleasant boundary, scanning **forward** in chars and tracking
     * byte cost as we go.
     */
    private fun nextBoundary(text: String, start: Int, maxBytes: Int): Int {
        val n = text.length
        var bytes = 0
        var lastPara = -1
        var lastLine = -1
        var lastSentence = -1
        var lastWord = -1
        var i = start
        while (i < n) {
            val c = text[i]
            val cb = utf8Len(c, text, i)
            if (bytes + cb > maxBytes) break
            bytes += cb
            i++
            // Track boundary candidates in priority order; pick the
            // latest seen of the highest-priority type at break time.
            if (c == '\n' && i < n && text[i] == '\n') {
                lastPara = i + 1
            } else if (c == '\n') {
                lastLine = i
            } else if ((c == '.' || c == '!' || c == '?') &&
                i < n && (text[i] == ' ' || text[i] == '\n')
            ) {
                lastSentence = i + 1
            } else if (c.isWhitespace()) {
                lastWord = i
            }
        }
        // We consumed the entire remainder.
        if (i == n) return n
        val candidate = when {
            lastPara > start -> lastPara
            lastLine > start -> lastLine
            lastSentence > start -> lastSentence
            lastWord > start -> lastWord
            else -> i
        }
        // Defensive: if a degenerate string makes us pick the same
        // offset twice (e.g. a single character > maxBytes when
        // encoded), force at least one char of progress.
        return if (candidate <= start) start + 1 else candidate
    }

    /** UTF-8 byte length of a single (possibly surrogate-pair) char. */
    private fun utf8Len(c: Char, text: String, i: Int): Int {
        val code = c.code
        return when {
            code < 0x80 -> 1
            code < 0x800 -> 2
            Character.isHighSurrogate(c) && i + 1 < text.length &&
                Character.isLowSurrogate(text[i + 1]) -> 4
            else -> 3
        }
    }
}
