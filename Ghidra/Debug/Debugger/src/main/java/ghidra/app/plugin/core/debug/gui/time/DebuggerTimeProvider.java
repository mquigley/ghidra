/* ###
 * IP: GHIDRA
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * 
 *      http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package ghidra.app.plugin.core.debug.gui.time;

import static ghidra.app.plugin.core.debug.gui.DebuggerResources.*;

import java.awt.event.MouseEvent;
import java.lang.invoke.MethodHandles;
import java.util.Objects;

import javax.swing.Icon;
import javax.swing.JComponent;

import docking.ActionContext;
import docking.action.*;
import docking.action.builder.ActionBuilder;
import docking.widgets.dialogs.InputDialog;
import ghidra.app.plugin.core.debug.DebuggerCoordinates;
import ghidra.app.plugin.core.debug.DebuggerPluginPackage;
import ghidra.app.plugin.core.debug.gui.DebuggerResources;
import ghidra.app.plugin.core.debug.gui.DebuggerSnapActionContext;
import ghidra.app.services.DebuggerTraceManagerService;
import ghidra.framework.options.SaveState;
import ghidra.framework.plugintool.*;
import ghidra.framework.plugintool.AutoService.Wiring;
import ghidra.framework.plugintool.annotation.AutoConfigStateField;
import ghidra.framework.plugintool.annotation.AutoServiceConsumed;
import ghidra.trace.model.time.schedule.TraceSchedule;
import ghidra.util.HelpLocation;
import ghidra.util.Msg;

public class DebuggerTimeProvider extends ComponentProviderAdapter {
	private static final AutoConfigState.ClassHandler<DebuggerTimeProvider> CONFIG_STATE_HANDLER =
		AutoConfigState.wireHandler(DebuggerTimeProvider.class, MethodHandles.lookup());

	interface GoToTimeAction {
		String NAME = "Go To Time";
		String DESCRIPTION = "Go to a specific time, optionally using emulation";
		String GROUP = GROUP_TRACE;
		Icon ICON = ICON_TIME;
		String HELP_ANCHOR = "goto_time";

		static ActionBuilder builder(Plugin owner) {
			String ownerName = owner.getName();
			return new ActionBuilder(NAME, ownerName).description(DESCRIPTION)
					.menuPath(DebuggerPluginPackage.NAME, NAME)
					.menuGroup(GROUP)
					.menuIcon(ICON)
					.keyBinding("CTRL G")
					.helpLocation(new HelpLocation(ownerName, HELP_ANCHOR));
		}
	}

	protected static boolean sameCoordinates(DebuggerCoordinates a, DebuggerCoordinates b) {
		if (!Objects.equals(a.getTrace(), b.getTrace())) {
			return false;
		}
		if (!Objects.equals(a.getTime(), b.getTime())) {
			return false;
		}
		return true;
	}

	protected final DebuggerTimePlugin plugin;

	DebuggerCoordinates current = DebuggerCoordinates.NOWHERE;

	@AutoServiceConsumed
	protected DebuggerTraceManagerService traceManager;
	@SuppressWarnings("unused")
	private final Wiring autoServiceWiring;

	/*testing*/ final DebuggerSnapshotTablePanel mainPanel;

	DockingAction actionGoToTime;
	ToggleDockingAction actionHideScratch;

	private DebuggerSnapActionContext myActionContext;

	@AutoConfigStateField
	/*testing*/ boolean hideScratch = true;

	public DebuggerTimeProvider(DebuggerTimePlugin plugin) {
		super(plugin.getTool(), TITLE_PROVIDER_TIME, plugin.getName());
		this.plugin = plugin;

		autoServiceWiring = AutoService.wireServicesConsumed(plugin, this);

		setTitle(TITLE_PROVIDER_TIME);
		setIcon(ICON_PROVIDER_TIME);
		setHelpLocation(HELP_PROVIDER_TIME);
		setWindowMenuGroup(DebuggerPluginPackage.NAME);

		mainPanel = new DebuggerSnapshotTablePanel(tool);
		buildMainPanel();

		myActionContext = new DebuggerSnapActionContext(current.getTrace(), current.getSnap());
		createActions();
		contextChanged();

		setVisible(true);
	}

	@Override
	public void addLocalAction(DockingActionIf action) {
		super.addLocalAction(action);
	}

	@Override
	public JComponent getComponent() {
		return mainPanel;
	}

	@Override
	public ActionContext getActionContext(MouseEvent event) {
		if (myActionContext == null) {
			return super.getActionContext(event);
		}
		return myActionContext;
	}

	protected void buildMainPanel() {
		mainPanel.getSelectionModel().addListSelectionListener(evt -> {
			if (evt.getValueIsAdjusting()) {
				return;
			}
			Long snap = mainPanel.getSelectedSnapshot();
			if (snap == null) {
				myActionContext = null;
				return;
			}
			if (snap.longValue() == current.getSnap()) {
				return;
			}
			myActionContext = new DebuggerSnapActionContext(current.getTrace(), snap);
			traceManager.activateSnap(snap);
			contextChanged();
		});
	}

	protected void createActions() {
		actionGoToTime = GoToTimeAction.builder(plugin)
				.enabledWhen(c -> current.getTrace() != null)
				.onAction(c -> activatedGoToTime())
				.buildAndInstall(tool);
		actionHideScratch = DebuggerResources.HideScratchSnapshotsAction.builder(plugin)
				.selected(hideScratch)
				.onAction(this::activatedHideScratch)
				.buildAndInstallLocal(this);
	}

	private void activatedGoToTime() {
		InputDialog dialog =
			new InputDialog("Go To Time", "Schedule:", current.getTime().toString());
		tool.showDialog(dialog);
		if (dialog.isCanceled()) {
			return;
		}
		try {
			TraceSchedule time = TraceSchedule.parse(dialog.getValue());
			traceManager.activateTime(time);
		}
		catch (IllegalArgumentException e) {
			Msg.showError(this, getComponent(), "Go To Time", "Could not parse schedule");
		}
	}

	private void activatedHideScratch(ActionContext ctx) {
		hideScratch = !hideScratch;
		mainPanel.setHideScratchSnapshots(hideScratch);
	}

	public void coordinatesActivated(DebuggerCoordinates coordinates) {
		if (sameCoordinates(current, coordinates)) {
			current = coordinates;
			return;
		}
		current = coordinates;

		mainPanel.setTrace(current.getTrace());
		mainPanel.setSelectedSnapshot(current.getSnap());
	}

	public void writeConfigState(SaveState saveState) {
		CONFIG_STATE_HANDLER.writeConfigState(this, saveState);
	}

	public void readConfigState(SaveState saveState) {
		CONFIG_STATE_HANDLER.readConfigState(this, saveState);

		actionHideScratch.setSelected(hideScratch);
		mainPanel.setHideScratchSnapshots(hideScratch);
	}
}
