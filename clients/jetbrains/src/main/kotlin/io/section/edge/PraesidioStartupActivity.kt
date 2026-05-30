package io.section.edge

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity

/**
 * Wakes up the [SectionApp] service on first project open after IDE
 * launch. We use a [ProjectActivity] (rather than the deprecated
 * `StartupActivity`) because the new platform API is stable across the
 * full 232–252 build range.
 *
 * The work is idempotent — [SectionApp.onStartup] dedupes via an
 * [java.util.concurrent.atomic.AtomicBoolean] so opening a second
 * project in the same IDE session is a no-op.
 */
class SectionStartupActivity : ProjectActivity {
    override suspend fun execute(project: Project) {
        SectionApp.getInstance().onStartup()
    }
}
