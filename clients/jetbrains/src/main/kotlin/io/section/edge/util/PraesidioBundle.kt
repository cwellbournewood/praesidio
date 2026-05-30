package io.section.edge.util

import com.intellij.DynamicBundle
import org.jetbrains.annotations.NonNls
import org.jetbrains.annotations.PropertyKey

private const val BUNDLE_NAME: @NonNls String = "messages.SectionBundle"

/**
 * Message bundle accessor. Mirrors the standard JetBrains pattern of a
 * [DynamicBundle] singleton that platform code can hot-swap to another
 * locale at runtime.
 *
 * Usage:
 * ```
 * SectionBundle.message("section.action.scan.empty")
 * SectionBundle.message("section.toolwindow.status.gateway", url)
 * ```
 */
object SectionBundle : DynamicBundle(BUNDLE_NAME) {
    /**
     * Look up `key` in the bundle and substitute `${0}`, `${1}`, … via
     * [java.text.MessageFormat]. The lookup is checked against the
     * compile-time bundle on a best-effort basis through
     * [PropertyKey].
     */
    @JvmStatic
    fun message(
        @PropertyKey(resourceBundle = BUNDLE_NAME) key: String,
        vararg params: Any,
    ): String = getMessage(key, *params)

    /** Lazy variant for tooltips / labels that aren't always rendered. */
    @JvmStatic
    fun lazyMessage(
        @PropertyKey(resourceBundle = BUNDLE_NAME) key: String,
        vararg params: Any,
    ): () -> String = { getMessage(key, *params) }
}
