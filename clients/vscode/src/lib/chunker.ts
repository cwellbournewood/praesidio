/**
 * Chunk a document for scanning.
 *
 * `/v1/scan` accepts up to 512_000 chars but we cap each request at
 * 256kB (262_144 bytes UTF-8) by default to stay well below
 * proxy / gateway body limits and to keep per-request latency low.
 *
 * Splitting rules:
 *  1. Prefer line boundaries; never split mid-codepoint.
 *  2. If a single line exceeds `maxBytes`, fall back to a hard byte
 *     split at the last valid UTF-8 boundary <= `maxBytes`.
 *  3. Each chunk carries its `startOffset` in the source string so
 *     callers can translate `findings[].start`/`.end` back to
 *     document positions.
 */

export interface Chunk {
  text: string;
  /** Character offset of this chunk inside the source string. */
  startOffset: number;
  /** Byte length of `text` encoded as UTF-8. */
  byteLength: number;
}

const utf8 = new TextEncoder();

export function chunkDocument(source: string, maxBytes = 262_144): Chunk[] {
  if (source.length === 0) return [];
  if (maxBytes <= 0) {
    throw new Error("maxBytes must be > 0");
  }

  // Fast path: whole document fits.
  const sourceBytes = utf8.encode(source).byteLength;
  if (sourceBytes <= maxBytes) {
    return [{ text: source, startOffset: 0, byteLength: sourceBytes }];
  }

  const chunks: Chunk[] = [];
  // Split into logical lines first (keep terminators).
  const lines: string[] = [];
  let i = 0;
  while (i < source.length) {
    const nl = source.indexOf("\n", i);
    if (nl === -1) {
      lines.push(source.slice(i));
      break;
    }
    lines.push(source.slice(i, nl + 1));
    i = nl + 1;
  }

  let buf = "";
  let bufBytes = 0;
  let bufStart = 0;
  let charOffset = 0;

  const flush = (): void => {
    if (buf.length === 0) return;
    chunks.push({ text: buf, startOffset: bufStart, byteLength: bufBytes });
    buf = "";
    bufBytes = 0;
  };

  for (const line of lines) {
    const lineBytes = utf8.encode(line).byteLength;

    if (lineBytes > maxBytes) {
      // Flush whatever we have buffered first.
      flush();
      // Hard-split this single line on byte boundaries.
      let pos = 0;
      while (pos < line.length) {
        const remaining = line.slice(pos);
        const segment = sliceByBytes(remaining, maxBytes);
        const segBytes = utf8.encode(segment).byteLength;
        chunks.push({
          text: segment,
          startOffset: charOffset + pos,
          byteLength: segBytes,
        });
        pos += segment.length;
      }
      charOffset += line.length;
      bufStart = charOffset;
      continue;
    }

    if (bufBytes + lineBytes > maxBytes && buf.length > 0) {
      flush();
      bufStart = charOffset;
    }
    if (buf.length === 0) {
      bufStart = charOffset;
    }
    buf += line;
    bufBytes += lineBytes;
    charOffset += line.length;
  }

  flush();
  return chunks;
}

/**
 * Return the longest prefix of `s` whose UTF-8 byte length is <=
 * `maxBytes`. Never splits a surrogate pair or a multi-byte codepoint.
 */
function sliceByBytes(s: string, maxBytes: number): string {
  if (utf8.encode(s).byteLength <= maxBytes) return s;
  // Binary-search the prefix length.
  let lo = 0;
  let hi = s.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi + 1) / 2);
    const candidate = s.slice(0, mid);
    // Avoid splitting a surrogate pair.
    const lastCode = candidate.charCodeAt(mid - 1);
    const isHighSurrogate = lastCode >= 0xd800 && lastCode <= 0xdbff;
    const segmentBytes = utf8.encode(candidate).byteLength;
    if (segmentBytes <= maxBytes && !isHighSurrogate) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return s.slice(0, lo);
}
