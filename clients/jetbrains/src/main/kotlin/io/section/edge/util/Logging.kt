package io.section.edge.util

import com.intellij.openapi.diagnostic.Logger

/**
 * Lazy logger accessor — using the reified-type variant keeps the
 * caller side line-and-class short while routing through the IntelliJ
 * platform's logger so logs appear in `idea.log`.
 */
inline fun <reified T> logger(): Logger = Logger.getInstance(T::class.java)

/**
 * Bundle key namespace for the plugin's message bundle.
 *
 * Kept here as a top-level const so callers don't depend on the
 * platform's PropertyKey annotation machinery — useful when the same
 * code is also exercised under plain JUnit.
 */
object Bundle {
    const val NAME = "messages.SectionBundle"
}
