package io.section.edge.toolwindow

import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory

/**
 * Factory for the Section tool window. Registered in plugin.xml with
 * `anchor="right"` so it docks alongside the standard structure /
 * services panes. Implementing [DumbAware] lets the window open even
 * while the IDE is indexing — none of our content depends on PSI or
 * the indexed model.
 */
class SectionToolWindowFactory : ToolWindowFactory, DumbAware {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = SectionToolWindowContent(project)
        val factory = ContentFactory.getInstance()
        val content = factory.createContent(panel.component, "", false)
        // The content is disposed automatically when the tool window
        // is closed; we register the panel so its listeners detach.
        content.setDisposer(panel)
        toolWindow.contentManager.addContent(content)
    }
}
