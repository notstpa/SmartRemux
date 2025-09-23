# =============================================================================
# IMPORTS AND DEPENDENCIES
# =============================================================================
# Import all required Python modules and libraries for the video remuxer GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import os
import threading
import queue
import time
import sys
import shutil
import json
import concurrent.futures


# =============================================================================
# MAIN APPLICATION CLASS - RemuxApp
# =============================================================================
# Enhanced Tkinter-based GUI application for remuxing video files with
# improved progress tracking, format support, and resume capability
class RemuxApp(tk.Tk):
    """
    Enhanced Tkinter-based GUI application for remuxing video files,
    featuring improved progress tracking, format support, and resume capability.
    """

    # =============================================================================
    # CONSTANTS AND CONFIGURATION
    # =============================================================================
    # Define application-wide constants and settings for consistent behavior
    WINDOW_WIDTH = 650
    WINDOW_HEIGHT = 600
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
    UI_STATE_DISABLED = "disabled"
    UI_STATE_NORMAL = "normal"

    # =============================================================================
    # INITIALIZATION METHOD
    # =============================================================================
    # Set up the application on startup including window configuration,
    # tool validation, state initialization, and widget creation
    def __init__(self):
        super().__init__()
        self.title("Stpa Remuxer v2.0")

        # Disable focus for all widgets
        self.option_add("*takeFocus", 0)

        # --- Window dimensions ---
        window_width, window_height = self.WINDOW_WIDTH, self.WINDOW_HEIGHT
        self.minsize(window_width, window_height)
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)
        self.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")

        # Set custom window icon with improved error handling and platform optimization
        self.set_window_icon("ICOtrans.ico")

        
        # --- Application State ---
        # Check for required tools (ffmpeg and ffprobe) at startup
        self.ffmpeg_path = self.find_ffmpeg_path()
        self.ffprobe_path = self.find_ffprobe_path()

        # Show error dialog with retry option if required tools are not found
        if not self.ffmpeg_path or not self.ffprobe_path:
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


        # --- Supported formats ---
        self.supported_formats = {
            'input': ['.mkv'],
            'output': ['.mp4', '.mov']
        }

        # --- Settings Variables ---
        self.use_timescale_option = tk.BooleanVar(value=True)
        self.timescale_is_source = tk.BooleanVar(value=True)
        self.timescale_preset_var = tk.StringVar(value=self.DEFAULT_TIMESCALE)
        self.timescale_custom_var = tk.StringVar(value="")
        self.auto_start_remux = tk.BooleanVar(value=True)
        self.include_audio = tk.BooleanVar(value=True)
        self.file_action_var = tk.StringVar(value=self.FILE_ACTION_MOVE)
        self.output_format_var = tk.StringVar(value=".mp4")
        self.validate_files_var = tk.BooleanVar(value=True)
        self.preserve_timestamps_var = tk.BooleanVar(value=True)
        self.preview_commands_var = tk.BooleanVar(value=False)
        self.overwrite_existing_var = tk.BooleanVar(value=False)

        # --- Settings State ---
        self.settings_disabled = False

        self.create_widgets()
        self.after(self.PROGRESS_UPDATE_INTERVAL, self.check_queue)

        # Remove focus from all existing widgets
        self.remove_focus_from_all_widgets()

        # Specifically configure notebook tabs
        self.configure_notebook_tabs()

        # Apply tab styling after a short delay to ensure tabs are created
        self.after(100, self.apply_tab_styling)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Load saved settings FIRST
        self.load_settings()

        # Add auto-save traces to all settings variables AFTER loading
        self.auto_start_remux.trace_add("write", lambda *args: self.auto_save_settings())
        self.include_audio.trace_add("write", lambda *args: self.auto_save_settings())
        self.file_action_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.output_format_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.validate_files_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.preserve_timestamps_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.preview_commands_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.overwrite_existing_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.use_timescale_option.trace_add("write", lambda *args: self.auto_save_settings())
        self.timescale_is_source.trace_add("write", lambda *args: self.auto_save_settings())
        self.timescale_preset_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.timescale_custom_var.trace_add("write", lambda *args: self.auto_save_settings())

        # Ensure timescale options are properly initialized on startup
        if self.use_timescale_option.get():
            self.toggle_timescale_selector()

    # =============================================================================
    # SETTINGS MANAGEMENT
    # =============================================================================
    # Handle application settings persistence, loading, saving, and restoration
    def get_settings_file_path(self):
        """Get the path to the settings file."""
        try:
            # Use the application's directory for settings
            # This allows different settings for different application locations
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
                "auto_start_remux": self.auto_start_remux.get(),
                "include_audio": self.include_audio.get(),
                "file_action": self.file_action_var.get(),
                "output_format": self.output_format_var.get(),
                "validate_files": self.validate_files_var.get(),
                "preserve_timestamps": self.preserve_timestamps_var.get(),
                "preview_commands": self.preview_commands_var.get(),
                "overwrite_existing": self.overwrite_existing_var.get(),
                "use_timescale": self.use_timescale_option.get(),
                "timescale_is_source": self.timescale_is_source.get(),
                "timescale_preset": self.timescale_preset_var.get(),
                "timescale_custom": self.timescale_custom_var.get(),
            }

            with open(self.get_settings_file_path(), 'w') as f:
                json.dump(settings, f, indent=2)

        except Exception as e:
            print(f"Failed to save settings: {e}")

    def auto_save_settings(self):
        """Auto-save settings when they change."""
        try:
            self.save_settings()
            # Show brief visual feedback that settings were saved
            self.show_settings_saved_feedback()
        except Exception as e:
            print(f"Failed to auto-save settings: {e}")

    def show_settings_saved_feedback(self):
        """Show brief visual feedback that settings were saved."""
        try:
            # Create a small label to show "Settings saved" briefly
            if not hasattr(self, 'settings_feedback_label'):
                self.settings_feedback_label = ttk.Label(self.settings_tab, text="✓ Settings saved", foreground="green", font=("Segoe UI", 8, "italic"))
                self.settings_feedback_label.place(relx=1.0, rely=0.0, x=-10, y=10, anchor="ne")

            # Update the label text and make it visible
            self.settings_feedback_label.config(text="✓ Settings saved")
            self.settings_feedback_label.lift()

            # Hide the feedback after 100 seconds
            self.after(100, lambda: self.settings_feedback_label.config(text=""))

        except Exception as e:
            print(f"Failed to show settings feedback: {e}")

    def load_settings(self):
        """Load settings from file."""
        try:
            settings_file = self.get_settings_file_path()
            if os.path.exists(settings_file):
                with open(settings_file, 'r') as f:
                    settings = json.load(f)

                # Apply loaded settings
                if "auto_start_remux" in settings:
                    self.auto_start_remux.set(settings["auto_start_remux"])
                if "include_audio" in settings:
                    self.include_audio.set(settings["include_audio"])
                if "file_action" in settings:
                    self.file_action_var.set(settings["file_action"])
                if "output_format" in settings:
                    self.output_format_var.set(settings["output_format"])
                if "validate_files" in settings:
                    self.validate_files_var.set(settings["validate_files"])
                if "preserve_timestamps" in settings:
                    self.preserve_timestamps_var.set(settings["preserve_timestamps"])
                if "preview_commands" in settings:
                    self.preview_commands_var.set(settings["preview_commands"])
                if "overwrite_existing" in settings:
                    self.overwrite_existing_var.set(settings["overwrite_existing"])
                if "use_timescale" in settings:
                    self.use_timescale_option.set(settings["use_timescale"])
                if "timescale_is_source" in settings:
                    self.timescale_is_source.set(settings["timescale_is_source"])
                if "timescale_preset" in settings:
                    self.timescale_preset_var.set(settings["timescale_preset"])
                if "timescale_custom" in settings:
                    self.timescale_custom_var.set(settings["timescale_custom"])

                # Update UI elements that depend on these settings
                self.on_timescale_option_change()
                # Ensure timescale options are properly initialized
                if self.use_timescale_option.get():
                    self.toggle_timescale_selector()

        except Exception as e:
            print(f"Failed to load settings: {e}")

    def restore_defaults(self):
        """Restore all settings to their default values."""
        try:
            # Reset all settings to defaults
            self.auto_start_remux.set(True)  # Changed to True as requested
            self.include_audio.set(True)
            self.file_action_var.set(self.FILE_ACTION_MOVE)
            self.output_format_var.set(".mp4")
            self.validate_files_var.set(True)
            self.preserve_timestamps_var.set(True)
            self.preview_commands_var.set(False)
            self.overwrite_existing_var.set(False)
            self.use_timescale_option.set(True)
            self.timescale_is_source.set(True)
            self.timescale_preset_var.set(self.DEFAULT_TIMESCALE)
            self.timescale_custom_var.set("")

            # Update UI elements
            self.on_timescale_option_change()
            # Ensure timescale options are properly initialized
            if self.use_timescale_option.get():
                self.toggle_timescale_selector()

        except Exception as e:
            print(f"Failed to restore defaults: {e}")

    # =============================================================================
    # UI SETUP METHODS
    # =============================================================================
    # Configure UI appearance, focus management, and widget styling
    def remove_focus_from_all_widgets(self):
        """Remove focus capability from all widgets to eliminate dotted borders."""
        def configure_widget(widget):
            try:
                # Remove highlight border
                widget.configure(highlightthickness=0, takefocus=0)
                # For ttk widgets, also configure style
                if hasattr(widget, 'configure'):
                    try:
                        widget.configure(takefocus=False)
                    except:
                        pass
            except:
                pass

        def traverse_widgets(parent):
            configure_widget(parent)
            for child in parent.winfo_children():
                configure_widget(child)
                traverse_widgets(child)

        traverse_widgets(self)

    def configure_notebook_tabs(self):
        """Specifically configure notebook tabs to remove focus dotted lines."""
        try:
            # Configure the notebook widget itself
            self.notebook.configure(takefocus=0)

            # The option database settings should handle the tabs
            # Just ensure the notebook doesn't take focus

        except Exception as e:
            print(f"Error configuring notebook tabs: {e}")

    def apply_tab_styling(self):
        """Apply styling to notebook tabs after they're created."""
        try:
            # Create a completely custom style for tabs
            style = ttk.Style()

            # Configure the tab style to remove all focus indicators
            style.configure("NoFocus.TNotebook.Tab",
                          background=self.cget("background"),
                          foreground="black",
                          lightcolor=self.cget("background"),
                          borderwidth=0,
                          focuscolor=self.cget("background"),
                          focusthickness=0,
                          highlightthickness=0,
                          highlightcolor=self.cget("background"))

            # Also configure the default TNotebook.Tab style
            style.configure("TNotebook.Tab",
                          focuscolor=self.cget("background"),
                          focusthickness=0,
                          highlightthickness=0,
                          highlightcolor=self.cget("background"))

            # Apply this style to all existing tabs
            for tab_id in self.notebook.tabs():
                try:
                    self.notebook.tab(tab_id, style="NoFocus.TNotebook.Tab")
                except tk.TclError:
                    # If the style doesn't exist, skip it
                    pass

        except Exception as e:
            print(f"Error applying tab styling: {e}")

    # =============================================================================
    # WIDGET CREATION METHODS
    # =============================================================================
    # Build the main interface components including tabs, frames, and controls
    def create_widgets(self):
        # Configure notebook to prevent focus indicators
        style = ttk.Style()
        style.configure("TNotebook",
                      focuscolor=self.cget("background"),
                      focusthickness=0,
                      highlightthickness=0)

        self.notebook = ttk.Notebook(self, takefocus=0)
        self.notebook.pack(padx=10, pady=10, expand=True, fill="both")

        # Bind to prevent focus on tab changes
        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self.focus())

        self.remuxer_tab = ttk.Frame(self.notebook, padding=(5, 5))
        self.notebook.add(self.remuxer_tab, text="Remuxer")

        self.settings_tab = ttk.Frame(self.notebook, padding=(5, 5))
        self.notebook.add(self.settings_tab, text="Settings")

        # Advanced tab removed - options moved to Settings tab

        self.logs_tab = ttk.Frame(self.notebook, padding=(5, 5))
        self.notebook.add(self.logs_tab, text="Logs")

        self.create_remuxer_widgets()
        self.create_settings_widgets()
        self.create_logs_widgets()

    def create_remuxer_widgets(self):
        # --- Source & Output Frame ---
        frame_folder = ttk.LabelFrame(self.remuxer_tab, text="Source & Output", padding=(15, 8))
        frame_folder.pack(padx=10, pady=5, fill="x")

        # Source folder selection row
        ttk.Label(frame_folder, text="Source:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.label_input_path = ttk.Label(frame_folder, text="No folder or files selected", wraplength=450)
        self.label_input_path.grid(row=0, column=1, sticky="w", pady=(0, 5), columnspan=2)
        self.btn_browse_folder = ttk.Button(frame_folder, text="Browse Folder", command=self.browse_input_folder)
        self.btn_browse_folder.grid(row=0, column=3, padx=(5, 0), pady=(0, 5))
        self.btn_browse_files = ttk.Button(frame_folder, text="Browse Files", command=self.browse_input_files)
        self.btn_browse_files.grid(row=0, column=4, padx=(5, 0), pady=(0, 5))

        ttk.Label(frame_folder, text="Output:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.label_output_path = ttk.Label(frame_folder, text="Same as source", wraplength=450)
        self.label_output_path.grid(row=1, column=1, sticky="w", pady=(0, 5))
        self.btn_browse_output = ttk.Button(frame_folder, text="Browse", command=self.browse_output_folder, width=8)
        self.btn_browse_output.grid(row=1, column=3, padx=(5, 0), pady=(0, 5))
        self.btn_clear_output = ttk.Button(frame_folder, text="Clear", command=self.clear_output_folder, width=8)
        self.btn_clear_output.grid(row=1, column=4, padx=(5, 0), pady=(0, 5))

        # --- Scanning Frame ---
        self.frame_scan = ttk.LabelFrame(self.remuxer_tab, text="Step 1: File Preparation", padding=(15, 8))
        self.frame_scan.pack(padx=10, pady=(5, 0), fill="x")
        self.label_scan_progress = ttk.Label(self.frame_scan, text="Ready to scan.")
        self.label_scan_progress.pack(pady=(0, 3), anchor="w")
        self.progress_bar_scan = ttk.Progressbar(self.frame_scan, orient="horizontal", mode="determinate")
        self.progress_bar_scan.pack(fill="x", pady=3)

        # Timer label for scan elapsed time
        self.label_scan_timer = ttk.Label(self.frame_scan, text="", font=("Segoe UI", 8, "italic"), foreground="gray")
        self.label_scan_timer.pack(pady=(0, 3), anchor="w")

        # --- Remuxing Frame ---
        self.frame_progress = ttk.LabelFrame(self.remuxer_tab, text="Step 2: Processing Files", padding=(15, 8))
        # Don't pack initially - will be shown after scan is complete

        # --- Current Activity Section ---
        frame_current = ttk.LabelFrame(self.frame_progress, text="Current Activity", padding=(10, 5))
        frame_current.pack(padx=5, pady=(0, 10), fill="x")

        # Current file information in dedicated section
        self.label_current_file = ttk.Label(frame_current, text="Current file: None", font=("Segoe UI", 9, "bold"))
        self.label_current_file.pack(anchor="w", pady=2)

        # Overall progress
        self.label_total_progress = ttk.Label(self.frame_progress, text="Total Progress: 0/0")
        self.label_total_progress.pack(pady=(0, 3), anchor="w")
        self.progress_bar_total = ttk.Progressbar(self.frame_progress, orient="horizontal", mode="determinate")
        self.progress_bar_total.pack(fill="x", pady=3)

        # Current file information moved to status area

        self.label_status = ttk.Label(self.frame_progress, text="Ready")
        self.label_status.pack(pady=5)

        # Parallel processing status (for future use)
        self.parallel_status_label = ttk.Label(self.frame_progress, text="")
        self.parallel_status_label.pack(pady=(3, 0))

        # Control buttons frame within Step 2
        frame_step2_buttons = ttk.Frame(self.frame_progress)
        frame_step2_buttons.pack(pady=(10, 0))

        # Create control buttons in Step 2 frame
        self.btn_pause = ttk.Button(frame_step2_buttons, text="Pause", command=self.toggle_pause, state=self.UI_STATE_DISABLED)
        self.btn_skip = ttk.Button(frame_step2_buttons, text="Skip Current", command=self.skip_current_file, state=self.UI_STATE_DISABLED)
        self.btn_cancel = ttk.Button(frame_step2_buttons, text="Cancel", command=self.cancel_processing, state=self.UI_STATE_DISABLED)
        self.btn_start_remux = ttk.Button(frame_step2_buttons, text="Start Remux", command=self.start_remux_thread, state=self.UI_STATE_DISABLED)

        # Pack control buttons in Step 2 frame (Start Remux on the left)
        # Don't pack buttons initially - they will be packed after scan is complete

        # --- Control Buttons Frame ---
        frame_buttons = ttk.Frame(self.remuxer_tab)
        frame_buttons.pack(pady=10)
        self.btn_run = ttk.Button(frame_buttons, text="Scan Files", command=self.handle_run_click, state=self.UI_STATE_DISABLED)
        self.btn_run.pack(side="left", padx=5)

        # Auto-start remux button on the right
        self.auto_start_checkbox = ttk.Checkbutton(frame_buttons, text="Auto-start Remux", variable=self.auto_start_remux)
        self.auto_start_checkbox.pack(side="right", padx=15)

        # Start Remux button will be created in Step 2 frame after scan

        # --- Control Buttons in Step 2 Frame (hidden initially) ---
        # These will be created after frame_step2_buttons is created

        # Log output moved to its own tab

    def create_settings_widgets(self):
        # --- Output Format ---
        frame_output_format = ttk.LabelFrame(self.settings_tab, text="Output Format", padding=(10, 5))
        frame_output_format.pack(padx=10, pady=5, fill="x")
        format_frame = ttk.Frame(frame_output_format)
        format_frame.pack(fill="x")
        ttk.Label(format_frame, text="Output format:").pack(side="left")
        format_combo = ttk.Combobox(format_frame, textvariable=self.output_format_var, state="readonly", width=8)
        format_combo["values"] = self.supported_formats['output']
        format_combo.pack(side="left", padx=(5, 0))
        ttk.Button(format_frame, text="?", width=2, command=self.show_output_format_info).pack(side="left", padx=(5, 0))

        # --- File Management ---
        frame_file_options = ttk.LabelFrame(self.settings_tab, text="Original File Management", padding=(10, 5))
        frame_file_options.pack(padx=10, pady=5, fill="x")

        file_options_frame = ttk.Frame(frame_file_options)
        file_options_frame.pack(fill="x")
        ttk.Radiobutton(file_options_frame, text="Move original to subfolder (default)", variable=self.file_action_var, value=self.FILE_ACTION_MOVE).pack(anchor="w")
        ttk.Radiobutton(file_options_frame, text="Keep original file in place", variable=self.file_action_var, value=self.FILE_ACTION_KEEP).pack(anchor="w")

        delete_frame = ttk.Frame(frame_file_options)
        delete_frame.pack(anchor="w")
        ttk.Radiobutton(delete_frame, text="Delete original file", variable=self.file_action_var, value=self.FILE_ACTION_DELETE).pack(side="left")
        ttk.Label(delete_frame, text="(Not recommended)", foreground="red", font=("Segoe UI", 8)).pack(side="left", padx=(5, 0))
        ttk.Button(delete_frame, text="?", width=2, command=self.show_file_management_info).pack(side="left", padx=(5, 0))

        # --- Processing Options ---
        frame_processing = ttk.LabelFrame(self.settings_tab, text="Processing Options", padding=(10, 5))
        frame_processing.pack(padx=10, pady=5, fill="x")
        
        # Audio options container (always packed, but contents change visibility)
        audio_container = ttk.Frame(frame_processing)
        audio_container.pack(fill="x", pady=2)
        
        audio_frame = ttk.Frame(audio_container)
        audio_frame.pack(fill="x")
        self.audio_checkbox = ttk.Checkbutton(audio_frame, text="Include Audio Streams", variable=self.include_audio)
        self.audio_checkbox.pack(side="left")
        ttk.Button(audio_frame, text="?", width=2, command=self.show_audio_info).pack(side="left", padx=(5, 0))
        
        # Audio options are now handled automatically - all audio tracks are mapped by default
        # when audio is included, making it simpler for users
        
        # Other processing options
        timestamp_frame = ttk.Frame(frame_processing)
        timestamp_frame.pack(fill="x")
        ttk.Checkbutton(timestamp_frame, text="Preserve original file timestamps", variable=self.preserve_timestamps_var).pack(side="left")
        ttk.Button(timestamp_frame, text="?", width=2, command=self.show_timestamp_info).pack(side="left", padx=(5, 0))

        overwrite_frame = ttk.Frame(frame_processing)
        overwrite_frame.pack(fill="x")
        ttk.Checkbutton(overwrite_frame, text="Overwrite existing output files", variable=self.overwrite_existing_var).pack(side="left")
        ttk.Button(overwrite_frame, text="?", width=2, command=self.show_overwrite_info).pack(side="left", padx=(5, 0))

        # --- Advanced Processing Options ---
        frame_advanced_options = ttk.LabelFrame(self.settings_tab, text="Advanced Processing Options", padding=(10, 5))
        frame_advanced_options.pack(padx=10, pady=5, fill="x")

        # File validation option
        validate_frame = ttk.Frame(frame_advanced_options)
        validate_frame.pack(fill="x")
        ttk.Checkbutton(validate_frame, text="Validate files before processing", variable=self.validate_files_var).pack(side="left")
        ttk.Button(validate_frame, text="?", width=2, command=self.show_validation_info).pack(side="left", padx=(5, 0))

        # Command preview option
        preview_frame = ttk.Frame(frame_advanced_options)
        preview_frame.pack(fill="x")
        ttk.Checkbutton(preview_frame, text="Show command preview before remuxing", variable=self.preview_commands_var).pack(side="left")
        ttk.Button(preview_frame, text="?", width=2, command=self.show_preview_info).pack(side="left", padx=(5, 0))


        # --- Video Timescale (VFR fix) ---
        self.fps_frame = ttk.LabelFrame(self.settings_tab, text="Video Timescale (VFR Fix)", padding=(10, 5))
        self.fps_frame.pack(padx=10, pady=5, fill="x")
        fps_header_frame = ttk.Frame(self.fps_frame)
        fps_header_frame.pack(anchor="w")
        ttk.Checkbutton(fps_header_frame, text="Set video timescale", variable=self.use_timescale_option, command=self.toggle_timescale_selector).pack(side="left")
        ttk.Button(fps_header_frame, text="?", width=2, command=self.show_timescale_info).pack(side="left", padx=(5, 0))
        
        self.timescale_options_container = ttk.Frame(self.fps_frame)
        self.timescale_is_source.trace_add("write", self.on_timescale_option_change)
        ttk.Radiobutton(self.timescale_options_container, text="Use original video's frame rate (scanned)", variable=self.timescale_is_source, value=True).pack(anchor="w", pady=2)
        
        preset_frame = ttk.Frame(self.timescale_options_container)
        preset_frame.pack(fill="x", padx=20)
        ttk.Radiobutton(preset_frame, text="Force preset timescale:", variable=self.timescale_is_source, value=False).pack(side="left")
        self.timescale_combobox = ttk.Combobox(preset_frame, textvariable=self.timescale_preset_var, state=self.UI_STATE_DISABLED, width=7)
        self.timescale_combobox["values"] = ("23.976", "24", "25", "29.97", "30", "50", "59.94", "60", "90", "120", "144", "Custom")
        self.timescale_combobox.set("24")
        self.timescale_combobox.pack(side="left", padx=(5, 10))
        self.timescale_combobox.bind("<<ComboboxSelected>>", self.check_custom_timescale)
        self.custom_timescale_entry = ttk.Entry(preset_frame, textvariable=self.timescale_custom_var, width=7, state=self.UI_STATE_DISABLED)
        self.custom_timescale_entry.pack(side="left", padx=(5, 0))

        # Settings management buttons after VFR section
        settings_buttons_frame = ttk.Frame(self.settings_tab)
        settings_buttons_frame.pack(fill="x", pady=(10, 0))

        # Center the button
        settings_buttons_frame.grid_columnconfigure(0, weight=1)
        settings_buttons_frame.grid_columnconfigure(2, weight=1)

        ttk.Button(settings_buttons_frame, text="Restore Defaults", command=self.restore_defaults).grid(row=0, column=1)


    def create_logs_widgets(self):
        """Create the logs tab with log output display."""
        # --- Log Output Frame ---
        self.log_frame = ttk.LabelFrame(self.logs_tab, text="Log Output", padding=(15, 8))
        self.log_frame.pack(padx=10, pady=5, fill="both", expand=True)

        # Button frame for log controls
        log_button_frame = ttk.Frame(self.log_frame)
        log_button_frame.pack(fill="x", pady=(0, 8))
        ttk.Button(log_button_frame, text="Copy Log", command=self.copy_log_to_clipboard).pack(side="right")
        ttk.Button(log_button_frame, text="Clear Log", command=self.clear_log).pack(side="right", padx=(10, 0))

        self.log_text = tk.Text(self.log_frame, height=self.LOG_TEXT_HEIGHT, wrap="word", state="disabled", bg="black", fg="white", font=("Courier New", 9))
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text["yscrollcommand"] = scrollbar.set

    def clear_log(self):
        """Clear the log output."""
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.config(state="disabled")

    # =============================================================================
    # FFMPEG COMMAND BUILDING
    # =============================================================================
    # Generate FFmpeg commands for video remuxing with proper parameters
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
            if settings["timescale_is_source"]:
                scan_result = settings["scan_results"].get(video_file_path, {})
                timescale = scan_result.get('fps')
                if not timescale:
                    self.process_queue.put(("LOG", f"Warning: No FPS found for {file_name}, timescale option skipped."))
            else:  # Use preset
                preset = settings["timescale_preset"]
                timescale = settings["timescale_custom"] if preset == "Custom" else preset

            if timescale:
                try:
                    float(timescale)
                    command.extend(["-video_track_timescale", str(timescale)])
                except ValueError:
                    self.process_queue.put(("LOG", f"Warning: Invalid timescale '{timescale}', skipping option."))

        command.append(output_file_path)

        return command, output_file_path

    # =============================================================================
    # FILE PROCESSING METHODS
    # =============================================================================
    # Execute FFmpeg processes and handle file operations during remuxing
    def execute_ffmpeg_process(self, command, output_file_path, file_name, duration, settings):
        """Execute FFmpeg process with real-time output reading to prevent freezing."""
        try:
            self.process_queue.put(("LOG", f""))
            self.process_queue.put(("LOG", f"{'='*60}"))
            self.process_queue.put(("LOG", f"[PROCESSING] {file_name}"))
            self.process_queue.put(("LOG", f"{'='*60}"))

            # Run the command with real-time output reading
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stdout and stderr
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )

            # Read output line by line to prevent freezing
            while True:
                if self.cancel_event.is_set():
                    process.terminate()
                    try:
                        if os.path.exists(output_file_path):
                            os.remove(output_file_path)
                    except Exception:
                        pass
                    return "cancelled"

                if self.skip_event.is_set():
                    self.process_queue.put(("LOG", f"[SKIP] Skipping file: {file_name}"))
                    process.terminate()
                    try:
                        if os.path.exists(output_file_path):
                            os.remove(output_file_path)
                    except Exception:
                        pass

                    # Skip file without moving original file to Remuxed folder
                    self.process_queue.put(("LOG", f"   [FILE] Original file left in place (skipped)"))
                    self.process_queue.put(("LOG", f"{'='*60}"))
                    self.process_queue.put(("LOG", f""))
                    return "skipped"

                # Check for pause event - this makes pause responsive during file processing
                if not self.pause_event.is_set():
                    # Pause requested - wait for resume or other events
                    while not self.pause_event.is_set() and not self.cancel_event.is_set() and not self.skip_event.is_set():
                        time.sleep(0.1)  # Small delay to prevent busy waiting

                    # If cancelled or skipped while paused, handle accordingly
                    if self.cancel_event.is_set():
                        process.terminate()
                        try:
                            if os.path.exists(output_file_path):
                                os.remove(output_file_path)
                        except Exception:
                            pass
                        return "cancelled"

                    if self.skip_event.is_set():
                        self.process_queue.put(("LOG", f"[SKIP] Skipping file: {file_name}"))
                        process.terminate()
                        try:
                            if os.path.exists(output_file_path):
                                os.remove(output_file_path)
                        except Exception:
                            pass
    
                        # Skip file without moving original file to Remuxed folder
                        self.process_queue.put(("LOG", f"   [FILE] Original file left in place (skipped)"))
                        self.process_queue.put(("LOG", f"{'='*60}"))
                        self.process_queue.put(("LOG", f""))
                        return "skipped"

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
                        if any(keyword in stripped_output for keyword in ['time=', 'frame=', 'size=', 'fps=', 'bitrate=']):
                            # Use a counter to reduce logging frequency (log every 3rd message)
                            if not hasattr(self, 'log_counter'):
                                self.log_counter = 0
                            self.log_counter += 1

                            if self.log_counter % 3 == 0:  # Log every 3rd progress message
                                self.process_queue.put(("LOG", f"   {stripped_output}"))

            # Wait for process to complete
            process.wait()

            if self.cancel_event.is_set():
                try:
                    if os.path.exists(output_file_path):
                        os.remove(output_file_path)
                except Exception:
                    pass
                return "cancelled"

            if process.returncode == 0:
                self.process_queue.put(("LOG", f""))
                self.process_queue.put(("LOG", f"   [SUCCESS] Remuxed successfully"))

                # Preserve original file timestamps if option is enabled
                if settings.get("preserve_timestamps", False):
                    # Derive video_file_path from output_file_path and file_name
                    video_file_path = os.path.join(os.path.dirname(output_file_path), file_name)
                    if self.preserve_file_timestamps(video_file_path, output_file_path):
                        self.process_queue.put(("LOG", f"   [TIMESTAMP] Timestamps preserved"))
                    else:
                        self.process_queue.put(("LOG", f"   [WARNING] Failed to preserve timestamps"))

                # Handle original file
                self.handle_original_file(file_name, output_file_path, settings)
                self.process_queue.put(("LOG", f"{'='*60}"))
                self.process_queue.put(("LOG", f""))
                return "completed"
            else:
                self.process_queue.put(("LOG", f"[ERROR] Failed remuxing {file_name}. Return code: {process.returncode}"))
                self.process_queue.put(("LOG", f"{'='*60}"))
                self.process_queue.put(("LOG", f""))
                return "error"

        except Exception as e:
            self.process_queue.put(("LOG", f"[CRITICAL] ERROR on {file_name}: {e}"))
            self.process_queue.put(("LOG", f"{'='*60}"))
            self.process_queue.put(("LOG", f""))
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
            if action == self.FILE_ACTION_MOVE:
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
                    self.process_queue.put(("LOG", f"   [FILE] Moved original to {original_ext}s folder"))
                else:
                    self.process_queue.put(("LOG", f"   [WARNING] Could not find source directory for {file_name}"))
            elif action == self.FILE_ACTION_DELETE:
                # Find the source directory for deletion
                source_dir = None
                for file_path in settings.get("files", []):
                    if os.path.basename(file_path) == file_name:
                        source_dir = os.path.dirname(file_path)
                        break

                if source_dir:
                    os.remove(os.path.join(source_dir, file_name))
                    self.process_queue.put(("LOG", f"   [DELETE] Deleted original file"))
                else:
                    self.process_queue.put(("LOG", f"   [WARNING] Could not find source directory for {file_name}"))
        except Exception as e:
            self.process_queue.put(("LOG", f"   [WARNING] Failed to handle original file: {str(e)}"))


    def get_audio_track_info(self, file_path):
        """Get information about audio tracks in the file."""
        try:
            command = [self.ffprobe_path, "-v", "error", "-select_streams", "a",
                       "-show_entries", "stream=index,codec_name,channels,language",
                       "-of", "csv=p=0", file_path]

            result = subprocess.run(command, capture_output=True, text=True, timeout=self.FFPROBE_TIMEOUT,
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

    # =============================================================================
    # UTILITY METHODS
    # =============================================================================
    # Provide helper functions for various operations like tool detection,
    # file validation, and resource path handling

    # ---------- Utility & Process Functions ----------

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
        # Create custom dialog
        dialog = tk.Toplevel(self)
        dialog.title("Missing Required Tools")
        dialog.geometry("450x250")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        # Set custom window icon for dialog
        try:
            icon_path = self.get_resource_path("ICOtrans.ico")
            try:
                dialog.iconbitmap(icon_path)
            except Exception:
                try:
                    from PIL import Image, ImageTk
                    icon = Image.open(icon_path)
                    icon = ImageTk.PhotoImage(icon)
                    dialog.iconphoto(True, icon)
                except Exception:
                    try:
                        icon = tk.PhotoImage(file=icon_path)
                        dialog.iconphoto(True, icon)
                    except Exception:
                        pass
        except Exception:
            pass

        # Center the dialog
        dialog.geometry("+%d+%d" % (self.winfo_rootx() + self.winfo_width()//2 - 225,
                                    self.winfo_rooty() + self.winfo_height()//2 - 125))

        # Main frame
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill="both", expand=True)

        # Missing tools message
        missing_tools = []
        if not self.ffmpeg_path:
            missing_tools.append("ffmpeg")
        if not self.ffprobe_path:
            missing_tools.append("ffprobe")

        tools_text = " and ".join(missing_tools)

        message_label = ttk.Label(main_frame,
                                 text=f"The following required tools are not found:\n\n{tools_text}\n\n"
                                      "Please ensure they are either:\n"
                                      "• In the same directory as this application, or\n"
                                      "• Available in your system PATH\n\n"
                                      "After adding the files, click 'Retry' to continue.",
                                 justify="left", wraplength=400)
        message_label.pack(pady=(0, 20))

        def retry_check():
            """Re-check for the missing tools."""
            self.ffmpeg_path = self.find_ffmpeg_path()
            self.ffprobe_path = self.find_ffprobe_path()

            if self.ffmpeg_path and self.ffprobe_path:
                # Both tools found, close dialog and continue initialization
                dialog.destroy()
                self.continue_initialization()
            else:
                # Still missing, show error message
                messagebox.showerror("Still Missing",
                                   "The required tools are still not found.\n\n"
                                   "Please ensure ffmpeg and ffprobe are properly installed\n"
                                   "and accessible before retrying.")

        def exit_application():
            """Exit the application."""
            dialog.destroy()
            self.destroy()

        # Button container frame
        button_container = ttk.Frame(main_frame)
        button_container.pack(pady=(20, 0))

        # Center the buttons horizontally
        button_container.grid_columnconfigure(0, weight=1)
        button_container.grid_columnconfigure(2, weight=1)

        # Retry button
        retry_btn = ttk.Button(button_container, text="Retry", command=retry_check)
        retry_btn.grid(row=0, column=1, padx=(0, 10))

        # Exit button
        exit_btn = ttk.Button(button_container, text="Exit", command=exit_application)
        exit_btn.grid(row=0, column=2)

        # Set focus on retry button by default
        retry_btn.focus()

        # Handle Enter key
        dialog.bind('<Return>', lambda e: retry_check())
        dialog.bind('<Escape>', lambda e: exit_application())

        # Handle window close button (X)
        dialog.protocol("WM_DELETE_WINDOW", exit_application)

    def continue_initialization(self):
        """Continue with the normal application initialization after tools are found."""
        # This method will be called after successful retry to continue __init__
        # Re-initialize the paths (they should now be found)
        self.ffmpeg_path = self.find_ffmpeg_path()
        self.ffprobe_path = self.find_ffprobe_path()

        # Continue with the rest of the initialization that was skipped
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

        # --- Supported formats ---
        self.supported_formats = {
            'input': ['.mkv'],
            'output': ['.mp4', '.mov']
        }

        # --- Settings Variables ---
        self.use_timescale_option = tk.BooleanVar(value=True)
        self.timescale_is_source = tk.BooleanVar(value=True)
        self.timescale_preset_var = tk.StringVar(value=self.DEFAULT_TIMESCALE)
        self.timescale_custom_var = tk.StringVar(value="")
        self.auto_start_remux = tk.BooleanVar(value=True)
        self.include_audio = tk.BooleanVar(value=True)
        self.file_action_var = tk.StringVar(value=self.FILE_ACTION_MOVE)
        self.output_format_var = tk.StringVar(value=".mp4")
        self.validate_files_var = tk.BooleanVar(value=True)
        self.preserve_timestamps_var = tk.BooleanVar(value=True)
        self.preview_commands_var = tk.BooleanVar(value=False)
        self.overwrite_existing_var = tk.BooleanVar(value=False)

        # --- Settings State ---
        self.settings_disabled = False

        # Create widgets and continue with normal initialization
        self.create_widgets()
        self.after(self.PROGRESS_UPDATE_INTERVAL, self.check_queue)

        # Remove focus from all existing widgets
        self.remove_focus_from_all_widgets()

        # Specifically configure notebook tabs
        self.configure_notebook_tabs()

        # Apply tab styling after a short delay to ensure tabs are created
        self.after(100, self.apply_tab_styling)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Load saved settings FIRST
        self.load_settings()

        # Add auto-save traces to all settings variables AFTER loading
        self.auto_start_remux.trace_add("write", lambda *args: self.auto_save_settings())
        self.include_audio.trace_add("write", lambda *args: self.auto_save_settings())
        self.file_action_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.output_format_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.validate_files_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.preserve_timestamps_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.preview_commands_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.overwrite_existing_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.use_timescale_option.trace_add("write", lambda *args: self.auto_save_settings())
        self.timescale_is_source.trace_add("write", lambda *args: self.auto_save_settings())
        self.timescale_preset_var.trace_add("write", lambda *args: self.auto_save_settings())
        self.timescale_custom_var.trace_add("write", lambda *args: self.auto_save_settings())

        # Ensure timescale options are properly initialized on startup
        if self.use_timescale_option.get():
            self.toggle_timescale_selector()

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
                self._log_icon_warning(f"Icon file not found: {icon_path}")
                return

            # Try platform-optimized methods first
            if self._set_icon_windows(icon_path):
                return
            if self._set_icon_pil(icon_path):
                return
            if self._set_icon_tkinter(icon_path):
                return

            self._log_icon_warning(f"Failed to set icon: {icon_path}")

        except Exception as e:
            self._log_icon_warning(f"Error setting icon: {e}")

    def _set_icon_windows(self, icon_path):
        """Try Windows-specific iconbitmap method."""
        if sys.platform == "win32":
            try:
                self.iconbitmap(icon_path)
                return True
            except (tk.TclError, OSError):
                pass
        return False

    def _set_icon_pil(self, icon_path):
        """Try PIL-based icon setting with size optimization."""
        try:
            from PIL import Image, ImageTk
            with Image.open(icon_path) as img:
                # Optimize icon size for better compatibility
                if max(img.size) > 256:
                    img = img.resize((256, 256), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            self.iconphoto(True, photo)
            return True
        except Exception:
            return False

    def _set_icon_tkinter(self, icon_path):
        """Try basic Tkinter PhotoImage method."""
        try:
            photo = tk.PhotoImage(file=icon_path)
            self.iconphoto(True, photo)
            return True
        except tk.TclError:
            return False

    def _log_icon_warning(self, message):
        """Log icon-related warnings using proper logging."""
        import logging
        logging.warning(message)

    def validate_video_file(self, file_path):
        """Validate that a file is a readable video file using ffprobe."""
        try:
            command = [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "stream=codec_name", "-of",
                       "default=noprint_wrappers=1:nokey=1", file_path]

            result = subprocess.run(command, capture_output=True, text=True, timeout=self.FFPROBE_TIMEOUT,
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

            result = subprocess.run(command, capture_output=True, text=True, timeout=self.FFPROBE_TIMEOUT,
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

    # =============================================================================
    # QUEUE PROCESSING
    # =============================================================================
    # Handle message processing from worker threads and update UI components
    # with progress information, status updates, and completion notifications

    def check_queue(self):
        """Process messages from the worker threads and update the UI accordingly.

        Limits processing to prevent UI blocking by processing only a few messages
        per iteration, then scheduling the next check.
        """
        try:
            # Process up to MAX_QUEUE_MESSAGES_PER_UPDATE messages per iteration to prevent UI blocking
            for _ in range(self.MAX_QUEUE_MESSAGES_PER_UPDATE):
                message = self.process_queue.get_nowait()
                msg_type, data = message

                # --- Scan Messages ---
                if msg_type == "SCAN_PROGRESS":
                    self.progress_bar_scan["value"] = data['percent']
                    self.label_scan_progress.config(text=f"Scanning: {data['current']}/{data['total']}")

                    # Update scan timer if scanning is in progress
                    if self.scan_start_time:
                        elapsed_seconds = int(time.time() - self.scan_start_time)
                        hours, remainder = divmod(elapsed_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if hours > 0:
                            timer_text = f"Elapsed: {hours:02d}:{minutes:02d}:{seconds:02d}"
                        else:
                            timer_text = f"Elapsed: {minutes:02d}:{seconds:02d}"
                        self.label_scan_timer.config(text=timer_text)
                elif msg_type == "SCAN_COMPLETE":
                    self.scan_results = data['results']
                    self.is_scanned = True
                    valid_files = sum(1 for v in data['results'].values() if v.get('valid', True))
                    total_files = len(data['results'])

                    # Calculate final scan elapsed time
                    final_elapsed_time = None
                    if self.scan_start_time:
                        elapsed_seconds = int(time.time() - self.scan_start_time)
                        hours, remainder = divmod(elapsed_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if hours > 0:
                            final_elapsed_time = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        else:
                            final_elapsed_time = f"{minutes:02d}:{seconds:02d}"
                        self.scan_start_time = None  # Reset timer

                    # Update Step 1 with scan results and hide progress bar
                    if valid_files == total_files:
                        self.label_scan_progress.config(text=f"✓ {valid_files}/{total_files} files ready to remux")
                    else:
                        self.label_scan_progress.config(text=f"⚠ {valid_files}/{total_files} files ready to remux")

                    # Show final elapsed time under the files ready message
                    if final_elapsed_time:
                        self.label_scan_timer.config(text=f"Scan completed in {final_elapsed_time}")

                    # Hide progress bar but keep the frame visible with results
                    self.progress_bar_scan.pack_forget()

                    # Show Step 2 frame after scan is complete
                    self.frame_progress.pack(padx=10, pady=5, fill="x")

                    # Update Step 2 frame title to show current step
                    self.frame_progress.config(text="Step 2: Processing Files")

                    # Control buttons are already packed in Step 2 frame, just enable Start Remux button
                    # Pause and Skip buttons remain disabled until remux starts
                    self.btn_cancel.config(state="normal")
                    self.btn_start_remux.config(state="normal")

                    # Make sure Start Remux button is visible and positioned correctly (leftmost)
                    # Pack buttons in the correct visual order: Start Remux, Pause, Skip, Cancel
                    self.btn_start_remux.pack(side="left", padx=5)
                    self.btn_pause.pack(side="left", padx=5)
                    self.btn_skip.pack(side="left", padx=5)
                    self.btn_cancel.pack(side="left", padx=5)

                    # Auto-start remuxing if option was enabled
                    if self.auto_start_remux.get():
                        # Start remuxing after 1 second delay (buttons are already positioned correctly)
                        self.after(1000, lambda: self.start_remux_thread(auto_start=True))

                    # Hide Scan Files button (no Start Remux button in bottom frame anymore)
                    self.btn_run.pack_forget()
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", f"Scan complete. Ready to remux.\n")
                    self.log_text.config(state="disabled")

                    # Re-enable source and output buttons after scan completes
                    self.btn_browse_folder.config(state="normal")
                    self.btn_browse_files.config(state="normal")
                    self.btn_browse_output.config(state="normal")
                    self.btn_clear_output.config(state="normal")
                
                # --- Remux Messages ---
                elif msg_type == "LOG":
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", data + "\n")
                    self.log_text.config(state="disabled")
                    self.log_text.see("end")
                elif msg_type == "STATUS":
                    self.label_status.config(text=data)
                elif msg_type == "PROGRESS":
                    self.progress_bar_total["value"] = data['total_percent']
                    self.label_total_progress.config(text=f"Total Progress: {data['current']}/{data['total']}")
                elif msg_type == "PARALLEL_STATUS":
                    self.parallel_status_label.config(text=data)
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

                    # Update Step 2 frame title to show completion
                    self.frame_progress.config(text="Step 2: Processing Complete")

                    # Update the total progress label to show final count in same style as scan results
                    total_processed = data['remuxed'] + data['skipped']
                    total_files = len(self.files_to_process)
                    if data['remuxed'] == total_files:
                        self.label_total_progress.config(text=f"✓ {data['remuxed']}/{total_files} files remuxed")
                    else:
                        self.label_total_progress.config(text=f"✓ {data['remuxed']}/{total_files} files remuxed")

                    # Clear current activity labels since processing is complete
                    self.label_current_file.config(text="Current file: None")
                    self.label_status.config(text="Complete")

                    # Reset button state before showing completion dialog
                    self.btn_run.config(state=self.UI_STATE_NORMAL, text="Scan Files")

                    # Re-enable source and output buttons after remuxing completes
                    self.btn_browse_folder.config(state="normal")
                    self.btn_browse_files.config(state="normal")
                    self.btn_browse_output.config(state="normal")
                    self.btn_clear_output.config(state="normal")

                    self.log_text.config(state="normal")
                    self.log_text.insert("end", f"Remux process completed successfully for all files.\n")
                    self.log_text.config(state="disabled")
                    self.show_completion_dialog(final_msg, data, elapsed_time)

        except queue.Empty:
            pass
        self.after(self.PROGRESS_UPDATE_INTERVAL, self.check_queue)

    # =============================================================================
    # UI STATE MANAGEMENT
    # =============================================================================
    # Manage application UI state transitions, button states, and interface updates
    # during different phases of operation (scanning, processing, idle)

    def reset_scan_state(self):
        """Reset the application to a pre-scan state when new files are selected.

        This method clears scan results and resets all progress indicators
        to their initial state, preparing the UI for a new scan operation.
        """
        self.is_scanned = False
        self.scan_results = {}
        self.scan_start_time = None  # Reset scan timer

        # Hide Step 2 frame and show Step 1 frame when resetting scan state
        try:
            self.frame_progress.pack_info()
            self.frame_progress.pack_forget()
        except:
            pass  # Frame is not currently packed, nothing to do

        # Show Step 1 frame
        self.frame_scan.pack(padx=10, pady=(5, 0), fill="x")

        # Show Auto-start Remux checkbox again
        self.auto_start_checkbox.pack(side="right", padx=15)

        # Disable control buttons when resetting scan state
        self.btn_pause.config(state=self.UI_STATE_DISABLED)
        self.btn_skip.config(state=self.UI_STATE_DISABLED)
        self.btn_cancel.config(state=self.UI_STATE_DISABLED)

        # Restore Scan Files button and hide Start Remux button
        self.btn_start_remux.pack_forget()
        self.btn_run.pack(side="left", padx=5)

        # Make sure all control buttons are properly unpacked to prevent positioning issues
        self.btn_pause.pack_forget()
        self.btn_skip.pack_forget()
        self.btn_cancel.pack_forget()

        self.btn_run.config(text="Scan Files", state=self.UI_STATE_NORMAL if self.files_to_process else self.UI_STATE_DISABLED)
        self.progress_bar_scan["value"] = 0
        self.progress_bar_total["value"] = 0
        self.label_scan_progress.config(text="Ready to scan.")
        self.label_total_progress.config(text="Total Progress: 0/0")
        self.label_current_file.config(text="Current file: None")

        # Clear timer display
        self.label_scan_timer.config(text="")

        # Restore progress bar for next scan
        self.progress_bar_scan.pack(fill="x", pady=3)

        # Re-enable source and output buttons when resetting scan state
        self.btn_browse_folder.config(state="normal")
        self.btn_browse_files.config(state="normal")
        self.btn_browse_output.config(state="normal")
        self.btn_clear_output.config(state="normal")

        # Ensure settings are enabled after scan reset
        if not self.settings_disabled:
            self.enable_settings_controls()

    def is_remuxer_running(self):
        """Check if the remuxer is currently running (scanning or remuxing)."""
        return self.btn_run.cget("text") in ["Scanning...", "Processing..."]

    def disable_settings_controls(self):
        """Disable all settings controls when remuxer is running to prevent changes."""
        # Disable notebook tabs to prevent switching
        self.notebook.tab(self.settings_tab, state="disabled")

        # Store current state for restoration
        self.settings_disabled = True

    def enable_settings_controls(self):
        """Re-enable all settings controls when remuxer stops."""
        # Re-enable notebook tabs
        self.notebook.tab(self.settings_tab, state="normal")

        # Clear the disabled flag
        self.settings_disabled = False

    def reset_ui_after_processing(self):
        """Reset the UI to its initial state after processing is complete.

        This method disables all processing controls, clears the file list,
        and resets the UI to prepare for a new operation.
        """
        self.btn_run.config(state=self.UI_STATE_NORMAL, text="Scan Files")
        self.btn_pause.config(state=self.UI_STATE_DISABLED, text="Pause")
        self.btn_skip.config(state=self.UI_STATE_DISABLED)
        self.btn_cancel.config(state=self.UI_STATE_DISABLED)
        self.btn_start_remux.config(state=self.UI_STATE_DISABLED, text="Start Remux")

        # Restore Scan Files button and hide Start Remux button
        self.btn_start_remux.pack_forget()
        self.btn_run.pack(side="left", padx=5)

        # Make sure all control buttons are properly unpacked to prevent positioning issues
        self.btn_pause.pack_forget()
        self.btn_skip.pack_forget()
        self.btn_cancel.pack_forget()

        # Show Step 1 frame and hide Step 2 frame
        self.frame_scan.pack(padx=10, pady=(5, 0), fill="x")
        self.frame_progress.pack_forget()

        # Show Auto-start Remux checkbox again
        self.auto_start_checkbox.pack(side="right", padx=15)
        self.is_scanned = False
        with self.process_lock:
            self.current_process = None
        self.files_to_process = []
        self.label_input_path.config(text="No folder or files selected")
        self.parallel_status_label.config(text="")
        self.label_status.config(text="Ready")

        # Reset output directory display
        self.output_directory = ""
        self.selected_output_directory = ""
        self.label_output_path.config(text="Same as source")

        self.reset_scan_state()
        self.enable_settings_controls()

    # =============================================================================
    # USER ACTION HANDLERS
    # =============================================================================
    # Handle user interactions with the GUI including file browsing, processing
    # controls, and application lifecycle management

    # ---------- User Actions ----------
    def browse_input_folder(self):
        """Open a directory dialog and select all supported video files from the chosen directory.

        This method scans the selected directory for files with supported input formats,
        counts files by format, and updates the UI to show the selection summary.
        """
        directory = filedialog.askdirectory()
        if directory:
            # Consistent case handling for extensions
            supported_extensions = [ext.lower() for ext in self.supported_formats['input']]
            self.files_to_process = [
                os.path.join(directory, f)
                for f in os.listdir(directory)
                if any(f.lower().endswith(ext) for ext in supported_extensions)
            ]
            format_counts = {}
            for file in self.files_to_process:
                ext = os.path.splitext(file)[1].lower()
                format_counts[ext] = format_counts.get(ext, 0) + 1

            self.label_input_path.config(text=f"{len(self.files_to_process)} files selected")
            self.reset_scan_state()

    def show_preview_dialog(self, auto_start=False):
        """Show preview of commands that would be executed."""
        if not self.files_to_process:
            messagebox.showwarning("No Files", "Please select files first.")
            return

        if not self.is_scanned:
            messagebox.showwarning("Not Scanned", "Please scan files first before previewing commands.")
            return

        self.preview_window = tk.Toplevel(self)
        self.preview_window.title("Command Preview")
        self.preview_window.geometry("800x500")

        # Set custom window icon for preview window
        try:
            # Try multiple methods for maximum compatibility
            icon_path = self.get_resource_path("ICOtrans.ico")

            # Method 1: Use iconbitmap (works best on Windows)
            try:
                self.preview_window.iconbitmap(icon_path)
            except Exception:
                # Method 2: Use iconphoto as fallback
                try:
                    from PIL import Image, ImageTk
                    icon = Image.open(icon_path)
                    icon = ImageTk.PhotoImage(icon)
                    self.preview_window.iconphoto(True, icon)
                except Exception:
                    # Method 3: Use default Tkinter PhotoImage
                    try:
                        icon = tk.PhotoImage(file=icon_path)
                        self.preview_window.iconphoto(True, icon)
                    except Exception:
                        print(f"Warning: Could not load custom icon for preview window: {icon_path}")

        except Exception as e:
            print(f"Warning: Could not load custom icon for preview window: {e}")

        # Center the preview window on screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - 800) // 2
        y = (screen_height - 500) // 2
        self.preview_window.geometry(f"+{x}+{y}")

        self.preview_window.transient(self)
        self.preview_window.grab_set()
        
        # Main frame
        main_frame = ttk.Frame(self.preview_window, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # Info label
        info_label = ttk.Label(main_frame, text=f"Preview of commands for {len(self.files_to_process)} files:")
        info_label.pack(anchor="w", pady=(0, 10))
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        text_widget = tk.Text(text_frame, wrap="word", font=("Courier New", 9))
        scrollbar = ttk.Scrollbar(text_frame, command=text_widget.yview)
        text_widget.config(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Generate and display commands
        commands = self.generate_preview_commands()
        for i, (input_file, command) in enumerate(commands, 1):
            filename = os.path.basename(input_file)
            text_widget.insert("end", f"{i}. {filename}\n")
            text_widget.insert("end", " ".join(command) + "\n\n")
        
        text_widget.config(state="disabled")
        
        # Button container frame
        button_container = ttk.Frame(main_frame)
        button_container.pack(pady=(10, 0))

        # Center the buttons horizontally
        button_container.grid_columnconfigure(0, weight=1)
        button_container.grid_columnconfigure(2, weight=1)

        # Start Remuxing button
        if auto_start:
            # Countdown variables
            self.countdown_seconds = 10
            self.countdown_active = True

            start_btn = ttk.Button(button_container, text=f"Start Remuxing (Auto-start in {self.countdown_seconds}s)",
                                  command=lambda: self.start_remuxing_from_preview(self.preview_window))
            start_btn.grid(row=0, column=1, padx=(0, 10))
            start_btn.configure(takefocus=0)

            # Countdown timer function
            def update_countdown():
                if not self.countdown_active or not self.preview_window.winfo_exists():
                    return

                self.countdown_seconds -= 1
                if self.countdown_seconds > 0:
                    start_btn.config(text=f"Start Remuxing (Auto-start in {self.countdown_seconds}s)")
                    # Schedule next update in 1 second
                    self.after(1000, update_countdown)
                else:
                    start_btn.config(text="Starting Remux...")
                    # Auto-start remuxing
                    if self.preview_window.winfo_exists():
                        self.start_remuxing_from_preview(self.preview_window)

            # Start countdown timer
            self.after(1000, update_countdown)  # Start updating after 1 second
        else:
            start_btn = ttk.Button(button_container, text="Start Remuxing",
                                  command=lambda: self.start_remuxing_from_preview(self.preview_window))
            start_btn.grid(row=0, column=1, padx=(0, 10))
            start_btn.configure(takefocus=0)

        # Close button
        close_btn = ttk.Button(button_container, text="Close", command=lambda: [setattr(self, 'countdown_active', False), self.preview_window.destroy()])
        close_btn.grid(row=0, column=2)
        close_btn.configure(takefocus=0)

        # Set focus on appropriate button by default
        if auto_start:
            close_btn.focus()  # Focus on close button when auto-start is enabled
        else:
            start_btn.focus()  # Focus on start button when manual start

    def generate_preview_commands(self):
        """Generate preview of all FFmpeg commands."""
        commands = []
        settings = {
            "output_dir": self.output_directory,
            "include_audio": self.include_audio.get(),
            "use_timescale": self.use_timescale_option.get(),
            "timescale_is_source": self.timescale_is_source.get(),
            "timescale_preset": self.timescale_preset_var.get(),
            "timescale_custom": self.timescale_custom_var.get(),
            "scan_results": self.scan_results,
        }

        for video_file_path in self.files_to_process:
            file_name = os.path.basename(video_file_path)
            file_name_no_ext = os.path.splitext(file_name)[0]
            output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
            output_file_path = os.path.join(output_dir_final, file_name_no_ext + self.output_format_var.get())

            command = [self.ffmpeg_path, "-y", "-i", video_file_path, "-c:v", "copy"]

            # Handle audio mapping
            if settings["include_audio"]:
                # Map all audio streams (simplified behavior)
                command.extend(["-map", "0:v", "-map", "0:a", "-c:a", "copy"])
            else:
                command.extend(["-an"])

            if settings["use_timescale"]:
                timescale = None
                if settings["timescale_is_source"]:
                    scan_result = settings["scan_results"].get(video_file_path, {})
                    timescale = scan_result.get('fps')
                else:
                    preset = settings["timescale_preset"]
                    timescale = settings["timescale_custom"] if preset == "Custom" else preset

                if timescale:
                    try:
                        float(timescale)
                        command.extend(["-video_track_timescale", str(timescale)])
                    except ValueError:
                        pass

            command.append(output_file_path)
            commands.append((video_file_path, command))

        return commands

    def browse_input_files(self):
        filetypes = [("All supported", " ".join([f"*{ext}" for ext in self.supported_formats['input']]))]
        filetypes.extend([(f"{ext.upper()} files", f"*{ext}") for ext in self.supported_formats['input']])
        files = filedialog.askopenfilenames(title="Select video files", filetypes=filetypes)
        if files:
            self.files_to_process = list(files)
            self.label_input_path.config(text=f"{len(self.files_to_process)} files selected")
            self.reset_scan_state()
            
    def browse_output_folder(self):
        directory = filedialog.askdirectory()
        if directory:
            self.output_directory = directory
            self.selected_output_directory = directory  # Track user selection
            # Force shortening for testing
            shortened = self.shorten_path(directory, 30)  # Very aggressive shortening
            self.label_output_path.config(text=shortened)
        else:
            self.output_directory = ""
            self.selected_output_directory = ""
            self.label_output_path.config(text="Same as source")

    def shorten_path(self, path, max_length=30):
        """Shorten a file path to fit within max_length characters."""
        if not path:
            return path

        if len(path) <= max_length:
            return path

        # Split the path into components (use / since Windows paths might use /)
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
        self.label_output_path.config(text="Same as source")

    def handle_run_click(self):
        """Handles the main button click, directing to scan or remux."""
        if not self.is_scanned:
            self.start_scan_thread()
        else:
            self.start_remux_thread()

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.config(text="Resume")
            self.process_queue.put(("LOG", "Paused."))
            self.process_queue.put(("STATUS", "Paused..."))
        else:
            self.pause_event.set()
            self.btn_pause.config(text="Pause")
            self.process_queue.put(("LOG", "Resumed."))
            self.process_queue.put(("STATUS", "Processing..."))

    def skip_current_file(self):
        """Skip the currently processing file."""
        # Set skip event - this will be handled by the processing thread
        self.skip_event.set()
        self.process_queue.put(("LOG", "Skipping current file..."))

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
        result = messagebox.askyesno("Cancel Processing",
                                   "Are you sure you want to cancel the current operation?\n\n" +
                                   "This will stop processing and reset the interface.")

        if result:  # User clicked Yes
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
            self.btn_browse_folder.config(state="normal")
            self.btn_browse_files.config(state="normal")
            self.btn_browse_output.config(state="normal")
            self.btn_clear_output.config(state="normal")
        else:  # User clicked No, restore previous state
            if not was_paused:
                self.pause_event.set()
                self.process_queue.put(("LOG", "Resumed after cancel dialog."))

    def on_closing(self):
        # Save settings before closing
        try:
            self.save_settings()
        except Exception as e:
            print(f"Failed to save settings on close: {e}")

        if self.btn_run['state'] == 'disabled':
            if messagebox.askyesno("Exit", "A process is running. Are you sure you want to exit?"):
                self.cancel_event.set()
                with self.process_lock:
                    if self.current_process:
                        try:
                            self.current_process.terminate()
                        except Exception:
                            pass
                self.destroy()
        else:
            # Check if we're in a post-completion state and need to reset
            if self.is_scanned and not self.files_to_process:
                # We're in a completed state, reset UI before closing
                self.reset_ui_after_processing()
            self.destroy()
# =============================================================================
# WORKER THREADS
# =============================================================================
# Handle background processing tasks including file scanning and remuxing
# operations using threading for non-blocking UI performance

# ---------- Worker Threads ----------

    def start_scan_thread(self):
        # Hide Auto-start Remux checkbox as soon as scanning starts
        self.auto_start_checkbox.pack_forget()

        # Start scan timer
        self.scan_start_time = time.time()

        # Disable source and output buttons during scanning
        self.btn_browse_folder.config(state="disabled")
        self.btn_browse_files.config(state="disabled")
        self.btn_browse_output.config(state="disabled")
        self.btn_clear_output.config(state="disabled")

        self.btn_run.config(text="Scanning...", state="disabled")
        self.log_text.config(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.config(state="disabled")
        self.process_queue.put(("LOG", f"Starting file scan for {len(self.files_to_process)} files..."))

        threading.Thread(target=self.scan_files_worker, args=(list(self.files_to_process),), daemon=True).start()

    def scan_single_file(self, file_path):
        """Scan a single video file for metadata (used by parallel worker)."""
        result = {'valid': True, 'fps': None, 'duration': 0}

        try:
            # Get FPS first (separate call to ensure proper logging)
            fps_command = [self.ffprobe_path, "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=avg_frame_rate", "-of",
                         "default=noprint_wrappers=1:nokey=1", file_path]

            fps_process = subprocess.run(fps_command, capture_output=True, text=True, check=True, timeout=self.FPS_SCAN_TIMEOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

            fps_fraction = fps_process.stdout.strip()
            if '/' in fps_fraction and fps_fraction != "0/0":
                num, den = map(int, fps_fraction.split('/'))
                if den != 0:
                    fps_value = num / den
                    result['fps'] = str(fps_value)
                    # Log FPS detection for VFR functionality
                    self.process_queue.put(("LOG", f"Detected FPS: {fps_value} for {os.path.basename(file_path)}"))
            elif fps_fraction and fps_fraction != "0/0":
                try:
                    fps_value = float(fps_fraction)
                    result['fps'] = fps_fraction
                    # Log FPS detection for VFR functionality
                    self.process_queue.put(("LOG", f"Detected FPS: {fps_value} for {os.path.basename(file_path)}"))
                except ValueError:
                    pass

            # Get duration and other info in a separate optimized call
            duration_command = [self.ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", file_path]

            duration_process = subprocess.run(duration_command, capture_output=True, text=True, timeout=self.FFPROBE_TIMEOUT,
                                            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

            if duration_process.returncode == 0:
                try:
                    result['duration'] = float(duration_process.stdout.strip())
                except ValueError:
                    pass

            # Get audio track info if audio is included (separate call for detailed audio info)
            if self.include_audio.get():
                audio_tracks = self.get_audio_track_info(file_path)
                result['audio_tracks'] = len(audio_tracks)
                if audio_tracks:
                    languages = [track['language'] for track in audio_tracks if track['language'] != 'und']
                    result['languages'] = languages

        except subprocess.TimeoutExpired:
            result['valid'] = False
            self.process_queue.put(("LOG", f"Warning: Timeout scanning: {os.path.basename(file_path)}"))
        except Exception as e:
            result['valid'] = False
            self.process_queue.put(("LOG", f"Warning: Error scanning {os.path.basename(file_path)}: {str(e)[:50]}"))

        return result

    def scan_files_worker(self, files):
        """Scan multiple video files in parallel for improved performance."""
        results = {}
        total_files = len(files)

        # Use ThreadPoolExecutor for parallel scanning
        max_scan_workers = min(8, total_files)  # Limit to 8 workers or number of files, whichever is smaller

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_scan_workers) as executor:
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

                        # FPS tracking removed per user request

                        completed_count += 1

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

        # High FPS detection feature removed per user request

        self.process_queue.put(('SCAN_COMPLETE', {'results': results}))

    def start_remux_thread(self, auto_start=False):

        # Show command preview if enabled
        if self.preview_commands_var.get():
            self.show_preview_dialog(auto_start=auto_start)
            # Wait for user to click Start or Close in the preview dialog
            self.wait_window(self.preview_window)
            # If user clicked Start, continue with remuxing
            if hasattr(self, 'preview_start_remuxing') and self.preview_start_remuxing:
                self.preview_start_remuxing = False  # Reset flag
            else:
                return  # User clicked Close, don't start remuxing

        # Disable source and output buttons during remuxing
        self.btn_browse_folder.config(state="disabled")
        self.btn_browse_files.config(state="disabled")
        self.btn_browse_output.config(state="disabled")
        self.btn_clear_output.config(state="disabled")

        self.btn_start_remux.config(state="disabled", text="Remuxing...")
        self.btn_pause.config(state="normal", text="Pause")
        self.btn_skip.config(state="normal")
        self.btn_cancel.config(state="normal")
        self.disable_settings_controls()
        self.cancel_event.clear()
        self.skip_event.clear()
        self.pause_event.set()

        settings = {
            "files": list(self.files_to_process),
            "output_dir": self.output_directory,
            "include_audio": self.include_audio.get(),
            "file_action": self.file_action_var.get(),
            "use_timescale": self.use_timescale_option.get(),
            "timescale_is_source": self.timescale_is_source.get(),
            "timescale_preset": self.timescale_preset_var.get(),
            "timescale_custom": self.timescale_custom_var.get(),
            "scan_results": self.scan_results,
            "output_format": self.output_format_var.get(),
            "preserve_timestamps": self.preserve_timestamps_var.get(),
            "overwrite_existing": self.overwrite_existing_var.get(),
        }

        # Record start time for elapsed time calculation
        self.processing_start_time = time.time()

        self.process_queue.put(("LOG", f"Remux process started for {len(settings['files'])} files..."))
        self.process_queue.put(("LOG", ""))
        threading.Thread(target=self.remux_videos_worker, args=(settings,), daemon=True).start()

    def remux_videos_worker(self, settings):
        """Process video files sequentially with simple monitoring."""
        total_videos = len(settings["files"])
        remuxed_count, skipped_count = 0, 0
        self.process_queue.put(("LOG", f"Starting remux for {total_videos} files..."))

        for i, video_file_path in enumerate(settings["files"]):
            self.pause_event.wait()
            if self.cancel_event.is_set():
                self.process_queue.put(("LOG", "Operation cancelled by user."))
                break

            # Reset skip event for each file
            self.skip_event.clear()

            file_name = os.path.basename(video_file_path)
            output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
            output_file_path = os.path.join(output_dir_final, os.path.splitext(file_name)[0] + settings["output_format"])

            # Get file info for progress tracking
            scan_result = settings["scan_results"].get(video_file_path, {})
            duration = scan_result.get('duration', 0)

            self.process_queue.put(("STATUS", f"Processing: {file_name}"))
            self.process_queue.put(("PROGRESS", {'total_percent': (i / total_videos) * 100, 'current': i, 'total': total_videos}))
            self.process_queue.put(("CURRENT_FILE", {'filename': file_name, 'duration': duration}))

            # Check if file is valid
            if not scan_result.get('valid', True):
                self.process_queue.put(("LOG", f"Skipping invalid file: {file_name}"))
                # Skip invalid file without moving original file to Remuxed folder
                self.process_queue.put(("LOG", f"   [FILE] Original file left in place (invalid)"))
                skipped_count += 1
                continue

            if os.path.exists(output_file_path):
                if settings.get("overwrite_existing", False):
                    self.process_queue.put(("LOG", f"Overwriting existing output: {file_name}"))
                else:
                    self.process_queue.put(("LOG", f"Skipping (output exists): {file_name}"))
                    # Skip file without moving original file to Remuxed folder
                    self.process_queue.put(("LOG", f"   [FILE] Original file left in place (skipped)"))
                    skipped_count += 1
                    continue

            # Build and execute command
            command, output_file_path = self.build_ffmpeg_command(video_file_path, settings)

            # Use simple execution without complex monitoring
            result = self.execute_ffmpeg_process(command, output_file_path, file_name, duration, settings)

            if result == "completed":
                remuxed_count += 1
            elif result == "skipped":
                skipped_count += 1
            elif result == "cancelled":
                break

        self.process_queue.put(("PROGRESS", {'total_percent': 100, 'current': total_videos, 'total': total_videos}))
        self.process_queue.put(("FINISHED", {'remuxed': remuxed_count, 'skipped': skipped_count}))

    def remux_single_file(self, video_file_path, settings, file_index, total_files):
        """Process a single video file (used by parallel worker)."""
        file_name = os.path.basename(video_file_path)
        output_dir_final = settings["output_dir"] or os.path.dirname(video_file_path)
        output_file_path = os.path.join(output_dir_final, os.path.splitext(file_name)[0] + settings["output_format"])

        # Get file info for progress tracking
        scan_result = settings["scan_results"].get(video_file_path, {})
        duration = scan_result.get('duration', 0)

        self.process_queue.put(("STATUS", f"Processing: {file_name}"))
        self.process_queue.put(("CURRENT_FILE", {'filename': file_name, 'duration': duration}))

        # Check if file is valid
        if not scan_result.get('valid', True):
            self.process_queue.put(("LOG", f"Skipping invalid file: {file_name}"))
            # Skip invalid file without moving original file to Remuxed folder
            self.process_queue.put(("LOG", f"   [FILE] Original file left in place (invalid)"))
            return "skipped"

        if os.path.exists(output_file_path):
            if settings.get("overwrite_existing", False):
                self.process_queue.put(("LOG", f"Overwriting existing output: {file_name}"))
            else:
                self.process_queue.put(("LOG", f"Skipping (output exists): {file_name}"))
                # Skip file without moving original file to Remuxed folder
                self.process_queue.put(("LOG", f"   [FILE] Original file left in place (skipped)"))
                return "skipped"

        # Build and execute command
        command, output_file_path = self.build_ffmpeg_command(video_file_path, settings)

        # Use simple execution without complex monitoring
        result = self.execute_ffmpeg_process(command, output_file_path, file_name, duration, settings)

        # Handle original file for completed files
        if result == "completed":
            self.handle_original_file(file_name, output_file_path, settings)

        return result

    # =============================================================================
    # UI CALLBACKS
    # =============================================================================
    # Handle UI event responses and dynamic updates for settings controls and
    # user interactions including timescale options, info dialogs, and validation

    # ---------- UI Callbacks ----------



    def on_timescale_option_change(self, *args):
        use_preset = not self.timescale_is_source.get()
        if use_preset and self.use_timescale_option.get():
            self.timescale_combobox.config(state="readonly")
            if self.timescale_preset_var.get() == "Custom":
                self.custom_timescale_entry.config(state="normal")
        else:
            self.timescale_combobox.config(state="disabled")
            self.custom_timescale_entry.config(state="disabled")
            
    def check_custom_timescale(self, event=None):
        if self.timescale_preset_var.get() == "Custom":
            self.custom_timescale_entry.config(state="normal")
        else:
            self.custom_timescale_entry.config(state="disabled")

    def toggle_timescale_selector(self):
        if self.use_timescale_option.get():
            self.timescale_options_container.pack(fill="x", pady=(5, 0), padx=10)
            # Force update of the options state
            self.after(10, self.on_timescale_option_change)
        else:
            self.timescale_options_container.pack_forget()
            # Reset the custom entry state when hiding
            self.timescale_combobox.config(state=self.UI_STATE_DISABLED)
            self.custom_timescale_entry.config(state=self.UI_STATE_DISABLED)

    def show_timescale_info(self):
        messagebox.showinfo(
            "Video Timescale Info",
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
        messagebox.showinfo(
            "File Validation",
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
        messagebox.showinfo(
            "Command Preview",
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
        messagebox.showinfo(
            "Output Format",
            "Choose the format for remuxed video files.\n\n"
            "Available formats:\n"
            "• MP4: Most compatible, works on all devices\n"
            "• MOV: Apple QuickTime format\n\n"
            "MP4 is recommended for general use."
        )

    def show_file_management_info(self):
        messagebox.showinfo(
            "Original File Management",
            "Controls what happens to original MKV files after remuxing.\n\n"
            "• Move to subfolder: Creates 'Remuxed' folder and moves originals there\n"
            "• Keep in place: Original files remain in their current location\n"
            "• Delete original: Permanently removes original files (not recommended)\n\n"
            "Move to subfolder is the safest option."
        )

    def show_audio_info(self):
        messagebox.showinfo(
            "Audio Streams",
            "Controls whether audio tracks are included in the remuxed files.\n\n"
            "• Include Audio: Copies all audio streams from original to output\n"
            "• Exclude Audio: Creates video-only files (silent)\n\n"
            "When audio is included, all audio tracks from the original file\n"
            "are automatically preserved in the output.\n\n"
            "Most videos should include audio for normal playback."
        )

    def show_timestamp_info(self):
        messagebox.showinfo(
            "Preserve Timestamps",
            "Copies the original file's creation and modification dates to the remuxed file.\n\n"
            "This helps maintain:\n"
            "• File organization in media libraries\n"
            "• Backup and sync software behavior\n"
            "• Historical file information\n\n"
            "Recommended for most users."
        )

    def show_overwrite_info(self):
        messagebox.showinfo(
            "Overwrite Existing Files",
            "Controls behavior when output files already exist.\n\n"
            "• Unchecked: Skip files if output already exists (default)\n"
            "• Checked: Overwrite existing files with new remux\n\n"
            "Use overwrite mode when re-processing the same files."
        )

    # =============================================================================
    # SETTINGS CONTROL CALLBACKS
    # =============================================================================
    # Handle settings-related UI interactions including log management,
    # completion dialogs, and directory operations

    # ---------- Settings Control Callbacks ----------


    def copy_log_to_clipboard(self):
        """Copy the log output to clipboard."""
        try:
            # Get all text from the log widget
            log_content = self.log_text.get(1.0, "end-1c")  # Get all text except the last newline

            if log_content.strip():  # Only copy if there's content
                # Copy to clipboard
                self.clipboard_clear()
                self.clipboard_append(log_content)
                self.update()  # Keep the clipboard data after the window closes

                # Show success message
                messagebox.showinfo("Success", "Log output copied to clipboard!")
            else:
                messagebox.showinfo("Info", "No log content to copy.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to copy log to clipboard: {str(e)}")

    def show_completion_dialog(self, message, data, elapsed_time=None):
        """Show completion dialog with options to open directory or close."""
        # Create custom dialog
        dialog = tk.Toplevel(self)
        dialog.title("Complete")
        dialog.geometry("350x180")  # Increased height to accommodate elapsed time
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        # Set custom window icon for completion dialog
        try:
            # Try multiple methods for maximum compatibility
            icon_path = self.get_resource_path("ICOtrans.ico")

            # Method 1: Use iconbitmap (works best on Windows)
            try:
                dialog.iconbitmap(icon_path)
            except Exception:
                # Method 2: Use iconphoto as fallback
                try:
                    from PIL import Image, ImageTk
                    icon = Image.open(icon_path)
                    icon = ImageTk.PhotoImage(icon)
                    dialog.iconphoto(True, icon)
                except Exception:
                    # Method 3: Use default Tkinter PhotoImage
                    try:
                        icon = tk.PhotoImage(file=icon_path)
                        dialog.iconphoto(True, icon)
                    except Exception:
                        print(f"Warning: Could not load custom icon for completion dialog: {icon_path}")

        except Exception as e:
            print(f"Warning: Could not load custom icon for completion dialog: {e}")

        # Center the dialog
        dialog.geometry("+%d+%d" % (self.winfo_rootx() + self.winfo_width()//2 - 175,
                                    self.winfo_rooty() + self.winfo_height()//2 - 90))

        # Main frame
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill="both", expand=True)

        # Message
        message_label = ttk.Label(main_frame, text=message, font=("Segoe UI", 10))
        message_label.pack(pady=(0, 10))

        # Elapsed time (if available)
        if elapsed_time:
            time_label = ttk.Label(main_frame, text=f"Elapsed time: {elapsed_time}", font=("Segoe UI", 9, "italic"), foreground="gray")
            time_label.pack(pady=(0, 20))

        def open_directory_and_close():
            dialog.destroy()
            self.open_output_directory()
            self.reset_ui_after_processing()

        def close_only():
            dialog.destroy()
            self.reset_ui_after_processing()

        # Button container frame
        button_container = ttk.Frame(main_frame)
        button_container.pack(pady=(20, 0))

        # Center the buttons horizontally
        button_container.grid_columnconfigure(0, weight=1)
        button_container.grid_columnconfigure(2, weight=1)

        # Open Directory button
        open_btn = ttk.Button(button_container, text="Open Location", command=open_directory_and_close)
        open_btn.grid(row=0, column=1, padx=(0, 10))

        # Close button
        close_btn = ttk.Button(button_container, text="Close", command=close_only)
        close_btn.grid(row=0, column=2)

        # Set focus on close button by default
        close_btn.focus()

        # Handle Enter key
        dialog.bind('<Return>', lambda e: close_only())
        dialog.bind('<Escape>', lambda e: close_only())

        # Handle window close button (X)
        def on_dialog_close():
            dialog.destroy()
            self.reset_ui_after_processing()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

    def start_remuxing_from_preview(self, preview_window):
        """Set flag to start remuxing and close the preview dialog."""
        self.preview_start_remuxing = True
        self.countdown_active = False  # Stop countdown if user manually clicked

        # Handle window close button (X) - this is a fallback in case the window
        # close button is clicked while the Start Remuxing button is being processed
        def on_dialog_close():
            self.countdown_active = False  # Stop countdown
            preview_window.destroy()
            # Don't reset UI here - let the calling method handle it

        preview_window.protocol("WM_DELETE_WINDOW", on_dialog_close)

        # Close the preview window
        preview_window.destroy()

    def open_output_directory(self):
        """Open the output directory in the system file explorer."""
        try:
            output_dir = self.output_directory
            if not output_dir:
                # If no output directory specified, use the source directory
                if self.files_to_process:
                    output_dir = os.path.dirname(self.files_to_process[0])

            if output_dir and os.path.exists(output_dir):
                if sys.platform == "win32":
                    os.startfile(output_dir)
                elif sys.platform == "darwin":  # macOS
                    subprocess.run(["open", output_dir])
                else:  # Linux and other Unix-like systems
                    subprocess.run(["xdg-open", output_dir])
                self.process_queue.put(("LOG", f"Opened output directory: {output_dir}"))
            else:
                self.process_queue.put(("LOG", "Warning: Output directory not found or not specified"))
        except Exception as e:
            self.process_queue.put(("LOG", f"Warning: Failed to open output directory: {str(e)}"))

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
# Entry point for running the application as a standalone script
if __name__ == "__main__":
   app = RemuxApp()
   app.mainloop()
