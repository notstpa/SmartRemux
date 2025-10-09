
# =============================================================================
# IMPORTS AND DEPENDENCIES
# =============================================================================
# Import all required Python modules and libraries for the PyQt video remuxer GUI
import sys
import os
import subprocess
import threading
import queue
import time
import json
import shutil
import concurrent.futures
from pathlib import Path

# PyQt imports
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QLabel, QPushButton, QProgressBar,
    QTextEdit, QTabWidget, QFrame, QGroupBox, QCheckBox, QRadioButton,
    QComboBox, QLineEdit, QScrollArea, QSplitter, QFileDialog,
    QMessageBox, QInputDialog, QDialog, QDialogButtonBox, QTextBrowser,
    QButtonGroup, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateTimeEdit,
    QSizePolicy
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, pyqtSlot, QTimer, QSettings, QDir,
    QStandardPaths, QUrl, QMimeData, QMutex, QWaitCondition, QObject
)
from PyQt5.QtGui import (
    QIcon, QFont, QPalette, QColor, QPixmap, QImage, QClipboard,
    QGuiApplication, QDesktopServices
)

# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================
WINDOW_WIDTH = 575
WINDOW_HEIGHT = 475
PROGRESS_UPDATE_INTERVAL = 100  # milliseconds
MAX_QUEUE_MESSAGES_PER_UPDATE = 10  # Maximum messages to process per UI update
FFPROBE_TIMEOUT = 5   # seconds (reduced for faster failure detection)
FPS_SCAN_TIMEOUT = 8  # seconds (reduced for faster failure detection)
PROCESS_TIMEOUT = 3600  # seconds (1 hour) - timeout for individual file processing
LOG_TEXT_HEIGHT = 8
DEFAULT_TIMESCALE = "30"

# File operation modes
FILE_ACTION_MOVE = "move"
FILE_ACTION_KEEP = "keep"
FILE_ACTION_DELETE = "delete"

# UI States
UI_STATE_DISABLED = False
UI_STATE_NORMAL = True

# =============================================================================
# MAIN APPLICATION CLASS - RemuxApp
# =============================================================================
class RemuxApp(QMainWindow):
    """
    Enhanced PyQt-based GUI application for remuxing video files,
    featuring improved progress tracking, format support, and resume capability.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stpa Remuxer v2.1")
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        # Allow vertical resizing by not constraining maximum height

        # Set custom window icon
        self.set_window_icon("ICOtrans.ico")

        # Center the window
        self.center_window()

        # Enable drag and drop for the main window
        self.setAcceptDrops(True)

        # Minimal bottom scanning status in the status bar
        self.scan_status_label = QLabel("")
        self.scan_status_bar = QProgressBar()
        self.scan_status_bar.setRange(0, 100)
        self.scan_status_bar.setTextVisible(False)
        self.scan_status_bar.setStyleSheet("""
            QProgressBar { background: #e5e7eb; border: 0; height: 6px; border-radius: 3px; }
            QProgressBar::chunk { background-color: #0078D7; border-radius: 3px; }
        """)
        self.scan_status_bar.hide()
        try:
            sb = self.statusBar()
            sb.setStyleSheet("QStatusBar{background:#fafafa;border-top:1px solid #ececec;}")
            # Hide label by default so the bar can span the width; keep for future if needed
            self.scan_status_label.hide()
            sb.addPermanentWidget(self.scan_status_bar, 1)
        except Exception:
            # Fallback if status bar isn't available
            pass

        # DEBUG: Log main window creation
        # print(f"[DEBUG] Main window created: {self.windowTitle()} at position ({self.x()}, {self.y()}) size ({self.width()}, {self.height()})")

        # --- Application State ---
        # Check for required tools (ffmpeg and ffprobe) at startup
        self.ffmpeg_path = self.find_ffmpeg_path()
        self.ffprobe_path = self.find_ffprobe_path()

        # DEBUG: Log tool paths
        # print(f"[DEBUG] FFmpeg path: {self.ffmpeg_path}")
        # print(f"[DEBUG] FFprobe path: {self.ffprobe_path}")

        # Show error dialog with retry option if required tools are not found
        if not self.ffmpeg_path or not self.ffprobe_path:
            # print("[DEBUG] Missing tools detected, showing dialog...")
            self.show_missing_tools_dialog()
            return  # Exit __init__ early if tools are missing

        self.output_directory = ""
        self.files_to_process = []
        self.scan_results = {}
        self.is_scanned = False
        self.process_queue = queue.Queue()
        self.current_process = None
        self.selected_output_directory = ""  # Track user-selected output directory

        # --- Threading locks for safety ---
        self.state_lock = threading.Lock()
        self.process_lock = threading.Lock()

        # --- Threading Events ---
        self.pause_event = threading.Event()
        self.pause_event.set()  # Set by default (not paused)
        self.cancel_event = threading.Event()
        self.skip_event = threading.Event()

        # --- Statistics ---
        self.processing_start_time = None  # Track when processing starts for elapsed time
        self.scan_start_time = None  # Track when scanning starts for elapsed time
        self.last_scan_time_str = None # Store the final scan time string

        # --- Supported formats ---
        self.supported_formats = {
            'input': ['.mkv'],
            'output': ['.mp4', '.mov']
        }

        # --- Settings Variables ---
        self.use_timescale_option = True
        self.include_audio = True
        self.file_action = FILE_ACTION_KEEP
        self.output_format = ".mp4"
        self.validate_files = True
        self.preserve_timestamps = True
        self.preview_commands = False
        self.overwrite_existing = False
        self.debug_mode = False  # Debug mode for showing detailed logs

        # --- Settings State ---
        self.settings_disabled = False

        # Create UI
        self.create_widgets()
        self.setup_timer()

        # Connect auto-save signals (skip btn_run and auto_start_checkbox since they no longer exist)
        self.setup_auto_save()

    def center_window(self):
        """Center the window on the screen."""
        frame_geometry = self.frameGeometry()
        center_point = QGuiApplication.primaryScreen().availableGeometry().center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

    def setup_timer(self):
        """Set up the progress update timer."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_queue)
        self.timer.start(PROGRESS_UPDATE_INTERVAL)

    def setup_auto_save(self):
        """Set up auto-save functionality for settings."""
        # Connect all setting controls to auto-save when changed
        # Checkboxes
        self.audio_checkbox.stateChanged.connect(self.update_checkbox_settings)
        self.timestamp_checkbox.stateChanged.connect(self.update_checkbox_settings)
        self.overwrite_checkbox.stateChanged.connect(self.update_checkbox_settings)
        self.validate_checkbox.stateChanged.connect(self.update_checkbox_settings)
        self.preview_checkbox.stateChanged.connect(self.update_checkbox_settings)
        self.timescale_checkbox.stateChanged.connect(self.update_checkbox_settings)

        # Radio Buttons (connect the group)
        self.file_action_group.buttonToggled.connect(self.update_file_action_setting)

        # Combos and Line Edits
        self.output_format_combo.currentTextChanged.connect(self.update_output_format_setting)

        # Connect all update handlers to also trigger auto-save
        for widget in self.settings_tab.findChildren(QWidget):
            if isinstance(widget, (QCheckBox, QRadioButton, QComboBox, QLineEdit)):
                if hasattr(widget, 'stateChanged'): widget.stateChanged.connect(self.auto_save_settings)
                if hasattr(widget, 'toggled'): widget.toggled.connect(self.auto_save_settings)
                if hasattr(widget, 'currentTextChanged'): widget.currentTextChanged.connect(self.auto_save_settings)
                if hasattr(widget, 'textChanged'): widget.textChanged.connect(self.auto_save_settings)

    def auto_save_settings(self):
        """Auto-save settings when they change."""
        try:
            self.save_settings()
            # Settings are saved automatically without user notification
            # to prevent UI shifting issues with status bar access
        except Exception as e:
            print(f"Failed to auto-save settings: {e}")

    def create_widgets(self):
        """Create the main interface components."""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)  # Add margins

        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # Create tabs
        self.remuxer_tab = QWidget()
        self.settings_tab = QWidget()
        self.logs_tab = QWidget()

        self.tab_widget.addTab(self.remuxer_tab, "Remuxer")
        self.tab_widget.addTab(self.settings_tab, "Settings")
        self.tab_widget.addTab(self.logs_tab, "Logs")

        # Create widgets for each tab
        self.create_remuxer_widgets()
        self.create_settings_widgets()
        self.create_logs_widgets()

    def create_remuxer_widgets(self):
        """Create widgets for the remuxer tab."""
        layout = QVBoxLayout(self.remuxer_tab)
        layout.setSpacing(5)  # Reduce space between each QGroupBox
        layout.setContentsMargins(10, 10, 10, 10)  # Add margins

        # --- Source & Output Frame ---
        source_output_group = QGroupBox("Source & Output")
        # ADD THIS STYLESHEET for consistent, compact appearance
        # Modern stylesheet for a consistent, clean appearance
        source_output_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(source_output_group)

        source_output_layout = QGridLayout(source_output_group)
        # ADJUST THESE MARGINS to reduce internal padding
        # Values are (left, top, right, bottom)
        source_output_layout.setContentsMargins(10, 15, 10, 5)

        # Source folder selection row
        source_output_layout.addWidget(QLabel("Source:"), 0, 0)
        self.label_input_path = QLabel("No folder or files selected")
        self.label_input_path.setWordWrap(True)
        source_output_layout.addWidget(self.label_input_path, 0, 1, 1, 2)
        self.btn_browse_folder = QPushButton("Browse Folder")
        self.btn_browse_folder.clicked.connect(self.browse_input_folder)
        source_output_layout.addWidget(self.btn_browse_folder, 0, 3)
        self.btn_browse_files = QPushButton("Browse Files")
        self.btn_browse_files.clicked.connect(self.browse_input_files)
        source_output_layout.addWidget(self.btn_browse_files, 0, 4)

        # Output folder selection row
        source_output_layout.addWidget(QLabel("Output:"), 1, 0)
        self.label_output_path = QLabel("Same as source")
        source_output_layout.addWidget(self.label_output_path, 1, 1)
        self.btn_browse_output = QPushButton("Browse")
        self.btn_browse_output.clicked.connect(self.browse_output_folder)
        source_output_layout.addWidget(self.btn_browse_output, 1, 3)
        self.btn_clear_output = QPushButton("Clear")
        self.btn_clear_output.clicked.connect(self.clear_output_folder)
        source_output_layout.addWidget(self.btn_clear_output, 1, 4)

        # --- Scanning Frame (Hidden - scanning happens automatically) ---
        self.scan_group = QGroupBox("Preparing files")
        # Cleaner, text-first appearance for scanning
        self.scan_group.setStyleSheet("""
            QGroupBox {
                background-color: #fafafa;
                border: 1px solid #ececec;
                border-radius: 10px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: 600;
                font-size: 10pt;
                subcontrol-origin: margin;
                padding: 2px 6px;
            }
        """)
        # Hide the scan group - scanning will happen automatically in background
        self.scan_group.hide()
        layout.addWidget(self.scan_group)

        scan_layout = QVBoxLayout(self.scan_group)
        scan_layout.setContentsMargins(12, 14, 12, 10)

        # Header and subtle caption
        self.scan_header_label = QLabel("Preparing files")
        self.scan_header_label.setStyleSheet("""
            QLabel { font-size: 12pt; font-weight: 600; color: #111827; }
        """)
        scan_layout.addWidget(self.scan_header_label)

        self.scan_caption_label = QLabel("Analyzing codecs and durations…")
        self.scan_caption_label.setStyleSheet("""
            QLabel { color: #6b7280; font-size: 9pt; }
        """)
        scan_layout.addWidget(self.scan_caption_label)

        # Compact progress badge (text-only, no bar)
        self.label_scan_progress = QLabel("Scanning 0/0")
        self.label_scan_progress.setStyleSheet("""
            QLabel {
                background-color: #eef2ff;
                color: #1e40af;
                border: 1px solid #c7d2fe;
                border-radius: 10px;
                padding: 6px 10px;
                margin-top: 4px;
                width: 100%;
            }
        """)
        scan_layout.addWidget(self.label_scan_progress)

        # Keep a hidden progress bar instance if needed later, but not shown
        self.progress_bar_scan = QProgressBar()
        self.progress_bar_scan.hide()

        # --- Remuxing Frame ---
        self.progress_group = QGroupBox("Remux")
        # ADD THIS STYLESHEET for consistent, compact appearance
        # Modern stylesheet for a consistent, clean appearance
        self.progress_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(self.progress_group)

        progress_layout = QVBoxLayout(self.progress_group)
        # ADJUST THESE MARGINS to reduce internal padding
        # Values are (left, top, right, bottom)
        progress_layout.setContentsMargins(10, 15, 10, 5)

        # Current Activity Section
        current_activity_group = QGroupBox("Current Activity")
        # ADD THIS STYLESHEET for consistent, compact appearance
        # Modern stylesheet for a consistent, clean appearance
        current_activity_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        progress_layout.addWidget(current_activity_group)

        current_layout = QVBoxLayout(current_activity_group)
        # ADJUST THESE MARGINS to reduce internal padding
        # Values are (left, top, right, bottom)
        current_layout.setContentsMargins(10, 15, 10, 5)

        self.label_current_file = QLabel("Current file: None")
        current_layout.addWidget(self.label_current_file)

        # Overall progress
        self.label_total_progress = QLabel("Total Progress: 0/?")
        progress_layout.addWidget(self.label_total_progress)

        self.progress_bar_total = QProgressBar()
        self.progress_bar_total.setRange(0, 100)
        self.progress_bar_total.setTextVisible(False)
        self.progress_bar_total.setStyleSheet("""
            QProgressBar {
                border: 1px solid #c0c0c0;
                border-radius: 5px;
                background-color: #e8e8e8;
                height: 12px;
            }
            QProgressBar::chunk {
                background-color: #0078D7; /* A nice blue */
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self.progress_bar_total)

        self.label_status = QLabel("Ready")
        progress_layout.addWidget(self.label_status)

        # Parallel processing status
        self.parallel_status_label = QLabel("")
        progress_layout.addWidget(self.parallel_status_label)

        # Control buttons frame
        buttons_layout = QHBoxLayout()
        progress_layout.addLayout(buttons_layout)

        buttons_layout.addStretch(1)  # Add stretchable space on the left

        self.btn_start_remux = QPushButton("Start Remux")
        self.btn_start_remux.clicked.connect(self.start_remux_thread)
        self.btn_start_remux.setEnabled(False)
        buttons_layout.addWidget(self.btn_start_remux)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_pause.setEnabled(False)
        buttons_layout.addWidget(self.btn_pause)

        self.btn_skip = QPushButton("Skip Current")
        self.btn_skip.clicked.connect(self.skip_current_file)
        self.btn_skip.setEnabled(False)
        buttons_layout.addWidget(self.btn_skip)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setEnabled(False)
        buttons_layout.addWidget(self.btn_cancel)

        buttons_layout.addStretch(1)  # Add stretchable space on the right

        # ADD THIS LINE AT THE END OF THE LAYOUT
        layout.addStretch(1)

    def create_settings_widgets(self):
        """Create widgets for the settings tab."""
        layout = QVBoxLayout(self.settings_tab)
        layout.setSpacing(5)  # Reduce space between each QGroupBox
        layout.setContentsMargins(10, 10, 10, 10)


        # --- Output Format ---
        output_format_group = QGroupBox("Output Format")
        # ADD THIS STYLESHEET to control the box's own margins and title padding
        # Modern stylesheet for a consistent, clean appearance
        output_format_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(output_format_group)

        format_layout = QHBoxLayout(output_format_group)
        # CHANGE THIS to reduce the padding inside the box
        # Values are (left, top, right, bottom)
        format_layout.setContentsMargins(10, 15, 10, 5)
        format_layout.addWidget(QLabel("Output format:"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(self.supported_formats['output'])
        self.output_format_combo.setCurrentText(self.output_format)
        format_layout.addWidget(self.output_format_combo)
        info_btn = QPushButton("?")
        info_btn.setFixedWidth(25)
        info_btn.clicked.connect(self.show_output_format_info)
        format_layout.addWidget(info_btn)
        format_layout.addStretch(1)  # MOVED: Now the stretch is at the end

        # --- File Management ---
        file_options_group = QGroupBox("Original File Management")
        # ADD THIS STYLESHEET to control the box's own margins and title padding
        # Modern stylesheet for a consistent, clean appearance
        file_options_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(file_options_group)

        file_layout = QVBoxLayout(file_options_group)
        file_layout.setSpacing(2)  # Reduce space between the radio buttons
        # CHANGE THIS to reduce the padding inside the box
        # Values are (left, top, right, bottom)
        file_layout.setContentsMargins(10, 15, 10, 5)

        self.file_action_group = QButtonGroup(self)

        self.move_radio = QRadioButton("Move original to subfolder")
        self.move_radio.setChecked(self.file_action == FILE_ACTION_MOVE)
        self.file_action_group.addButton(self.move_radio)
        file_layout.addWidget(self.move_radio)

        self.keep_radio = QRadioButton("Keep original file in place (default)")
        self.keep_radio.setChecked(self.file_action == FILE_ACTION_KEEP)
        self.file_action_group.addButton(self.keep_radio)
        file_layout.addWidget(self.keep_radio)

        delete_layout = QHBoxLayout()
        delete_layout.setSpacing(2)  # Reduce spacing between elements
        file_layout.addLayout(delete_layout)

        self.delete_radio = QRadioButton("Delete original file")
        self.delete_radio.setChecked(self.file_action == FILE_ACTION_DELETE)
        self.file_action_group.addButton(self.delete_radio)
        delete_layout.addWidget(self.delete_radio)

        delete_info = QLabel("(Not recommended)")
        delete_info.setStyleSheet("color: red; font-size: 8pt;")
        delete_layout.addWidget(delete_info)

        delete_info_btn = QPushButton("?")
        delete_info_btn.setFixedWidth(25) # ADD THIS to keep the button small
        delete_info_btn.clicked.connect(self.show_file_management_info)
        delete_layout.addWidget(delete_info_btn)

        delete_layout.addStretch(1) # ADD THIS to absorb extra space

        # --- Processing Options ---
        processing_group = QGroupBox("Processing Options")
        # ADD THIS STYLESHEET to control the box's own margins and title padding
        # Modern stylesheet for a consistent, clean appearance
        processing_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(processing_group)

        processing_layout = QVBoxLayout(processing_group)
        # CHANGE THIS to reduce the padding inside the box
        # Values are (left, top, right, bottom)
        processing_layout.setContentsMargins(10, 15, 10, 5)
        processing_layout.setSpacing(4) # Also reduce spacing between items in this group

        # Audio options
        audio_layout = QHBoxLayout()
        audio_layout.setSpacing(2)  # Reduce spacing between elements
        self.audio_checkbox = QCheckBox("Include Audio Streams")
        self.audio_checkbox.setChecked(self.include_audio)
        audio_layout.addWidget(self.audio_checkbox)
        audio_info_btn = QPushButton("?")
        audio_info_btn.setFixedWidth(25)  # Give the button a small, fixed width
        audio_info_btn.clicked.connect(self.show_audio_info)
        audio_layout.addWidget(audio_info_btn)
        audio_layout.addStretch(1)  # Add stretch to push widgets to the left
        processing_layout.addLayout(audio_layout)

        # Other processing options
        timestamp_layout = QHBoxLayout()
        timestamp_layout.setSpacing(2)  # Reduce spacing between elements
        self.timestamp_checkbox = QCheckBox("Preserve original file timestamps")
        self.timestamp_checkbox.setChecked(self.preserve_timestamps)
        timestamp_layout.addWidget(self.timestamp_checkbox)
        timestamp_info_btn = QPushButton("?")
        timestamp_info_btn.setFixedWidth(25)
        timestamp_info_btn.clicked.connect(self.show_timestamp_info)
        timestamp_layout.addWidget(timestamp_info_btn)
        timestamp_layout.addStretch(1)  # Add stretch to push widgets to the left
        processing_layout.addLayout(timestamp_layout)

        overwrite_layout = QHBoxLayout()
        overwrite_layout.setSpacing(2)  # Reduce spacing between elements
        self.overwrite_checkbox = QCheckBox("Overwrite existing output files")
        self.overwrite_checkbox.setChecked(self.overwrite_existing)
        overwrite_layout.addWidget(self.overwrite_checkbox)
        overwrite_info_btn = QPushButton("?")
        overwrite_info_btn.setFixedWidth(25)
        overwrite_info_btn.clicked.connect(self.show_overwrite_info)
        overwrite_layout.addWidget(overwrite_info_btn)
        overwrite_layout.addStretch(1)  # Add stretch to push widgets to the left
        processing_layout.addLayout(overwrite_layout)

        # --- Advanced Processing Options ---
        advanced_group = QGroupBox("Advanced Processing Options")
        # ADD THIS STYLESHEET to control the box's own margins and title padding
        # Modern stylesheet for a consistent, clean appearance
        advanced_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(advanced_group)

        advanced_layout = QVBoxLayout(advanced_group)
        # CHANGE THIS to reduce the padding inside the box
        # Values are (left, top, right, bottom)
        advanced_layout.setContentsMargins(10, 15, 10, 5)

        # File validation option
        validate_layout = QHBoxLayout()
        validate_layout.setSpacing(2)  # Reduce spacing between elements
        self.validate_checkbox = QCheckBox("Validate files before processing")
        self.validate_checkbox.setChecked(self.validate_files)
        validate_layout.addWidget(self.validate_checkbox)
        validate_info_btn = QPushButton("?")
        validate_info_btn.setFixedWidth(25)
        validate_info_btn.clicked.connect(self.show_validation_info)
        validate_layout.addWidget(validate_info_btn)
        validate_layout.addStretch(1)  # Add stretch to push widgets to the left
        advanced_layout.addLayout(validate_layout)

        # Command preview option
        preview_layout = QHBoxLayout()
        preview_layout.setSpacing(2)  # Reduce spacing between elements
        self.preview_checkbox = QCheckBox("Show command preview before remuxing")
        self.preview_checkbox.setChecked(self.preview_commands)
        preview_layout.addWidget(self.preview_checkbox)
        preview_info_btn = QPushButton("?")
        preview_info_btn.setFixedWidth(25)
        preview_info_btn.clicked.connect(self.show_preview_info)
        preview_layout.addWidget(preview_info_btn)
        preview_layout.addStretch(1)  # Add stretch to push widgets to the left
        advanced_layout.addLayout(preview_layout)

        # Video Timescale (VFR fix) option
        timescale_layout = QHBoxLayout()
        timescale_layout.setSpacing(2)  # Reduce spacing between elements
        self.timescale_checkbox = QCheckBox("Set video timescale")
        self.timescale_checkbox.setChecked(self.use_timescale_option)
        timescale_layout.addWidget(self.timescale_checkbox)
        timescale_info_btn = QPushButton("?")
        timescale_info_btn.setFixedWidth(25)
        timescale_info_btn.clicked.connect(self.show_timescale_info)
        timescale_layout.addWidget(timescale_info_btn)
        timescale_layout.addStretch(1)  # Add stretch to push widgets to the left
        advanced_layout.addLayout(timescale_layout)

        # --- REMOVED: Video Timescale (VFR fix) GroupBox ---
        # The timescale option is now integrated into the Advanced Processing group.
        # The QRadioButton is also removed as it's now redundant.
        # The following UI elements are no longer needed:
        # self.fps_group, self.timescale_options_container, self.timescale_source_radio
        # Settings management buttons
        settings_buttons_layout = QHBoxLayout()
        layout.addLayout(settings_buttons_layout)

        settings_buttons_layout.addStretch(1)  # Add stretchable space on the left

        self.restore_defaults_btn = QPushButton("Restore Defaults")
        self.restore_defaults_btn.clicked.connect(self.restore_defaults)
        settings_buttons_layout.addWidget(self.restore_defaults_btn)

        settings_buttons_layout.addStretch(1)  # Add stretchable space on the right

        # Hide Step 2 initially - only show after scanning files
        self.progress_group.hide()

        # Center the content vertically by adding stretch at top and bottom
        layout.insertStretch(0, 1)  # Add stretch at the beginning
        layout.addStretch(1)        # Keep stretch at the end for balance

        # Load saved settings after creating all widgets
        self.load_settings()

    def create_logs_widgets(self):
        """Create widgets for the logs tab."""
        layout = QVBoxLayout(self.logs_tab)
        layout.setSpacing(5)  # Reduce space between each QGroupBox
        layout.setContentsMargins(10, 10, 10, 10)  # Add margins

        # --- Log Output Frame ---
        log_group = QGroupBox("Log Output")
        log_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # ADD THIS STYLESHEET for consistent, compact appearance
        # Modern stylesheet for a consistent, clean appearance
        log_group.setStyleSheet("""
            QGroupBox {
                background-color: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox::title {
                font-weight: bold;
                font-size: 9pt;
                subcontrol-origin: margin;
                padding: 0 5px;
            }
        """)
        layout.addWidget(log_group)

        log_layout = QVBoxLayout(log_group)
        # ADJUST THESE MARGINS to reduce internal padding
        # Values are (left, top, right, bottom)
        log_layout.setContentsMargins(10, 15, 10, 10)

        # Button frame for log controls
        log_button_layout = QHBoxLayout()
        log_layout.addLayout(log_button_layout)
 
        # Debug toggle checkbox
        self.debug_checkbox = QCheckBox("Debug Info")
        self.debug_checkbox.setChecked(self.debug_mode)
        self.debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
        log_button_layout.addWidget(self.debug_checkbox)

        log_button_layout.addStretch(1)  # Add stretchable space to push buttons to the right

        self.copy_log_btn = QPushButton("Copy Log")
        self.copy_log_btn.clicked.connect(self.copy_log_to_clipboard)
        log_button_layout.addWidget(self.copy_log_btn)

        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        log_button_layout.addWidget(self.clear_log_btn)

        self.export_log_btn = QPushButton("Export Log")
        self.export_log_btn.clicked.connect(self.export_log_to_file)
        log_button_layout.addWidget(self.export_log_btn)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setMinimumHeight(300)  # Back to original height
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))  # Better monospace font
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)  # No word wrapping

        # Set log text styling for better readability
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)

        log_layout.addWidget(self.log_text)

    def clear_log(self):
        """Clear the log output."""
        self.log_text.clear()

    def toggle_debug_mode(self, state):
        """Toggle debug mode on/off."""
        self.debug_mode = (state == Qt.Checked)
        if self.debug_mode:
            self.log_text.append("[DEBUG] Debug mode enabled - detailed logging will be shown")
        else:
            pass
            # self.log_text.append("[DEBUG] Debug mode disabled - only normal messages will be shown")


    def export_log_to_file(self):
        """Export the log output to a text file."""
        try:
            log_content = self.log_text.toPlainText()

            if not log_content.strip():
                QMessageBox.information(self, "Info", "No log content to export.")
                return

            # Get current timestamp for filename
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"remuxer_log_{timestamp}.txt"

            # Open file dialog
            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Log", default_filename, "Text files (*.txt)"
            )

            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(log_content)

                QMessageBox.information(self, "Success", f"Log exported to:\n{filename}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export log: {str(e)}")

    # =============================================================================
    # SETTINGS MANAGEMENT
    # =============================================================================
    def get_settings_file_path(self):
        """Get the path to the settings file."""
        try:
            # Use the application's directory for settings
            if getattr(sys, 'frozen', False):
                # PyInstaller executable
                app_dir = os.path.dirname(sys.executable)
            else:
                # Regular Python script
                app_dir = os.path.dirname(os.path.abspath(__file__))

            return os.path.join(app_dir, "remuxer_settings.json")
        except:
            # Fallback to current directory
            return "remuxer_settings.json"

    def save_settings(self):
        """Save current settings to file."""
        try:
            settings = {
                "include_audio": self.include_audio,
                "file_action": self.file_action,
                "output_format": self.output_format,
                "validate_files": self.validate_files,
                "preserve_timestamps": self.preserve_timestamps,
                "preview_commands": self.preview_commands,
                "overwrite_existing": self.overwrite_existing,
                "use_timescale": self.use_timescale_option,
            }

            with open(self.get_settings_file_path(), 'w') as f:
                json.dump(settings, f, indent=2)

        except Exception as e:
            print(f"Failed to save settings: {e}")

    def load_settings(self):
        """Load settings from file."""
        try:
            settings_file = self.get_settings_file_path()
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)

                # Apply loaded settings
                if "include_audio" in settings:
                    self.include_audio = settings["include_audio"]
                    self.audio_checkbox.setChecked(self.include_audio)
                if "file_action" in settings:
                    self.file_action = settings["file_action"]
                    if self.file_action == FILE_ACTION_MOVE:
                        self.move_radio.setChecked(True)
                    elif self.file_action == FILE_ACTION_KEEP:
                        self.keep_radio.setChecked(True)
                    elif self.file_action == FILE_ACTION_DELETE:
                        self.delete_radio.setChecked(True)
                if "output_format" in settings:
                    self.output_format = settings["output_format"]
                    self.output_format_combo.setCurrentText(self.output_format)
                if "validate_files" in settings:
                    self.validate_files = settings["validate_files"]
                    self.validate_checkbox.setChecked(self.validate_files)
                if "preserve_timestamps" in settings:
                    self.preserve_timestamps = settings["preserve_timestamps"]
                    self.timestamp_checkbox.setChecked(self.preserve_timestamps)
                if "preview_commands" in settings:
                    self.preview_commands = settings["preview_commands"]
                    self.preview_checkbox.setChecked(self.preview_commands)
                if "overwrite_existing" in settings:
                    self.overwrite_existing = settings["overwrite_existing"]
                    self.overwrite_checkbox.setChecked(self.overwrite_existing)
                if "use_timescale" in settings:
                    self.use_timescale_option = settings["use_timescale"]
                    self.timescale_checkbox.setChecked(self.use_timescale_option)

        except Exception as e:
            print(f"Failed to load settings: {e}")

    def restore_defaults(self):
        """Restore all settings to their default values."""
        try:
            # Reset all settings to defaults
            self.include_audio = True
            self.audio_checkbox.setChecked(True)
            self.file_action = FILE_ACTION_KEEP
            self.keep_radio.setChecked(True)
            self.output_format = ".mp4"
            self.output_format_combo.setCurrentText(self.output_format)
            self.validate_files = True
            self.validate_checkbox.setChecked(True)
            self.preserve_timestamps = True
            self.timestamp_checkbox.setChecked(True)
            self.preview_commands = False
            self.preview_checkbox.setChecked(False)
            self.overwrite_existing = False
            self.overwrite_checkbox.setChecked(False)
            self.use_timescale_option = True
            self.timescale_checkbox.setChecked(True)

        except Exception as e:
            print(f"Failed to restore defaults: {e}")

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================
    def find_ffmpeg_path(self):
        """Find ffmpeg executable by checking current directory first, then system PATH."""
        # First, try to find ffmpeg in the current directory (same as application)
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            ffmpeg_local_path = os.path.join(base_path, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")

            if os.path.exists(ffmpeg_local_path):
                return ffmpeg_local_path
        except Exception:
            pass

        # If not found locally, check system PATH
        try:
            # Use shutil.which to find ffmpeg in system PATH
            ffmpeg_path = shutil.which("ffmpeg")
            if ffmpeg_path:
                return ffmpeg_path
        except Exception:
            pass

        # If still not found, return None
        return None

    def find_ffprobe_path(self):
        """Find ffprobe executable by checking current directory first, then system PATH."""
        # First, try to find ffprobe in the current directory (same as application)
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            ffprobe_local_path = os.path.join(base_path, "ffprobe.exe" if sys.platform == "win32" else "ffprobe")

            if os.path.exists(ffprobe_local_path):
                return ffprobe_local_path
        except Exception:
            pass

        # If not found locally, check system PATH
        try:
            # Use shutil.which to find ffprobe in system PATH
            ffprobe_path = shutil.which("ffprobe")
            if ffprobe_path:
                return ffprobe_path
        except Exception:
            pass

        # If still not found, return None
        return None

    def show_missing_tools_dialog(self):
        """Show dialog when required tools (ffmpeg/ffprobe) are missing."""
        missing_tools = []
        if not self.ffmpeg_path:
            missing_tools.append("ffmpeg")
        if not self.ffprobe_path:
            missing_tools.append("ffprobe")

        tools_text = " and ".join(missing_tools)

        # print(f"[DEBUG] Creating missing tools dialog for: {tools_text}")
        msg = QMessageBox(self)
        msg.setWindowTitle("Missing Required Tools")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(f"The following required tools are not found:\n\n{tools_text}\n\n"
                   "Please ensure they are either:\n"
                   "• In the same directory as this application, or\n"
                   "• Available in your system PATH\n\n"
                   "After adding the files, click 'Retry' to continue.")

        retry_btn = msg.addButton("Retry", QMessageBox.ActionRole)
        exit_btn = msg.addButton("Exit", QMessageBox.RejectRole)

        # print(f"[DEBUG] Showing missing tools dialog...")
        msg.exec_()
        # print(f"[DEBUG] Missing tools dialog closed, user clicked: {msg.clickedButton().text()}")

        if msg.clickedButton() == retry_btn:
            # print("[DEBUG] User clicked Retry, re-checking tool paths...")
            self.ffmpeg_path = self.find_ffmpeg_path()
            self.ffprobe_path = self.find_ffprobe_path()

            # print(f"[DEBUG] After retry - FFmpeg path: {self.ffmpeg_path}")
            # print(f"[DEBUG] After retry - FFprobe path: {self.ffprobe_path}")

            if self.ffmpeg_path and self.ffprobe_path:
                # Both tools found, continue initialization
                # print("[DEBUG] Tools found after retry, continuing initialization...")
                pass
            else:
                # Still missing, show error message
                # print("[DEBUG] Tools still missing, showing error dialog...")
                error_msg = QMessageBox(self)
                error_msg.setWindowTitle("Still Missing")
                error_msg.setIcon(QMessageBox.Critical)
                error_msg.setText("The required tools are still not found.\n\n"
                                "Please ensure ffmpeg and ffprobe are properly installed\n"
                                "and accessible before retrying.")
                # print(f"[DEBUG] Showing error dialog...")
                error_msg.exec_()
                # print(f"[DEBUG] Error dialog closed")
                sys.exit(1)
        else:
            # print("[DEBUG] User clicked Exit, terminating application...")
            sys.exit(0)

    def get_resource_path(self, relative_path):
        """Get the absolute path to a resource file, handling PyInstaller bundling."""
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            # Use the script's directory instead of current working directory
            base_path = os.path.dirname(os.path.abspath(__file__))

        # Only add .exe extension for actual executable files, not data files
        if (sys.platform == "win32" and
            not relative_path.endswith((".exe", ".ico", ".json", ".txt", ".md"))):
            relative_path += ".exe"

        return os.path.join(base_path, relative_path)

    def set_window_icon(self, icon_filename="ICOtrans.ico"):
        """Set window icon using multiple fallback methods with platform optimization."""
        try:
            icon_path = self.get_resource_path(icon_filename)
            if not os.path.exists(icon_path):
                print(f"Icon file not found: {icon_path}")
                return

            # Try to load the icon
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.setWindowIcon(icon)
            else:
                print(f"Failed to load icon: {icon_path}")

        except Exception as e:
            print(f"Error setting icon: {e}")

    # =============================================================================
    # QUEUE PROCESSING
    # =============================================================================
    def check_queue(self):
        """Process messages from the worker threads and update the UI accordingly."""
        try:
            # Process up to MAX_QUEUE_MESSAGES_PER_UPDATE messages per iteration to prevent UI blocking
            for _ in range(MAX_QUEUE_MESSAGES_PER_UPDATE):
                message = self.process_queue.get_nowait()
                msg_type, data = message

                # --- Skip Button Reset Message ---
                if msg_type == "SKIP_BUTTON_RESET":
                    self.btn_skip.setEnabled(True)
                    self.btn_skip.setText("Skip Current")

                # --- Scan Messages ---
                elif msg_type == "SCAN_PROGRESS":
                    # Drive slim bottom bar; keep panel out of the way
                    try:
                        self.scan_status_bar.setValue(int(data['percent']))
                        if not self.scan_status_bar.isVisible():
                            self.scan_status_bar.show()
                    except Exception:
                        pass

                elif msg_type == "SCAN_COMPLETE":
                    self.scan_results = data['results']
                    self.is_scanned = True
                    valid_files = sum(1 for v in data['results'].values() if v.get('valid', True))
                    total_files = len(data['results'])

                    # DEBUG: Log a simple confirmation that the scan is complete.
                    # The detailed per-file logs have already been sent from the worker.
                    if self.debug_mode:
                        self.log_text.append(f"[DEBUG] SCAN_COMPLETE received")

                    # Calculate final scan elapsed time
                    final_elapsed_time = None
                    if self.scan_start_time:
                        elapsed_seconds = int(time.time() - self.scan_start_time)
                        hours, remainder = divmod(elapsed_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if hours > 0:
                            final_elapsed_time = f"{hours}h {minutes}m {seconds}s"
                        else:
                            final_elapsed_time = f"{minutes}m {seconds}s"
                        self.scan_start_time = None  # Reset timer
                        self.last_scan_time_str = final_elapsed_time # Store for completion dialog

                    # Update scan progress label
                    if valid_files == total_files:
                        self.label_scan_progress.setText(f"✓ {valid_files}/{total_files} files ready to remux")
                    else:
                        self.label_scan_progress.setText(f"⚠ {valid_files}/{total_files} files ready to remux")

                    # Hide scan interface after scanning completes and hide slim bar
                    self.scan_group.hide()
                    try:
                        self.scan_status_bar.hide()
                    except Exception:
                        pass

                    # Show remux interface after scanning completes
                    self.progress_group.show()
                    self.progress_group.setTitle("Remux")

                    # Enable Start Remux button
                    self.btn_start_remux.setEnabled(True)
                    self.btn_start_remux.show()

                    # Initialize remux interface with correct total file count
                    self.label_total_progress.setText(f"Total Progress: 0/{total_files}")
                    self.label_current_file.setText("Current file: None")
                    self.label_status.setText("Ready")
                    self.progress_bar_total.setValue(0)

                    # Enable cancel button for safety
                    self.btn_cancel.setEnabled(True)

                    # Auto-start remuxing is now automatic

                    self.log_text.append("Scan complete. Ready to remux.")

                    # Re-enable source and output buttons after scan completes
                    self.btn_browse_folder.setEnabled(True)
                    self.btn_browse_files.setEnabled(True)
                    self.btn_browse_output.setEnabled(True)
                    self.btn_clear_output.setEnabled(True)

                # --- Remux Messages ---
                elif msg_type == "LOG":
                    # Format log messages with timestamps for better readability
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    formatted_message = f"[{timestamp}] {data}"
                    self.log_text.append(formatted_message)
                    # Scroll to bottom
                    scrollbar = self.log_text.verticalScrollBar()
                    scrollbar.setValue(scrollbar.maximum())

                elif msg_type == "STATUS":
                    self.label_status.setText(data)

                elif msg_type == "PROGRESS":
                    self.progress_bar_total.setValue(int(data['total_percent']))
                    self.label_total_progress.setText(f"Total Progress: {data['current']}/{data['total']}")

                elif msg_type == "CURRENT_FILE":
                    self.label_current_file.setText(f"Current file: {data['filename']}")

                elif msg_type == "PARALLEL_STATUS":
                    self.parallel_status_label.setText(data)

                elif msg_type == "FINISHED":
                    # Calculate elapsed time
                    elapsed_time = None
                    if self.processing_start_time:
                        elapsed_seconds = time.time() - self.processing_start_time
                        hours, remainder = divmod(int(elapsed_seconds), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if hours > 0:
                            elapsed_time = f"{hours}h {minutes}m {seconds}s"
                        else:
                            elapsed_time = f"{minutes}m {seconds}s"

                    final_msg = f"Finished! Remuxed: {data['remuxed']}, Skipped: {data['skipped']}"

                    # Update the total progress label to show final count in same style as scan results
                    total_processed = data['remuxed'] + data['skipped']
                    total_files = len(self.files_to_process)
                    if data['remuxed'] == total_files:
                        self.label_total_progress.setText(f"✓ {data['remuxed']}/{total_files} files remuxed")
                    else:
                        self.label_total_progress.setText(f"✓ {data['remuxed']}/{total_files} files remuxed")

                    # Clear current activity labels since processing is complete
                    self.label_current_file.setText("Current file: None")
                    self.label_status.setText("Complete")

                    # The UI will be reset after the completion dialog is closed.
                    self.log_text.append("Remux process completed successfully for all files.")
                    self.show_completion_dialog(final_msg, data, elapsed_time, self.last_scan_time_str)

        except queue.Empty:
            pass

    # =============================================================================
    # UI STATE MANAGEMENT
    # =============================================================================
    def start_automatic_scan(self):
        """Start automatic scanning in background and show scan interface."""
        if not self.files_to_process:
            return

        # Keep scan panel hidden; show slim bottom progress bar
        try:
            self.scan_status_bar.setValue(0)
            self.scan_status_bar.show()
        except Exception:
            pass

        # Hide the remux interface until scanning is complete
        self.progress_group.hide()

        # Auto-start functionality is now automatic

        # Disable source and output buttons during scanning
        self.btn_browse_folder.setEnabled(False)
        self.btn_browse_files.setEnabled(False)
        self.btn_browse_output.setEnabled(False)
        self.btn_clear_output.setEnabled(False)

        # Start the actual scanning in background
        self.start_scan_thread()

    def reset_scan_state(self):
        """Reset the application to a pre-scan state when new files are selected."""
        self.is_scanned = False
        self.scan_results = {}
        self.scan_start_time = None  # Reset scan timer
        self.last_scan_time_str = None # Reset scan time string

        # Hide Step 2 frame and show Step 1 frame when resetting scan state
        self.progress_group.hide()

        # Keep Step 1 frame hidden
        self.scan_group.hide()

        # Disable control buttons when resetting scan state
        self.btn_pause.setEnabled(False)
        self.btn_skip.setEnabled(False)
        self.btn_cancel.setEnabled(False)

        # Hide Start Remux button and reset textual indicators
        self.btn_start_remux.hide()
        self.progress_bar_total.setValue(0)
        self.label_scan_progress.setText("")
        try:
            self.scan_status_label.setText("")
        except Exception:
            pass
        self.label_total_progress.setText("Total Progress: 0/0")
        self.label_current_file.setText("Current file: None")


        # Re-enable source and output buttons when resetting scan state
        self.btn_browse_folder.setEnabled(True)
        self.btn_browse_files.setEnabled(True)
        self.btn_browse_output.setEnabled(True)
        self.btn_clear_output.setEnabled(True)

        # Ensure settings are enabled after scan reset
        if not self.settings_disabled:
            self.enable_settings_controls()

    def is_remuxer_running(self):
        """Check if the remuxer is currently running (scanning or remuxing)."""
        return self.btn_start_remux.text() in ["Remuxing..."]

    def disable_settings_controls(self):
        """Disable all settings controls when remuxer is running to prevent changes."""
        # Disable notebook tabs to prevent switching
        self.tab_widget.setTabEnabled(1, False)  # Settings tab

        # Store current state for restoration
        self.settings_disabled = True

    def enable_settings_controls(self):
        """Re-enable all settings controls when remuxer stops."""
        # Re-enable notebook tabs
        self.tab_widget.setTabEnabled(1, True)  # Settings tab

        # Clear the disabled flag
        self.settings_disabled = False

    def reset_ui_after_processing(self):
        """Reset the UI to its initial state after processing is complete."""
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("Pause")
        self.btn_skip.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_start_remux.setEnabled(False)
        self.btn_start_remux.setText("Start Remux")

        # Hide Start Remux button
        self.btn_start_remux.hide()

        # Hide both interface frames
        self.scan_group.hide()
        self.progress_group.hide()

        # Reset scan state
        self.is_scanned = False
        self.scan_results = {}
        with self.process_lock:
            self.current_process = None
        # Clear files_to_process after completion
        self.files_to_process = []
        self.label_input_path.setText("No folder or files selected")
        self.parallel_status_label.setText("")
        self.label_status.setText("Ready")

        # Reset output directory display
        self.output_directory = ""
        self.selected_output_directory = ""
        self.label_output_path.setText("Same as source")

        self.reset_scan_state()
        self.enable_settings_controls()

    # =============================================================================
    # USER ACTION HANDLERS
    # =============================================================================
    def browse_input_folder(self):
        """Open a directory dialog and select all supported video files from the chosen directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Source Directory")
        if directory:
            # Consistent case handling for extensions
            supported_extensions = [ext.lower() for ext in self.supported_formats['input']]
            all_files = os.listdir(directory)
            self.files_to_process = [
                os.path.join(directory, f)
                for f in all_files
                if any(f.lower().endswith(ext) for ext in supported_extensions)
            ]
            format_counts = {}
            for file in self.files_to_process:
                ext = os.path.splitext(file)[1].lower()
                format_counts[ext] = format_counts.get(ext, 0) + 1

            # DEBUG: Add logging to track file selection (only in debug mode)
            if self.debug_mode:
                self.log_text.append(f"[DEBUG] Selected directory: {directory}")
                self.log_text.append(f"[DEBUG] Found {len(all_files)} total files in directory")
                self.log_text.append(f"[DEBUG] Supported extensions: {supported_extensions}")
                self.log_text.append(f"[DEBUG] Found {len(self.files_to_process)} supported files")
                for ext, count in format_counts.items():
                    self.log_text.append(f"[DEBUG]   {ext}: {count} files")

            self.label_input_path.setText(f"{len(self.files_to_process)} files selected")

            # Start automatic scanning and show remux interface immediately
            if self.files_to_process:
                self.start_automatic_scan()
            else:
                self.reset_scan_state()

    def browse_input_files(self):
        """Browse for individual input files."""
        filetypes = [("All supported", " ".join([f"*{ext}" for ext in self.supported_formats['input']]))]
        filetypes.extend([(f"{ext.upper()} files", f"*{ext}") for ext in self.supported_formats['input']])
        files, _ = QFileDialog.getOpenFileNames(self, "Select video files", "", ";;".join([f"{name} ({pattern})" for name, pattern in filetypes]))
        if files:
            self.files_to_process = list(files)

            # DEBUG: Add logging to track file selection (only in debug mode)
            if self.debug_mode:
                self.log_text.append(f"[DEBUG] Selected {len(self.files_to_process)} individual files:")
                for file in self.files_to_process:
                    self.log_text.append(f"[DEBUG]   {os.path.basename(file)}")

            self.label_input_path.setText(f"{len(self.files_to_process)} files selected")

            # Start automatic scanning and show remux interface immediately
            if self.files_to_process:
                self.start_automatic_scan()
            else:
                self.reset_scan_state()

    def browse_output_folder(self):
        """Browse for output directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_directory = directory
            self.selected_output_directory = directory  # Track user selection
            # Force shortening for testing
            shortened = self.shorten_path(directory, 30)  # Very aggressive shortening
            self.label_output_path.setText(shortened)
        else:
            self.output_directory = ""
            self.selected_output_directory = ""
            self.label_output_path.setText("Same as source")

    def shorten_path(self, path, max_length=30):
        """Shorten a file path to fit within max_length characters."""
        if not path:
            return path

        if len(path) <= max_length:
            return path

        # Split the path into components
        parts = path.split('/')

        if len(parts) <= 1:
            return path

        # Simple approach: show drive + first folder + ... + last folder
        if len(parts) >= 2:
            result = parts[0] + "/" + parts[1] + "/.../" + parts[-1]
            return result

        # Fallback
        return path

    def clear_output_folder(self):
        """Clear the custom output folder and reset to 'Same as source'."""
        self.output_directory = ""
        self.selected_output_directory = ""
        self.label_output_path.setText("Same as source")


    def update_checkbox_settings(self):
        """Update boolean settings from their corresponding checkboxes."""
        self.include_audio = self.audio_checkbox.isChecked()
        self.preserve_timestamps = self.timestamp_checkbox.isChecked()
        self.overwrite_existing = self.overwrite_checkbox.isChecked()
        self.validate_files = self.validate_checkbox.isChecked()
        self.preview_commands = self.preview_checkbox.isChecked()
        self.use_timescale_option = self.timescale_checkbox.isChecked()

        # After updating, trigger the auto-save
        self.auto_save_settings()

    def update_file_action_setting(self):
        """Update the file_action setting when radio buttons change."""
        if self.move_radio.isChecked():
            self.file_action = FILE_ACTION_MOVE
        elif self.keep_radio.isChecked():
            self.file_action = FILE_ACTION_KEEP
        elif self.delete_radio.isChecked():
            self.file_action = FILE_ACTION_DELETE

    def update_timescale_setting(self):
        """Update the timescale settings when radio buttons change."""
        pass # This function is now mostly handled by toggle_timescale_selector

    def update_output_format_setting(self, text):
        """Update the output_format setting when combo box changes."""
        self.output_format = text


    def toggle_pause(self):
        """Toggle pause state."""
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.setText("Resume")
            self.process_queue.put(("LOG", "Remuxing paused."))
            self.process_queue.put(("STATUS", "Paused..."))
        else:
            self.pause_event.set()
            self.btn_pause.setText("Pause")
            self.process_queue.put(("LOG", "Remuxing resumed."))
            self.process_queue.put(("STATUS", "Remuxing..."))

    def skip_current_file(self):
        """Skip the currently processing file by moving to next in queue."""
        with self.process_lock:
            self.process_queue.put(("LOG", "[SKIP] User requested skip - moving to next file"))
            
            # Terminate current process immediately
            if hasattr(self, 'current_process') and self.current_process:
                try:
                    self.current_process.terminate()
                    self.current_process.kill()  # Force kill immediately
                except Exception:
                    pass
                self.current_process = None
            
            # Set skip flag - this will be picked up by the processing loop
            self.skip_event.set()
            
            # Show brief feedback but don't disable button
            original_text = self.btn_skip.text()
            self.btn_skip.setText("Skipping...")
            
            # Reset button text quickly but keep it enabled
            QTimer.singleShot(300, lambda: self.btn_skip.setText(original_text))
            
            # Force UI update to ensure responsiveness
            self.process_queue.put(("LOG", f"[DEBUG] Skip requested. Current file index: {getattr(self, 'current_file_index', 'unknown')}"))

    def force_kill_process(self):
        """Force kill the current process if it's still running."""
        with self.process_lock:
            if self.current_process:
                try:
                    self.current_process.kill()
                except Exception:
                    pass
    
    def reset_skip_button_immediately(self):
        """Reset skip button to normal state."""
        self.btn_skip.setEnabled(True)
        self.btn_skip.setText("Skip Current")
    
    def reset_skip_button_if_needed(self):
        """Reset skip button if it's still in skipping state."""
        if self.btn_skip.text() == "Skipping..." or not self.btn_skip.isEnabled():
            self.reset_skip_button_immediately()

        # Try to terminate current process if it exists (parallel mode)
        with self.process_lock:
            if self.current_process:
                try:
                    self.current_process.terminate()
                except Exception:
                    pass

    def cancel_processing(self):
        """Cancel processing with proper synchronization and reset UI."""
        # Store current pause state
        was_paused = not self.pause_event.is_set()

        # Temporarily pause to prevent race conditions
        if not was_paused:
            self.pause_event.clear()

        # Show confirmation dialog
        result = QMessageBox.question(self, "Cancel Processing",
                                    "Are you sure you want to cancel the current operation?\n\n" +
                                    "This will stop processing and reset the interface.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if result == QMessageBox.Yes:
            self.cancel_event.set()
            with self.process_lock:
                if self.current_process:
                    self.process_queue.put(("LOG", "Sending termination signal to FFmpeg..."))
                    try:
                        self.current_process.terminate()
                    except Exception:
                        pass

            # Reset UI to initial state
            self.reset_ui_after_processing()
            self.process_queue.put(("LOG", "Operation cancelled and interface reset."))

            # Re-enable source and output buttons after cancellation
            self.btn_browse_folder.setEnabled(True)
            self.btn_browse_files.setEnabled(True)
            self.btn_browse_output.setEnabled(True)
            self.btn_clear_output.setEnabled(True)
        else:
            # User clicked No, restore previous state
            if not was_paused:
                self.pause_event.set()
                self.process_queue.put(("LOG", "Resumed after cancel dialog."))

    def closeEvent(self, event):
        """Handle application close event."""
        # Save settings before closing
        try:
            self.save_settings()
        except Exception as e:
            print(f"Failed to save settings on close: {e}")

        if self.is_remuxer_running():
            result = QMessageBox.question(self, "Exit", "A process is running. Are you sure you want to exit?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if result == QMessageBox.No:
                event.ignore()
                return

            self.cancel_event.set()
            with self.process_lock:
                if self.current_process:
                    try:
                        self.current_process.terminate()
                    except Exception:
                        pass

        # Check if we're in a post-completion state and need to reset
        if self.is_scanned and not self.files_to_process:
            # We're in a completed state, reset UI before closing
            self.reset_ui_after_processing()

        event.accept()

    # =============================================================================
    # SETTINGS UI METHODS
    # =============================================================================

    # =============================================================================
    # INFO DIALOGS
    # =============================================================================
    def show_timescale_info(self):
        """Show timescale information dialog."""
        QMessageBox.information(self, "Video Timescale Info",
            "This option can fix playback issues with Variable Frame Rate (VFR) videos.\n\n"
            "• Use original frame rate: Scans each file to find its FPS and uses that value (Recommended).\n\n"
            "• Force preset timescale: Forces a specific value for all videos. Useful if scanning fails or for special cases.\n\n"
            "VIDEO EDITING BENEFITS:\n"
            "• Smooth playback in video editors\n"
            "• Accurate frame-accurate editing\n"
            "• Prevents stuttering and sync issues\n"
            "• Better compatibility with editing software"
        )

    def show_validation_info(self):
        """Show validation information dialog."""
        QMessageBox.information(self, "File Validation",
            "File validation uses ffprobe to check if video files are readable before processing.\n\n"
            "Benefits:\n"
            "• Prevents errors during remuxing\n"
            "• Identifies corrupted files early\n"
            "• Provides better error reporting\n\n"
            "Drawbacks:\n"
            "• Slightly slower scanning process\n"
            "• May reject files that could be processed\n\n"
            "Recommendation: Enable for large batches, disable for quick processing."
        )

    def show_preview_info(self):
        """Show preview information dialog."""
        QMessageBox.information(self, "Command Preview",
            "Command preview shows all FFmpeg commands before processing starts.\n\n"
            "This feature is useful for:\n"
            "• Understanding what the application will do\n"
            "• Debugging processing issues\n"
            "• Learning FFmpeg command structure\n"
            "• Verifying settings before processing\n\n"
            "The preview window shows:\n"
            "• Input and output file paths\n"
            "• All FFmpeg parameters being used\n"
            "• Audio mapping configuration\n"
            "• Timescale settings (if enabled)"
        )

    def show_output_format_info(self):
        """Show output format information dialog."""
        QMessageBox.information(self, "Output Format",
            "Choose the format for remuxed video files.\n\n"
            "Available formats:\n"
            "• MP4: Most compatible, works on all devices\n"
            "• MOV: Apple QuickTime format\n\n"
            "MP4 is recommended for general use."
        )

    def show_file_management_info(self):
        """Show file management information dialog."""
        QMessageBox.information(self, "Original File Management",
            "Controls what happens to original MKV files after remuxing.\n\n"
            "• Move to subfolder: Creates 'Remuxed' folder and moves originals there\n"
            "• Keep in place: Original files remain in their current location\n"
            "• Delete original: Permanently removes original files (not recommended)\n\n"
            "Move to subfolder is the safest option."
        )

    def show_audio_info(self):
        """Show audio information dialog."""
        QMessageBox.information(self, "Audio Streams",
            "Controls whether audio tracks are included in the remuxed files.\n\n"
            "• Include Audio: Copies all audio streams from original to output\n"
            "• Exclude Audio: Creates video-only files (silent)\n\n"
            "When audio is included, all audio tracks from the original file\n"
            "are automatically preserved in the output.\n\n"
            "Most videos should include audio for normal playback."
        )

    def show_timestamp_info(self):
        """Show timestamp information dialog."""
        QMessageBox.information(self, "Preserve Timestamps",
            "Copies the original file's creation and modification dates to the remuxed file.\n\n"
            "This helps maintain:\n"
            "• File organization in media libraries\n"
            "• Backup and sync software behavior\n"
            "• Historical file information\n\n"
            "Recommended for most users."
        )

    def show_overwrite_info(self):
        """Show overwrite information dialog."""
        QMessageBox.information(self, "Overwrite Existing Files",
            "Controls behavior when output files already exist.\n\n"
            "• Unchecked: Skip files if output already exists (default)\n"
            "• Checked: Overwrite existing files with new remux\n\n"
            "Use overwrite mode when re-processing the same files."
        )

    # =============================================================================
    # LOG MANAGEMENT
    # =============================================================================
    def copy_log_to_clipboard(self):
        """Copy the log output to clipboard."""
        try:
            # Get all text from the log widget
            log_content = self.log_text.toPlainText()

            if log_content.strip():  # Only copy if there's content
                # Copy to clipboard
                clipboard = QApplication.clipboard()
                clipboard.setText(log_content)

                # Show success message
                QMessageBox.information(self, "Success", "Log output copied to clipboard!")
            else:
                QMessageBox.information(self, "Info", "No log content to copy.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to copy log to clipboard: {str(e)}")

    def show_completion_dialog(self, message, data, elapsed_time=None, scan_time=None):
        """Show completion dialog with options to open directory or close."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Complete")
        dialog.setModal(True)
        dialog.setFixedSize(350, 170)

        # Set window flags to ensure it stays on top and is properly layered
        dialog.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)

        # Ensure the dialog is raised to the top
        dialog.raise_()
        dialog.activateWindow()

        # Override close event to ensure UI reset happens
        dialog.closeEvent = lambda event: self.handle_completion_dialog_close(dialog, event)

        layout = QVBoxLayout(dialog)
 
        # Add stretchable space to push content down
        layout.addStretch(1)
 
        # Message
        message_label = QLabel(message)
        message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(message_label)
 
        # Scan time (if available)
        if scan_time:
            scan_time_label = QLabel(f"Scan time: {scan_time}")
            scan_time_label.setAlignment(Qt.AlignCenter)
            scan_time_label.setStyleSheet("font-style: italic; color: gray;")
            layout.addWidget(scan_time_label)

        # Remux elapsed time (if available)
        if elapsed_time:
            remux_time_label = QLabel(f"Remux time: {elapsed_time}")
            remux_time_label.setAlignment(Qt.AlignCenter)
            remux_time_label.setStyleSheet("font-style: italic; color: gray;")
            layout.addWidget(remux_time_label)
 
        # Add stretchable space to push content up
        layout.addStretch(1)
 
        # Buttons
        buttons = QDialogButtonBox()
        open_btn = buttons.addButton("Open Location", QDialogButtonBox.ActionRole)
        close_btn = buttons.addButton("Close", QDialogButtonBox.RejectRole)
 
        open_btn.clicked.connect(lambda: self.open_output_directory_and_close(dialog))
        close_btn.clicked.connect(lambda: self.close_completion_dialog(dialog))
 
        layout.addWidget(buttons)

        dialog.exec_()

    def open_output_directory_and_close(self, dialog):
        """Open output directory and close completion dialog."""
        if self.debug_mode:
            self.log_text.append("[DEBUG] User clicked 'Open Location' in completion dialog")
        dialog.accept()
        self.open_output_directory()
        self.reset_ui_after_processing()

    def close_completion_dialog(self, dialog):
        """Close completion dialog."""
        if self.debug_mode:
            self.log_text.append("[DEBUG] User clicked 'Close' in completion dialog")
        dialog.accept()
        self.reset_ui_after_processing()

    def handle_completion_dialog_close(self, dialog, event):
        """Handle completion dialog close event (including X button)."""
        if self.debug_mode:
            self.log_text.append("[DEBUG] Completion dialog closed via X button or other method")
        # Always reset UI when dialog is closed, regardless of how
        self.reset_ui_after_processing()
        event.accept()

    def open_output_directory(self):
        """Open the output directory in the system file explorer."""
        try:
            output_dir = self.output_directory
            if not output_dir:
                # If no output directory specified, use the source directory
                if self.files_to_process:
                    output_dir = os.path.dirname(self.files_to_process[0])

            if output_dir and os.path.exists(output_dir):
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))
                self.process_queue.put(("LOG", f"Opened output directory: {output_dir}"))
            else:
                self.process_queue.put(("LOG", "Warning: Output directory not found or not specified"))
        except Exception as e:
            self.process_queue.put(("LOG", f"Warning: Failed to open output directory: {str(e)}"))

    # =============================================================================
    # DRAG AND DROP HANDLERS
    # =============================================================================
    def dragEnterEvent(self, event):
        """Handle drag enter events to accept file drops."""
        # Check if the event contains URLs (file paths)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()  # Accept the drop

    def dropEvent(self, event):
        """Handle drop events to process dropped files."""
        urls = event.mimeData().urls()
        if not urls:
            return

        # Filter for local files with supported extensions
        supported_extensions = [ext.lower() for ext in self.supported_formats['input']]
        dropped_files = []
        for url in urls:
            if url.isLocalFile():
                file_path = url.toLocalFile()
                if any(file_path.lower().endswith(ext) for ext in supported_extensions):
                    dropped_files.append(file_path)

        if not dropped_files:
            self.log_text.append("Warning: No supported files were dropped.")
            return

        # Update the list of files to process
        self.files_to_process = dropped_files

        # DEBUG: Add logging to track file selection (only in debug mode)
        if self.debug_mode:
            self.log_text.append(f"[DEBUG] Dropped {len(self.files_to_process)} supported files:")
            for file in self.files_to_process:
                self.log_text.append(f"[DEBUG]   {os.path.basename(file)}")

        # Update UI and start automatic scanning
        self.label_input_path.setText(f"{len(self.files_to_process)} files selected")

        # Start automatic scanning and show remux interface immediately
        if self.files_to_process:
            self.start_automatic_scan()
        else:
            self.reset_scan_state()

    # =============================================================================
    # WORKER THREADS
    # =============================================================================
    def start_scan_thread(self):
        """Start the file scanning thread."""
        # Clear cancel event in case it was set from a previous cancelled operation
        self.cancel_event.clear()

        # DEBUG: Log files to process before starting scan (only in debug mode)
        if self.debug_mode:
            self.log_text.append(f"[DEBUG] Starting scan with {len(self.files_to_process)} files in queue:")
            for i, file_path in enumerate(self.files_to_process, 1):
                self.log_text.append(f"[DEBUG]   {i}. {os.path.basename(file_path)} - {file_path}")


        # Start scan timer
        self.scan_start_time = time.time()

        # Disable source and output buttons during scanning
        self.btn_browse_folder.setEnabled(False)
        self.btn_browse_files.setEnabled(False)
        self.btn_browse_output.setEnabled(False)
        self.btn_clear_output.setEnabled(False)

        # Scanning started automatically - no button to update
        self.log_text.clear()

        # Add session header to log
        from datetime import datetime
        session_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.process_queue.put(("LOG", "=" * 70))
        self.process_queue.put(("LOG", f"STPA REMUXER LOG SESSION - {session_time}"))
        self.process_queue.put(("LOG", "=" * 70))

        threading.Thread(target=self.scan_files_worker, args=(list(self.files_to_process),), daemon=True).start()


    def start_remux_thread(self):
        """Start the remuxing thread, showing a preview if enabled."""
        # If the preview option is checked, show the dialog and wait
        if self.preview_commands:
            # The dialog's result will be True if "accept()" was called, False otherwise
            user_accepted = self.show_preview_dialog()

            # Only proceed if the user clicked "Start Remuxing" in the dialog
            if not user_accepted:
                # If user closed dialog, show Start Remux button
                self.btn_start_remux.show()
                self.btn_start_remux.setEnabled(True)
                self.log_text.append("Preview cancelled. Click 'Start Remux' to begin processing.")
                return  # Stop here if the user closed the dialog

        # If we get here, either the preview was disabled or the user accepted it.
        # We can now safely start the remuxing process.
        self.start_remuxing_process()

    def start_remuxing_process(self):
        """Start the actual remuxing process after preview (if enabled)."""
        # Disable source and output buttons during remuxing
        self.btn_browse_folder.setEnabled(False)
        self.btn_browse_files.setEnabled(False)
        self.btn_browse_output.setEnabled(False)
        self.btn_clear_output.setEnabled(False)

        self.btn_start_remux.setEnabled(False)
        self.btn_start_remux.setText("Remuxing...")
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("Pause")
        self.btn_skip.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.disable_settings_controls()
        self.cancel_event.clear()
        self.pause_event.set()


        settings = {
            "files": list(self.files_to_process),
            "output_dir": self.output_directory,
            "include_audio": self.include_audio,
            "file_action": self.file_action,
            "use_timescale": self.use_timescale_option,
            "scan_results": self.scan_results,
            "output_format": self.output_format,
            "preserve_timestamps": self.preserve_timestamps,
            "overwrite_existing": self.overwrite_existing,
        }

        # Record start time for elapsed time calculation
        self.processing_start_time = time.time()

        self.process_queue.put(("LOG", "=" * 70))
        self.process_queue.put(("LOG", f"Remux process started for {len(settings['files'])} files..."))
        threading.Thread(target=self.remux_videos_worker, args=(settings,), daemon=True).start()
        # Set initial status
        self.process_queue.put(("STATUS", "Remuxing..."))

    def scan_files_worker(self, files):
        """Scan multiple video files in parallel for improved performance."""
        results = {}
        total_files = len(files)

        # DEBUG: Log scanning start (only in debug mode)
        if self.debug_mode:
            self.process_queue.put(("LOG", f"[DEBUG] Starting scan of {total_files} files"))
            self.process_queue.put(("LOG", f"[DEBUG] FFmpeg path: {self.ffmpeg_path}"))
            self.process_queue.put(("LOG", f"[DEBUG] FFprobe path: {self.ffprobe_path}"))
            self.process_queue.put(("LOG", f"[DEBUG] Validation enabled: {self.validate_files}"))

        # Use ThreadPoolExecutor for parallel scanning
        max_workers = min(8, os.cpu_count() or 1) if total_files > 1 else 1

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all scan tasks
                future_to_file = {
                    executor.submit(self.scan_single_file, file_path): file_path
                    for file_path in files
                }

                # Process completed tasks
                completed_count = 0
                for future in concurrent.futures.as_completed(future_to_file):
                    if self.cancel_event.is_set():
                        # Cancel remaining tasks
                        for f in future_to_file:
                            if not f.done():
                                f.cancel()
                        break

                    file_path = future_to_file[future]

                    try:
                        result = future.result()
                        results[file_path] = result

                        completed_count += 1

                        # DEBUG: Log each file result as it completes (only in debug mode)
                        if self.debug_mode:
                            file_name = os.path.basename(file_path)
                            is_valid = result.get('valid', False)
                            fps = result.get('fps', 'N/A')
                            duration = result.get('duration', 0)
                            audio_tracks = result.get('audio_tracks', 0)
                            # Use a cleaner, formatted string for the log
                            self.process_queue.put(("LOG", f"[DEBUG] Scanned {file_name}: valid={is_valid}, fps={fps}, duration={duration:.2f}s, audio={audio_tracks}"))
                        # Batch progress updates to reduce UI overhead (every 5 files or at the end)
                        if completed_count % 5 == 0 or completed_count == total_files:
                            progress_percent = (completed_count / total_files) * 100
                            self.process_queue.put(('SCAN_PROGRESS', {
                                'current': completed_count,
                                'total': total_files,
                                'percent': progress_percent
                            }))

                    except Exception as e:
                        completed_count += 1
                        results[file_path] = {'valid': False, 'fps': None, 'duration': 0}
                        self.process_queue.put(("LOG", f"Warning: Error scanning {os.path.basename(file_path)}: {str(e)[:50]}"))

                        # Batch progress updates
                        if completed_count % 5 == 0 or completed_count == total_files:
                            progress_percent = (completed_count / total_files) * 100
                            self.process_queue.put(('SCAN_PROGRESS', {
                                'current': completed_count,
                                'total': total_files,
                                'percent': progress_percent
                            }))

        except Exception as e:
            self.process_queue.put(("LOG", f"Error in parallel scanning: {str(e)}"))
            # Fallback to sequential processing for remaining files
            remaining_files = [f for f in files if f not in results]
            if remaining_files:
                self.process_queue.put(("LOG", f"Falling back to sequential scanning for {len(remaining_files)} files..."))
                for i, file_path in enumerate(remaining_files):
                    if self.cancel_event.is_set():
                        break

                    result = self.scan_single_file(file_path)
                    results[file_path] = result
                    completed_count = len(results)

                    # Batch progress updates
                    if completed_count % 5 == 0 or completed_count == total_files:
                        progress_percent = (completed_count / total_files) * 100
                        self.process_queue.put(('SCAN_PROGRESS', {
                            'current': completed_count,
                            'total': total_files,
                            'percent': progress_percent
                        }))

        # DEBUG: Log final results summary (only in debug mode)
        if self.debug_mode:
            valid_count = sum(1 for r in results.values() if r.get('valid', False))
            invalid_count = len(results) - valid_count
            self.process_queue.put(("LOG", f"[DEBUG] Scan complete: {valid_count} valid, {invalid_count} invalid files"))
            self.process_queue.put(("LOG", f"[DEBUG] Total results: {len(results)}"))

        # Add a summary of validation if it was enabled
        if self.validate_files:
            valid_count = sum(1 for r in results.values() if r.get('valid', True))
            total_count = len(results)
            self.process_queue.put(("LOG", f"Validated {valid_count}/{total_count} files successfully."))

        # --- ADDED: FPS Summary ---
        fps_summary = {}
        for result in results.values():
            fps = result.get('fps')
            if fps:
                try:
                    # Round to 3 decimal places to group similar FPS (e.g., 23.976)
                    rounded_fps = f"{float(fps):.3f}".rstrip('0').rstrip('.')
                    fps_summary[rounded_fps] = fps_summary.get(rounded_fps, 0) + 1
                except (ValueError, TypeError):
                    # Handle non-numeric FPS values if they somehow occur
                    fps_summary[fps] = fps_summary.get(fps, 0) + 1

        if fps_summary:
            self.process_queue.put(("LOG", "Detected Frame Rates:"))
            # Sort by FPS value (as float) for a clean, ordered list
            for fps, count in sorted(fps_summary.items(), key=lambda item: float(item[0])):
                self.process_queue.put(("LOG", f"  - {fps} FPS: {count} file(s)"))
        # --- END ADDITION ---

        self.process_queue.put(('SCAN_COMPLETE', {'results': results}))

    def scan_single_file(self, file_path):
        """Scan a single video file for metadata (used by parallel worker)."""
        result = {'valid': True, 'fps': None, 'duration': 0}
        file_name = os.path.basename(file_path) # Get the filename for logging

        # Skip validation if validation is disabled
        if not self.validate_files:
            try:
                # Get FPS first (separate call to ensure proper logging)
                fps_command = [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=avg_frame_rate", "-of",
                             "default=noprint_wrappers=1:nokey=1", file_path]

                fps_process = subprocess.run(fps_command, capture_output=True, text=True, check=True, timeout=FPS_SCAN_TIMEOUT,
                                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

                fps_fraction = fps_process.stdout.strip()
                if '/' in fps_fraction and fps_fraction != "0/0":
                    num, den = map(int, fps_fraction.split('/'))
                    if den != 0:
                        fps_value = num / den
                        result['fps'] = str(fps_value)
                elif fps_fraction and fps_fraction != "0/0":
                    try:
                        fps_value = float(fps_fraction)
                        result['fps'] = fps_fraction
                    except ValueError:
                        pass

                # Get duration and other info in a separate optimized call
                duration_command = [self.ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=noprint_wrappers=1:nokey=1", file_path]

                duration_process = subprocess.run(duration_command, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
                                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

                if duration_process.returncode == 0:
                    try:
                        result['duration'] = float(duration_process.stdout.strip())
                    except ValueError:
                        pass

                # Get audio track info if audio is included (separate call for detailed audio info)
                if self.include_audio:
                    audio_tracks = self.get_audio_track_info(file_path)
                    result['audio_tracks'] = len(audio_tracks)
                    if audio_tracks:
                        languages = [track['language'] for track in audio_tracks if track['language'] != 'und']
                        result['languages'] = languages

            except subprocess.TimeoutExpired:
                self.process_queue.put(("LOG", f"Warning: Timeout scanning: {file_name}"))
            except Exception as e:
                self.process_queue.put(("LOG", f"Warning: Error scanning {file_name}: {str(e)}"))

            return result

        # Perform validation if validation is enabled
        try:
            # Get FPS first (separate call to ensure proper logging)
            fps_command = [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=avg_frame_rate", "-of",
                         "default=noprint_wrappers=1:nokey=1", file_path]

            fps_process = subprocess.run(fps_command, capture_output=True, text=True, check=True, timeout=FPS_SCAN_TIMEOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

            fps_fraction = fps_process.stdout.strip()
            if '/' in fps_fraction and fps_fraction != "0/0":
                num, den = map(int, fps_fraction.split('/'))
                if den != 0:
                    fps_value = num / den
                    result['fps'] = str(fps_value)
            elif fps_fraction and fps_fraction != "0/0":
                try:
                    fps_value = float(fps_fraction)
                    result['fps'] = fps_fraction
                except ValueError:
                    pass

            # Get duration and other info in a separate optimized call
            duration_command = [self.ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", file_path]

            duration_process = subprocess.run(duration_command, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
                                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

            if duration_process.returncode == 0:
                try:
                    result['duration'] = float(duration_process.stdout.strip())
                except ValueError:
                    pass

            # Get audio track info if audio is included (separate call for detailed audio info)
            if self.include_audio:
                audio_tracks = self.get_audio_track_info(file_path)
                result['audio_tracks'] = len(audio_tracks)
                if audio_tracks:
                    languages = [track['language'] for track in audio_tracks if track['language'] != 'und']
                    result['languages'] = languages

        except subprocess.TimeoutExpired:
            result['valid'] = False
            self.process_queue.put(("LOG", f"Warning: Timeout scanning: {file_name}"))
        except Exception as e:
            result['valid'] = False
            self.process_queue.put(("LOG", f"Warning: Error scanning {file_name}: {str(e)}"))

        # *** ADDED THIS BLOCK TO LOG VALIDATION STATUS ***
        # Only log validation failures to reduce log spam
        if not result['valid']:
            self.process_queue.put(("LOG", f"✗ Validation failed for {file_name}"))

        return result

    def remux_videos_worker(self, settings):
        """Process video files with simple queue-based skip functionality."""
        self.file_queue = settings["files"][:] # Create a copy of the file list
        total_videos = len(self.file_queue)
        remuxed_count, skipped_count, error_count = 0, 0, 0
        
        self.current_file_index = 0
        
        while self.current_file_index < len(self.file_queue):
            if self.cancel_event.is_set():
                self.process_queue.put(("LOG", "Operation cancelled by user."))
                break
            
            # Determine current file and info up front so we can update UI even while paused
            video_file_path = self.file_queue[self.current_file_index]
            file_name = os.path.basename(video_file_path)
            scan_result = settings["scan_results"].get(video_file_path, {})
            duration = scan_result.get('duration', 0)
            # Prepare output paths early so we can handle MOVE action even on pre-start or paused skips
            output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
            output_file_path = os.path.join(output_dir_final, os.path.splitext(file_name)[0] + settings["output_format"])

            # Update UI for the current file immediately
            self.process_queue.put(("LOG", f"Processing file {self.current_file_index + 1}/{total_videos}: {file_name}"))
            self.process_queue.put(("PROGRESS", {'total_percent': (self.current_file_index / total_videos) * 100, 'current': self.current_file_index, 'total': total_videos}))
            self.process_queue.put(("CURRENT_FILE", {'filename': file_name, 'duration': duration}))

            # If paused, allow unlimited skipping without starting the process
            if not self.pause_event.is_set():
                while not self.pause_event.is_set():
                    if self.cancel_event.is_set():
                        self.process_queue.put(("LOG", "Operation cancelled by user."))
                        break
                    if self.skip_event.is_set():
                        # Handle skip while paused: advance to next file and update UI/progress
                        self.skip_event.clear()
                        skipped_count += 1
                        self.process_queue.put(("LOG", f"[SKIP] Skipped while paused: {file_name}"))
                        # Move original if configured to do so, even on skip
                        if settings.get("file_action") == FILE_ACTION_MOVE:
                            try:
                                self.handle_original_file(file_name, output_file_path, settings)
                            except Exception as _e:
                                self.process_queue.put(("LOG", f"   -> WARNING: Failed moving original on skip: {_e}"))
                        self.current_file_index += 1

                        # Update progress and current file label for the next item
                        current_processed = self.current_file_index
                        self.process_queue.put(("PROGRESS", {'total_percent': (current_processed / total_videos) * 100, 'current': current_processed, 'total': total_videos}))
                        if self.current_file_index < len(self.file_queue):
                            next_video_file_path = self.file_queue[self.current_file_index]
                            next_file_name = os.path.basename(next_video_file_path)
                            next_scan_result = settings["scan_results"].get(next_video_file_path, {})
                            next_duration = next_scan_result.get('duration', 0)
                            self.process_queue.put(("CURRENT_FILE", {'filename': next_file_name, 'duration': next_duration}))
                            # Update local context for handling multiple rapid skips while paused
                            video_file_path = next_video_file_path
                            file_name = next_file_name
                            scan_result = next_scan_result
                            duration = next_duration
                            # Recompute output paths for the new current file
                            output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
                            output_file_path = os.path.join(output_dir_final, os.path.splitext(file_name)[0] + settings["output_format"])
                        else:
                            self.process_queue.put(("CURRENT_FILE", {'filename': 'Processing Complete', 'duration': 0}))
                            break
                    else:
                        time.sleep(0.1)

                # If cancelled during pause, stop
                if self.cancel_event.is_set():
                    break

                # If we reached the end while paused due to skipping past the last item
                if self.current_file_index >= len(self.file_queue):
                    break

            # If a skip was requested just before starting, treat it as pre-start skip
            if self.skip_event.is_set():
                self.skip_event.clear()
                skipped_count += 1
                self.process_queue.put(("LOG", f"[SKIP] Skipped before starting: {file_name}"))
                # Move original if configured to do so, even on skip
                if settings.get("file_action") == FILE_ACTION_MOVE:
                    try:
                        self.handle_original_file(file_name, output_file_path, settings)
                    except Exception as _e:
                        self.process_queue.put(("LOG", f"   -> WARNING: Failed moving original on skip: {_e}"))
                self.current_file_index += 1

                # Update progress and set the next current file immediately
                current_processed = self.current_file_index
                self.process_queue.put(("PROGRESS", {'total_percent': (current_processed / total_videos) * 100, 'current': current_processed, 'total': total_videos}))
                if self.current_file_index < len(self.file_queue):
                    next_video_file_path = self.file_queue[self.current_file_index]
                    next_file_name = os.path.basename(next_video_file_path)
                    next_scan_result = settings["scan_results"].get(next_video_file_path, {})
                    next_duration = next_scan_result.get('duration', 0)
                    self.process_queue.put(("CURRENT_FILE", {'filename': next_file_name, 'duration': next_duration}))
                else:
                    self.process_queue.put(("CURRENT_FILE", {'filename': 'Processing Complete', 'duration': 0}))
                continue

            # Re-enable skip button for each file
            self.process_queue.put(("SKIP_BUTTON_RESET", None))

            # Check if file is valid
            if not scan_result.get('valid', True):
                self.process_queue.put(("LOG", f"Skipping invalid file: {file_name}"))
                skipped_count += 1
                self.current_file_index += 1
                continue

            # Build and execute command
            command, output_file_path = self.build_ffmpeg_command(video_file_path, settings)

            # Process the file
            result = self.execute_ffmpeg_process(command, output_file_path, file_name, duration, settings, video_file_path)

            # Handle result
            if result == "error":
                error_count += 1
                skipped_count += 1
                self.process_queue.put(("LOG", f"[DEBUG] File error: {file_name}"))
            elif result == "completed":
                remuxed_count += 1
                self.process_queue.put(("LOG", f"[DEBUG] File completed: {file_name}"))
            elif result == "skipped":
                skipped_count += 1
                self.process_queue.put(("LOG", f"[DEBUG] File skipped: {file_name}"))
                # Move original if configured to do so on skip after process started or output existed
                if settings.get("file_action") == FILE_ACTION_MOVE:
                    try:
                        self.handle_original_file(file_name, output_file_path, settings)
                    except Exception as _e:
                        self.process_queue.put(("LOG", f"   -> WARNING: Failed moving original on skip: {_e}"))
            elif result == "cancelled":
                break
                
            # Move to next file
            self.current_file_index += 1
            
            # Update progress immediately after processing each file
            current_processed = self.current_file_index
            self.process_queue.put(("PROGRESS", {'total_percent': (current_processed / total_videos) * 100, 'current': current_processed, 'total': total_videos}))
            
            # Update UI to show next file if there are more files
            if self.current_file_index < len(self.file_queue):
                next_video_file_path = self.file_queue[self.current_file_index]
                next_file_name = os.path.basename(next_video_file_path)
                next_scan_result = settings["scan_results"].get(next_video_file_path, {})
                next_duration = next_scan_result.get('duration', 0)
                
                self.process_queue.put(("CURRENT_FILE", {'filename': next_file_name, 'duration': next_duration}))
                self.process_queue.put(("LOG", f"[DEBUG] UI updated for next file: {next_file_name}"))
            else:
                self.process_queue.put(("CURRENT_FILE", {'filename': 'Processing Complete', 'duration': 0}))
                self.process_queue.put(("LOG", f"[DEBUG] All files processed. Queue complete."))
        
        self.process_queue.put(("PROGRESS", {'total_percent': 100, 'current': total_videos, 'total': total_videos}))
        self.process_queue.put(("FINISHED", {'remuxed': remuxed_count, 'skipped': skipped_count}))

    def execute_ffmpeg_process(self, command, output_file_path, file_name, duration, settings, source_file_path):
        """Execute FFmpeg process with real-time output reading to prevent freezing."""
        # --- Consolidated Pre-check and Logging ---
        if os.path.exists(output_file_path):
            if settings.get("overwrite_existing", False):
                self.process_queue.put(("LOG", f"Remuxing: {file_name} (Overwriting existing)"))
            else:
                self.process_queue.put(("LOG", f"Skipping: {file_name} (Output file already exists)"))
                return "skipped"
        else:
            self.process_queue.put(("LOG", f"Remuxing: {file_name}"))
        # --- End Consolidation ---

        try:
            # self.process_queue.put(("LOG", f""))
            # self.process_queue.put(("LOG", f"{'='*60}"))
            # self.process_queue.put(("LOG", f"[PROCESSING] {file_name}"))
            # self.process_queue.put(("LOG", f"{'='*60}"))

            # Run the command with real-time output reading
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stdout and stderr
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            # Store process reference for skip functionality
            with self.process_lock:
                self.current_process = process

            # Read output line by line to prevent freezing
            while True:
                # Check for skip - immediate return if skip requested
                if self.skip_event.is_set():
                    # Clear skip event immediately to allow next skip
                    self.skip_event.clear()
                    
                    self.process_queue.put(("LOG", f"[SKIP] Skipping {file_name} - moving to next file"))
                    
                    # Re-enable skip button immediately
                    self.process_queue.put(("SKIP_BUTTON_RESET", None))
                    
                    process.terminate()
                    try:
                        process.kill()
                    except Exception:
                        pass
                    
                    # Clean up output file
                    try:
                        if os.path.exists(output_file_path):
                            os.remove(output_file_path)
                    except Exception:
                        pass
                    
                    # Clear process reference
                    with self.process_lock:
                        self.current_process = None
                    
                    return "skipped"

                # Check for cancel event
                if self.cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    
                    try:
                        if os.path.exists(output_file_path):
                            os.remove(output_file_path)
                    except Exception:
                        pass
                    
                    with self.process_lock:
                        self.current_process = None
                    return "cancelled"

                # Check for pause event - this makes pause responsive during file processing
                if not self.pause_event.is_set():
                    # Pause requested - wait for resume or other events
                    while not self.pause_event.is_set() and not self.cancel_event.is_set() and not self.skip_event.is_set():
                        time.sleep(0.1)  # Small delay to prevent busy waiting

                    # If cancelled or skipped while paused, handle accordingly
                    if self.cancel_event.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        
                        try:
                            if os.path.exists(output_file_path):
                                os.remove(output_file_path)
                        except Exception:
                            pass
                        
                        with self.process_lock:
                            self.current_process = None
                        return "cancelled"

                    # Check for skip during pause
                    if self.skip_event.is_set():
                        # Skip requested while paused - handle it
                        continue

                    # If we get here, pause was lifted, continue processing
                    continue

                # Read output line by line to prevent buffer overflow and freezing
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break

                if output:
                    # Log FFmpeg output with detailed information but less frequently
                    stripped_output = output.strip()
                    if stripped_output:
                        # Log detailed progress information but reduce frequency
                        if self.debug_mode and any(keyword in stripped_output for keyword in ['time=', 'frame=', 'size=', 'fps=', 'bitrate=']):
                            self.process_queue.put(("LOG", f"   [FFMPEG] {stripped_output}"))

            # Wait for process to complete
            process.wait()

            # Clear the process reference
            with self.process_lock:
                self.current_process = None

            # Re-enable skip button for next file
            self.process_queue.put(("SKIP_BUTTON_RESET", None))

            if self.cancel_event.is_set():
                try:
                    if os.path.exists(output_file_path):
                        os.remove(output_file_path)
                except Exception:
                    pass
                return "cancelled"

            if process.returncode == 0:
                self.process_queue.put(("LOG", f"   -> Success"))

                # Preserve original file timestamps if option is enabled
                if settings.get("preserve_timestamps", False):
                    # Use the original source file path that was passed to this function
                    # DEBUG: Log the paths being used for timestamp preservation
                    if self.debug_mode:
                        self.process_queue.put(("LOG", f"   [DEBUG] Attempting timestamp preservation"))
                        self.process_queue.put(("LOG", f"   [DEBUG] Source file path: {source_file_path}"))
                        self.process_queue.put(("LOG", f"   [DEBUG] Target file path: {output_file_path}"))
                        self.process_queue.put(("LOG", f"   [DEBUG] Source file exists: {os.path.exists(source_file_path)}"))
                        self.process_queue.put(("LOG", f"   [DEBUG] Target file exists: {os.path.exists(output_file_path)}"))
                    if self.preserve_file_timestamps(source_file_path, output_file_path):
                        if self.debug_mode:
                            self.process_queue.put(("LOG", f"   -> [DEBUG] Timestamps preserved"))
                    else:
                        self.process_queue.put(("LOG", f"   -> WARNING: Failed to preserve timestamps"))

                # Handle original file
                self.handle_original_file(file_name, output_file_path, settings)
                return "completed"
            else:
                self.process_queue.put(("LOG", f"   -> ERROR: Failed remuxing {file_name}. Return code: {process.returncode}"))
                return "error"

        except Exception as e:
            self.process_queue.put(("LOG", f"   -> CRITICAL ERROR: {e}"))
            with self.process_lock:
                self.current_process = None
            # Re-enable skip button for next file
            self.process_queue.put(("SKIP_BUTTON_RESET", None))
            return "error"

    def preserve_file_timestamps(self, source_file, target_file):
        """Copy timestamps from source file to target file."""
        try:
            # Get timestamps from source file
            stat_info = os.stat(source_file)
            access_time = stat_info.st_atime
            modify_time = stat_info.st_mtime

            # Apply timestamps to target file
            os.utime(target_file, (access_time, modify_time))
            return True
        except Exception as e:
            self.process_queue.put(("LOG", f"Warning: Failed to preserve timestamps: {str(e)}"))
            return False

    def handle_original_file(self, file_name, output_file_path, settings):
        """Handle the original file based on the file action setting."""
        action = settings["file_action"]
        try:
            if action == FILE_ACTION_MOVE:
                # Move to subfolder - always in source directory, not output directory
                # Find the source directory by looking through files_to_process
                source_dir = None
                for file_path in settings.get("files", []):
                    if os.path.basename(file_path) == file_name:
                        source_dir = os.path.dirname(file_path)
                        break

                if source_dir:
                    original_ext = os.path.splitext(file_name)[1].upper()[1:]
                    subfolder = os.path.join(source_dir, "Remuxed")
                    os.makedirs(subfolder, exist_ok=True)
                    shutil.move(os.path.join(source_dir, file_name), os.path.join(subfolder, file_name))
                    if self.debug_mode:
                        self.process_queue.put(("LOG", f"   -> [DEBUG] Original moved to 'Remuxed' folder"))
                else:
                    self.process_queue.put(("LOG", f"   -> WARNING: Could not find source directory for {file_name}"))
            elif action == FILE_ACTION_DELETE:
                # Find the source directory for deletion
                source_dir = None
                for file_path in settings.get("files", []):
                    if os.path.basename(file_path) == file_name:
                        source_dir = os.path.dirname(file_path)
                        break

                if source_dir:
                    os.remove(os.path.join(source_dir, file_name))
                    if self.debug_mode:
                        self.process_queue.put(("LOG", f"   -> [DEBUG] Original file deleted"))
                else:
                    self.process_queue.put(("LOG", f"   -> WARNING: Could not find source directory for {file_name}"))
        except Exception as e:
            self.process_queue.put(("LOG", f"   -> WARNING: Failed to handle original file: {str(e)}"))

    def get_audio_track_info(self, file_path):
        """Get information about audio tracks in the file."""
        try:
            command = [self.ffprobe_path, "-v", "error", "-select_streams", "a",
                       "-show_entries", "stream=index,codec_name,channels,language",
                       "-of", "csv=p=0", file_path]

            result = subprocess.run(command, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

            if result.returncode == 0:
                tracks = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(',')
                        if len(parts) >= 3:
                            index, codec, channels = parts[0], parts[1], parts[2]
                            language = parts[3] if len(parts) > 3 and parts[3] else "und"
                            tracks.append({
                                'index': int(index),
                                'codec': codec,
                                'channels': channels,
                                'language': language
                            })
                return tracks
            else:
                self.process_queue.put(("LOG", f"Warning: ffprobe failed for audio tracks in {os.path.basename(file_path)}"))
                return []
        except subprocess.TimeoutExpired:
            self.process_queue.put(("LOG", f"Warning: Timeout getting audio tracks for {os.path.basename(file_path)}"))
            return []
        except Exception as e:
            self.process_queue.put(("LOG", f"Warning: Error getting audio tracks for {os.path.basename(file_path)}: {str(e)}"))
            return []

    def validate_video_file(self, file_path):
        """Validate that a file is a readable video file using ffprobe."""
        try:
            command = [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "stream=codec_name", "-of",
                       "default=noprint_wrappers=1:nokey=1", file_path]

            result = subprocess.run(command, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            return result.returncode == 0 and result.stdout.strip()
        except subprocess.TimeoutExpired:
            self.process_queue.put(("LOG", f"Warning: Timeout validating {os.path.basename(file_path)}"))
            return False
        except Exception as e:
            self.process_queue.put(("LOG", f"Warning: Error validating {os.path.basename(file_path)}: {str(e)}"))
            return False

    def get_video_duration(self, file_path):
        """Get video duration in seconds."""
        try:
            command = [self.ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", file_path]

            result = subprocess.run(command, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                self.process_queue.put(("LOG", f"Warning: ffprobe failed to get duration for {os.path.basename(file_path)}"))
                return 0
        except subprocess.TimeoutExpired:
            self.process_queue.put(("LOG", f"Warning: Timeout getting duration for {os.path.basename(file_path)}"))
            return 0
        except ValueError:
            self.process_queue.put(("LOG", f"Warning: Invalid duration format for {os.path.basename(file_path)}"))
            return 0
        except Exception as e:
            self.process_queue.put(("LOG", f"Warning: Error getting duration for {os.path.basename(file_path)}: {str(e)}"))
            return 0

    def build_ffmpeg_command(self, video_file_path, settings):
        """Build FFmpeg command for remuxing a video file."""
        file_name = os.path.basename(video_file_path)
        file_name_no_ext = os.path.splitext(file_name)[0]
        output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
        output_file_path = os.path.join(output_dir_final, file_name_no_ext + settings["output_format"])

        command = [self.ffmpeg_path, "-y", "-i", video_file_path, "-c:v", "copy"]

        # Handle audio mapping
        if settings["include_audio"]:
            # Map all audio streams (simplified behavior)
            command.extend(["-map", "0:v", "-map", "0:a", "-c:a", "copy"])
        else:
            command.extend(["-an"])

        # Handle timescale options
        if settings["use_timescale"]:
            timescale = None
            scan_result = settings["scan_results"].get(video_file_path, {})
            timescale = scan_result.get('fps')
            if not timescale:
                self.process_queue.put(("LOG", f"Warning: No FPS found for {file_name}, timescale option skipped."))

            if timescale:
                try:
                    float(timescale)
                    command.extend(["-video_track_timescale", str(timescale)])
                except ValueError:
                    self.process_queue.put(("LOG", f"Warning: Invalid timescale '{timescale}', skipping option."))

        command.append(output_file_path)

        return command, output_file_path

    def show_preview_dialog(self, auto_start=False):
        """Show preview of commands that would be executed."""
        if not self.files_to_process:
            QMessageBox.warning(self, "No Files", "Please select files first.")
            return

        if not self.is_scanned:
            QMessageBox.warning(self, "Not Scanned", "Please scan files first before previewing commands.")
            return

        self.preview_window = QDialog(self)
        self.preview_window.setWindowTitle("Command Preview")
        self.preview_window.setModal(True)
        self.preview_window.resize(800, 500)

        layout = QVBoxLayout(self.preview_window)

        # Info label
        info_label = QLabel(f"Preview of commands for {len(self.files_to_process)} files:")
        layout.addWidget(info_label)

        # Text widget with scrollbar
        text_widget = QTextEdit()
        text_widget.setFont(QFont("Consolas", 9))  # Better monospace font
        text_widget.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(text_widget)

        # Generate and display commands
        commands = self.generate_preview_commands()
        for i, (input_file, command) in enumerate(commands, 1):
            filename = os.path.basename(input_file)
            text_widget.append(f"{i}. {filename}")
            text_widget.append(" ".join(command))
            text_widget.append("")

        # Button container frame
        button_container = QHBoxLayout()
        layout.addLayout(button_container)

        button_container.addStretch()

        # Start Remuxing button
        if auto_start:
            # Countdown variables
            self.countdown_seconds = 10
            self.countdown_active = True

            start_btn = QPushButton(f"Start Remuxing (Auto-start in {self.countdown_seconds}s)")
            start_btn.clicked.connect(lambda: self.start_remuxing_from_preview(self.preview_window))
            button_container.addWidget(start_btn)

            # Countdown timer function
            def update_countdown():
                if not self.countdown_active or not self.preview_window.isVisible():
                    return

                self.countdown_seconds -= 1
                if self.countdown_seconds > 0:
                    start_btn.setText(f"Start Remuxing (Auto-start in {self.countdown_seconds}s)")
                    # Schedule next update in 1 second
                    QTimer.singleShot(1000, update_countdown)
                else:
                    start_btn.setText("Starting Remux...")
                    # Auto-start remuxing
                    if self.preview_window.isVisible():
                        self.start_remuxing_from_preview(self.preview_window)

            # Start countdown timer
            QTimer.singleShot(1000, update_countdown)  # Start updating after 1 second
        else:
            start_btn = QPushButton("Start Remuxing")
            start_btn.clicked.connect(lambda: self.start_remuxing_from_preview(self.preview_window))
            button_container.addWidget(start_btn)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(lambda: [setattr(self, 'countdown_active', False), self.preview_window.reject()])
        button_container.addWidget(close_btn)

        # ADD THIS LINE to execute the dialog and return its result
        return self.preview_window.exec_()

    def generate_preview_commands(self):
        """Generate preview of all FFmpeg commands."""
        commands = []
        settings = {
            "output_dir": self.output_directory,
            "include_audio": self.include_audio,
            "use_timescale": self.use_timescale_option,
            "scan_results": self.scan_results,
        }

        for video_file_path in self.files_to_process:
            file_name = os.path.basename(video_file_path)
            file_name_no_ext = os.path.splitext(file_name)[0]
            output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
            output_file_path = os.path.join(output_dir_final, file_name_no_ext + self.output_format)

            command = [self.ffmpeg_path, "-y", "-i", video_file_path, "-c:v", "copy"]

            # Handle audio mapping
            if settings["include_audio"]:
                # Map all audio streams (simplified behavior)
                command.extend(["-map", "0:v", "-map", "0:a", "-c:a", "copy"])
            else:
                command.extend(["-an"])

            if settings["use_timescale"]:
                timescale = None
                scan_result = settings["scan_results"].get(video_file_path, {})
                timescale = scan_result.get('fps')
                if timescale:
                    try:
                        float(timescale)
                        command.extend(["-video_track_timescale", str(timescale)])
                    except ValueError:
                        pass

            command.append(output_file_path)
            commands.append((video_file_path, command))

        return commands

    def start_remuxing_from_preview(self, preview_window):
        """Closes the preview dialog and signals acceptance."""
        self.countdown_active = False  # Stop countdown if user manually clicked
        preview_window.accept() # This closes the dialog and returns an "Accepted" result

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    # print("[DEBUG] Starting application...")
    # print(f"[DEBUG] Script arguments: {sys.argv}")
    # print(f"[DEBUG] Current working directory: {os.getcwd()}")

    # Check if QApplication already exists
    app = QApplication.instance()
    if app is None:
        # print("[DEBUG] Creating new QApplication instance...")
        app = QApplication(sys.argv)
    else:
        pass
        # print("[DEBUG] Using existing QApplication instance...")

    # Set a modern, clean font for the application with fallbacks
    font = QFont()
    font.setFamilies(["Roboto", "Segoe UI", "Arial"])
    font.setPointSize(9)
    app.setFont(font)

    # print(f"[DEBUG] Number of top-level windows before creating main window: {len(app.topLevelWindows())}")

    window = RemuxApp()
    # print(f"[DEBUG] Main window created: {window}")
    # print(f"[DEBUG] Number of top-level windows after creating main window: {len(app.topLevelWindows())}")

    window.show()
    # print(f"[DEBUG] Main window shown, visible: {window.isVisible()}")
    # print(f"[DEBUG] Final number of top-level windows: {len(app.topLevelWindows())}")

    sys.exit(app.exec_())
