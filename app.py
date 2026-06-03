from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRegion,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSystemTrayIcon,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Breadcrumbs"
NOTE_TYPES = {
    "TASK": "#7a684f",
    "BLOCKER": "#e35f45",
    "INFO": "#65805a",
    "REQUEST": "#c59b46",
}

INK = "#312b24"
MUTED = "#756c60"
PAPER = "#fcfbf7"
PAPER_2 = "#f4efe5"
PAPER_3 = "#f8f4ec"
EDGE = "#ded6c8"
FIELD = "#fffdf8"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = app_dir()
NOTES_DIR = APP_DIR / "notes"


def week_stamp(value: datetime) -> str:
    iso = value.isocalendar()
    return f"CW{iso.week}.{iso.weekday}"


def today_note_path() -> Path:
    now = datetime.now()
    return NOTES_DIR / f"{now:%Y-%m-%d} {week_stamp(now)}.txt"


def ensure_note_file(path: Path) -> None:
    if path.exists():
        return

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    date_part = path.stem.split(" ", 1)[0]
    week_part = path.stem.split(" ", 1)[1] if " " in path.stem else ""
    title = f"{date_part} {week_part}".strip()
    path.write_text(f"# Work Notes - {title}\n\n## Notes\n\n", encoding="utf-8")


def startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is not set; cannot locate the Windows Startup folder.")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_file() -> Path:
    return startup_folder() / "Breadcrumbs Notes.bat"


def startup_launcher_content() -> str:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        command = f'start "" "{executable}"'
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executable = pythonw if pythonw.exists() else Path(sys.executable).resolve()
        script = Path(__file__).resolve()
        command = f'start "" "{executable}" "{script}"'

    return f'@echo off\ncd /d "{APP_DIR}"\n{command}\n'


def is_startup_enabled() -> bool:
    return startup_file().exists()


def set_startup_enabled(enabled: bool) -> None:
    path = startup_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(startup_launcher_content(), encoding="utf-8")
    elif path.exists():
        path.unlink()


def create_app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    colors = ["#7a684f", "#c59b46", "#e35f45", "#65805a"]
    cell = size // 4
    gap = max(3, size // 16)
    start = (size - (cell * 2 + gap)) // 2
    positions = [(start, start), (start + cell + gap, start), (start, start + cell + gap), (start + cell + gap, start + cell + gap)]

    for color, (x, y) in zip(colors, positions):
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x, y, cell, cell, 3, 3)

    painter.end()
    return QIcon(pixmap)


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DragTitleBar(QFrame):
    def __init__(self, window: QWidget) -> None:
        super().__init__()
        self._window = window
        self._drag_offset = None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class FileLinkLabel(ClickableLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumWidth(170)
        self.setFixedHeight(22)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        hovered = self.underMouse()
        color = QColor("#85683b" if hovered else MUTED)

        font = QFont("Segoe UI", 8)
        font.setWeight(QFont.Weight.DemiBold)
        font.setUnderline(hovered)
        painter.setFont(font)
        painter.setPen(color)

        metrics = QFontMetrics(font)
        text_rect = QRect(0, 0, self.width(), self.height())
        text = metrics.elidedText(self.text().strip(), Qt.TextElideMode.ElideLeft, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class HelpIcon(QLabel):
    def __init__(self) -> None:
        super().__init__("i")
        self.setObjectName("helpIcon")
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.setFixedSize(14, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def enterEvent(self, event) -> None:
        QToolTip.showText(
            self.mapToGlobal(QPoint(-142, self.height() + 4)),
            "Ctrl+Enter  save note\nEsc  hide popup",
            self,
        )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)


class CloseLabel(ClickableLabel):
    def __init__(self) -> None:
        super().__init__("x")
        self.setObjectName("closeIcon")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(16, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class TypeButton(QAbstractButton):
    def __init__(self, text: str, color: str, is_last: bool = False) -> None:
        super().__init__()
        self._color = QColor(color)
        self._is_last = is_last
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        return QSize(104, 55)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.isChecked():
            painter.fillRect(self.rect(), QColor(FIELD))
        elif self.underMouse():
            painter.fillRect(self.rect(), QColor("#fffaf1"))

        if not self._is_last:
            painter.setPen(QPen(QColor(222, 214, 200, 205), 1))
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        bar_width = 5 if self.isChecked() else 4
        bar_rect = QRect(10, (self.height() - 22) // 2, bar_width, 22)
        painter.fillRect(bar_rect, self._color)

        font = QFont("Segoe UI", 8)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(self._color if not self.underMouse() else QColor("#6a5740"))
        painter.drawText(
            QRect(32, 0, self.width() - 38, self.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.text(),
        )

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)


class NotePopup(QWidget):
    saved = Signal()

    def __init__(self) -> None:
        super().__init__()

        self.current_type = "TASK"
        self.type_buttons: dict[str, TypeButton] = {}

        self.setWindowTitle(APP_NAME)
        self.setFixedSize(420, 260)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(self.stylesheet())

        self._build_ui()
        self._bind_shortcuts()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.refresh_time_and_file)
        self.clock_timer.start(30_000)
        self.refresh_time_and_file()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        titlebar = DragTitleBar(self)
        titlebar.setObjectName("titlebar")
        title_layout = QHBoxLayout(titlebar)
        title_layout.setContentsMargins(13, 0, 10, 0)
        title_layout.setSpacing(9)

        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)
        brand_layout.addWidget(self._crumb_icon())

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        brand_layout.addWidget(title)

        self.saved_label = QLabel("Saved")
        self.saved_label.setObjectName("savedFeedback")
        self.saved_label.setFixedWidth(46)
        self.saved_label.hide()
        self.saved_effect = QGraphicsOpacityEffect(self.saved_label)
        self.saved_effect.setOpacity(0.0)
        self.saved_label.setGraphicsEffect(self.saved_effect)
        self.saved_animation = QPropertyAnimation(self.saved_effect, b"opacity", self)
        self.saved_animation.setDuration(1050)
        self.saved_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.saved_animation.setKeyValueAt(0.0, 0.0)
        self.saved_animation.setKeyValueAt(0.18, 1.0)
        self.saved_animation.setKeyValueAt(0.68, 1.0)
        self.saved_animation.setKeyValueAt(1.0, 0.0)
        self.saved_animation.finished.connect(self.saved_label.hide)
        brand_layout.addWidget(self.saved_label)

        self.clock_label = QLabel()
        self.clock_label.setObjectName("clock")

        help_label = HelpIcon()
        close_label = CloseLabel()
        close_label.clicked.connect(self.hide)

        title_layout.addWidget(brand)
        title_layout.addStretch(1)
        title_layout.addWidget(self.clock_label)
        title_layout.addWidget(help_label)
        title_layout.addWidget(close_label)
        root.addWidget(titlebar)

        content = QFrame()
        content.setObjectName("content")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        type_panel = QFrame()
        type_panel.setObjectName("typePanel")
        type_layout = QVBoxLayout(type_panel)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(0)

        self.type_group = QButtonGroup(self)
        self.type_group.setExclusive(True)
        note_items = list(NOTE_TYPES.items())
        for index, (note_type, color) in enumerate(note_items):
            button = TypeButton(note_type, color, is_last=index == len(note_items) - 1)
            button.clicked.connect(lambda checked=False, value=note_type: self.set_note_type(value))
            self.type_group.addButton(button)
            self.type_buttons[note_type] = button
            type_layout.addWidget(button)

        content_layout.addWidget(type_panel)

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(12, 12, 12, 12)
        composer_layout.setSpacing(8)

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(8)

        append_label = QLabel("Appending to:")
        append_label.setObjectName("metaLabel")
        self.file_label = FileLinkLabel()
        self.file_label.setObjectName("fileLink")
        self.file_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_label.clicked.connect(self.open_today_file)

        meta.addWidget(append_label)
        meta.addStretch(1)
        meta.addWidget(self.file_label)

        self.note_edit = QTextEdit()
        self.note_edit.setObjectName("noteEdit")
        self.note_edit.setAcceptRichText(False)
        self.note_edit.setPlaceholderText("Write a note...")

        composer_layout.addLayout(meta)
        composer_layout.addWidget(self.note_edit, 1)
        content_layout.addWidget(composer, 1)

        root.addWidget(content, 1)
        self.set_note_type(self.current_type)

    def _crumb_icon(self) -> QWidget:
        icon = QWidget()
        icon.setFixedSize(17, 17)
        layout = QGridLayout(icon)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        for index, color in enumerate(NOTE_TYPES.values()):
            square = QFrame()
            square.setStyleSheet(f"background: {color}; border-radius: 2px;")
            square.setFixedSize(7, 7)
            layout.addWidget(square, index // 2, index % 2)

        return icon

    def _bind_shortcuts(self) -> None:
        save_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        save_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save_shortcut.activated.connect(self.save_note)

        save_enter_shortcut = QShortcut(QKeySequence("Ctrl+Enter"), self)
        save_enter_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save_enter_shortcut.activated.connect(self.save_note)

        hide_shortcut = QShortcut(QKeySequence("Esc"), self)
        hide_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        hide_shortcut.activated.connect(self.hide)

    def resizeEvent(self, event) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.0, 0.0, -1.0, -1.0), 8.0, 8.0)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(event)

    def stylesheet(self) -> str:
        return f"""
            NotePopup {{
                background: {PAPER};
                color: {INK};
                border: 1px solid rgba(0, 0, 0, 38);
                border-radius: 8px;
                font-family: "Segoe UI";
            }}

            QFrame#titlebar {{
                background: {PAPER_2};
                border-bottom: 1px solid {EDGE};
                min-height: 40px;
                max-height: 40px;
            }}

            QLabel#title {{
                color: #6e5c44;
                font-size: 12px;
                font-weight: 700;
            }}

            QLabel#clock {{
                color: #6b6257;
                font-size: 12px;
                font-weight: 700;
            }}

            QLabel#helpIcon {{
                color: #7e7468;
                font-size: 11px;
                font-style: italic;
                font-weight: 800;
                padding-left: 4px;
            }}

            QLabel#closeIcon {{
                color: #8b8175;
                font-size: 12px;
                font-weight: 700;
            }}

            QLabel#closeIcon:hover {{
                color: #6a5740;
                background: #fffaf1;
                border-radius: 4px;
            }}

            QFrame#content {{
                background: {PAPER};
            }}

            QFrame#typePanel {{
                min-width: 104px;
                max-width: 104px;
                background: {PAPER_3};
                border-right: 1px solid {EDGE};
            }}

            QFrame#composer {{
                background: {PAPER};
            }}

            QLabel#metaLabel {{
                color: {MUTED};
                font-size: 11px;
                font-weight: 650;
            }}

            QLabel#savedFeedback {{
                color: #65805a;
                font-size: 11px;
                font-weight: 700;
            }}

            QLabel#fileLink {{
                background: transparent;
            }}

            QTextEdit#noteEdit {{
                color: #3d342b;
                background: {FIELD};
                border: 1px solid #d9d1c2;
                border-radius: 6px;
                padding: 10px 11px;
                font-size: 13px;
                selection-background-color: #e8d6ad;
            }}

            QTextEdit#noteEdit:hover {{
                background: #fffefa;
                border-color: #c8bca8;
            }}

            QTextEdit#noteEdit:focus {{
                border-color: #b89c60;
            }}

            QTextEdit#noteEdit[savedPulse="true"] {{
                background: #fbfff8;
                border-color: #7fa66e;
            }}

            QToolTip {{
                color: #5f564b;
                background: {FIELD};
                border: 1px solid #d6c8b5;
                padding: 7px;
            }}
        """

    def set_note_type(self, note_type: str) -> None:
        self.current_type = note_type
        for value, button in self.type_buttons.items():
            button.setChecked(value == note_type)

    def refresh_time_and_file(self) -> None:
        now = datetime.now()
        self.clock_label.setText(f"{now:%H:%M}")
        self.file_label.setText(today_note_path().name)

    def show_popup(self) -> None:
        self.refresh_time_and_file()
        self._position_near_cursor()
        self.show()
        self.raise_()
        self.activateWindow()
        self.note_edit.setFocus(Qt.FocusReason.PopupFocusReason)

    def _position_near_cursor(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        geometry = screen.availableGeometry()

        margin = 18
        x = geometry.right() - self.width() - margin + 1
        y = geometry.bottom() - self.height() - margin + 1
        self.move(x, y)

    def save_note(self) -> None:
        text = self.note_edit.toPlainText().strip()
        if not text:
            return

        path = today_note_path()
        now = datetime.now()
        entry = f"[{now:%H:%M}] {self.current_type}\n{text}\n\n"

        try:
            ensure_note_file(path)
            with path.open("a", encoding="utf-8") as file:
                file.write(entry)
        except OSError as error:
            QMessageBox.critical(self, "Could not save note", str(error))
            return

        self.note_edit.clear()
        self.note_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.play_saved_feedback()
        self.saved.emit()

    def play_saved_feedback(self) -> None:
        self.saved_animation.stop()
        self.saved_effect.setOpacity(0.0)
        self.saved_label.show()
        self.saved_animation.start()

        self.note_edit.setProperty("savedPulse", True)
        self.note_edit.style().unpolish(self.note_edit)
        self.note_edit.style().polish(self.note_edit)
        self.note_edit.update()
        QTimer.singleShot(520, self.clear_saved_pulse)

    def clear_saved_pulse(self) -> None:
        self.note_edit.setProperty("savedPulse", False)
        self.note_edit.style().unpolish(self.note_edit)
        self.note_edit.style().polish(self.note_edit)
        self.note_edit.update()

    def open_today_file(self) -> None:
        try:
            path = today_note_path()
            ensure_note_file(path)
            subprocess.Popen(["notepad.exe", str(path)])
        except OSError as error:
            QMessageBox.critical(self, "Could not open today's file", str(error))

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


class TrayApp:
    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.icon = create_app_icon()
        self.popup = NotePopup()
        self.popup.setWindowIcon(self.icon)

        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self.on_tray_activated)

        self.tray_menu = QMenu()
        self.tray_menu.setStyleSheet(self.menu_stylesheet())
        self.add_note_action = QAction("Add note", self.tray_menu)
        self.open_today_action = QAction("Open today's file", self.tray_menu)
        self.open_folder_action = QAction("Open notes folder", self.tray_menu)
        self.startup_action = QAction("Start with Windows", self.tray_menu)
        self.quit_action = QAction("Quit", self.tray_menu)

        self.actions = [
            self.add_note_action,
            self.open_today_action,
            self.open_folder_action,
            self.startup_action,
            self.quit_action,
        ]

        self.add_note_action.triggered.connect(self.popup.show_popup)
        self.open_today_action.triggered.connect(self.open_today_file)
        self.open_folder_action.triggered.connect(self.open_notes_folder)
        self.startup_action.triggered.connect(self.toggle_startup)
        self.quit_action.triggered.connect(self.quit)

        self.tray_menu.addAction(self.add_note_action)
        self.tray_menu.addAction(self.open_today_action)
        self.tray_menu.addAction(self.open_folder_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.startup_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.tray_menu)
        self.refresh_startup_action()
        self.tray.show()

    def menu_stylesheet(self) -> str:
        return f"""
            QMenu {{
                color: {INK};
                background: {FIELD};
                border: 1px solid #d6c8b5;
                border-radius: 8px;
                padding: 6px;
                font-family: "Segoe UI";
                font-size: 12px;
            }}

            QMenu::item {{
                min-width: 176px;
                min-height: 25px;
                padding: 4px 12px 4px 10px;
                border-radius: 5px;
            }}

            QMenu::item:selected {{
                color: #6a5740;
                background: #fffaf1;
            }}

            QMenu::separator {{
                height: 1px;
                background: {EDGE};
                margin: 5px 7px;
            }}
        """

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.popup.show_popup()

    def open_today_file(self) -> None:
        self.popup.open_today_file()

    def open_notes_folder(self) -> None:
        try:
            NOTES_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(NOTES_DIR)
        except OSError as error:
            QMessageBox.critical(self.popup, "Could not open notes folder", str(error))

    def refresh_startup_action(self) -> None:
        enabled = is_startup_enabled()
        self.startup_action.setText("Start with Windows\t✓" if enabled else "Start with Windows")

    def toggle_startup(self) -> None:
        try:
            set_startup_enabled(not is_startup_enabled())
        except OSError as error:
            QMessageBox.critical(self.popup, "Could not update Windows startup", str(error))
        except RuntimeError as error:
            QMessageBox.critical(self.popup, "Could not update Windows startup", str(error))
        finally:
            self.refresh_startup_action()

    def quit(self) -> None:
        self.tray.hide()
        self.app.quit()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "The system tray is not available.")
        return 1

    tray_app = TrayApp(app)
    app.tray_app = tray_app
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
