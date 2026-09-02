"""PySide6 views for the unified robot control console."""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QStackedWidget,
    QSplitter,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .controller import SCENARIOS, ConsoleController
from .models import Environment, Lifecycle, LinkState


def _label(text="", role="muted"):
    label = QLabel(text)
    label.setProperty("role", role)
    return label


class VideoPlaceholder(QWidget):
    """A rendered stand-in that reserves the frame and overlay coordinate space."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 220)
        self._frame_id = 0
        self._overlays_visible = True
        self._rotation_degrees = 90
        self._connected = False
        self._frozen = False
        self._image = None

    def set_state(self, video):
        self._frame_id = video.frame_id
        self._overlays_visible = video.overlays_visible
        self._rotation_degrees = video.rotation_degrees
        self._connected = video.link == LinkState.ONLINE
        self._frozen = video.frozen
        self.update()

    def set_frame(self, frame):
        """Display a copied decoder frame owned by the GUI thread."""
        if self._frozen:
            return
        self._image = frame.image
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        painter.fillRect(rect, QColor("#090e15"))

        grid_pen = QPen(QColor("#172333"), 1)
        painter.setPen(grid_pen)
        step = 36
        for x in range(0, rect.width(), step):
            painter.drawLine(x, 0, x, rect.height())
        for y in range(0, rect.height(), step):
            painter.drawLine(0, y, rect.width(), y)

        floor_y = int(rect.height() * 0.72)
        painter.setPen(QPen(QColor("#33465d"), 1))
        painter.drawLine(0, floor_y, rect.width(), floor_y)
        painter.setBrush(QColor("#344454"))
        base_w = max(90, rect.width() // 5)
        base_h = max(30, rect.height() // 8)
        base_x = int(rect.width() * 0.29)
        base_y = floor_y - base_h
        painter.drawRoundedRect(base_x, base_y, base_w, base_h, 7, 7)
        painter.setPen(QPen(QColor("#b3c2d2"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        shoulder_x = base_x + int(base_w * 0.62)
        shoulder_y = base_y
        elbow_x = shoulder_x + int(rect.width() * 0.08)
        elbow_y = int(rect.height() * 0.37)
        tip_x = elbow_x - int(rect.width() * 0.16)
        tip_y = int(rect.height() * 0.53)
        painter.drawLine(shoulder_x, shoulder_y, elbow_x, elbow_y)
        painter.drawLine(elbow_x, elbow_y, tip_x, tip_y)

        if self._image is not None and not self._image.isNull():
            rotated = self._image.transformed(QTransform().rotate(-self._rotation_degrees))
            scaled = rotated.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawImage((rect.width() - scaled.width()) // 2, (rect.height() - scaled.height()) // 2, scaled)

        if self._overlays_visible:
            target = rect.adjusted(int(rect.width() * 0.72), int(rect.height() * 0.48), -int(rect.width() * 0.13), -int(rect.height() * 0.24))
            painter.setPen(QPen(QColor("#4f8cff"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(target, 4, 4)
            painter.setBrush(QColor("#4f8cff"))
            label_rect = target.adjusted(0, -24, -max(0, target.width() - 118), -target.height())
            painter.drawRoundedRect(label_rect, 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, "object-17 / 0.94")
            cross_x = rect.width() // 2
            cross_y = rect.height() // 2
            painter.setPen(QPen(QColor("#d7e5f4"), 1))
            painter.drawEllipse(cross_x - 12, cross_y - 12, 24, 24)
            painter.drawLine(cross_x - 20, cross_y, cross_x + 20, cross_y)
            painter.drawLine(cross_x, cross_y - 20, cross_x, cross_y + 20)

        painter.setPen(QColor("#d9e7f7"))
        state = "LIVE" if self._connected else "NO SIGNAL"
        if self._frozen:
            state = "FROZEN"
        painter.drawText(12, 22, "%s / frame %d" % (state, self._frame_id))
        painter.setPen(QColor("#95a2b3"))
        painter.drawText(
            rect.adjusted(0, 0, -12, -8),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            "placeholder / display rotation %d deg" % self._rotation_degrees,
        )


class MainWindow(QMainWindow):
    """A responsive desktop shell that binds widgets only to ConsoleController."""

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller or ConsoleController(parent=self)
        self.setWindowTitle("Robot Console - Simulator")
        self.setMinimumSize(1000, 620)
        self.resize(1440, 900)
        self._fault_codes = []
        self._build_window()
        self._connect_signals()
        self._apply_state(self.controller.state)
        self._simulator_timer = QTimer(self)
        self._simulator_timer.setInterval(100)
        self._simulator_timer.timeout.connect(self.controller.tick)
        self._simulator_timer.start()

    def _build_window(self):
        self.setStyleSheet(_stylesheet())
        central = QWidget()
        central.setObjectName("consoleRoot")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(10, 10, 10, 6)
        root_layout.setSpacing(10)
        root_layout.addWidget(self._build_topbar())

        body = QSplitter(Qt.Orientation.Vertical)
        body.setChildrenCollapsible(False)
        body.addWidget(self._build_main_workspace())
        body.addWidget(self._build_diagnostics())
        body.setStretchFactor(0, 8)
        body.setStretchFactor(1, 3)
        body.setSizes([520, 150])
        root_layout.addWidget(body, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.video_health_label = _label("Video offline")
        self.esp_health_label = _label("ESP32 offline")
        self.arm_health_label = _label("Arm offline")
        self.log_health_label = _label("Simulator journal active")
        for widget in (self.video_health_label, self.esp_health_label, self.arm_health_label, self.log_health_label):
            status.addWidget(widget)
            status.addWidget(_label("   "))
        status.addPermanentWidget(_label("No hardware transport in Phase A"))
        self.setStatusBar(status)

    def _build_topbar(self):
        frame = QFrame()
        frame.setObjectName("topbar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 8, 12, 8)
        layout.setSpacing(10)
        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(0)
        brand_layout.addWidget(_label("Robot Console", "title"))
        brand_layout.addWidget(_label("Development workspace", "muted"))
        layout.addWidget(brand)

        self.environment_group = QButtonGroup(self)
        self.simulator_button = QToolButton()
        self.simulator_button.setText("Simulator")
        self.simulator_button.setCheckable(True)
        self.hardware_button = QToolButton()
        self.hardware_button.setText("Hardware")
        self.hardware_button.setCheckable(True)
        self.environment_group.addButton(self.simulator_button)
        self.environment_group.addButton(self.hardware_button)
        mode_frame = QFrame()
        mode_frame.setObjectName("modeFrame")
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(3, 3, 3, 3)
        mode_layout.setSpacing(3)
        mode_layout.addWidget(self.simulator_button)
        mode_layout.addWidget(self.hardware_button)
        layout.addWidget(mode_frame)

        self.video_chip = _label("[ ] Video offline", "chip")
        self.esp_chip = _label("[ ] ESP32 offline", "chip")
        self.arm_chip = _label("[ ] Arm offline", "chip")
        layout.addWidget(self.video_chip)
        layout.addWidget(self.esp_chip)
        layout.addWidget(self.arm_chip)
        layout.addStretch(1)
        self.scenario_combo = QComboBox()
        self.scenario_combo.setToolTip("Deterministic simulator fault scenario")
        for key, title in SCENARIOS:
            self.scenario_combo.addItem(title, key)
        layout.addWidget(self.scenario_combo)
        self.stop_button = QPushButton("Chassis software stop")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setToolTip("Simulator request only in Phase A; this is not a physical emergency stop.")
        layout.addWidget(self.stop_button)
        return frame

    def _build_main_workspace(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_video_panel())
        self.chassis_panel = self._build_chassis_panel()
        self.arm_panel = self._build_arm_panel()
        self.controls_splitter = QSplitter(Qt.Orientation.Vertical)
        self.controls_splitter.setChildrenCollapsible(False)
        self.controls_splitter.addWidget(self.chassis_panel)
        self.controls_splitter.addWidget(self.arm_panel)
        self.controls_splitter.setStretchFactor(0, 1)
        self.controls_splitter.setStretchFactor(1, 1)
        self.controls_tabs = QTabWidget()
        self.controls_host = QStackedWidget()
        self.controls_host.addWidget(self.controls_splitter)
        self.controls_host.addWidget(self.controls_tabs)
        self._compact_controls = False
        splitter.addWidget(self.controls_host)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([850, 470])
        return splitter

    def _set_compact_controls(self, compact):
        if compact == self._compact_controls:
            return
        panels = ((self.chassis_panel, "Chassis"), (self.arm_panel, "Robot arm"))
        if compact:
            for panel, title in panels:
                panel.setParent(None)
                self.controls_tabs.addTab(panel, title)
            self.controls_host.setCurrentWidget(self.controls_tabs)
        else:
            for panel, _title in panels:
                index = self.controls_tabs.indexOf(panel)
                if index >= 0:
                    self.controls_tabs.removeTab(index)
                panel.setParent(None)
                self.controls_splitter.addWidget(panel)
            self.controls_host.setCurrentWidget(self.controls_splitter)
            self.controls_splitter.setSizes([1, 1])
        self._compact_controls = compact

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._set_compact_controls(self.height() < 800 or self.width() < 1280)

    def _panel(self, title, status_text=""):
        panel = QFrame()
        panel.setProperty("panel", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("panelHeader")
        head_layout = QHBoxLayout(header)
        head_layout.setContentsMargins(11, 7, 11, 7)
        head_layout.setSpacing(8)
        head_layout.addWidget(_label(title, "panelTitle"))
        head_layout.addStretch(1)
        status_label = _label(status_text, "chip")
        head_layout.addWidget(status_label)
        layout.addWidget(header)
        return panel, layout, status_label

    def _build_video_panel(self):
        panel, layout, self.video_panel_status = self._panel("Camera", "[ ] Preview offline")
        self.video_canvas = VideoPlaceholder()
        layout.addWidget(self.video_canvas, 1)
        toolbar = QFrame()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(7)
        self.video_connect_button = QPushButton("Connect preview")
        self.snapshot_button = QPushButton("Snapshot")
        self.rotate_button = QPushButton("Rotate 90 deg")
        self.overlay_button = QPushButton("Hide overlay")
        self.freeze_button = QPushButton("Freeze")
        for widget in (self.video_connect_button, self.snapshot_button, self.rotate_button, self.overlay_button, self.freeze_button):
            toolbar_layout.addWidget(widget)
        toolbar_layout.addStretch(1)
        self.video_metrics_label = _label("No decoded frames", "muted")
        toolbar_layout.addWidget(self.video_metrics_label)
        layout.addWidget(toolbar)
        return panel

    def _build_chassis_panel(self):
        panel, layout, self.chassis_panel_status = self._panel("Chassis", "[ ] Offline")
        status_grid = QHBoxLayout()
        status_grid.setContentsMargins(10, 7, 10, 3)
        status_grid.setSpacing(8)
        self.chassis_tcp_value = _label("Offline", "value")
        self.chassis_motion_value = _label("Locked", "value")
        for name, value in (("Link", self.chassis_tcp_value), ("Drive", self.chassis_motion_value)):
            status_grid.addWidget(_label(name))
            status_grid.addWidget(value)
        status_grid.addStretch(1)
        layout.addLayout(status_grid)

        session = QHBoxLayout()
        session.setContentsMargins(10, 4, 10, 6)
        session.setSpacing(6)
        self.chassis_connect_button = QPushButton("Connect")
        self.chassis_enable_button = QPushButton("Enable")
        self.chassis_disable_button = QPushButton("Disable")
        for widget in (self.chassis_connect_button, self.chassis_enable_button, self.chassis_disable_button):
            session.addWidget(widget)
        session.addStretch(1)
        layout.addLayout(session)

        controls = QHBoxLayout()
        controls.setContentsMargins(10, 4, 10, 8)
        controls.setSpacing(13)
        pad = QGridLayout()
        pad.setSpacing(4)
        self.chassis_direction_buttons = []
        commands = (
            ("CCW", 0, 0, (0, 0, -1)),
            ("FWD", 0, 1, (1, 0, 0)),
            ("CW", 0, 2, (0, 0, 1)),
            ("LEFT", 1, 0, (0, 1, 0)),
            ("STOP", 1, 1, None),
            ("RIGHT", 1, 2, (0, -1, 0)),
            ("BACK", 2, 1, (-1, 0, 0)),
        )
        for text, row, column, direction in commands:
            button = QPushButton(text)
            button.setObjectName("directionButton" if direction is not None else "localStopButton")
            if direction is None:
                button.clicked.connect(self.controller.chassis_stop)
            else:
                button.pressed.connect(lambda item=direction: self._start_chassis_hold(item))
                button.released.connect(self.controller.chassis_stop)
            pad.addWidget(button, row, column)
            self.chassis_direction_buttons.append(button)
        controls.addLayout(pad)

        limits = QVBoxLayout()
        self.linear_limit_label = _label("Speed 80 mm/s")
        self.linear_slider = QSlider(Qt.Orientation.Horizontal)
        self.linear_slider.setRange(10, 200)
        self.linear_slider.setValue(80)
        self.angular_limit_label = _label("Turn 240 mrad/s")
        self.angular_slider = QSlider(Qt.Orientation.Horizontal)
        self.angular_slider.setRange(10, 400)
        self.angular_slider.setValue(240)
        self.chassis_vector_label = _label("Cmd 0 / 0 / 0", "muted")
        for widget in (self.linear_limit_label, self.linear_slider, self.angular_limit_label, self.angular_slider, self.chassis_vector_label):
            limits.addWidget(widget)
        controls.addLayout(limits, 1)
        layout.addLayout(controls)
        return panel

    def _spin(self, value, minimum=-360.0, maximum=360.0, suffix=" deg"):
        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def _form_page(self, labels, values, ranges=None):
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(7)
        spins = []
        for index, (label, value) in enumerate(zip(labels, values)):
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            cell_layout.addWidget(_label(label))
            lower, upper, suffix = ranges[index] if ranges else (-360.0, 360.0, " deg")
            spin = self._spin(value, lower, upper, suffix)
            cell_layout.addWidget(spin)
            spins.append(spin)
            layout.addWidget(cell, index // 3, index % 3)
        return page, spins, layout

    def _build_arm_panel(self):
        panel, layout, self.arm_panel_status = self._panel("Robot arm", "[ ] Gateway offline")
        route = QGridLayout()
        route.setContentsMargins(10, 8, 10, 4)
        self.arm_gateway_value = _label("Offline", "value")
        self.arm_uart_value = _label("Offline", "value")
        self.arm_controller_value = _label("Offline", "value")
        self.arm_task_value = _label("Idle", "value")
        for index, (name, value) in enumerate((("MaixCam", self.arm_gateway_value), ("UART / LAN1", self.arm_uart_value), ("Controller", self.arm_controller_value), ("Task", self.arm_task_value))):
            row, column = (index // 2) * 2, index % 2
            route.addWidget(_label(name), row, column)
            route.addWidget(value, row + 1, column)
        layout.addLayout(route)

        arm_session = QHBoxLayout()
        arm_session.setContentsMargins(10, 4, 10, 6)
        self.arm_connect_button = QPushButton("Connect arm route")
        self.arm_recheck_button = QPushButton("Recheck status")
        arm_session.addWidget(self.arm_connect_button)
        arm_session.addWidget(self.arm_recheck_button)
        arm_session.addStretch(1)
        layout.addLayout(arm_session)

        self.arm_runtime_detail = _label("Route offline. Connect to request arm status.", "muted")
        self.arm_runtime_detail.setWordWrap(True)
        detail_frame = QFrame()
        detail_layout = QHBoxLayout(detail_frame)
        detail_layout.setContentsMargins(10, 2, 10, 7)
        detail_layout.addWidget(self.arm_runtime_detail, 1)
        layout.addWidget(detail_frame)

        self.arm_tabs = QTabWidget()
        joint_jog_page = QWidget()
        joint_jog_layout = QGridLayout(joint_jog_page)
        joint_jog_layout.setContentsMargins(10, 8, 10, 8)
        self.joint_jog_step = self._spin(2.0, 0.1, 360.0, " deg")
        self.arm_jog_speed = self._spin(5.0, 1.0, 100.0, " %")
        self.arm_jog_accel = self._spin(5.0, 1.0, 100.0, " %")
        joint_jog_layout.addWidget(_label("Step"), 0, 0)
        joint_jog_layout.addWidget(self.joint_jog_step, 0, 1)
        joint_jog_layout.addWidget(_label("Speed"), 0, 2)
        joint_jog_layout.addWidget(self.arm_jog_speed, 0, 3)
        joint_jog_layout.addWidget(_label("Accel"), 0, 4)
        joint_jog_layout.addWidget(self.arm_jog_accel, 0, 5)
        self.joint_jog_buttons = []
        for index in range(6):
            row, column = 1 + index // 2, (index % 2) * 3
            minus, plus = QPushButton("−"), QPushButton("+")
            joint_jog_layout.addWidget(_label("J%d" % (index + 1)), row, column)
            joint_jog_layout.addWidget(minus, row, column + 1)
            joint_jog_layout.addWidget(plus, row, column + 2)
            self.joint_jog_buttons.extend((minus, plus))
        self.arm_tabs.addTab(joint_jog_page, "J1-J6 jog")

        xyz_jog_page = QWidget()
        xyz_jog_layout = QGridLayout(xyz_jog_page)
        xyz_jog_layout.setContentsMargins(10, 8, 10, 8)
        self.xyz_jog_step = self._spin(5.0, 0.1, 500.0, " mm")
        xyz_jog_layout.addWidget(_label("Step"), 0, 0)
        xyz_jog_layout.addWidget(self.xyz_jog_step, 0, 1)
        xyz_jog_layout.addWidget(_label("Uses the same speed and acceleration from J1-J6 jog."), 0, 2, 1, 4)
        self.xyz_jog_buttons = []
        for index, axis in enumerate("XYZ"):
            minus, plus = QPushButton("−"), QPushButton("+")
            xyz_jog_layout.addWidget(_label(axis), index + 1, 0)
            xyz_jog_layout.addWidget(minus, index + 1, 1)
            xyz_jog_layout.addWidget(plus, index + 1, 2)
            self.xyz_jog_buttons.extend((minus, plus))
        self.arm_tabs.addTab(xyz_jog_page, "XYZ jog")

        joint_page, self.joint_spins, joint_layout = self._form_page(
            ("J1", "J2", "J3", "J4", "J5", "J6"),
            (0.0, -18.0, 32.0, 0.0, 76.0, 0.0),
        )
        self.joint_execute_button = QPushButton("Execute joint move")
        joint_layout.addWidget(_label("Measured joint pose: unavailable", "muted"), 2, 0, 1, 2)
        joint_layout.addWidget(self.joint_execute_button, 2, 2)
        self.arm_tabs.addTab(joint_page, "Absolute J")

        cartesian_page, self.cartesian_spins, cartesian_layout = self._form_page(
            ("X", "Y", "Z", "Rx", "Ry", "Rz"),
            (320.0, 0.0, 280.0, 180.0, 0.0, 90.0),
            ((-2_000.0, 2_000.0, " mm"), (-2_000.0, 2_000.0, " mm"), (-2_000.0, 2_000.0, " mm"), (-360.0, 360.0, " deg"), (-360.0, 360.0, " deg"), (-360.0, 360.0, " deg")),
        )
        self.linear_execute_button = QPushButton("Execute linear move")
        cartesian_layout.addWidget(_label("Measured Cartesian pose: unavailable", "muted"), 2, 0, 1, 2)
        cartesian_layout.addWidget(self.linear_execute_button, 2, 2)
        self.arm_tabs.addTab(cartesian_page, "Absolute XYZ")

        gripper_page = QWidget()
        gripper_layout = QHBoxLayout(gripper_page)
        gripper_layout.setContentsMargins(10, 12, 10, 12)
        grip_cell = QVBoxLayout()
        grip_cell.addWidget(_label("Requested width"))
        self.gripper_spin = self._spin(35.0, 0.0, 100.0, " mm")
        grip_cell.addWidget(self.gripper_spin)
        gripper_layout.addLayout(grip_cell)
        gripper_layout.addWidget(_label("Capability and terminal width feedback are unavailable.", "muted"), 1)
        self.gripper_execute_button = QPushButton("Set gripper width")
        gripper_layout.addWidget(self.gripper_execute_button)
        self.arm_tabs.addTab(gripper_page, "Gripper")
        layout.addWidget(self.arm_tabs, 1)
        return panel

    def _build_diagnostics(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        journal, journal_layout, _ = self._panel("Command and event journal")
        self.journal_table = QTableWidget(0, 6)
        self.journal_table.setHorizontalHeaderLabels(("Time", "Target", "Command", "ID", "Lifecycle", "Result"))
        self.journal_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.journal_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.journal_table.verticalHeader().setVisible(False)
        self.journal_table.setAlternatingRowColors(True)
        self.journal_table.horizontalHeader().setStretchLastSection(True)
        journal_layout.addWidget(self.journal_table, 1)
        splitter.addWidget(journal)

        faults, faults_layout, _ = self._panel("Active faults")
        self.fault_list = QListWidget()
        self.fault_detail = _label("No active faults.", "muted")
        self.fault_detail.setWordWrap(True)
        fault_actions = QHBoxLayout()
        self.fault_ack_button = QPushButton("Acknowledge")
        self.fault_recheck_button = QPushButton("Recheck")
        fault_actions.addWidget(self.fault_ack_button)
        fault_actions.addWidget(self.fault_recheck_button)
        fault_actions.addStretch(1)
        faults_layout.addWidget(self.fault_list, 1)
        faults_layout.addWidget(self.fault_detail)
        faults_layout.addLayout(fault_actions)
        splitter.addWidget(faults)
        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([800, 360])
        return splitter

    def _connect_signals(self):
        self.simulator_button.clicked.connect(lambda: self.controller.set_environment(Environment.SIMULATOR))
        self.hardware_button.clicked.connect(lambda: self.controller.set_environment(Environment.HARDWARE))
        self.scenario_combo.currentIndexChanged.connect(self._scenario_changed)
        self.stop_button.clicked.connect(self.controller.chassis_stop)
        self.video_connect_button.clicked.connect(self._toggle_video_connection)
        self.snapshot_button.clicked.connect(self.controller.snapshot)
        self.rotate_button.clicked.connect(self.controller.rotate_video)
        self.overlay_button.clicked.connect(self.controller.toggle_overlays)
        self.freeze_button.clicked.connect(self.controller.toggle_video_freeze)
        self.chassis_connect_button.clicked.connect(self._toggle_chassis_connection)
        self.chassis_enable_button.clicked.connect(self.controller.chassis_enable)
        self.chassis_disable_button.clicked.connect(self.controller.chassis_disable)
        self.linear_slider.valueChanged.connect(self._update_limit_labels)
        self.angular_slider.valueChanged.connect(self._update_limit_labels)
        self.arm_connect_button.clicked.connect(self._toggle_arm_connection)
        self.arm_recheck_button.clicked.connect(self.controller.recheck)
        for index in range(6):
            self.joint_jog_buttons[index * 2].clicked.connect(lambda _checked=False, i=index: self._jog_joint(i, -1))
            self.joint_jog_buttons[index * 2 + 1].clicked.connect(lambda _checked=False, i=index: self._jog_joint(i, 1))
        for index in range(3):
            self.xyz_jog_buttons[index * 2].clicked.connect(lambda _checked=False, i=index: self._jog_xyz(i, -1))
            self.xyz_jog_buttons[index * 2 + 1].clicked.connect(lambda _checked=False, i=index: self._jog_xyz(i, 1))
        self.joint_execute_button.clicked.connect(self._execute_joint)
        self.linear_execute_button.clicked.connect(self._execute_linear)
        self.gripper_execute_button.clicked.connect(self._execute_gripper)
        self.fault_list.currentRowChanged.connect(self._fault_selected)
        self.fault_ack_button.clicked.connect(self._acknowledge_selected_fault)
        self.fault_recheck_button.clicked.connect(self.controller.recheck)
        self.controller.state_changed.connect(self._apply_state)
        self.controller.event_added.connect(self._append_event)
        self.controller.faults_changed.connect(self._apply_faults)
        self.controller.video_frame_ready.connect(self.video_canvas.set_frame)

    def _scenario_changed(self):
        self.controller.set_scenario(self.scenario_combo.currentData())

    def _toggle_video_connection(self):
        if self.controller.state.video.link == LinkState.OFFLINE:
            self.controller.connect_video()
        else:
            self.controller.disconnect_video()

    def _toggle_chassis_connection(self):
        if self.controller.state.chassis.link == LinkState.OFFLINE:
            self.controller.connect_chassis()
        else:
            self.controller.disconnect_chassis()

    def _toggle_arm_connection(self):
        if self.controller.state.arm.gateway == LinkState.OFFLINE:
            self.controller.connect_arm()
        else:
            self.controller.disconnect_arm()

    def _update_limit_labels(self):
        self.linear_limit_label.setText("Speed %d mm/s" % self.linear_slider.value())
        self.angular_limit_label.setText("Turn %d mrad/s" % self.angular_slider.value())

    def _start_chassis_hold(self, direction):
        linear = self.linear_slider.value()
        angular = self.angular_slider.value()
        vx = direction[0] * linear
        vy = direction[1] * linear
        omega = direction[2] * angular
        self.controller.chassis_velocity(vx, vy, omega)

    def _execute_joint(self):
        detail = ", ".join("%.1f" % spin.value() for spin in self.joint_spins)
        payload = {"joint_deg": [spin.value() for spin in self.joint_spins], "accel_pct": int(self.arm_jog_accel.value()), "speed_pct": int(self.arm_jog_speed.value())}
        self._finish_simulated_arm_if_needed(self.controller.execute_arm("arm.move_joint", "joint_deg=[%s]" % detail, payload))

    def _execute_linear(self):
        detail = ", ".join("%.1f" % spin.value() for spin in self.cartesian_spins)
        payload = {"pose": [spin.value() for spin in self.cartesian_spins], "user": 0, "tool": 0, "accel_pct": int(self.arm_jog_accel.value()), "speed_pct": int(self.arm_jog_speed.value())}
        self._finish_simulated_arm_if_needed(self.controller.execute_arm("arm.move_linear", "pose=[%s]" % detail, payload))

    def _execute_gripper(self):
        self._finish_simulated_arm_if_needed(self.controller.execute_arm("arm.gripper", "width_mm=%.1f" % self.gripper_spin.value(), {"width_mm": self.gripper_spin.value()}))

    def _finish_simulated_arm_if_needed(self, accepted):
        if accepted and self.controller.state.environment == Environment.SIMULATOR:
            QTimer.singleShot(650, self.controller.complete_arm_command)

    def _jog_joint(self, index, direction):
        accepted = self.controller.jog_arm_joint(
            index, direction * self.joint_jog_step.value(),
            self.arm_jog_accel.value(), self.arm_jog_speed.value(),
        )
        self._finish_simulated_arm_if_needed(accepted)

    def _jog_xyz(self, index, direction):
        accepted = self.controller.jog_arm_xyz(
            index, direction * self.xyz_jog_step.value(),
            self.arm_jog_accel.value(), self.arm_jog_speed.value(),
        )
        self._finish_simulated_arm_if_needed(accepted)

    @staticmethod
    def _state_text(link):
        return {
            LinkState.ONLINE: "Online",
            LinkState.DEGRADED: "Degraded",
            LinkState.UNKNOWN: "Unknown",
            LinkState.OFFLINE: "Offline",
        }[link]

    @staticmethod
    def _chip_text(name, link):
        marker = {
            LinkState.ONLINE: "[+]",
            LinkState.DEGRADED: "[!]",
            LinkState.UNKNOWN: "[?]",
            LinkState.OFFLINE: "[ ]",
        }[link]
        return "%s %s %s" % (marker, name, MainWindow._state_text(link).lower())

    def _set_chip(self, label, name, link):
        label.setText(self._chip_text(name, link))
        label.setProperty("state", link.value)
        label.style().unpolish(label)
        label.style().polish(label)

    def _apply_state(self, state):
        hardware_title = "Hardware (manual enabled)" if self.controller._hardware_manual_enabled() else "Hardware (locked)"
        self.setWindowTitle("Robot Console - %s" % ("Simulator" if state.environment == Environment.SIMULATOR else hardware_title))
        self.simulator_button.setChecked(state.environment == Environment.SIMULATOR)
        self.hardware_button.setChecked(state.environment == Environment.HARDWARE)
        self.scenario_combo.setEnabled(state.environment == Environment.SIMULATOR)
        self._set_chip(self.video_chip, "Video", state.video.link)
        self._set_chip(self.esp_chip, "ESP32", state.chassis.link)
        self._set_chip(self.arm_chip, "Arm", state.arm.gateway)

        self._set_chip(self.video_panel_status, "Preview", state.video.link)
        self.video_canvas.set_state(state.video)
        self.video_connect_button.setText("Disconnect preview" if state.video.link != LinkState.OFFLINE else "Connect preview")
        self.freeze_button.setText("Resume" if state.video.frozen else "Freeze")
        self.overlay_button.setText("Show overlay" if not state.video.overlays_visible else "Hide overlay")
        self.video_metrics_label.setText(
            "%s / %s / %.0f fps / frame %d / decode %s / age %s"
            % (
                self._state_text(state.video.link),
                "%d x %d" % state.video.resolution if state.video.resolution else "resolution unavailable",
                state.video.fps,
                state.video.frame_id,
                "%d ms" % state.video.decode_latency_ms if state.video.decode_latency_ms is not None else "unavailable",
                "%d ms" % state.video.last_frame_age_ms if state.video.last_frame_age_ms is not None else "unavailable",
            )
        )

        chassis = state.chassis
        self._set_chip(self.chassis_panel_status, chassis.reported_state, chassis.link)
        self.chassis_tcp_value.setText(self._state_text(chassis.link))
        self.chassis_motion_value.setText("Enabled" if chassis.motion_enabled else "Disabled" if chassis.motion_permitted else "Locked")
        self.chassis_connect_button.setText("Disconnect" if chassis.link != LinkState.OFFLINE else "Connect")
        manual_mode = state.environment == Environment.SIMULATOR or self.controller._hardware_manual_enabled()
        if state.environment == Environment.HARDWARE and self.controller._hardware_manual_enabled():
            limits = self.controller.runtime.config.manual_chassis
            self.linear_slider.setMaximum(limits.linear_limit_mm_s)
            self.angular_slider.setMaximum(limits.angular_limit_mrad_s)
        self.chassis_enable_button.setEnabled(manual_mode and chassis.link == LinkState.ONLINE and chassis.authenticated and chassis.motion_permitted and not chassis.motion_enabled)
        self.chassis_disable_button.setEnabled(manual_mode and chassis.motion_enabled)
        self.chassis_vector_label.setText(
            "Cmd %d / %d / %d"
            % chassis.velocity
        )
        for button in self.chassis_direction_buttons:
            button.setEnabled(self.controller.can_chassis_move() or button.objectName() == "localStopButton")

        arm = state.arm
        self._set_chip(self.arm_panel_status, "Gateway", arm.gateway)
        self.arm_gateway_value.setText(self._state_text(arm.gateway))
        self.arm_uart_value.setText(self._state_text(arm.uart_lan1))
        self.arm_controller_value.setText(self._state_text(arm.controller))
        self.arm_task_value.setText("%s / %s" % (arm.task.value.title(), arm.reported_state))
        self.arm_connect_button.setText("Disconnect arm route" if arm.gateway != LinkState.OFFLINE else "Connect arm route")
        arm_enabled = self.controller.can_arm_move()
        for button in self.joint_jog_buttons + self.xyz_jog_buttons + [self.joint_execute_button, self.linear_execute_button, self.gripper_execute_button]:
            button.setEnabled(arm_enabled)
        self.arm_tabs.setVisible(True)
        if state.environment == Environment.HARDWARE:
            if arm.gateway != LinkState.ONLINE:
                detail = "Connect MaixCam to use the arm route."
            elif arm.control_mode == "yolo" and arm.motion_permitted:
                detail = "YOLO manual mode: repeatable jog and direct commands enabled; Dobot controller safeguards remain active."
            else:
                detail = "Route ready, but the deployed controller is not in YOLO mode."
        else:
            detail = "Simulator: repeatable jog and direct commands use simulated lifecycle events."
        self.arm_runtime_detail.setText(detail)

        self.video_health_label.setText("Video %s" % self._state_text(state.video.link).lower())
        health_age = "%d ms" % chassis.health_age_ms if chassis.health_age_ms is not None else "unavailable"
        self.esp_health_label.setText("ESP32 health %s" % health_age)
        arm_age = "%d ms" % arm.last_status_age_ms if arm.last_status_age_ms is not None else "unavailable"
        self.arm_health_label.setText("Arm status age %s" % arm_age)

    def _append_event(self, event):
        self.journal_table.insertRow(0)
        timestamp = datetime.fromtimestamp(event.timestamp_ms / 1000).strftime("%H:%M:%S.%f")[:-3]
        values = (timestamp, event.target, event.command, event.correlation_id, event.lifecycle.value.upper(), event.result)
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if event.lifecycle in (Lifecycle.REJECTED, Lifecycle.FAULT, Lifecycle.UNKNOWN):
                item.setForeground(QColor("#e5ad45" if event.lifecycle == Lifecycle.REJECTED else "#ff6b6b"))
            self.journal_table.setItem(0, column, item)
        self.journal_table.setRowHeight(0, 25)
        while self.journal_table.rowCount() > 200:
            self.journal_table.removeRow(self.journal_table.rowCount() - 1)

    def _apply_faults(self, faults):
        selected = self.fault_list.currentRow()
        self.fault_list.clear()
        self._fault_codes = []
        for fault in faults:
            marker = {"info": "i", "warning": "!", "fault": "!", "unknown": "?"}.get(fault.severity, "!")
            text = "%s %s: %s" % (marker, fault.source.title(), fault.summary)
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, fault.code)
            self.fault_list.addItem(item)
            self._fault_codes.append(fault.code)
        if self.fault_list.count():
            self.fault_list.setCurrentRow(min(max(selected, 0), self.fault_list.count() - 1))
        else:
            self.fault_detail.setText("No active faults.")
            self.fault_ack_button.setEnabled(False)

    def _fault_selected(self, row):
        if row < 0 or row >= len(self.controller.state.faults):
            return
        fault = self.controller.state.faults[row]
        acknowledged = "acknowledged" if fault.acknowledged else "unacknowledged"
        self.fault_detail.setText("%s / %s / %s\n%s" % (fault.severity.upper(), fault.source, acknowledged, fault.summary))
        self.fault_ack_button.setEnabled(not fault.acknowledged)

    def _acknowledge_selected_fault(self):
        item = self.fault_list.currentItem()
        if item is not None:
            self.controller.acknowledge_fault(item.data(Qt.ItemDataRole.UserRole))

    def run_smoke_assertions(self):
        """Verify that construction preserves the safe simulator default."""
        state = self.controller.state
        assert state.environment == Environment.SIMULATOR
        assert state.chassis.motion_enabled is False
        assert state.arm.manual_unlocked is False
        assert self.joint_execute_button.isEnabled() is False
        assert self.video_canvas.minimumWidth() > 0

    def closeEvent(self, event):
        runtime = getattr(self.controller, "runtime", None)
        if runtime is not None:
            runtime.close()
        super().closeEvent(event)


def _stylesheet():
    return """
    QWidget#consoleRoot { background: #0d1117; color: #edf2f7; font-family: 'Segoe UI'; }
    QFrame#topbar, QFrame[panel='true'] { background: #161c24; border: 1px solid #2a3442; border-radius: 10px; }
    QFrame#panelHeader { border-bottom: 1px solid #2a3442; border-top-left-radius: 10px; border-top-right-radius: 10px; }
    QFrame#modeFrame { background: #0d1117; border: 1px solid #2a3442; border-radius: 8px; }
    QLabel[role='title'] { font-size: 15px; font-weight: 600; }
    QLabel[role='panelTitle'] { font-size: 14px; font-weight: 600; }
    QLabel[role='muted'] { color: #95a2b3; }
    QLabel[role='value'] { color: #edf2f7; font-weight: 600; }
    QLabel[role='chip'] { color: #cbd5e1; background: #1c2430; border: 1px solid #2a3442; border-radius: 12px; padding: 4px 8px; }
    QLabel[role='chip'][state='online'] { color: #62d69c; border-color: #236645; }
    QLabel[role='chip'][state='degraded'] { color: #e5ad45; border-color: #72551d; }
    QLabel[role='chip'][state='unknown'] { color: #e5ad45; border-color: #72551d; }
    QLabel[role='chip'][state='offline'] { color: #95a2b3; }
    QPushButton, QToolButton { background: #1c2430; border: 1px solid #2a3442; border-radius: 7px; padding: 6px 10px; min-height: 22px; }
    QPushButton:hover, QToolButton:hover { background: #263449; }
    QPushButton:disabled, QToolButton:disabled { color: #667085; background: #141a22; border-color: #202a36; }
    QToolButton:checked { background: #3f7fe8; color: white; border-color: #4f8cff; }
    QPushButton#stopButton { color: #ff8787; border-color: #d84a4a; background: #402020; font-weight: 600; }
    QPushButton#directionButton, QPushButton#localStopButton { min-width: 40px; min-height: 32px; padding: 2px; font-size: 11px; }
    QPushButton#localStopButton { color: #ff8787; }
    QSlider::groove:horizontal { height: 5px; background: #445064; border-radius: 2px; }
    QSlider::handle:horizontal { width: 14px; margin: -5px 0; border-radius: 7px; background: #4f8cff; }
    QDoubleSpinBox, QComboBox { background: #0d1117; border: 1px solid #2a3442; border-radius: 6px; padding: 4px 6px; min-height: 23px; }
    QTabWidget::pane { border: 1px solid #2a3442; border-radius: 7px; }
    QTabBar::tab { background: #161c24; color: #95a2b3; padding: 7px 12px; border: 0; }
    QTabBar::tab:selected { color: #72a4ff; border-bottom: 2px solid #4f8cff; }
    QTableWidget, QListWidget { background: #141a22; border: 0; alternate-background-color: #19212c; gridline-color: #2a3442; }
    QTableWidget::item, QListWidget::item { padding: 5px; }
    QHeaderView::section { background: #161c24; color: #95a2b3; border: 0; border-bottom: 1px solid #2a3442; padding: 6px; }
    QStatusBar { background: #161c24; color: #95a2b3; border-top: 1px solid #2a3442; }
    QSplitter::handle { background: #0d1117; }
    """
