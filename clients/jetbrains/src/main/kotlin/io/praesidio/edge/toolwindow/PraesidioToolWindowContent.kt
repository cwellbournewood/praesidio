package io.praesidio.edge.toolwindow

import com.intellij.openapi.Disposable
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionPlaces
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.options.ShowSettingsUtil
import com.intellij.openapi.project.Project
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.messages.MessageBusConnection
import com.intellij.util.ui.JBUI
import io.praesidio.edge.actions.SignInController
import io.praesidio.edge.gateway.RecentDecisionsService
import io.praesidio.edge.proxy.ProxyController
import io.praesidio.edge.settings.PraesidioConfigurable
import io.praesidio.edge.settings.PraesidioSettings
import io.praesidio.edge.util.PraesidioBundle.message
import java.awt.BorderLayout
import java.awt.Dimension
import java.awt.event.ActionListener
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import javax.swing.Box
import javax.swing.BoxLayout
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JTable
import javax.swing.table.AbstractTableModel
import javax.swing.table.TableColumnModel

/**
 * Single-panel tool window content: status row at the top, then a
 * table of recent decisions, then an action button row. Subscribes to
 * the [RecentDecisionsService] and [ProxyController] message-bus
 * topics so updates appear without polling.
 */
class PraesidioToolWindowContent(
    private val project: Project,
) : Disposable {

    private val statusGateway = JBLabel()
    private val statusSignIn = JBLabel()
    private val statusProxy = JBLabel()

    private val decisionsModel = DecisionsTableModel()
    private val decisionsTable = JTable(decisionsModel).apply {
        setShowGrid(false)
        rowHeight = JBUI.scale(22)
        autoCreateRowSorter = true
        fillsViewportHeight = true
        intercellSpacing = JBUI.size(0, 0)
    }

    private val toggleProxyBtn = JButton(message("praesidio.toolwindow.button.toggleProxy"))
    private val settingsBtn = JButton(message("praesidio.toolwindow.button.openSettings"))
    private val signInBtn = JButton(message("praesidio.toolwindow.button.signIn"))

    private val bus: MessageBusConnection =
        ApplicationManager.getApplication().messageBus.connect(this)

    val component: JComponent by lazy { buildComponent() }

    init {
        bus.subscribe(
            RecentDecisionsService.TOPIC,
            RecentDecisionsService.Listener { decision ->
                ApplicationManager.getApplication().invokeLater {
                    decisionsModel.prepend(decision)
                    refreshStatus()
                }
            },
        )
        bus.subscribe(
            ProxyController.TOPIC,
            ProxyController.Listener { _, _ ->
                ApplicationManager.getApplication().invokeLater { refreshStatus() }
            },
        )
        // Hydrate from whatever the service already has.
        decisionsModel.replace(RecentDecisionsService.getInstance().snapshot())
        refreshStatus()
    }

    override fun dispose() {
        bus.disconnect()
    }

    private fun buildComponent(): JComponent {
        toggleProxyBtn.addActionListener(handleToggleProxy())
        settingsBtn.addActionListener(handleOpenSettings())
        signInBtn.addActionListener(handleSignIn())

        val statusPane = JBPanel<JBPanel<*>>().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
            border = JBUI.Borders.empty(8, 10)
            add(statusGateway)
            add(Box.createVerticalStrut(JBUI.scale(2)))
            add(statusSignIn)
            add(Box.createVerticalStrut(JBUI.scale(2)))
            add(statusProxy)
        }

        configureColumns(decisionsTable.columnModel)
        val tableScroll = JBScrollPane(decisionsTable).apply {
            border = JBUI.Borders.empty(0, 10)
            preferredSize = Dimension(JBUI.scale(360), JBUI.scale(280))
        }

        val buttonsPane = JBPanel<JBPanel<*>>().apply {
            layout = BoxLayout(this, BoxLayout.X_AXIS)
            border = JBUI.Borders.empty(8, 10)
            add(toggleProxyBtn)
            add(Box.createHorizontalStrut(JBUI.scale(6)))
            add(signInBtn)
            add(Box.createHorizontalGlue())
            add(settingsBtn)
        }

        return JBPanel<JBPanel<*>>().apply {
            layout = BorderLayout()
            add(statusPane, BorderLayout.NORTH)
            add(tableScroll, BorderLayout.CENTER)
            add(buttonsPane, BorderLayout.SOUTH)
        }
    }

    private fun configureColumns(cm: TableColumnModel) {
        cm.getColumn(0).preferredWidth = JBUI.scale(80) // time
        cm.getColumn(1).preferredWidth = JBUI.scale(70) // action
        cm.getColumn(2).preferredWidth = JBUI.scale(70) // findings
        cm.getColumn(3).preferredWidth = JBUI.scale(120) // client
    }

    private fun refreshStatus() {
        val settings = PraesidioSettings.getInstance()
        statusGateway.text = message(
            "praesidio.toolwindow.status.gateway",
            settings.gatewayUrl,
        )
        statusSignIn.text = if (settings.signedInAs.isNotEmpty()) {
            message("praesidio.toolwindow.status.signedIn", settings.signedInAs)
        } else {
            message("praesidio.toolwindow.status.signedOut")
        }
        val proxyLabel = when (ProxyController.getInstance().state) {
            ProxyController.ProxyState.RUNNING ->
                message("praesidio.toolwindow.status.proxy.running")
            else ->
                message("praesidio.toolwindow.status.proxy.stopped")
        }
        statusProxy.text = message("praesidio.toolwindow.status.proxy", proxyLabel)
    }

    private fun handleToggleProxy(): ActionListener = ActionListener {
        // Re-use the existing AnAction so all sites toggle through one
        // code path. The button is just a discoverable shortcut.
        val mgr = ActionManager.getInstance()
        val action: AnAction? = mgr.getAction("io.praesidio.edge.actions.ToggleProxyAction")
        if (action != null) {
            val event = AnActionEvent.createFromAnAction(
                action,
                null,
                ActionPlaces.TOOLWINDOW_CONTENT,
                DataContext.EMPTY_CONTEXT,
            )
            action.actionPerformed(event)
        }
    }

    private fun handleOpenSettings(): ActionListener = ActionListener {
        ShowSettingsUtil.getInstance()
            .showSettingsDialog(project, PraesidioConfigurable::class.java)
    }

    private fun handleSignIn(): ActionListener = ActionListener {
        SignInController().start()
    }

    /**
     * Table model backed by an in-memory copy of the recent decisions
     * list. We keep a separate copy here (not a live reference into
     * the service's deque) because the table model has to be modified
     * on the EDT.
     */
    private class DecisionsTableModel : AbstractTableModel() {
        private val rows = mutableListOf<RecentDecisionsService.Decision>()

        private val timeFormatter: DateTimeFormatter =
            DateTimeFormatter.ofPattern("HH:mm:ss").withZone(ZoneId.systemDefault())

        private val columns = arrayOf(
            message("praesidio.toolwindow.recent.column.time"),
            message("praesidio.toolwindow.recent.column.action"),
            message("praesidio.toolwindow.recent.column.findings"),
            message("praesidio.toolwindow.recent.column.client"),
        )

        fun prepend(decision: RecentDecisionsService.Decision) {
            rows.add(0, decision)
            // Keep the model in sync with the service capacity.
            val cap = PraesidioSettings.getInstance().recentDecisionsLimit
            while (rows.size > cap) rows.removeAt(rows.lastIndex)
            fireTableDataChanged()
        }

        fun replace(values: List<RecentDecisionsService.Decision>) {
            rows.clear()
            rows.addAll(values)
            fireTableDataChanged()
        }

        override fun getRowCount(): Int = rows.size

        override fun getColumnCount(): Int = columns.size

        override fun getColumnName(column: Int): String = columns[column]

        override fun getValueAt(rowIndex: Int, columnIndex: Int): Any =
            with(rows[rowIndex]) {
                when (columnIndex) {
                    0 -> timeFormatter.format(occurredAt)
                    1 -> action
                    2 -> "${findings} f / ${transforms} t"
                    3 -> client
                    else -> ""
                }
            }

        override fun isCellEditable(rowIndex: Int, columnIndex: Int): Boolean = false
    }
}
