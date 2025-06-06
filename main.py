#!/usr/bin/env python3
"""
Tennis Court Detector - Detects people on tennis courts using YOLOv8 models
"""
import os
import cv2 # type: ignore
import numpy as np # type: ignore
import json
import torch # type: ignore
from shapely.geometry import Polygon, Point # type: ignore
from typing import List, Tuple
import tkinter as tk
from PIL import Image, ImageTk
import sys
import ssl
import argparse
import time
import io
from datetime import datetime
from contextlib import redirect_stdout, redirect_stderr
import contextlib
import threading
from multiprocessing import cpu_count, Pool
from functools import partial
import urllib.request
import re
import urllib.error
import urllib.parse
import importlib.util
import traceback
from collections import Counter
import logging
import subprocess
import math
import platform
import camera as camera_module # Import camera module

# Context manager to suppress stdout and stderr
class suppress_stdout_stderr:
    """
    Context manager to suppress standard output and error streams.
    
    Usage:
        with suppress_stdout_stderr():
            # code that might print unwanted output
    """
    def __enter__(self):
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.stdout
        sys.stderr = self.stderr

# Global variables
args = None  # Will store command-line arguments
# Check if ultralytics is installed for YOLOv8 models
try:
    import ultralytics # type: ignore
    ULTRALYTICS_AVAILABLE = True
except ImportError:
    ULTRALYTICS_AVAILABLE = False
# Fix macOS SSL certificate issues
if sys.platform == 'darwin':
    # Check if we're running on macOS and set default SSL context
    try:
        # Try to import certifi for better certificate handling
        import certifi # type: ignore
        ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        # If certifi isn't available, try the default macOS certificate location
        ssl._create_default_https_context = lambda: ssl.create_default_context()
# === CONFIGURATION SETTINGS ===
class Config:
    # Color settings for court detection
    COURT_COLORS = {
        "blue": {
            "lower": [90, 40, 40],
            "upper": [120, 255, 255]
        },
        "green": {
            "lower": [40, 40, 40],
            "upper": [80, 255, 255]
        },
        "red": {
            "lower": [0, 50, 50],
            "upper": [10, 255, 255],
            "lower2": [170, 50, 50],
            "upper2": [180, 255, 255]
        }
    }
    
    # Court detection parameters
    class Court:
        MIN_AREA = 3000              # Reduced from 5000 to detect smaller courts
        MAX_AREA = 200000            # Increased from 150000 to detect larger courts
        MIN_SCORE = 0.5              # Minimum score for a valid court
        MIN_ASPECT_RATIO = 1.0       # Reduced from 1.2 to allow more court shapes
        MAX_ASPECT_RATIO = 4.0       # Increased from 3.0 to allow wider courts
        MIN_BLUE_RATIO = 0.2         # Reduced from 0.3 to be more lenient
        MIN_GREEN_RATIO = 0.02       # Reduced from 0.05 to be more lenient

    # Saved court positions
    COURT_POSITIONS = []            # Filled after detection, loaded from config
    
    # Morphological operation settings
    class Morphology:
        KERNEL_SIZE = 5              # Kernel size for morphological operations
        ITERATIONS = 2               # Number of iterations for closing operations
    
    # Court area definitions
    IN_BOUNDS_COLOR = "blue"         # Color that represents in-bounds
    OUT_BOUNDS_COLOR = "green"       # Color that represents out-of-bounds
    
    # Visualization settings
    class Visual:
        COURT_OUTLINE_COLOR = (0, 255, 0)        # Green
        COURT_OUTLINE_THICKNESS = 4              # Line thickness
        PERSON_IN_BOUNDS_COLOR = (0, 255, 0)     # Green for people in court
        PERSON_OUT_BOUNDS_COLOR = (0, 165, 255)  # Orange for people near court
        PERSON_OFF_COURT_COLOR = (0, 0, 255)     # Red for people off court
        TEXT_COLOR = (255, 255, 255)             # White
        FONT_SCALE = 0.5                         # Text size
        TEXT_THICKNESS = 2                       # Text thickness
        DRAW_COURT_OUTLINE = True                # Whether to draw court outline
        SHOW_COURT_NUMBER = True                # Whether to show court number in labels
        SHOW_DETAILED_LABELS = True             # Whether to show detailed labels on output image
    
    # Terminal output settings
    class Output:
        VERBOSE = True               # Show detailed output
        USE_COLOR_OUTPUT = True      # Use colored terminal output
        SHOW_TIMESTAMP = True        # Show timestamps in output
        SUPER_QUIET = False          # Super quiet mode (almost no output)
        SUMMARY_ONLY = False         # Only show summary of results
        EXTRA_VERBOSE = False         # Show extra detailed output for Raspberry Pi
        
        # ANSI color codes for terminal output
        COLORS = {
            "INFO": "\033[94m",      # Blue
            "SUCCESS": "\033[92m",   # Green
            "WARNING": "\033[93m",   # Yellow
            "ERROR": "\033[91m",     # Red
            "DEBUG": "\033[90m",     # Gray
            "RESET": "\033[0m",      # Reset
            "BOLD": "\033[1m",       # Bold
            "UNDERLINE": "\033[4m"   # Underline
        }
    
    # Debug mode
    DEBUG_MODE = False              # Detailed debug output mode
    
    # Paths and directories
    class Paths:
        IMAGES_DIR = "images"
        INPUT_IMAGE = "input.png"
        OUTPUT_IMAGE = "output.png"
        MODELS_DIR = "models"
        
        @classmethod
        def input_path(cls):
            return os.path.join(cls.IMAGES_DIR, cls.INPUT_IMAGE)
            
        @classmethod
        def output_path(cls):
            return os.path.join(cls.IMAGES_DIR, cls.OUTPUT_IMAGE)
            
        @classmethod
        def debug_dir(cls):
            return os.path.join(os.path.dirname(cls.output_path()), "debug")
    
    # Model settings
    class Model:
        NAME = "yolov8x"             # YOLOv5 model size (yolov5s, yolov5m, yolov5l, etc.)
        CONFIDENCE = 0.1             # Detection confidence threshold (lowered from 0.3)
        IOU = 0.45                   # IoU threshold
        CLASSES = [0]                # Only detect people (class 0)
        
        # YOLOv5 model URLs - add more as needed
        MODEL_URLS = {
            "yolov5n": "https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5n.pt",
            "yolov5s": "https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5s.pt",
            "yolov5m": "https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5m.pt",
            "yolov5l": "https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5l.pt",
            "yolov5x": "https://github.com/ultralytics/yolov5/releases/download/v6.0/yolov5x.pt",
            # YOLOv6 models
            "yolov6n": "https://github.com/meituan/YOLOv6/releases/download/0.2.0/yolov6n.pt",
            "yolov6s": "https://github.com/meituan/YOLOv6/releases/download/0.2.0/yolov6s.pt",
            "yolov6m": "https://github.com/meituan/YOLOv6/releases/download/0.2.0/yolov6m.pt",
            "yolov6l": "https://github.com/meituan/YOLOv6/releases/download/0.2.0/yolov6l.pt",
            # YOLOv7 models
            "yolov7": "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7.pt",
            "yolov7-tiny": "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7-tiny.pt",
            "yolov7x": "https://github.com/WongKinYiu/yolov7/releases/download/v0.1/yolov7x.pt",
            # YOLOv8 models
            "yolov8n": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt",
            "yolov8s": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8s.pt",
            "yolov8m": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8m.pt",
            "yolov8l": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8l.pt",
            "yolov8x": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8x.pt",
            # YOLOv9 models (added for future compatibility)
            "yolov9c": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov9c.pt",
            "yolov9e": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov9e.pt",
            "yolov9m": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov9m.pt",
            "yolov9s": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov9s.pt",
            "yolov9n": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov9n.pt",
            "yolov9x": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov9x.pt",
            # YOLOv10 models (added for future compatibility)
            "yolov10n": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov10n.pt",
            "yolov10s": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov10s.pt",
            "yolov10m": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov10m.pt",
            "yolov10l": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov10l.pt",
            "yolov10x": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov10x.pt",
            # YOLOv11 models (placeholder for future versions)
            "yolov11n": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov11n.pt",
            "yolov11s": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov11s.pt",
            "yolov11m": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov11m.pt",
            "yolov11l": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov11l.pt",
            "yolov11x": "https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov11x.pt",
            # YOLOv12 models
            "yolov12n": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov12n.pt",
            "yolov12s": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov12s.pt",
            "yolov12m": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov12m.pt",
            "yolov12l": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov12l.pt",
            "yolov12x": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov12x.pt",
        }
        
        @classmethod
        def get_model_url(cls, model_name):
            """Get URL for a YOLO model, including newer versions not explicitly listed."""
            model_name = model_name.lower()
            
            # Check if model exists directly in our dictionary
            if model_name in cls.MODEL_URLS:
                return cls.MODEL_URLS[model_name]
            
            # Handle dynamically newer YOLO versions (v9-v20)
            # Extract version and size from model name
            if model_name.startswith("yolov"):
                try:
                    # Extract version number and size
                    version_match = re.search(r'yolov(\d+)([a-z\-]+)?', model_name)
                    if version_match:
                        version = version_match.group(1)
                        size = version_match.group(2) or "s"  # Default to small if no size specified
                        
                        # If it's version 9 or higher, use the ultralytics assets pattern
                        if int(version) >= 9:
                            return f"https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov{version}{size}.pt"
                except:
                    pass  # If parsing fails, fall back to default
            
            # Default to yolov5s if model not found
            OutputManager.log(f"Unknown model {model_name}; using yolov5s", "WARNING")
            return cls.MODEL_URLS["yolov5s"]
    
    # Multiprocessing settings
    class MultiProcessing:
        ENABLED = True              # Enable multiprocessing
        NUM_PROCESSES = 4           # Number of CPU cores to use
        CHUNK_SIZE = 75             # Chunk size for processing

    # Camera settings (New)
    class Camera:
        WIDTH = 1280
        HEIGHT = 720

# === Output Manager Class ===
# Moved up to be defined before config loading
class OutputManager:
    """
    Centralized output manager for all terminal output.
    Provides professional formatting, reliable animations, and clean output management.
    """
    # ANSI color and style codes
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    RESET = "\033[0m"

    @classmethod
    def supports_color(cls):
        """Return True if the running environment supports color output."""
        if not sys.stdout.isatty():
            return False
        if os.environ.get("NO_COLOR"):
            return False
        return True

    @classmethod
    def colorize(cls, text, color):
        """Wrap text with ANSI color codes if enabled."""
        if cls._use_color:
            return f"{color}{text}{cls.RESET}"
        return text

    @staticmethod
    def clean_message(message: str) -> str:
        """Simple cleanup for log messages."""
        if not message:
            return ""
        msg = str(message).strip()
        msg = re.sub(r"\s+", " ", msg)
        if msg and msg[0].islower():
            msg = msg[0].upper() + msg[1:]
        return msg
    
    # Symbols for different message types
    SYMBOLS = {
        "INFO": "ℹ",
        "SUCCESS": "✓",
        "WARNING": "⚠",
        "ERROR": "✗",
        "DEBUG": "•",
        "FATAL": "☠",
        "STATUS": "→",
    }
    
    # Track messages for summary
    warnings = []
    errors = []
    successes = []
    info = []
    
    # Animation state
    _animation_active = False
    _animation_thread = None
    _stop_animation = False
    _progress_total = 0
    _progress_current = 0
    
    # Message deduplication
    _last_message = None
    _message_count = 0
    
    # Use class-level config initially, can be updated later
    _verbose = Config.Output.VERBOSE
    _super_quiet = Config.Output.SUPER_QUIET
    _summary_only = Config.Output.SUMMARY_ONLY
    _extra_verbose = Config.Output.EXTRA_VERBOSE
    _use_color = Config.Output.USE_COLOR_OUTPUT and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    _show_timestamp = Config.Output.SHOW_TIMESTAMP

    @classmethod
    def configure(cls, config_data):
        """Configure OutputManager based on loaded config data."""
        output_config = config_data.get('Output', {})
        cls._verbose = output_config.get('VERBOSE', Config.Output.VERBOSE)
        cls._super_quiet = output_config.get('SUPER_QUIET', Config.Output.SUPER_QUIET)
        cls._summary_only = output_config.get('SUMMARY_ONLY', Config.Output.SUMMARY_ONLY)
        cls._extra_verbose = output_config.get('EXTRA_VERBOSE', Config.Output.EXTRA_VERBOSE)
        cls._use_color = Config.Output.USE_COLOR_OUTPUT and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        # Keep color and timestamp from default class config for now
        # Could add these to config.json if needed

    @classmethod
    def reset_logs(cls):
        """Reset logged messages."""
        cls.warnings = []
        cls.errors = []
        cls.successes = []
        cls.info = []
        cls._last_message = None
        cls._message_count = 0
        
    @classmethod
    def _should_print_message(cls, message, level):
        """Determine if a message should be printed based on verbosity levels."""
        if cls._super_quiet:
            return level in ["ERROR", "FATAL", "STATUS"]
        if cls._summary_only:
            return level in ["ERROR", "FATAL", "STATUS"]
            
        if not cls._verbose and level == "DEBUG":
            return False
            
        # Prevent duplicate consecutive messages
        # if message == cls._last_message:
        #     cls._message_count += 1
        #     # Print a summary message if the count reaches a certain threshold
        #     # (This part can be complex to get right, maybe simpler to just allow repeats for now)
        #     # sys.stdout.write(f"\r{cls._last_message} (x{cls._message_count + 1})")
        #     # sys.stdout.flush()
        #     return False # Don't print the duplicate yet
        # else:
        #     if cls._message_count > 0:
        #         # Print the final count of the previous message
        #         # sys.stdout.write(f"\r{cls._last_message} (x{cls._message_count + 1})\n")
        #         # sys.stdout.flush()
        #         pass # Decide how to handle this
        #     cls._last_message = message
        #     cls._message_count = 0
        
        return True
        
    @classmethod
    def log(cls, message, level="INFO"):
        """Log a message to the terminal with appropriate formatting and level."""
        cls._ensure_animation_stopped() # Stop animation before printing normal log
        
        if not cls._should_print_message(message, level):
            return
            
        color_map = {
            "INFO": cls.BLUE,
            "SUCCESS": cls.GREEN,
            "WARNING": cls.YELLOW,
            "ERROR": cls.RED,
            "DEBUG": cls.GRAY,
            "FATAL": cls.RED,  # Fatal errors use red
            "STATUS": cls.CYAN,  # Status messages
        }
        
        level_upper = level.upper()
        symbol = cls.SYMBOLS.get(level_upper, "")
        color = color_map.get(level_upper, cls.RESET)
        bold = cls.BOLD if level_upper in ["ERROR", "FATAL"] else ""
        
        timestamp = datetime.now().strftime("%H:%M:%S") + " " if cls._show_timestamp else ""
        
        # Record messages for summary (excluding DEBUG)
        clean_msg = cls.clean_message(message)
        if level_upper == "WARNING": cls.warnings.append(clean_msg)
        elif level_upper == "ERROR": cls.errors.append(clean_msg)
        elif level_upper == "SUCCESS": cls.successes.append(clean_msg)
        elif level_upper == "INFO": cls.info.append(clean_msg)

        formatted = f"{symbol} {clean_msg}"
        if cls._use_color:
            formatted = cls.colorize(formatted, color)
            if bold:
                formatted = f"{cls.BOLD}{formatted}{cls.RESET}"
        output = f"{timestamp}{formatted}\n"
        sys.stdout.write(output)
        sys.stdout.flush()
        
        if level_upper == "FATAL":
            cls.fancy_summary("Fatal Error", clean_msg, is_error=True)
            sys.exit(1)
            
    @classmethod
    def status(cls, message):
        """Log a status message."""
        cls.log(message, level="STATUS")
        
    @classmethod
    def create_final_summary(cls, people_count, total_courts, output_path=None, 
                             processing_time=None,
                             detailed_court_counts=None,
                             duration_court_detection=0.0,
                             duration_people_detection=0.0,
                             duration_position_analysis=0.0):
        """Create a formatted summary of the detection results."""
        if cls._super_quiet:
            return ""
            
        summary_lines = []
        summary_lines.append("Detection Summary")
        summary_lines.append("-" * 30)
        summary_lines.append(f"Total Courts Detected: {cls.BOLD}{total_courts}{cls.RESET}")
        summary_lines.append(f"Total People Detected: {cls.BOLD}{people_count}{cls.RESET}")
        
        if detailed_court_counts:
            summary_lines.append("\nPeople per Court:")
            total_in_bounds = 0
            total_out_bounds = 0
            for court_num, counts in sorted(detailed_court_counts.items()):
                in_bounds = counts.get('in_bounds', 0)
                out_bounds = counts.get('out_bounds', 0)
                summary_lines.append(f"  Court {court_num}: {cls.GREEN}{in_bounds} in bounds{cls.RESET}, {cls.YELLOW}{out_bounds} nearby{cls.RESET}")
                total_in_bounds += in_bounds
                total_out_bounds += out_bounds
            summary_lines.append(f"  Total on Courts: {cls.GREEN}{total_in_bounds}{cls.RESET}")
            summary_lines.append(f"  Total Near Courts: {cls.YELLOW}{total_out_bounds}{cls.RESET}")
        
        # Timing information
        summary_lines.append("\nPerformance:")
        if duration_court_detection > 0:
            summary_lines.append(f"  Court Detection: {duration_court_detection:.2f}s")
        if duration_people_detection > 0:
            summary_lines.append(f"  People Detection: {duration_people_detection:.2f}s")
        if duration_position_analysis > 0:
            summary_lines.append(f"  Position Analysis: {duration_position_analysis:.2f}s")
        
        if output_path:
            summary_lines.append(f"\nOutput Image: {cls.UNDERLINE}{output_path}{cls.RESET}")
            
        # Display warnings and errors
        if cls.warnings:
            summary_lines.append(f"\n{cls.YELLOW}Warnings:{cls.RESET}")
            for warning in cls.warnings:
                summary_lines.append(f"  - {warning}")
        if cls.errors:
            summary_lines.append(f"\n{cls.RED}Errors:{cls.RESET}")
            for error in cls.errors:
                summary_lines.append(f"  - {error}")
                
        return "\n".join(summary_lines)

    @classmethod
    def _ensure_animation_stopped(cls):
        """Make sure any running animation is stopped and cleaned up."""
        if cls._animation_active:
            cls._stop_animation = True
            if cls._animation_thread:
                cls._animation_thread.join() # Wait for thread to finish
            cls._animation_active = False
            cls._animation_thread = None
            sys.stdout.write("\r" + " " * 80 + "\r") # Clear the animation line
            sys.stdout.flush()
            
    @classmethod
    def _run_animation_thread(cls, animate_func):
        """Internal method to run the animation loop in a thread."""
        try:
            animate_func()
        except Exception as e:
            # If animation thread crashes, log it but don't kill main process
            print(f"\n[Animation Error] {e}\n")
        finally:
            cls._animation_active = False # Ensure flag is reset
            # Don't clear line here, stop_animation handles it
            
    @classmethod
    def animate(cls, message, is_progress=False, total=20):
        """Start a terminal animation or progress bar."""
        cls._ensure_animation_stopped() # Stop previous animation if any
        
        cls._stop_animation = False
        cls._animation_active = True
        cls._progress_total = total
        cls._progress_current = 0
        
        if is_progress:
            # --- Progress Bar Animation --- 
            def animate():
                bar_length = 20 # Length of the progress bar
                while not cls._stop_animation:
                    percent = int(100 * (cls._progress_current / float(cls._progress_total)))
                    filled_length = int(bar_length * cls._progress_current // cls._progress_total)
                    bar = '█' * filled_length + '-' * (bar_length - filled_length)
                    # Use \r to return cursor to start of line
                    prefix = cls.colorize(f"{cls.SYMBOLS['STATUS']} {message}", cls.CYAN) if cls._use_color else f"{cls.SYMBOLS['STATUS']} {message}"
                    bar_output = f"[{bar}] {percent}%"
                    sys.stdout.write(f"\r{prefix} {bar_output}")
                    sys.stdout.flush()
                    time.sleep(0.1)
                    if cls._progress_current >= cls._progress_total:
                        break # Exit if progress complete
                # Final update to show 100% if needed
                percent = 100
                bar = '█' * bar_length
                prefix = cls.colorize(f"{cls.SYMBOLS['STATUS']} {message}", cls.CYAN) if cls._use_color else f"{cls.SYMBOLS['STATUS']} {message}"
                bar_output = f"[{bar}] {percent}%"
                sys.stdout.write(f"\r{prefix} {bar_output}")
                sys.stdout.flush()
        else:
            # --- Spinner Animation --- 
            def animate():
                spin_chars = ['-', '\\', '|', '/']
                i = 0
                while not cls._stop_animation:
                    # Use \r to return cursor to start of line
                    prefix = cls.colorize(f"{cls.SYMBOLS['STATUS']} {message}", cls.CYAN) if cls._use_color else f"{cls.SYMBOLS['STATUS']} {message}"
                    sys.stdout.write(f"\r{prefix} {spin_chars[i % len(spin_chars)]}")
                    sys.stdout.flush()
                    i += 1
                    time.sleep(0.1)
                    
        cls._animation_thread = threading.Thread(target=cls._run_animation_thread, args=(animate,), daemon=True)
        cls._animation_thread.start()
        
    @classmethod
    def set_progress(cls, value):
        """Update the progress value for the progress bar animation."""
        if cls._animation_active:
            cls._progress_current = min(value, cls._progress_total) # Cap at total
        
    @classmethod
    def stop_animation(cls, success=True):
        """Stop the current animation and optionally print a final status."""
        if not cls._animation_active:
            return
            
        cls._ensure_animation_stopped() # Join thread and clear line
        
        # Optionally print final status (e.g., Success ✓ or Failure ✗)
        # This depends on how you want the flow - often the next log message handles this
        # For example, after animate('Downloading'), you might log('Download complete', 'SUCCESS')
        
    @classmethod
    def summarize_detections(cls, courts, people, people_locations):
        """Generate a simple summary string of detections."""
        court_count = len(courts)
        people_count = len(people)
        in_bounds_count = len([loc for loc in people_locations if loc['location'] == 'In Bounds'])
        out_bounds_count = len([loc for loc in people_locations if loc['location'] == 'Out of Bounds'])
        off_court_count = people_count - (in_bounds_count + out_bounds_count)
        
        summary = f"Courts: {court_count}, People: {people_count} (In: {in_bounds_count}, Near: {out_bounds_count}, Off: {off_court_count})"
        return summary

    @classmethod
    def fancy_summary(cls, title, content, processing_time=None, is_error=False):
        """
        Prints a visually distinct summary box in the terminal.
        Handles multiline content.
        """
        cls._ensure_animation_stopped()
        if cls._super_quiet:
            return
        
        lines = content.split('\n') if content else []
        max_len = len(title) + 4 # Initial length based on title
        for line in lines:
            # Strip ANSI codes for length calculation
            clean_line = re.sub(r'\x1b\[[0-9;]*[mK]', '', line)
            max_len = max(max_len, len(clean_line))
            
        border_color = cls.RED if is_error else cls.GREEN
        bold = cls.BOLD
        reset = cls.RESET
        
        # Top border with title
        top = cls.colorize(f"╔{'═' * (max_len + 2)}╗", border_color)
        middle = cls.colorize(f"║ {bold}{title.center(max_len)}{reset}", border_color) + cls.colorize(" ║", border_color)
        divider = cls.colorize(f"╠{'═' * (max_len + 2)}╣", border_color)
        print(top)
        print(middle)
        print(divider)
        
        # Content lines
        for line in lines:
            clean_line = re.sub(r'\x1b\[[0-9;]*[mK]', '', line)
            padding = max_len - len(clean_line)
            content_line = cls.colorize(f"║ {line}{' ' * padding} ", border_color) + cls.colorize("║", border_color)
            print(content_line)
            
        # Processing time if provided
        if processing_time is not None:
            time_str = f"Total Time: {processing_time:.2f}s"
            padding = max_len - len(time_str)
            print(cls.colorize(f"╠{'═' * (max_len + 2)}╣", border_color))
            time_line = cls.colorize(f"║ {cls.GRAY}{time_str}{' ' * padding} ", border_color) + cls.colorize("║", border_color)
            print(time_line)
        
        # Bottom border
        print(cls.colorize(f"╚{'═' * (max_len + 2)}╝", border_color))
        print() # Add a blank line after the summary

    # --- Potential Fixes --- 
    # Store potential issues and fixes
    potential_issues = {}
    
    @classmethod
    def add_potential_issue(cls, issue_key, description, fix_suggestion):
        """Add a potential issue detected during runtime."""
        if issue_key not in cls.potential_issues:
            cls.potential_issues[issue_key] = {"description": description, "fix": fix_suggestion}

    @classmethod
    def get_potential_fixes(cls):
        """Format potential issues and fixes for display."""
        if not cls.potential_issues:
            return ""
            
        output = [f"{cls.YELLOW}{cls.BOLD}Potential Issues & Fixes:{cls.RESET}"]
        for key, data in cls.potential_issues.items():
            output.append(f"- {cls.YELLOW}Issue:{cls.RESET} {data['description']}")
            output.append(f"  {cls.GREEN}Suggestion:{cls.RESET} {data['fix']}")
            
        return "\n".join(output)
        
# === Load Configuration from JSON if it exists ===
CONFIG_FILE = "config.json"
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            _loaded_config = json.load(f)
            # Update Config class attributes directly (or use a dedicated function)
            # Camera Settings
            if 'Camera' in _loaded_config:
                Config.Camera.WIDTH = _loaded_config['Camera'].get('width', Config.Camera.WIDTH)
                Config.Camera.HEIGHT = _loaded_config['Camera'].get('height', Config.Camera.HEIGHT)
            # Model Settings
            if 'Model' in _loaded_config:
                Config.Model.NAME = _loaded_config['Model'].get('NAME', Config.Model.NAME)
                Config.Model.CONFIDENCE = _loaded_config['Model'].get('CONFIDENCE', Config.Model.CONFIDENCE)
                Config.Model.IOU = _loaded_config['Model'].get('IOU', Config.Model.IOU)
                Config.Model.CLASSES = _loaded_config['Model'].get('CLASSES', Config.Model.CLASSES)
            # Output Settings
            if 'Output' in _loaded_config:
                Config.Output.VERBOSE = _loaded_config['Output'].get('VERBOSE', Config.Output.VERBOSE)
                Config.Output.SUPER_QUIET = _loaded_config['Output'].get('SUPER_QUIET', Config.Output.SUPER_QUIET)
                Config.Output.SUMMARY_ONLY = _loaded_config['Output'].get('SUMMARY_ONLY', Config.Output.SUMMARY_ONLY)
                Config.Output.EXTRA_VERBOSE = _loaded_config['Output'].get('EXTRA_VERBOSE', Config.Output.EXTRA_VERBOSE)
            # Debug Mode
            Config.DEBUG_MODE = _loaded_config.get('DEBUG_MODE', Config.DEBUG_MODE)
            # Multiprocessing Settings
            if 'MultiProcessing' in _loaded_config:
                Config.MultiProcessing.ENABLED = _loaded_config['MultiProcessing'].get('ENABLED', Config.MultiProcessing.ENABLED)
                Config.MultiProcessing.NUM_PROCESSES = _loaded_config['MultiProcessing'].get('NUM_PROCESSES', Config.MultiProcessing.NUM_PROCESSES)

            # Pre-detected court positions
            if 'CourtPositions' in _loaded_config:
                Config.COURT_POSITIONS = []
                for court in _loaded_config.get('CourtPositions', []):
                    try:
                        if 'points' in court:
                            pts = [tuple(int(v) for v in p) for p in court['points']][:8]
                        else:
                            pts = [
                                tuple(int(v) for v in court['top_left']),
                                tuple(int(v) for v in court['top_right']),
                                tuple(int(v) for v in court['bottom_right']),
                                tuple(int(v) for v in court['bottom_left'])
                            ]
                        Config.COURT_POSITIONS.append({'points': pts})
                    except Exception:
                        continue

            # Configure OutputManager AFTER loading config
            OutputManager.configure(_loaded_config)
            OutputManager.log(f"Loaded configuration from {CONFIG_FILE}", "DEBUG")
            
    except json.JSONDecodeError as e:
        OutputManager.log(f"Error decoding {CONFIG_FILE}: {e}. Using default class values.", "WARNING")
    except Exception as e:
        OutputManager.log(f"Could not apply {CONFIG_FILE}: {e}. Using default class values.", "WARNING")
else:
    OutputManager.log(f"{CONFIG_FILE} not found. Using default class values.", "DEBUG")
# === End Load Configuration ===

def parse_court_positions_arg(arg):
    """Parse --court-positions argument into a list of court dictionaries."""
    positions = []
    for part in arg.split(';'):
        part = part.strip()
        if not part:
            continue
        nums = [int(n) for n in part.split(',')]
        if len(nums) == 16:
            pts = [(nums[i], nums[i+1]) for i in range(0, 16, 2)]
        elif len(nums) == 8:
            pts = [
                (nums[0], nums[1]),
                (nums[2], nums[3]),
                (nums[4], nums[5]),
                (nums[6], nums[7]),
            ]
        elif len(nums) == 4:
            x, y, w, h = nums
            pts = [
                (x, y),
                (x + w, y),
                (x + w, y + h),
                (x, y + h)
            ]
        else:
            raise ValueError(f"Invalid court position: '{part}'")
        positions.append({'points': pts[:8]})
    if not positions:
        raise ValueError("No valid court positions provided")
    return positions


def court_positions_defined() -> bool:
    """Check if court positions contain any non-zero coordinates."""
    if not Config.COURT_POSITIONS:
        return False
    for court in Config.COURT_POSITIONS:
        pts = court.get('points', [])
        for p in pts:
            if any(int(v) != 0 for v in p):
                return True
    return False


def select_court_positions_gui(image, existing=None, max_courts=4):
    """Tkinter-based GUI to select court polygons with animated buttons."""
    height, width = image.shape[:2]

    # Resize image to fit within 800x600 while preserving aspect ratio
    max_w, max_h = 800, 600
    scale = min(max_w / width, max_h / height, 1.0)
    disp_w, disp_h = int(width * scale), int(height * scale)
    if scale != 1.0:
        resized = cv2.resize(image, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
    else:
        resized = image

    img_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)

    root = tk.Tk()
    root.title("Edit Courts")

    canvas = tk.Canvas(root, width=disp_w, height=disp_h)
    canvas.pack(side=tk.LEFT)
    tk_img = ImageTk.PhotoImage(pil_img)
    canvas.create_image(0, 0, anchor="nw", image=tk_img)

    sidebar = tk.Frame(root, bg="#333")
    sidebar.pack(side=tk.RIGHT, fill=tk.Y)

    instructions = (
        "Click '+' to start a new court and "
        "mark corners with the mouse. Use 'Done' "
        "to close the current court or 'Finish' "
        "when all courts are added."
    )
    instr_label = tk.Label(
        sidebar,
        text=instructions,
        wraplength=140,
        justify=tk.LEFT,
        bg="#333",
        fg="white",
    )
    instr_label.pack(padx=5, pady=(5, 0))

    listbox = tk.Listbox(sidebar, bg="#222", fg="white", highlightthickness=0)
    listbox.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

    btn_frame = tk.Frame(sidebar, bg="#333")
    btn_frame.pack(pady=10)

    def style_button(btn):
        """Style sidebar buttons so they remain readable"""
        btn.configure(
            bg="#e0e0e0",
            fg="black",
            activebackground="#c0c0c0",
            activeforeground="black",
            relief=tk.FLAT,
            bd=1,
            highlightthickness=0,
        )
        btn.bind("<Enter>", lambda e: btn.configure(bg="#d0d0d0"))
        btn.bind("<Leave>", lambda e: btn.configure(bg="#e0e0e0"))

    add_btn = tk.Button(btn_frame, text="+", width=4)
    del_btn = tk.Button(btn_frame, text="-", width=4)
    done_btn = tk.Button(btn_frame, text="Done", width=6)
    finish_btn = tk.Button(btn_frame, text="Finish", width=6)

    for b in (add_btn, del_btn, done_btn, finish_btn):
        style_button(b)
        b.pack(pady=2)

    courts: List[List[Tuple[int, int]]] = []
    if existing:
        for court in existing:
            try:
                pts = [
                    (int(p[0] * scale), int(p[1] * scale)) for p in court['points'][:8]
                ]
            except Exception:
                try:
                    pts = [
                        (int(court['top_left'][0] * scale), int(court['top_left'][1] * scale)),
                        (int(court['top_right'][0] * scale), int(court['top_right'][1] * scale)),
                        (int(court['bottom_right'][0] * scale), int(court['bottom_right'][1] * scale)),
                        (int(court['bottom_left'][0] * scale), int(court['bottom_left'][1] * scale)),
                    ]
                except Exception:
                    continue
            courts.append(pts)
            listbox.insert(tk.END, f"Court {len(courts)}")
            canvas.create_polygon(pts, outline="green", fill="", width=2, tags=f"court{len(courts)-1}")

    mode = "idle"
    curr_pts: List[Tuple[int, int]] = []
    curr_drawn = []

    def redraw_current():
        for item in curr_drawn:
            canvas.delete(item)
        curr_drawn.clear()
        if curr_pts:
            for p in curr_pts:
                curr_drawn.append(canvas.create_oval(p[0]-3, p[1]-3, p[0]+3, p[1]+3, fill="red", outline=""))
            if len(curr_pts) > 1:
                for i in range(len(curr_pts)-1):
                    curr_drawn.append(canvas.create_line(curr_pts[i], curr_pts[i+1], fill="red"))

    def on_canvas_click(event):
        nonlocal mode, curr_pts
        if mode != "adding":
            return
        p = (event.x, event.y)
        curr_pts.append(p)
        if len(curr_pts) > 2:
            first = curr_pts[0]
            if (first[0]-p[0])**2 + (first[1]-p[1])**2 < 100:
                done_current()
                return
        redraw_current()

    canvas.bind("<Button-1>", on_canvas_click)

    def refresh_listbox():
        listbox.delete(0, tk.END)
        for i in range(len(courts)):
            listbox.insert(tk.END, f"Court {i+1}")

    def done_current():
        nonlocal mode, curr_pts
        if len(curr_pts) >= 3:
            courts.append(curr_pts.copy())
            canvas.create_polygon(curr_pts, outline="green", fill="", width=2, tags=f"court{len(courts)-1}")
            refresh_listbox()
        curr_pts = []
        redraw_current()
        mode = "idle"

    def start_add():
        nonlocal mode, curr_pts
        if len(courts) >= max_courts:
            return
        mode = "adding"
        curr_pts = []
        redraw_current()

    def delete_selected():
        sel = listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        courts.pop(idx)
        canvas.delete(f"court{idx}")
        for i in range(idx, len(courts)):
            canvas.itemconfigure(f"court{i+1}", tags=f"court{i}")
        refresh_listbox()

    def finish():
        root.destroy()

    add_btn.configure(command=start_add)
    del_btn.configure(command=delete_selected)
    done_btn.configure(command=done_current)
    finish_btn.configure(command=finish)

    root.mainloop()

    courts_out = []
    for pts in courts:
        if len(pts) < 4:
            continue
        scaled = [[int(p[0] / scale), int(p[1] / scale)] for p in pts[:8]]
        courts_out.append({'points': scaled})
    return courts_out

def create_blue_mask(image):
    """Create a mask for blue areas in the image"""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Get blue range from config
    blue_range = Config.COURT_COLORS["blue"]
    lower = np.array(blue_range["lower"])
    upper = np.array(blue_range["upper"])
    
    # Create mask
    blue_mask = cv2.inRange(hsv, lower, upper)
    
    # Clean up mask
    kernel = np.ones((Config.Morphology.KERNEL_SIZE, Config.Morphology.KERNEL_SIZE), np.uint8)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_OPEN, kernel)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel, iterations=Config.Morphology.ITERATIONS)
    
    return blue_mask
def create_green_mask(image):
    """Create a mask for green areas in the image"""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    
    # Get green range from config
    green_range = Config.COURT_COLORS["green"]
    lower = np.array(green_range["lower"])
    upper = np.array(green_range["upper"])
    
    # Create mask
    green_mask = cv2.inRange(hsv, lower, upper)
    
    # Clean up mask
    kernel = np.ones((Config.Morphology.KERNEL_SIZE, Config.Morphology.KERNEL_SIZE), np.uint8)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel, iterations=Config.Morphology.ITERATIONS)
    
    return green_mask
def is_sky_region(contour, image_height, image_width):
    """Check if a contour is likely to be sky based on position and characteristics"""
    x, y, w, h = cv2.boundingRect(contour)
    
    # Sky is usually at the top of the image
    is_at_top = y < image_height * 0.15
    
    # Sky is usually wide
    is_wide = w > image_width * 0.5
    
    # Sky usually has a small height
    is_short = h < image_height * 0.2
    
    # Check if the contour is likely to be sky
    return is_at_top and (is_wide or is_short)
def process_court_contour(contour, blue_mask, green_mask, height, width):
    """Process a single court contour - designed for multiprocessing"""
    area = cv2.contourArea(contour)
    # Filter by minimum area to avoid noise
    if area < Config.Court.MIN_AREA:
        return None
        
    # Get bounding box for aspect ratio check
    x, y, w, h = cv2.boundingRect(contour)
    
    # Create slightly dilated mask for this blue region to check if it's next to green
    region_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.drawContours(region_mask, [contour], -1, 255, -1)
    
    # Dilate the region mask slightly to check for adjacent green pixels
    kernel = np.ones((15, 15), np.uint8)
    dilated_region = cv2.dilate(region_mask, kernel, iterations=1)
    
    # Check if there's green adjacent to this blue region
    green_nearby = cv2.bitwise_and(green_mask, dilated_region)
    green_nearby_pixels = cv2.countNonZero(green_nearby)
    
    # If there's no green nearby, it's not a court
    if green_nearby_pixels < 100:  # Threshold for minimum green pixels needed
        return None
    
    # Get the blue area itself
    blue_area = cv2.bitwise_and(blue_mask, region_mask)
    blue_pixels = cv2.countNonZero(blue_area)
    
    # Get convex hull for better shape
    hull = cv2.convexHull(contour)
    
    # Approximate polygon
    perimeter = cv2.arcLength(hull, True)
    approx = cv2.approxPolyDP(hull, 0.02 * perimeter, True)
    
    # Calculate centroid
    M = cv2.moments(contour)
    if M["m00"] != 0:
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
    else:
        cx, cy = x + w//2, y + h//2
    
    # Save court info with all required keys
    court_info = {
        'contour': contour,
        'approx': approx,
        'hull': hull,
        'area': area,
        'blue_ratio': 1.0,  # This is a blue region, so ratio is 1
        'green_ratio': green_nearby_pixels / area,
        'blue_mask': blue_area,
        'green_mask': green_nearby,
        'blue_pixels': blue_pixels,
        'green_pixels': green_nearby_pixels,
        'centroid': (cx, cy),
        'bbox': (x, y, w, h)
    }
    
    return court_info
def check_person_on_court(person_data):
    """
    Process a single person to determine court position - designed for multiprocessing
    person_data: tuple of (person, courts)
    Returns: (court_index, area_type)
    """
    person, courts = person_data
    
    # Get the bounding box coordinates
    x1, y1, x2, y2 = person['bbox']
    
    # Calculate the bottom half of the bounding box
    bottom_y1 = y1 + (y2 - y1) // 2  # Start from middle of box
    bottom_y2 = y2  # End at bottom of box
    
    # Create points for the bottom half of the bounding box
    bottom_points = [
        Point(x1, bottom_y1),
        Point(x2, bottom_y1),
        Point(x2, bottom_y2),
        Point(x1, bottom_y2)
    ]
    
    # Check each court
    for court_idx, court in enumerate(courts):
        # Get the court polygon
        approx = court['approx']
        points = approx.reshape(-1, 2)
        court_polygon = Polygon(points)
        
        # Check if any of the bottom points are inside the court
        for point in bottom_points:
            if court_polygon.contains(point):
                # Person is on this court - now determine if they're on blue (in-bounds) or green (out-bounds)
                x, y = int(point.x), int(point.y)
                
                # Check if the point is on blue area (in-bounds)
                blue_mask = court['blue_mask']
                if y < blue_mask.shape[0] and x < blue_mask.shape[1] and blue_mask[y, x] > 0:
                    return court_idx, 'in_bounds'
                
                # Check if the point is on green area (out-bounds)
                green_mask = court['green_mask']
                if y < green_mask.shape[0] and x < green_mask.shape[1] and green_mask[y, x] > 0:
                    return court_idx, 'out_bounds'
                
                # If not specifically on blue or green, consider it in-bounds if the court has more blue than green
                if court['blue_ratio'] > court['green_ratio']:
                    return court_idx, 'in_bounds'
                else:
                    return court_idx, 'out_bounds'
    
    # If we reached here, the person is not on any court
    return -1, 'off_court'
def process_courts_parallel(blue_contours, blue_mask, green_mask, height, width):
    """Process court contours in parallel using multiprocessing"""
    if not Config.MultiProcessing.ENABLED or len(blue_contours) <= 5:
        # For few contours, sequential processing is faster
        courts = []
        for contour in blue_contours:
            court_info = process_court_contour(contour, blue_mask, green_mask, height, width)
            if court_info:
                courts.append(court_info)
                # OutputManager.log(f"Court {len(courts)} accepted: Area={court_info['area']:.1f}, Green nearby pixels={court_info['green_pixels']}", "SUCCESS") # Removed log
        return courts
    
    # For many contours, use multiprocessing
    OutputManager.log(
        f"Processing {len(blue_contours)} possible courts using {Config.MultiProcessing.NUM_PROCESSES} workers",
        "INFO",
    )
    
    # Create a partial function with fixed arguments
    process_func = partial(process_court_contour, blue_mask=blue_mask, green_mask=green_mask, 
                          height=height, width=width)
    
    # Create a pool and process contours in parallel
    with Pool(processes=Config.MultiProcessing.NUM_PROCESSES) as pool:
        results = pool.map(process_func, blue_contours)
    
    # Filter None results and collect valid courts
    courts = [court for court in results if court is not None]
    
    # Log the results # Removed individual court logs
    # for i, court in enumerate(courts):
    #     OutputManager.log(f"Court {i+1} accepted: Area={court['area']:.1f}, Green nearby pixels={court['green_pixels']}", "SUCCESS")
    
    return courts
def analyze_people_positions_parallel(people, courts):
    """Analyze positions of people on courts using multiprocessing, suppressing output."""
    if not people or not courts:
         return [(-1, 'off_court') for _ in people] # Return default if no people or courts

    if not Config.MultiProcessing.ENABLED or len(people) <= 5:
        # For few people, sequential processing is faster
        people_locations = []
        for person in people:
            # Wrap individual check if needed, though less likely source
            with suppress_stdout_stderr():
                 court_idx, area_type = is_person_on_court(person, courts)
            people_locations.append((court_idx, area_type))
        return people_locations
    
    # For many people, use multiprocessing
    OutputManager.log(
        f"Analyzing {len(people)} people with {Config.MultiProcessing.NUM_PROCESSES} workers",
        "INFO",
    )
    
    # Create input data for the pool
    input_data = [(person, courts) for person in people]
    
    # Create a pool and process positions in parallel, suppressing output
    people_locations = []
    try:
        with suppress_stdout_stderr(): # Suppress pool/worker output
             with Pool(processes=Config.MultiProcessing.NUM_PROCESSES) as pool:
                 people_locations = pool.map(check_person_on_court, input_data)
    except Exception as e:
        OutputManager.log(f"Error during parallel position analysis: {e}", "ERROR")
        # Fallback to sequential processing on error
        OutputManager.log("Falling back to sequential position analysis.", "WARNING")
        people_locations = []
        for person_data in input_data:
             with suppress_stdout_stderr():
                 court_idx, area_type = check_person_on_court(person_data)
             people_locations.append((court_idx, area_type))

    return people_locations
def detect_tennis_court(image, debug_folder=None):
    """
    Detect tennis courts in an image using color masking and contour analysis.
    Simplified approach: Every blue area next to green is a court.
    Returns list of tennis court contours.
    
    Optimized for Raspberry Pi Zero with multiprocessing support.
    """
    height, width = image.shape[:2]
    
    # Create masks
    OutputManager.status("Creating blue and green masks...")
    blue_mask = create_blue_mask(image)
    green_mask = create_green_mask(image)
    
    # Save raw masks for debugging
    if debug_folder and Config.DEBUG_MODE and Config.Output.VERBOSE:
        cv2.imwrite(os.path.join(debug_folder, "blue_mask_raw.png"), blue_mask)
        cv2.imwrite(os.path.join(debug_folder, "green_mask_raw.png"), green_mask)
    
    # Find blue contours (potential courts)
    OutputManager.status("Analyzing potential court shapes...")
    blue_contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Process contours in parallel
    valid_courts = process_courts_parallel(blue_contours, blue_mask, green_mask, height, width)
    
    # Save debug visualizations
    if debug_folder and Config.DEBUG_MODE and Config.Output.VERBOSE:
        # Create visualization of masks
        masks_viz = np.zeros((height, width, 3), dtype=np.uint8)
        masks_viz[blue_mask > 0] = [255, 0, 0]  # Blue
        masks_viz[green_mask > 0] = [0, 255, 0]  # Green
        cv2.imwrite(os.path.join(debug_folder, "color_masks.png"), masks_viz)
        
        # Create visualization of all courts
        if valid_courts:
            courts_viz = image.copy()
            for i, court in enumerate(valid_courts):
                # Draw court outline
                cv2.drawContours(courts_viz, [court['approx']], 0, Config.Visual.COURT_OUTLINE_COLOR, 2)
                
                # Add court number
                x, y, w, h = court['bbox']
                cv2.putText(courts_viz, f"Court {i+1}", (x + w//2 - 40, y + h//2),
                           cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            
            cv2.imwrite(os.path.join(debug_folder, "courts_detected.png"), courts_viz)
    
    if valid_courts:
        OutputManager.log(f"Found {len(valid_courts)} tennis courts", "SUCCESS")
    else:
        OutputManager.log("No tennis courts detected", "WARNING")
    
    return valid_courts
def is_person_on_court(person, courts):
    """
    Determine if a person is on a tennis court.
    Returns (court_index, area_type) where area_type is 'in_bounds', 'out_bounds', or 'off_court'
    Uses bottom half of bounding box for more accurate placement.
    """
    # Get the bounding box coordinates
    x1, y1, x2, y2 = person['bbox']
    
    # Calculate the bottom half of the bounding box
    bottom_y1 = y1 + (y2 - y1) // 2  # Start from middle of box
    bottom_y2 = y2  # End at bottom of box
    
    # Create points for the bottom half of the bounding box
    bottom_points = [
        Point(x1, bottom_y1),
        Point(x2, bottom_y1),
        Point(x2, bottom_y2),
        Point(x1, bottom_y2)
    ]
    
    # Check each court
    for court_idx, court in enumerate(courts):
        # Get the court polygon
        approx = court['approx']
        points = approx.reshape(-1, 2)
        court_polygon = Polygon(points)
        
        # Check if any of the bottom points are inside the court
        for point in bottom_points:
            if court_polygon.contains(point):
                # Person is on this court - now determine if they're on blue (in-bounds) or green (out-bounds)
                x, y = int(point.x), int(point.y)
                
                # Check if the point is on blue area (in-bounds)
                blue_mask = court['blue_mask']
                if y < blue_mask.shape[0] and x < blue_mask.shape[1] and blue_mask[y, x] > 0:
                    return court_idx, 'in_bounds'
                
                # Check if the point is on green area (out-bounds)
                green_mask = court['green_mask']
                if y < green_mask.shape[0] and x < green_mask.shape[1] and green_mask[y, x] > 0:
                    return court_idx, 'out_bounds'
                
                # If not specifically on blue or green, consider it in-bounds if the court has more blue than green
                if court['blue_ratio'] > court['green_ratio']:
                    return court_idx, 'in_bounds'
                else:
                    return court_idx, 'out_bounds'
    
    # If we reached here, the person is not on any court
    return -1, 'off_court'
def assign_court_numbers(blue_mask_connected):
    """
    Assign court numbers by clustering blue regions
    Returns a labeled mask where each court has a unique number
    """
    # Find all connected components in the blue mask
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(blue_mask_connected, connectivity=8)
    
    # The first label (0) is the background, so we start from 1
    courts = []
    
    # Filter out small components (noise)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= Config.Court.MIN_AREA:
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            
            # Create a mask for this court
            court_mask = (labels == i).astype(np.uint8) * 255
            
            # Find contours of the court
            contours, _ = cv2.findContours(court_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                contour = contours[0]  # Use the largest contour
                
                # Get convex hull for better shape
                hull = cv2.convexHull(contour)
                
                # Approximate polygon
                perimeter = cv2.arcLength(hull, True)
                approx = cv2.approxPolyDP(hull, 0.02 * perimeter, True)
                
                # Calculate centroid
                M = cv2.moments(contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                else:
                    cx, cy = x + w//2, y + h//2
                
                courts.append({
                    'id': i,
                    'area': area,
                    'bbox': (x, y, w, h),
                    'centroid': centroids[i],
                    'contour': contour,
                    'approx': approx,
                    'hull': hull,
                    'blue_ratio': 1.0,  # This is a blue region
                    'green_ratio': 0.0,  # Will be updated later
                    'blue_mask': court_mask,
                    'green_mask': np.zeros_like(court_mask),  # Will be updated later
                    'blue_pixels': area,
                    'green_pixels': 0  # Will be updated later
                })
    
    # Sort courts by x-coordinate to assign numbers from left to right
    courts.sort(key=lambda c: c['centroid'][0])
    
    # Create a renumbered mask
    court_mask = np.zeros_like(blue_mask_connected, dtype=np.uint8)
    
    # Assign new court numbers (1, 2, 3, ...) to each court based on sorted order
    for i, court in enumerate(courts):
        court_id = i + 1  # Start numbering from 1
        court['court_number'] = court_id
        # Extract original label mask and assign new number
        court_region = (labels == court['id']).astype(np.uint8) * court_id
        court_mask = cv2.add(court_mask, court_region)
    
    return court_mask, courts
def detect_people_ultralytics(model, image, confidence=0.25):
    """
    Detect people using the ultralytics API directly.
    Returns a list of people with their bounding boxes and confidence scores.
    
    This function uses a completely separate codepath for YOLOv8+ models.
    """
    people = []
    
    try:
        # Check if ultralytics is available
        if not ULTRALYTICS_AVAILABLE:
            OutputManager.log("Ultralytics package not installed - required for YOLOv8+ models", "ERROR")
            OutputManager.log("Install with: pip install ultralytics", "INFO")
            return people
            
        # Run prediction with person class only
        results = model.predict(
            image, 
            conf=confidence,  # Confidence threshold
            classes=[0],      # Only detect people (class 0)
            verbose=False     # Don't print progress
        )
        
        # Process results - directly extract people
        if len(results) > 0 and hasattr(results[0], 'boxes'):
            boxes = results[0].boxes
            
            # Check if we found any boxes
            if len(boxes) > 0:
                # OutputManager.log(f"YOLOv8 detected {len(boxes)} people", "SUCCESS") # Removed log
                
                # Process each detection
                for box in boxes:
                    # Get class and confidence
                    cls = int(box.cls.item()) if hasattr(box, 'cls') else 0
                    if cls == 0:  # Person class
                        conf = float(box.conf.item()) if hasattr(box, 'conf') else 0.0
                        
                        # Get coordinates - handle different tensor formats
                        if hasattr(box, 'xyxy'):
                            # Get coordinates as numpy array
                            xyxy = box.xyxy[0].cpu().numpy()
                            x1, y1, x2, y2 = map(int, xyxy)
                            
                            # Calculate center point and foot position
                            center_x = (x1 + x2) // 2
                            center_y = (y1 + y2) // 2
                            foot_x = center_x
                            foot_y = y2  # Bottom of bounding box represents feet
                            
                            # Add to people list
                            people.append({
                                'position': (center_x, center_y),
                                'foot_position': (foot_x, foot_y),
                                'bbox': (x1, y1, x2, y2),
                                'confidence': conf
                            })
            # else: # Removed log
                # OutputManager.log("YOLOv8 found no people in the image", "INFO")
    except Exception as e:
        OutputManager.log(f"Error in ultralytics detection: {str(e)}", "ERROR")
        if "AttributeError" in str(e) and "module 'torch.nn.modules.module'" in str(e):
            OutputManager.log("This seems to be a compatibility issue with PyTorch and ultralytics", "INFO")
            OutputManager.log("Try updating PyTorch: pip install -U torch torchvision", "INFO")
        elif "No module named 'ultralytics'" in str(e):
            OutputManager.log("Ultralytics package is not installed", "ERROR")
            OutputManager.log("Install with: pip install ultralytics", "INFO")
    
    # Log how many people we found # Removed log
    # if people:
    #     OutputManager.log(f"Ultralytics API found {len(people)} people", "SUCCESS")
    # else:
    #     OutputManager.log("No people detected with ultralytics API", "INFO")
        
    return people
def main(use_gui_courts=False):
    """Main function optimized for Raspberry Pi Zero"""
    # Start timer
    start_time = time.time()
    # Initialize detailed timing variables
    duration_court_detection = 0.0
    duration_people_detection = 0.0
    duration_position_analysis = 0.0
    
    # Reset any previously tracked logs
    OutputManager.reset_logs()
    
    # Initialize multiprocessing if enabled
    if Config.MultiProcessing.ENABLED:
        if Config.MultiProcessing.NUM_PROCESSES <= 0:
            Config.MultiProcessing.NUM_PROCESSES = min(3, cpu_count())

        OutputManager.log(f"Multiprocessing enabled with {Config.MultiProcessing.NUM_PROCESSES} processes", "INFO")

    try:
        input_path = Config.Paths.input_path()  # Default input path

        if use_gui_courts:
            # GUI mode skips camera capture and court/people detection
            OutputManager.status("Loading image")
            if input_path == Config.Paths.input_path():
                try:
                    os.makedirs(os.path.dirname(input_path), exist_ok=True)
                    OutputManager.log(f"Created images directory at {os.path.dirname(input_path)}", "INFO")
                except Exception as e:
                    OutputManager.log(f"Cannot create images directory: {str(e)}", "ERROR")

            image = cv2.imread(input_path)
            if image is None:
                OutputManager.log(f"Unable to open the image at {input_path}", "ERROR")
                return 1

            OutputManager.log(
                "Launching GUI to select court positions. Press 'Finish' or 'q' when done", "INFO"
            )
            selected = select_court_positions_gui(image, Config.COURT_POSITIONS)
            if selected:
                Config.COURT_POSITIONS = []
                for b in selected:
                    try:
                        x, y, w, h = b  # backward compatibility if bbox tuple
                        pts = [
                            (x, y),
                            (x + w, y),
                            (x + w, y + h),
                            (x, y + h),
                        ]
                    except Exception:
                        if 'points' in b:
                            pts = [tuple(p) for p in b['points']][:8]
                        else:
                            pts = [
                                tuple(b['top_left']),
                                tuple(b['top_right']),
                                tuple(b['bottom_right']),
                                tuple(b['bottom_left']),
                            ]
                    Config.COURT_POSITIONS.append({'points': pts})
                try:
                    existing_cfg = {}
                    if os.path.exists(CONFIG_FILE):
                        with open(CONFIG_FILE, "r") as f:
                            existing_cfg = json.load(f)
                    existing_cfg["CourtPositions"] = Config.COURT_POSITIONS
                    json_text = json.dumps(existing_cfg, indent=4)
                    with open(CONFIG_FILE, "w") as f:
                        f.write(json_text)
                    OutputManager.log("Court positions saved via GUI", "DEBUG")
                except Exception as e:
                    OutputManager.log(f"Couldn't save court positions: {str(e)}", "WARNING")
            else:
                OutputManager.log("No courts selected in GUI", "WARNING")
            return 0

        # === Camera Logic ===
        if not args.no_camera:  # Attempt camera capture by default
            camera_output_dir = "output"
            camera_output_filename = "input.png"
            camera_output_path = os.path.join(camera_output_dir, camera_output_filename)
            
            OutputManager.log(f"Capturing image to {camera_output_path}", "INFO")
            try:
                # Ensure output directory exists
                os.makedirs(camera_output_dir, exist_ok=True)
                
                # Call takePhoto from the imported module with proper output suppression
                with suppress_stdout_stderr():
                    capture_success = camera_module.takePhoto(
                        output_dir=camera_output_dir,
                        output_filename=camera_output_filename,
                        width=Config.Camera.WIDTH,  # Use width from Config
                        height=Config.Camera.HEIGHT # Use height from Config
                    )
                
                if capture_success:
                    OutputManager.log("Captured image from camera", "SUCCESS")
                    input_path = camera_output_path # Update input path to the captured image
                else:
                    OutputManager.log("Camera capture failed; using default image", "ERROR")
                    # input_path remains Config.Paths.input_path()
            except Exception as cam_e:
                OutputManager.log(f"Camera capture error: {cam_e}", "ERROR")
                OutputManager.log("Using default input image", "WARNING")
                # input_path remains Config.Paths.input_path()
        else:
            OutputManager.log("Camera skipped (--no-camera); using default image", "INFO")
            # input_path is already Config.Paths.input_path()
        # === End Camera Logic ===

        # Load image
        # input_path is now set based on camera logic or default
        try:
            # First ensure the images directory exists if using default input
            if input_path == Config.Paths.input_path():
                try:
                    os.makedirs(os.path.dirname(input_path), exist_ok=True)
                    OutputManager.log(f"Created images dir {os.path.dirname(input_path)}", "INFO")
                except Exception as e:
                    OutputManager.log(f"Cannot create images dir: {e}", "ERROR")
            
            # Load the image
            OutputManager.status("Loading image")
            image = cv2.imread(input_path)
            
            # Check image loaded successfully
            if image is not None:
                OutputManager.log(f"Loaded image {image.shape[1]}x{image.shape[0]}", "SUCCESS")
                if Config.Output.EXTRA_VERBOSE:
                    OutputManager.log(f"Image type {image.dtype}, channels {image.shape[2]}", "INFO")
            else:
                OutputManager.log(f"Cannot open image {input_path}", "ERROR")
                # Show final summary with error and exit
                processing_time = time.time() - start_time
                final_summary = OutputManager.create_final_summary(
                    people_count=None,
                    total_courts=0,
                    output_path=None,
                    processing_time=processing_time,
                    detailed_court_counts={}
                )
                print_error_summary(final_summary)
                return 1
        except Exception as e:
            OutputManager.log(f"Error loading image: {e}", "ERROR")
            processing_time = time.time() - start_time
            final_summary = OutputManager.create_final_summary(
                people_count=None,
                total_courts=0,
                output_path=None,
                processing_time=processing_time,
                detailed_court_counts={}
            )
            print_error_summary(final_summary)
            return 1
        
        # Set up debug folder
        try:
            if Config.DEBUG_MODE:
                debug_folder = Config.Paths.debug_dir()
                os.makedirs(debug_folder, exist_ok=True)
                OutputManager.log(f"Debug folder: {debug_folder}", "DEBUG")
            else:
                debug_folder = None
        except Exception as e:
            OutputManager.log(f"Could not create debug folder: {e}", "WARNING")
            debug_folder = None  # Set to None to prevent further debug saves
            # Continue execution even if debug folder can't be created

        # Detect tennis courts
        t_start_court = time.time() # Start timing for court detection

        if court_positions_defined():
            OutputManager.log("Using saved court positions from config", "INFO")
            height, width = image.shape[:2]
            court_numbers_mask = np.zeros((height, width), dtype=np.uint8)
            court_mask = np.zeros((height, width), dtype=np.uint8)
            courts = []
            for idx, court in enumerate(Config.COURT_POSITIONS):
                pts = np.array(court.get('points', [])[:8], dtype=np.int32)
                if len(pts) < 4:
                    continue
                cv2.fillPoly(court_numbers_mask, [pts], idx + 1)
                cv2.fillPoly(court_mask, [pts], 255)
                xs = pts[:,0]
                ys = pts[:,1]
                x, y = int(xs.min()), int(ys.min())
                w, h = int(xs.max() - xs.min()), int(ys.max() - ys.min())
                approx = pts.reshape(-1,1,2)
                courts.append({
                    'court_number': idx + 1,
                    'bbox': (x, y, w, h),
                    'centroid': (x + w / 2, y + h / 2),
                    'approx': approx,
                    'contour': approx,
                    'hull': approx,
                    'blue_ratio': 1.0,
                    'green_ratio': 0.0,
                    'blue_mask': np.zeros((height, width), dtype=np.uint8),
                    'green_mask': np.zeros((height, width), dtype=np.uint8),
                    'area': w * h,
                    'blue_pixels': w * h,
                    'green_pixels': 0
                })
            blue_mask_raw = np.zeros((height, width), dtype=np.uint8)
            green_mask = np.zeros((height, width), dtype=np.uint8)
            court_mask_viz = np.zeros((height, width, 3), dtype=np.uint8)
            court_mask_viz[court_mask > 0] = [255, 127, 0]
            valid_regions = len(courts)
            duration_court_detection = 0.0
        else:
            try:
                OutputManager.status("Finding courts...") # Consolidated status
            # OutputManager.status("Analyzing court colors") # Removed
                blue_mask = create_blue_mask(image)
                green_mask = create_green_mask(image)
                # OutputManager.log("Court colors analyzed", "SUCCESS") # Removed
                if Config.Output.EXTRA_VERBOSE:
                    OutputManager.log(f"Blue mask: {np.count_nonzero(blue_mask)} pixels, Green mask: {np.count_nonzero(green_mask)} pixels", "INFO")
                
                # Process the raw blue mask to avoid connecting unrelated areas like the sky
                blue_mask_raw = blue_mask.copy()
                
                # Create court mask where green overrides blue
                height, width = image.shape[:2]
                court_mask = np.zeros((height, width), dtype=np.uint8)
                court_mask[blue_mask_raw > 0] = 1  # Blue areas
                court_mask[green_mask > 0] = 0     # Green areas override blue
                
                # Filter out blue regions that don't have any green nearby (like sky)
                # OutputManager.status("Processing court regions") # Removed
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(blue_mask_raw, connectivity=8)
                if Config.Output.EXTRA_VERBOSE:
                     OutputManager.log(f"Found {num_labels-1} initial connected blue regions", "DEBUG")
                
                # For each blue region, check if there's green nearby
                filtered_court_mask = np.zeros_like(court_mask)
                valid_regions = 0
                
                for i in range(1, num_labels):
                    region = (labels == i).astype(np.uint8)
                    area = stats[i, cv2.CC_STAT_AREA]
                    
                    # Skip very small regions
                    if area < Config.Court.MIN_AREA:
                        continue
                    
                    # Dilate the region to check for nearby green
                    kernel = np.ones((15, 15), np.uint8)
                    dilated_region = cv2.dilate(region, kernel, iterations=1)
                    
                    # Check if there's green nearby this blue region
                    green_nearby = cv2.bitwise_and(green_mask, dilated_region)
                    green_nearby_pixels = cv2.countNonZero(green_nearby)
                    
                    # Only keep blue regions that have at least some green nearby
                    if green_nearby_pixels > 30:  # Reduced from 50 to be more lenient
                        # This is likely a court (not sky) - keep it
                        filtered_court_mask[region > 0] = court_mask[region > 0]
                        valid_regions += 1
                        if Config.Output.EXTRA_VERBOSE:
                            OutputManager.log(f"Region {i}: area={area}, green nearby={green_nearby_pixels} - likely court", "DEBUG")
                
                # OutputManager.log(f"Court regions processed: {valid_regions} valid regions found", "SUCCESS") # Removed
                
                # Use the filtered court mask for further processing
                court_mask = filtered_court_mask
            except Exception as e:
                OutputManager.log(f"Error processing court colors/regions: {str(e)}", "ERROR")
                # Continue with blank masks as a fallback
                height, width = image.shape[:2]
                blue_mask_raw = np.zeros((height, width), dtype=np.uint8)
                green_mask = np.zeros((height, width), dtype=np.uint8)
                court_mask = np.zeros((height, width), dtype=np.uint8)
                valid_regions = 0 # Ensure this is defined

        if Config.Output.EXTRA_VERBOSE:
            OutputManager.log(f"Valid blue regions kept: {valid_regions}", "INFO")

        # Save raw masks for debugging
        if debug_folder and Config.DEBUG_MODE:
            try:
                cv2.imwrite(os.path.join(debug_folder, "blue_mask_raw.png"), blue_mask_raw)
                cv2.imwrite(os.path.join(debug_folder, "green_mask.png"), green_mask)
                cv2.imwrite(os.path.join(debug_folder, "filtered_court_mask.png"), court_mask * 255)
                OutputManager.log("Saved debug masks", "DEBUG")
            except Exception as e:
                OutputManager.log(f"Could not save debug masks: {e}", "WARNING")
        
        # Create colored visualization of masks
        try:
            court_mask_viz = np.zeros((height, width, 3), dtype=np.uint8)
            court_mask_viz[blue_mask_raw > 0] = [255, 0, 0]  # Blue for all blue areas
            court_mask_viz[green_mask > 0] = [0, 255, 0]     # Green areas override blue
            
            # Highlight filtered courts in a brighter blue
            filtered_blue = np.zeros_like(court_mask_viz)
            filtered_blue[court_mask > 0] = [255, 127, 0]  # Bright blue for valid courts
            cv2.addWeighted(court_mask_viz, 1, filtered_blue, 0.7, 0, court_mask_viz)
        except Exception as e:
            OutputManager.log(f"Court visualization error: {e}", "WARNING")
            court_mask_viz = image.copy()  # Use original image as fallback
        
        # Assign court numbers to each separate blue region if not preloaded
        if not court_positions_defined():
            try:
                court_numbers_mask, courts = assign_court_numbers(court_mask)

                # Output appropriate message based on court detection
                if len(courts) == 0:
                    OutputManager.log("No tennis courts found in the image", "WARNING")
                else:
                    OutputManager.log(f"Found {len(courts)} tennis court{'s' if len(courts) > 1 else ''}", "SUCCESS")
                    if Config.Output.EXTRA_VERBOSE:
                        for i, court in enumerate(courts):
                            cx, cy = court['centroid']
                            area = court['area']
                            OutputManager.log(f"Court {i+1}: center=({int(cx)}, {int(cy)}), area={area:.1f} pixels", "DEBUG")
            except Exception as e:
                OutputManager.log(f"Error identifying courts: {str(e)}", "ERROR")
                courts = []
                court_numbers_mask = np.zeros_like(court_mask)

        if not court_positions_defined() and courts:
            # Save detected court points for JSON serialization
            Config.COURT_POSITIONS = []
            for c in courts:
                pts = [tuple(map(int, p)) for p in c['approx'].reshape(-1, 2)[:8]]
                if len(pts) < 4:
                    x, y, w, h = [int(v) for v in c['bbox']]
                    pts = [
                        (x, y),
                        (x + w, y),
                        (x + w, y + h),
                        (x, y + h),
                    ]
                Config.COURT_POSITIONS.append({'points': pts})

            try:
                with open(CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}

            cfg['CourtPositions'] = Config.COURT_POSITIONS

            # Serialize to a string first to avoid corrupting the file if it fails
            try:
                json_text = json.dumps(cfg, indent=4)
                with open(CONFIG_FILE, 'w') as f:
                    f.write(json_text)
                OutputManager.log("Saved court positions to config", "DEBUG")
            except Exception as e:
                OutputManager.log(f"Couldn't save court positions: {str(e)}", "WARNING")
        
        # Create a color-coded court mask for visualization
        try:
            court_viz = np.zeros((height, width, 3), dtype=np.uint8)
            
            # Assign different colors to each court
            court_colors = [
                (64, 128, 255),    # Light Blue
                (255, 64, 64),    # Light Red
                (128, 64, 255),  # Light Purple
                (64, 255, 128),   # Light Green
                (255, 128, 64),   # Light Orange
                (128, 255, 64)    # Lime Green
            ]
            
            # Draw each court with a different color
            for court in courts:
                court_id = court['court_number']
                color_idx = (court_id - 1) % len(court_colors)
                court_color = court_colors[color_idx]
                
                # Extract court mask
                court_mask_individual = (court_numbers_mask == court_id).astype(np.uint8) * 255
                # Find contours of the court
                court_contours, _ = cv2.findContours(court_mask_individual, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # Draw the court area
                court_area = np.zeros_like(court_viz)
                court_area[court_mask_individual > 0] = court_color
                cv2.addWeighted(court_viz, 1, court_area, 0.7, 0, court_viz)
                
                # Draw court number at center only if enabled in debug visualizations too
                if hasattr(Config.Visual, 'SHOW_COURT_LABELS') and Config.Visual.SHOW_COURT_LABELS:
                    cx, cy = int(court['centroid'][0]), int(court['centroid'][1])
                    cv2.putText(court_viz, f"Court {court_id}", (cx-40, cy), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        except Exception as e:
            OutputManager.log(f"Error creating court visualization: {str(e)}", "WARNING")
            court_viz = image.copy()  # Use original image as fallback
        
        # Save court visualization
        if debug_folder and Config.DEBUG_MODE:
            try:
                cv2.imwrite(os.path.join(debug_folder, "courts_numbered.png"), court_viz)
                OutputManager.log("Saved court visualization", "DEBUG")
            except Exception as e:
                OutputManager.log(f"Could not save court visualization: {e}", "WARNING")
        
        # Create a semi-transparent overlay of the masks on the original image
        try:
            alpha = 0.5  # Transparency factor
            mask_overlay = image.copy()
            # Apply the colored masks with transparency
            cv2.addWeighted(court_mask_viz, alpha, mask_overlay, 1 - alpha, 0, mask_overlay)
        except Exception as e:
            OutputManager.log(f"Mask overlay error: {e}", "WARNING")
            mask_overlay = image.copy()  # Use original image as fallback

        duration_court_detection = time.time() - t_start_court

        # Detect people
        people = []
        model_path = None # Initialize model_path
        t_start_people = time.time() # Start timing for people detection (includes download & load)
        try:
            OutputManager.status("Looking for people")
            
            # Check if models directory exists
            models_dir = Config.Paths.MODELS_DIR
            if not os.path.exists(models_dir):
                try:
                    os.makedirs(models_dir, exist_ok=True)
                    OutputManager.log(f"Created models directory at {models_dir}", "DEBUG") # Changed to DEBUG
                except Exception as e:
                    OutputManager.log(f"Cannot create models directory: {str(e)}", "ERROR")
                    # If we can't create models dir, we likely can't proceed with model loading
                    raise e 
            
            # Get the model name from config and download if needed
            model_name = Config.Model.NAME
            OutputManager.log(f"Selected model: {model_name}", "INFO")
            
            # Check if SSL verification should be disabled
            disable_ssl = False
            if hasattr(args, 'disable_ssl_verify') and args.disable_ssl_verify:
                disable_ssl = True
            
            try:
                # Download model if it doesn't exist (or use existing)
                model_path = download_yolo_model(
                    model_name, 
                    url=Config.Model.get_model_url(model_name),
                    disable_ssl_verify=disable_ssl
                )
                # Update model_name based on potential fallback in download function
                model_name = Config.Model.NAME 
            except Exception as e:
                 # If download/fallback fails, try YOLOv5s as a last resort if not already tried
                if model_name != "yolov5s":
                    OutputManager.log(f"Falling back to YOLOv5s model after error with {model_name}", "WARNING")
                    try:
                        model_path = download_yolo_model(
                            "yolov5s", 
                            url=Config.Model.get_model_url("yolov5s"),
                            disable_ssl_verify=True  # Force disable SSL for fallback
                        )
                        model_name = "yolov5s"
                        Config.Model.NAME = "yolov5s" # Ensure config matches
                    except Exception as e2:
                         OutputManager.log(f"Failed to download or find fallback model yolov5s: {str(e2)}", "FATAL")
                         raise Exception(f"Essential model assets could not be obtained. Original error: {str(e)}. Fallback error: {str(e2)}")
                else:
                    OutputManager.log(f"Failed to obtain model {model_name}: {str(e)}", "FATAL")
                    raise e
            
            # Load the YOLO model with better error handling
            model = None
            try:
                # OutputManager.status(f"Loading model: {Config.Model.NAME}") # Removed
                # Determine model type AFTER potential download/fallback
                is_yolo_v8_or_newer_load = (Config.Model.NAME.startswith("yolov8") or 
                                          any(Config.Model.NAME.lower().startswith(f"yolov{v}") for v in range(9, 20)))

                if is_yolo_v8_or_newer_load:
                    if not ULTRALYTICS_AVAILABLE:
                        OutputManager.log("Ultralytics package not installed. Cannot load YOLOv8+ model.", "ERROR")
                        OutputManager.log("Please install with: pip install ultralytics", "INFO")
                        # Cannot proceed without ultralytics for these models
                        raise ImportError("Ultralytics package required for this model is not installed.")
                    else:
                        with suppress_stdout_stderr(): # Suppress Ultralytics init messages
                            from ultralytics import YOLO # type: ignore
                            model = YOLO(model_path) 
                else: # YOLOv5
                    with suppress_stdout_stderr():
                        model = torch.hub.load('ultralytics/yolov5', 'custom', path=model_path, verbose=False)
                
                if model is not None:
                    OutputManager.log(f"Loaded model {Config.Model.NAME}", "SUCCESS")
                else:
                    # This case should ideally be caught earlier, but adding safeguard
                    raise Exception(f"Model {Config.Model.NAME} could not be loaded despite successful download/find.")

            except Exception as e:
                # Handle SSL certificate errors during download/load more gracefully if they reach here
                if "ssl" in str(e).lower() and not disable_ssl and not is_yolo_v8_or_newer_load: # SSL context mainly for hub
                    OutputManager.log(f"SSL error loading model via torch hub: {str(e)}", "WARNING")
                    OutputManager.log(f"Attempting to reload {Config.Model.NAME} with SSL verification disabled for hub load.", "INFO")
                    try:
                        original_ssl_context = ssl._create_default_https_context
                        ssl._create_default_https_context = ssl._create_unverified_context
                        with suppress_stdout_stderr():
                             model = torch.hub.load('ultralytics/yolov5', 'custom', path=model_path, verbose=False, force_reload=True)
                        ssl._create_default_https_context = original_ssl_context
                        if model is not None:
                             OutputManager.log(f"Reloaded {Config.Model.NAME} with SSL disabled", "SUCCESS")
                        else: raise Exception("SSL Retry load returned None")
                    except Exception as e_ssl_retry:
                        ssl._create_default_https_context = original_ssl_context # Restore context
                        OutputManager.log(f"SSL retry failed: {e_ssl_retry}", "ERROR")
                        raise e # Re-raise original error
                else:
                    OutputManager.log(f"Error loading model {Config.Model.NAME}: {e}", "ERROR")
                    # Attempt to create a summary and exit
                    processing_time = time.time() - start_time
                    final_summary_str = OutputManager.create_final_summary(
                        people_count=None,
                        total_courts=len(courts) if 'courts' in locals() else 0,
                        output_path=None,
                        processing_time=processing_time,
                        detailed_court_counts={}
                    )
                    OutputManager.fancy_summary("ERROR SUMMARY", final_summary_str, processing_time=processing_time, is_error=True)
                    return 1 # Exit due to model load failure
            
            # Run detection
            # OutputManager.status("Running person detection") # Removed
            pred_results = None
            
            with suppress_stdout_stderr(): # Wrap all prediction calls
                try:
                    current_model_name = Config.Model.NAME # Get current model name, could have changed due to fallback
                    is_yolo_v8_or_newer_runtime = (current_model_name.startswith("yolov8") or 
                                                 any(current_model_name.lower().startswith(f"yolov{v}") for v in range(9, 20)))

                    if is_yolo_v8_or_newer_runtime and ULTRALYTICS_AVAILABLE and model is not None:
                        # Ensure model is the correct type if ultralytics is used
                        if not isinstance(model, ultralytics.YOLO):
                            OutputManager.log(f"Model type mismatch for {current_model_name}. Expected Ultralytics YOLO object.", "WARNING")
                            # Attempt re-load just in case
                            with suppress_stdout_stderr(): model = ultralytics.YOLO(model_path)
                        pred_results = model.predict(image, classes=Config.Model.CLASSES, conf=Config.Model.CONFIDENCE, verbose=False)
                    elif model: # Assuming YOLOv5 or a hub-loaded model
                        # Set attributes for hub model if necessary (might be redundant if always set, but safe)
                        if not is_yolo_v8_or_newer_runtime: 
                             model.conf = Config.Model.CONFIDENCE
                             model.iou = Config.Model.IOU 
                             model.classes = Config.Model.CLASSES
                        # Force CPU device on Raspberry Pi Zero for non-Ultralytics YOLO models
                        if not (is_yolo_v8_or_newer_runtime and ULTRALYTICS_AVAILABLE) and "arm" in platform.machine().lower():
                             if hasattr(model, 'cpu'): model.cpu()
                             OutputManager.log("Using CPU for YOLO inference (Raspberry Pi)", "DEBUG")
                        pred_results = model(image)
                    else:
                        OutputManager.log("Model not available for prediction.", "ERROR")
                        # Handle error appropriately, e.g., by setting people to empty and allowing summary
                        people = [] # Ensure people is empty
                        pred_results = [] # Ensure results is empty/list

                except RuntimeError as e:
                    if "out of memory" in str(e).lower():
                        OutputManager.log("CUDA out of memory; trying smaller image", "WARNING")
                        scale_factor = 0.5  # Scale to 50%
                        small_img_width = int(image.shape[1] * scale_factor)
                        small_img_height = int(image.shape[0] * scale_factor)
                        small_img = cv2.resize(image, (small_img_width, small_img_height))
                        
                        # Retry prediction on smaller image
                        with suppress_stdout_stderr(): # Suppress output for retry as well
                            if is_yolo_v8_or_newer_runtime and ULTRALYTICS_AVAILABLE and model is not None:
                                pred_results = model.predict(small_img, classes=Config.Model.CLASSES, conf=Config.Model.CONFIDENCE, verbose=False)
                            elif model:
                                pred_results = model(small_img)
                        OutputManager.log(
                            f"Used scaled image {small_img.shape[1]}x{small_img.shape[0]} for detection",
                            "INFO",
                        )
                    else:
                        OutputManager.log(f"Runtime error during prediction: {str(e)}", "ERROR")
                        raise e # Re-raise other runtime errors
                except Exception as e_pred:
                    OutputManager.log(f"Unexpected error during prediction: {str(e_pred)}", "ERROR")
                    # Log traceback if debug enabled
                    if Config.DEBUG_MODE:
                         OutputManager.log(traceback.format_exc(), "DEBUG")
                    people = [] # Ensure people list is empty on prediction failure
                    pred_results = [] # Ensure results is empty/list
            
            # Process results
            # OutputManager.status("Processing detection results") # Removed
            
            # Skip processing if YOLOv8/v12 already handled (Revisit this logic - seems results are now unified)
            # if not ('skip_processing' in locals() and skip_processing):
            
            # Handle different model result formats
            current_model_name = Config.Model.NAME # Use potentially updated name
            is_newer_yolo = (current_model_name.startswith("yolov8") or 
                             any(current_model_name.lower().startswith(f"yolov{v}") for v in range(9, 20)))
            
            people = [] # Reset people list before processing results
            if pred_results is not None:
                try:
                     # Check if this is YOLOv8 or newer model (ultralytics results)
                     if is_newer_yolo and ULTRALYTICS_AVAILABLE:
                         # Process Ultralytics results (typically a list of Results objects)
                         if isinstance(pred_results, list) and len(pred_results) > 0:
                             boxes = pred_results[0].boxes # Access boxes from the first Results object
                             if boxes is not None and len(boxes) > 0:
                                 for box in boxes:
                                     cls_id = int(box.cls.item()) if box.cls is not None else -1
                                     if cls_id in Config.Model.CLASSES:
                                         conf = float(box.conf.item()) if box.conf is not None else 0.0
                                         if conf >= Config.Model.CONFIDENCE:
                                             xyxy = box.xyxy[0].cpu().numpy()
                                             x1, y1, x2, y2 = map(int, xyxy)
                                             people.append({
                                                 'position': ((x1 + x2) // 2, (y1 + y2) // 2),
                                                 'foot_position': ((x1 + x2) // 2, y2),
                                                 'bbox': (x1, y1, x2, y2),
                                                 'confidence': conf
                                             })
                         else:
                              OutputManager.log(f"No detections found in Ultralytics results for {current_model_name}.", "INFO")

                     else: # YOLOv5 results format - using pandas
                         df = pred_results.pandas().xyxy[0]
                         # Filter by class (person is class 0)
                         df_people = df[df['class'].isin(Config.Model.CLASSES)]
                         
                         for _, row in df_people.iterrows():
                             if row['confidence'] >= Config.Model.CONFIDENCE:
                                 x1, y1, x2, y2 = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
                                 people.append({
                                     'position': ((x1 + x2) // 2, (y1 + y2) // 2),
                                     'foot_position': ((x1 + x2) // 2, y2),
                                     'bbox': (x1, y1, x2, y2),
                                     'confidence': row['confidence']
                                 })
                except AttributeError as e_attr:
                     # Handle specific errors like missing 'pandas' for YOLOv8 results processed incorrectly
                     if "'list' object has no attribute 'pandas'" in str(e_attr) and is_newer_yolo:
                         OutputManager.log(f"Attempted to process {current_model_name} results using YOLOv5 format. Check model loading logic.", "ERROR")
                         # Potentially try reprocessing as Ultralytics results if pred_results look like it
                     else:
                         OutputManager.log(f"Error processing detection results: {str(e_attr)}", "ERROR")
                         if Config.DEBUG_MODE: OutputManager.log(traceback.format_exc(), "DEBUG")
                except Exception as e_proc:
                     OutputManager.log(f"Unexpected error processing results: {str(e_proc)}", "ERROR")
                     if Config.DEBUG_MODE: OutputManager.log(traceback.format_exc(), "DEBUG")

            # Log final count after processing
            if people:
                 OutputManager.log(f"Detected {len(people)} {'person' if len(people) == 1 else 'people'} matching criteria.", "SUCCESS")
            else:
                 OutputManager.log("No people detected matching criteria.", "INFO")

            # Log details if extra verbose - KEEPING THIS FOR DEBUGGING
            if Config.Output.EXTRA_VERBOSE and people:
                 OutputManager.log("--- Detected People Details ---", "DEBUG")
                 for i, person in enumerate(people):
                     x1, y1, x2, y2 = person['bbox']
                     conf = person['confidence']
                     OutputManager.log(f"  Person {i+1}: bbox=({x1},{y1},{x2},{y2}), confidence={conf:.2f}", "DEBUG")
                 OutputManager.log("----------------------------- ", "DEBUG")
        except Exception as e:
            error_msg = str(e)
            # Consolidate error logging for people detection phase
            OutputManager.log(f"Error during people detection phase: {error_msg}", "ERROR")
            # Add specific advice based on error type if possible
            if isinstance(e, ImportError) and "Ultralytics" in error_msg:
                OutputManager.log(" -> Please install Ultralytics: pip install ultralytics", "INFO")
            elif "CUDA out of memory" in error_msg:
                 OutputManager.log(" -> Try using a smaller model or the --device cpu flag.", "INFO")
            elif isinstance(e, FileNotFoundError):
                 OutputManager.log(" -> Check model path and file existence.", "INFO")
            elif Config.DEBUG_MODE:
                 OutputManager.log(traceback.format_exc(), "DEBUG")
            
            people = [] # Ensure people list is empty on error
        
        duration_people_detection = time.time() - t_start_people # End timing for people detection

        # Determine if each person is on a court
        people_locations = []
        detailed_court_counts = {} # For summary: {court_num: {'in_bounds': 0, 'out_bounds': 0}}
        # Initialize counts for summary, even if no people/courts found later
        in_bounds_count, out_bounds_count, off_court_count = 0,0,0

        t_start_pos = time.time() # Start timing for position analysis
        try:
            if people and courts:
                # OutputManager.status("Analyzing positions using multiprocessing") # Removed status
                
                # Process in parallel using our optimized function
                people_locations = analyze_people_positions_parallel(people, courts)
                
                OutputManager.log("Position analysis complete", "SUCCESS") # Simplified message
                
                # Count people by location type FOR SUMMARY
                in_bounds_count = sum(1 for _, area_type in people_locations if area_type == 'in_bounds')
                out_bounds_count = sum(1 for _, area_type in people_locations if area_type == 'out_bounds')
                off_court_count = sum(1 for _, area_type in people_locations if area_type == 'off_court')
                
                # OutputManager.log(f"Position breakdown: {in_bounds_count} in-bounds, {out_bounds_count} sidelines, {off_court_count} off-court", "INFO") # Removed log
            else:
                # If no people or no courts, no need to analyze positions
                people_locations = [(-1, 'off_court') for _ in range(len(people))]
                in_bounds_count, out_bounds_count, off_court_count = 0, 0, len(people)
        except Exception as e:
            OutputManager.log(f"Error analyzing positions: {str(e)}", "ERROR")
            # Create fallback position data
            people_locations = [(-1, 'off_court') for _ in range(len(people))]
            in_bounds_count, out_bounds_count, off_court_count = 0, 0, len(people)
        
        duration_position_analysis = time.time() - t_start_pos # End timing for position analysis

        # Calculate court_counts for detailed summary (on court vs sideline)
        # This replaces the old simple court_counts which was just total people per court
        detailed_court_counts = {} 
        for person_idx, (court_idx, area_type) in enumerate(people_locations):
            if court_idx >= 0:
                court_num = court_idx + 1
                if court_num not in detailed_court_counts:
                    detailed_court_counts[court_num] = {'in_bounds': 0, 'out_bounds': 0}
                if area_type == 'in_bounds':
                    detailed_court_counts[court_num]['in_bounds'] += 1
                elif area_type == 'out_bounds': # 'out_bounds' corresponds to sideline
                    detailed_court_counts[court_num]['out_bounds'] += 1
        
        # Create final output image
        try:
            OutputManager.status("Rendering output image")
            output_image = image.copy()
            
            # Draw court outlines with different colors
            for court in courts:
                court_id = court['court_number']
                color_idx = (court_id - 1) % len(court_colors)
                court_color = court_colors[color_idx]
                
                # Extract court mask
                court_mask_individual = (court_numbers_mask == court_id).astype(np.uint8) * 255
                # Find contours of the court
                court_contours, _ = cv2.findContours(court_mask_individual, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                # Draw the court outline
                cv2.drawContours(output_image, court_contours, -1, court_color, 2)
                
                # Draw court number at center only if enabled
                if Config.Visual.SHOW_COURT_NUMBER:
                    cx, cy = int(court['centroid'][0]), int(court['centroid'][1])
                    cv2.putText(output_image, f"Court {court_id}", (cx-40, cy), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            
            # Draw people and their locations
            for i, person in enumerate(people):
                court_idx, area_type = people_locations[i]
                
                # Draw bounding box and label
                x1, y1, x2, y2 = person['bbox']
                
                # Choose color based on location
                if court_idx >= 0:
                    court_number = court_idx + 1
                    if area_type == 'in_bounds':
                        color = Config.Visual.PERSON_IN_BOUNDS_COLOR
                        label = f"Court {court_number}" if Config.Visual.SHOW_DETAILED_LABELS else ""
                    else:  # out_bounds
                        color = Config.Visual.PERSON_OUT_BOUNDS_COLOR
                        label = f"Court {court_number} • Sideline" if Config.Visual.SHOW_DETAILED_LABELS else ""
                else:
                    color = Config.Visual.PERSON_OFF_COURT_COLOR
                    label = "Not on court" if Config.Visual.SHOW_DETAILED_LABELS else ""
                
                # Draw bounding box
                cv2.rectangle(output_image, (x1, y1), (x2, y2), color, 2)
                
                # Draw foot position marker - smaller and less intrusive
                foot_x, foot_y = person['foot_position']
                cv2.circle(output_image, (foot_x, foot_y), 3, color, -1)
                
                # Only draw text labels if specified
                if Config.Visual.SHOW_DETAILED_LABELS and label:
                    # Draw label with black background for readability
                    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 
                                               Config.Visual.FONT_SCALE, 
                                               Config.Visual.TEXT_THICKNESS)[0]
                    cv2.rectangle(output_image, (x1, y1 - text_size[1] - 5), 
                                 (x1 + text_size[0], y1), color, -1)
                    cv2.putText(output_image, label, (x1, y1 - 5), 
                               cv2.FONT_HERSHEY_SIMPLEX, 
                               Config.Visual.FONT_SCALE, 
                               Config.Visual.TEXT_COLOR, 
                               Config.Visual.TEXT_THICKNESS)
                    
                    # Add person index number
                    cv2.putText(output_image, f"Person {i+1}", (x1, y2 + 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, Config.Visual.FONT_SCALE, 
                                color, Config.Visual.TEXT_THICKNESS)
                else:
                    # Just add a small number indicator for simpler display
                    cv2.putText(output_image, f"{i+1}", (x1, y1 - 5), 
                               cv2.FONT_HERSHEY_SIMPLEX, 
                               Config.Visual.FONT_SCALE, 
                               Config.Visual.TEXT_COLOR, 
                               Config.Visual.TEXT_THICKNESS)
            
            OutputManager.log("Output image created", "SUCCESS")
        except Exception as e:
            OutputManager.log(f"Error creating output image: {e}", "ERROR")
            output_image = image.copy()  # Use original image as fallback
        
        # Save the final output image
        output_path = Config.Paths.output_path()
        try:
            OutputManager.status("Saving results")
            
            # Ensure output directory exists
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    OutputManager.log(f"Created output dir {output_dir}", "INFO")
                except Exception as e:
                    OutputManager.log(f"Cannot create output dir: {e}", "ERROR")
            
            cv2.imwrite(output_path, output_image)
            OutputManager.log(f"Results saved to {output_path}", "SUCCESS")
        except Exception as e:
            OutputManager.log(f"Error saving output image: {e}", "ERROR")
            output_path = None
        
        # Create the adaptive final summary
        processing_time = time.time() - start_time
        # OutputManager.log(f"Total processing time: {processing_time:.2f} seconds", "INFO") # Removed log
        
        final_summary = OutputManager.create_final_summary(
            people_count=len(people),
            total_courts=len(courts),
            output_path=output_path,
            # processing_time is handled by fancy_summary for total time
            detailed_court_counts=detailed_court_counts,
            duration_court_detection=duration_court_detection,
            duration_people_detection=duration_people_detection,
            duration_position_analysis=duration_position_analysis
        )
        
        # Use the fancy summary method
        OutputManager.fancy_summary(
            "RESULTS SUMMARY", 
            final_summary, 
            processing_time=processing_time
        )
        
        # If there were errors that didn't cause a fatal exit, still indicate an error status
        if OutputManager.errors:
            return 1
        
        return 0
    except Exception as e:
        # This is the main catch-all for any unhandled exceptions in the try block
        OutputManager.log(f"Unhandled error in main function: {str(e)}", "ERROR")
        
        # Create a basic summary with the error
        processing_time = time.time() - start_time
        final_summary = OutputManager.create_final_summary(
            people_count=None,
            total_courts=0,
            output_path=None,
            processing_time=processing_time,
            detailed_court_counts={}
        )
        print_error_summary(final_summary)
        return 1
# Add a backward compatibility wrapper for the old log function
def log(message, level="INFO"):
    """Wrapper for backward compatibility with the old log function"""
    OutputManager.log(message, level)
def print_error_summary(summary):
    """Print error summary with the fancy box style and troubleshooting information"""
    # First clear any lingering output
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()
    
    # Add troubleshooting section if errors are present
    if OutputManager.errors:
        # Get the potential fixes
        fixes = OutputManager.get_potential_fixes()
        if fixes:
            if "TROUBLESHOOTING" not in summary:
                summary += "\n\nTROUBLESHOOTING"
                for fix_line in fixes.split('\n'):
                    summary += f"\n{fix_line}"
        
        # Add common checking steps if not already present
        if "requirements.txt" not in summary:
            summary += "\n\nBASIC CHECKS:"
            summary += "\n1. Ensure all dependencies are installed: pip install -r requirements.txt"
            summary += "\n2. Check that the input image exists and is readable"
            summary += "\n3. Verify YOLOv5 model is downloaded in models/ directory"
            summary += "\n4. Check for sufficient disk space and permissions"
            summary += "\n5. Run with --debug flag for more detailed information"
    
    # Use the fancy summary with an error title
    is_error = bool(OutputManager.errors)
    title = "ERROR SUMMARY" if is_error else "WARNING SUMMARY"
    OutputManager.fancy_summary(title, summary, is_error=is_error)
    
    # Flush to ensure immediate display
    sys.stdout.flush()
def download_yolo_model(model_name, url=None, disable_ssl_verify=False):
    """Download YOLO model if it doesn't exist, or use existing model in directory."""
    models_dir = Config.Paths.MODELS_DIR
    os.makedirs(models_dir, exist_ok=True)
    
    model_path = os.path.join(models_dir, f"{model_name}.pt")
    
    # Check if the specified model exists
    if os.path.exists(model_path):
        OutputManager.log(f"Model file found: {model_name}.pt", "SUCCESS")
        return model_path
    
    # If specified model not found, check for *any* .pt file in the models directory
    OutputManager.log(f"Model file '{model_name}.pt' not found locally", "WARNING")
    try:
        existing_models = [f for f in os.listdir(models_dir) if f.endswith('.pt')]
        if existing_models:
            # Sort to ensure consistent selection (e.g., alphabetical)
            existing_models.sort()
            fallback_model_name = os.path.splitext(existing_models[0])[0]
            fallback_model_path = os.path.join(models_dir, existing_models[0])
            OutputManager.log(f"Found local model file {existing_models[0]}", "INFO")
            # Update Config to reflect the model being used (important for later logic)
            Config.Model.NAME = fallback_model_name
            return fallback_model_path
        else:
            OutputManager.log("No models found locally", "INFO")
    except OSError as e:
        OutputManager.log(f"Could not scan models directory: {e}", "WARNING")
        # Continue to download attempt

    # Proceed to download if no local model is found or used
    OutputManager.log(f"Downloading model {model_name}", "INFO")
    
    # Get URL if not provided
    if url is None:
        url = Config.Model.get_model_url(model_name)
    
    OutputManager.status(f"Downloading {model_name} from {url}")
    
    try:
        # Handle SSL verification
        context = None
        if disable_ssl_verify:
            context = ssl._create_unverified_context()
            OutputManager.log("SSL verification disabled for download", "WARNING")
        elif sys.platform == 'darwin':
            try:
                import certifi # type: ignore
                context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                OutputManager.log("Certifi not installed, using default system certificates for macOS.", "INFO")
                # Fallback to default context, might fail if certs aren't installed
                context = ssl.create_default_context()
        else:
            # For other OS, use the default context
            context = ssl.create_default_context()
        
        # Create a progress reporter for the download
        last_percent = -1
        def report_progress(blocknum, blocksize, totalsize):
            nonlocal last_percent
            if totalsize > 0:
                percent = min(int(blocknum * blocksize * 100 / totalsize), 100)
                # Only update status if percentage changes significantly
                if percent > last_percent:
                    # OutputManager.status(f"Downloading {model_name}: {percent}% ({blocknum * blocksize // 1024 // 1024}MB / {totalsize // 1024 // 1024}MB)") # Removed status update
                    last_percent = percent
        
        # Download the file using urllib.request with context
        try:
            with urllib.request.urlopen(url, context=context) as response, open(model_path, 'wb') as out_file:
                total_size = int(response.info().get('Content-Length', -1))
                block_size = 8192
                block_num = 0
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    out_file.write(buffer)
                    block_num += 1
                    report_progress(block_num, block_size, total_size)
            
            # Final status update
            OutputManager.status(f"Download {model_name}: 100% Complete") 
            OutputManager.log(f"Model {model_name} downloaded successfully", "SUCCESS")
            return model_path
        except (urllib.error.URLError, ssl.SSLError, TimeoutError) as e:
            OutputManager.log(f"Error downloading model: {str(e)}", "ERROR")
            
            # Clean up partially downloaded file
            if os.path.exists(model_path):
                try: os.remove(model_path) 
                except: pass

            # Special handling for SSL certificate errors
            if isinstance(e, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
                OutputManager.log("SSL certificate verification failed. Try running with --disable-ssl-verify", "WARNING")
                OutputManager.log("Alternatively, you can manually download the model:", "INFO")
                OutputManager.log(f"1. Download from: {url}", "INFO")
                OutputManager.log(f"2. Save it to: {model_path}", "INFO")
                
                # For macOS users, provide specific instructions
                if sys.platform == 'darwin':
                    OutputManager.log("For macOS users, ensure certificates are installed (e.g., via certifi or Install Certificates.command)", "INFO")
            
            # Try an alternative URL if this is a YOLOv8 model
            if model_name.startswith("yolov8") and "ultralytics/assets" in url:
                alt_url = f"https://github.com/ultralytics/ultralytics/releases/download/v8.0.0/{model_name}.pt"
                OutputManager.log(f"Trying alternative URL for {model_name}: {alt_url}", "INFO")
                try:
                    # Retry download with alternative URL
                    with urllib.request.urlopen(alt_url, context=context) as response, open(model_path, 'wb') as out_file:
                        total_size = int(response.info().get('Content-Length', -1))
                        block_size = 8192
                        block_num = 0
                        while True:
                            buffer = response.read(block_size)
                            if not buffer:
                                break
                            out_file.write(buffer)
                            block_num += 1
                            report_progress(block_num, block_size, total_size) # Reuse progress reporter
                    OutputManager.status(f"Downloading {model_name}: 100% Complete")
                    OutputManager.log(f"Model {model_name} downloaded successfully from alternative URL", "SUCCESS")
                    return model_path
                except Exception as e2:
                    OutputManager.log(f"Alternative download also failed: {str(e2)}", "ERROR")
                    if os.path.exists(model_path): # Clean up again
                        try: os.remove(model_path)
                        except: pass
            
            raise Exception(f"Model file not found and could not be downloaded. Error: {str(e)}")
    
    except Exception as e:
        # Clean up any partially downloaded file if an unexpected error occurred
        if os.path.exists(model_path) and OutputManager.info and \
           "downloaded successfully" not in OutputManager.info[-1]:
            try:
                os.remove(model_path)
            except Exception:
                pass
        
        # Log the error and re-raise
        OutputManager.log(f"Failed to download {model_name}: {str(e)}", "FATAL")
        raise
# Function to install ultralytics package
def install_ultralytics():
    """Install ultralytics package for YOLOv8 models"""
    print("======================================================")
    print("  Installing ultralytics package for YOLOv8 models")
    print("======================================================")
    
    try:
        # Check if pip is available
        subprocess.check_call([sys.executable, "-m", "pip", "--version"])
        
        # Install ultralytics
        print("\nInstalling ultralytics package...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "ultralytics"])
        
        # Verify installation
        print("\nVerifying installation...")
        subprocess.check_call([sys.executable, "-c", "import ultralytics; print(f'Ultralytics version: {ultralytics.__version__}')"])
        
        print("\n✅ Installation successful!")
        print("\nYou can now use YOLOv8 models with the main script.")
        print("Try running: python main.py --model yolov8x")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error: {str(e)}")
        print("\nManual installation instructions:")
        print("1. Open a terminal or command prompt")
        print("2. Run: pip install ultralytics")
        print("3. Then run the main script with: python main.py --model yolov8x")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        return False
# Function to test YOLOv8 detection
def test_yolov8_detector(image_path, model_name="yolov8x.pt", confidence=0.15, verbose=True):
    """Test YOLOv8 detection on an image"""
    if verbose:
        print(f"Testing YOLOv8 detection on {image_path} with model {model_name}")
    
    # Check if ultralytics is available
    try:
        from ultralytics import YOLO
    except ImportError:
        if verbose:
            print("ERROR: ultralytics package is not installed.")
            print("Install with: pip install ultralytics or use the install_ultralytics() function")
        return []
    
    # Load the model
    try:
        model = YOLO(model_name)
    except Exception as e:
        if verbose:
            print(f"Error loading model: {str(e)}")
        return []
    
    # Load the image
    if os.path.exists(image_path):
        if verbose:
            print(f"Image found: {image_path}")
        image = cv2.imread(image_path)
        if verbose:
            print(f"Image size: {image.shape}")
    else:
        if verbose:
            print(f"Image not found: {image_path}")
        return []
    
    # Run prediction
    try:
        results = model.predict(
            source=image,
            conf=confidence,  # Person class only
            classes=[0],      # Person class only
            verbose=verbose,  # Only show output if verbose
            save=False,       # Don't save output images
            project="test_output",
            name="yolo_test"
        )
    except Exception as e:
        if verbose:
            print(f"Error during prediction: {str(e)}")
        return []
    
    # Process results
    people = []
    if len(results) > 0:
        if verbose:
            print(f"\nResults type: {type(results)}")
            print(f"Number of results: {len(results)}")
        
        # Check for boxes
        if hasattr(results[0], 'boxes'):
            boxes = results[0].boxes
            if verbose:
                print(f"\nDetected boxes: {len(boxes)}")
            
            # Process each detection
            for i, box in enumerate(boxes):
                try:
                    cls = int(box.cls.item()) if hasattr(box, 'cls') else -1
                    conf = float(box.conf.item()) if hasattr(box, 'conf') else 0
                    
                    if cls == 0:  # Person class
                        # Get coordinates
                        xyxy = box.xyxy[0].cpu().numpy()
                        x1, y1, x2, y2 = map(int, xyxy)
                        
                        # Add to people list
                        person = {
                            'position': ((x1 + x2) // 2, (y1 + y2) // 2),
                            'foot_position': ((x1 + x2) // 2, y2),
                            'bbox': (x1, y1, x2, y2),
                            'confidence': conf
                        }
                        people.append(person)
                        if verbose:
                            print(f"Person {i+1}: bbox=({x1},{y1},{x2},{y2}), conf={conf:.2f}")
                except Exception as e:
                    if verbose:
                        print(f"Error processing detection {i}: {str(e)}")
            
            if verbose:
                print(f"\nTotal people detected: {len(people)}")
        elif verbose:
            print("No boxes attribute found in results")
    elif verbose:
        print("No results returned from model")
    
    # Return the people list for use in main.py
    return people

# Add this function after the test_yolov8_detector function

def run_performance_tests(input_image, output_dir="test_results", quick_mode=False, 
                          specific_models=None, specific_resolution=None, specific_device=None):
    """
    Run a series of performance tests with different configurations to find the fastest combination.
    
    Args:
        input_image: Path to input image for testing
        output_dir: Directory to save test results
        quick_mode: If True, run a limited set of tests
        specific_models: List of specific models to test
        specific_resolution: Specific resolution to test (tuple of width,height)
        specific_device: Specific device to test ('cpu' or 'cuda')
    """
    # Create results directory
    os.makedirs(output_dir, exist_ok=True)
    results_file = os.path.join(output_dir, "performance_results.txt")
    
    # Settings to test - default choices
    all_models = [
        "yolov5n", "yolov8n", "yolov5s", "yolov8s",  # Smallest/fastest models first
        "yolov5m", "yolov8m"  # Medium models (skip larger models for speed)
    ]
    
    # Camera resolutions to test (for simulation only - not actually capturing)
    all_resolutions = [
        (640, 480),    # VGA
        (1280, 720),   # 720p
        (1920, 1080),  # 1080p
        (2304, 1296),  # 3MP 
        (4608, 2592)   # 12MP (Camera 3 full resolution)
    ]
    
    # Process counts to test - default values
    all_process_counts = [1, 2, 4, 8]
    if cpu_count() <= 4:
        all_process_counts = [1, 2, max(1, cpu_count()-1)]
    
    # Confidence thresholds - default values
    all_confidence_thresholds = [0.1, 0.25, 0.4]
    
    # Devices to test - default values
    all_devices = ["cpu"]
    if torch.cuda.is_available():
        all_devices.append("cuda")
        print("CUDA detected - will test GPU acceleration")
    
    # Apply parameter overrides based on function arguments
    # Quick mode override
    if quick_mode:
        all_models = all_models[:2]  # Just yolov5n and yolov8n
        all_resolutions = [all_resolutions[0], all_resolutions[1]]  # Just VGA and 720p
        all_process_counts = [1, max(1, cpu_count()-1)]  # Just 1 and max-1
        all_confidence_thresholds = [0.25]  # Just middle confidence value
    
    # Specific models override
    if specific_models:
        models_to_test = specific_models
        # Verify models exist
        for model in models_to_test:
            if model not in Config.Model.MODEL_URLS:
                print(f"WARNING: Model {model} not found in known models - it may not work")
    else:
        models_to_test = all_models
    
    # Specific resolution override
    if specific_resolution:
        resolutions = [specific_resolution]
    else:
        resolutions = all_resolutions
    
    # Specific device override
    if specific_device:
        if specific_device == "cuda" and not torch.cuda.is_available():
            print("WARNING: CUDA requested but not available, falling back to CPU")
            devices = ["cpu"]
        else:
            devices = [specific_device]
    else:
        devices = all_devices
    
    # Process counts and confidence thresholds stay at defaults
    process_counts = all_process_counts
    confidence_thresholds = all_confidence_thresholds
    
    # Track results
    results = []
    test_count = (len(models_to_test) * 
                 len(process_counts) * 
                 len(confidence_thresholds) * 
                 len(devices) * 
                 len(resolutions))
    
    # Rest of the function remains the same...

# Now update the command-line arguments parsing (in the if __name__ == "__main__": block)
# Add this to the parser.add_argument section:

if __name__ == "__main__":
    try:
        # Add command-line arguments for easier use
        parser = argparse.ArgumentParser(description="Tennis Court Detection System")
        parser.add_argument("--input", type=str, help="Path to input image", default=Config.Paths.input_path())
        parser.add_argument("--output", type=str, help="Path for output image", default=Config.Paths.output_path())
        parser.add_argument("--debug", action="store_true", help="Enable debug mode with additional outputs")
        parser.add_argument("--quiet", action="store_true", help="Reduce console output")
        parser.add_argument("--show-labels", action="store_true", help="Show detailed labels on output image")
        parser.add_argument("--show-court-labels", action="store_true", help="Show court numbers on output image")
        parser.add_argument("--device", type=str, choices=["cpu", "cuda"], help="Device to use for inference", default=None)
        parser.add_argument("--disable-ssl-verify", action="store_true", help="Disable SSL verification for downloads")
        parser.add_argument("--model", type=str, help="YOLO model to use (yolov5s, yolov5m, yolov5l, etc.)", default=Config.Model.NAME)
        parser.add_argument("--no-multiprocessing", action="store_true", help="Disable multiprocessing")
        parser.add_argument("--processes", type=int, help="Number of processes to use for multiprocessing", default=Config.MultiProcessing.NUM_PROCESSES)
        parser.add_argument("--extra-verbose", action="store_true", help="Show extra detailed output for debugging")
        parser.add_argument("--force-macos-cert-install", action="store_true", help="Force macOS certificate installation")
        parser.add_argument(
            "--court-positions",
            type=str,
            help="Set court positions manually as 'x1,y1,...,x8,y8;x1,y1,...'"
        )
        parser.add_argument(
            "--set-courts-gui",
            action="store_true",
            help="Interactively select court corners via GUI"
        )
        parser.add_argument(
            "--reset-courts",
            action="store_true",
            help="Reset saved court positions so they will be detected again"
        )
        # Add new arguments for merged functionality
        parser.add_argument("--install-ultralytics", action="store_true", help="Install the ultralytics package")
        parser.add_argument("--test-yolo", action="store_true", help="Run YOLO model test on the input image")
        parser.add_argument("--no-camera", action="store_true", help="Skip camera capture and use default input image") # Add skip camera flag
        
        # Add new test mode arguments
        parser.add_argument("--test-mode", action="store_true", help="Run performance tests to find fastest configuration")
        parser.add_argument("--test-output-dir", type=str, default="test_results", help="Directory to save test results")
        parser.add_argument("--test-quick", action="store_true", help="Run a quick test with limited models and configurations")
        parser.add_argument("--test-models", type=str, default="all", help="Comma-separated list of models to test, e.g., 'yolov8n,yolov5n'")
        parser.add_argument("--test-with-resolution", type=str, help="Use only the specified resolution for testing, e.g., '1280x720'")
        parser.add_argument("--test-with-device", type=str, choices=["cpu", "cuda"], help="Use only the specified device for testing")
        
        # Parse arguments
        try:
            args = parser.parse_args()
        except Exception as e:
            print(f"\nError parsing command-line arguments: {str(e)}")
            print("Run with --help for usage information")
            sys.exit(1)
            
        # Handle new merged functionality
        if args.install_ultralytics:
            success = install_ultralytics()
            sys.exit(0 if success else 1)
            
        if args.test_yolo:
            # Get image path from command line
            image_path = args.input
            
            # Ensure models directory exists
            if not os.path.exists(Config.Paths.MODELS_DIR):
                os.makedirs(Config.Paths.MODELS_DIR, exist_ok=True)
                print(f"Created models directory at {Config.Paths.MODELS_DIR}")
            
            # Run the test with verbose output
            model_name = args.model
            test_yolov8_detector(image_path, model_name=model_name, verbose=not args.quiet)
            sys.exit(0)
        
        # Handle SSL verification setting early
        if args.disable_ssl_verify:
            ssl._create_default_https_context = ssl._create_unverified_context
            print("SSL verification disabled")
        
        # Handle macOS certificate installation
        if args.force_macos_cert_install and sys.platform == 'darwin':
            print("Attempting to install macOS certificates...")
            try:
                import subprocess
                subprocess.call(['/Applications/Python 3.9/Install Certificates.command'], shell=True)
                print("Certificate installation attempted. If it doesn't work, try with Python 3.10 or 3.11 instead.")
            except Exception as e:
                print(f"Certificate installation failed: {str(e)}")
                print("Try manually running the 'Install Certificates.command' script in your Python application folder.")

        if args.reset_courts:
            Config.COURT_POSITIONS = []
            try:
                existing_cfg = {}
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, "r") as f:
                        existing_cfg = json.load(f)
                existing_cfg["CourtPositions"] = Config.COURT_POSITIONS
                with open(CONFIG_FILE, "w") as f:
                    json.dump(existing_cfg, f, indent=4)
                OutputManager.log("Court positions cleared", "INFO")
            except Exception as e:
                OutputManager.log(f"Could not reset court positions: {e}", "WARNING")

        # Update config based on arguments
        try:
            if args.input != Config.Paths.input_path():
                Config.Paths.INPUT_IMAGE = os.path.basename(args.input)
                Config.Paths.IMAGES_DIR = os.path.dirname(args.input)
            
            if args.output != Config.Paths.output_path():
                Config.Paths.OUTPUT_IMAGE = os.path.basename(args.output)
                Config.Paths.IMAGES_DIR = os.path.dirname(args.output)
            
            Config.DEBUG_MODE = args.debug
            Config.Output.VERBOSE = not args.quiet
            Config.Visual.SHOW_DETAILED_LABELS = args.show_labels
            Config.Visual.SHOW_COURT_LABELS = args.show_court_labels
            
            # Update model name if specified
            if args.model:
                Config.Model.NAME = args.model
                print(f"Using model: {Config.Model.NAME}")
            
            # Update multiprocessing settings
            Config.MultiProcessing.ENABLED = not args.no_multiprocessing
            if args.processes > 0:
                Config.MultiProcessing.NUM_PROCESSES = args.processes
            

            # Update extra verbose setting
            if args.extra_verbose:
                Config.Output.EXTRA_VERBOSE = True

            # Manually set court positions from command line
            if args.court_positions:
                try:
                    Config.COURT_POSITIONS = parse_court_positions_arg(args.court_positions)

                    existing_cfg = {}
                    if os.path.exists(CONFIG_FILE):
                        try:
                            with open(CONFIG_FILE, 'r') as f:
                                existing_cfg = json.load(f)
                        except Exception:
                            existing_cfg = {}

                    existing_cfg['CourtPositions'] = Config.COURT_POSITIONS

                    json_text = json.dumps(existing_cfg, indent=4)
                    with open(CONFIG_FILE, 'w') as f:
                        f.write(json_text)
                    OutputManager.log("Court positions set via command line", "DEBUG")
                except Exception as e:
                    OutputManager.log(f"Invalid --court-positions: {str(e)}", "ERROR")
                    sys.exit(1)

            use_gui_courts = args.set_courts_gui
            
            # Handle test mode
            if args.test_mode:
                # Parse any specific test parameters
                specific_models = None
                if args.test_models and args.test_models.lower() != "all":
                    specific_models = [model.strip() for model in args.test_models.split(",")]
                
                specific_resolution = None
                if args.test_with_resolution:
                    try:
                        width, height = map(int, args.test_with_resolution.split("x"))
                        specific_resolution = (width, height)
                    except:
                        print(f"Invalid resolution format: {args.test_with_resolution}, expected WIDTHxHEIGHT (e.g., 1280x720)")
                        sys.exit(1)
                
                # Run the test
                best_config, best_time = run_performance_tests(
                    args.input, 
                    args.test_output_dir, 
                    quick_mode=args.test_quick,
                    specific_models=specific_models,
                    specific_resolution=specific_resolution,
                    specific_device=args.test_with_device
                )
                
                # Option to apply the best configuration
                use_best = input("\nWould you like to apply the best configuration now? (y/n): ").lower().strip() == 'y'
                if use_best:
                    # Parse the best config
                    parts = best_config.split('_')
                    model = parts[0]
                    processes = int(parts[1].replace('p', ''))
                    confidence = float(parts[2].replace('c', ''))
                    resolution = parts[3].replace('r', '').split('x')
                    width, height = int(resolution[0]), int(resolution[1])
                    device = parts[4]
                    
                    # Apply the best config
                    Config.Model.NAME = model
                    Config.Model.CONFIDENCE = confidence
                    Config.MultiProcessing.NUM_PROCESSES = processes
                    Config.MultiProcessing.ENABLED = (processes > 1)
                    Config.Camera.WIDTH = width
                    Config.Camera.HEIGHT = height
                    
                    print(f"\nApplied best configuration:")
                    print(f"  - Model: {model}")
                    print(f"  - Processes: {processes}")
                    print(f"  - Confidence: {confidence}")
                    print(f"  - Resolution: {width}x{height}")
                    print(f"  - Device: {device}")
                    
                    # Save to config.json for future use
                    save_config = input("Would you like to save this configuration to config.json for future use? (y/n): ").lower().strip() == 'y'
                    if save_config:
                        config_data = {
                            "Model": {
                                "NAME": model,
                                "CONFIDENCE": confidence,
                                "IOU": Config.Model.IOU,
                                "CLASSES": Config.Model.CLASSES
                            },
                            "MultiProcessing": {
                                "ENABLED": Config.MultiProcessing.ENABLED,
                                "NUM_PROCESSES": processes
                            },
                            "Camera": {
                                "width": width,
                                "height": height
                            },
                            "Output": {
                                "VERBOSE": Config.Output.VERBOSE,
                                "SUPER_QUIET": Config.Output.SUPER_QUIET,
                                "SUMMARY_ONLY": Config.Output.SUMMARY_ONLY,
                                "EXTRA_VERBOSE": Config.Output.EXTRA_VERBOSE
                            }
                        }
                        
                        try:
                            with open(CONFIG_FILE, 'w') as f:
                                json.dump(config_data, f, indent=4)
                            print(f"Configuration saved to {CONFIG_FILE}")
                        except Exception as e:
                            print(f"Error saving configuration: {str(e)}")
                    
                    # Ask if they want to run with this configuration
                    run_with_best = input("Would you like to run with this configuration now? (y/n): ").lower().strip() == 'y'
                    if run_with_best:
                        args.model = model
                        args.processes = processes
                        if device == "cuda" and torch.cuda.is_available():
                            args.device = "cuda"
                        else:
                            args.device = "cpu"
                        print(f"\nRunning with best configuration...")
                        sys.exit(main(use_gui_courts))
                    else:
                        print("Exiting.")
                        sys.exit(0)
                else:
                    print("Exiting.")
                    sys.exit(0)
            
            sys.exit(main(use_gui_courts))
        except Exception as e:
            print(f"\nError setting up configuration: {str(e)}")
            sys.exit(1)
    except ModuleNotFoundError as e:
        # For missing modules, provide direct installation instructions
        module_name = str(e).split("'")[1] if "'" in str(e) else "unknown"
        error_message = f"Missing module: {module_name}"
        install_cmd = ""
        
        # Provide specific installation commands for common modules
        if module_name == "cv2":
            if sys.platform == "linux" and os.uname().machine.startswith('arm'):
                # Raspberry Pi specific OpenCV installation
                install_cmd = "sudo apt update && sudo apt install -y python3-opencv\n\nOR for full requirements:\n\nsudo apt update && sudo apt install -y python3-opencv python3-numpy\npip3 install torch torchvision shapely"
            else:
                install_cmd = "pip install opencv-python"
        elif module_name == "numpy":
            if sys.platform == "linux" and os.uname().machine.startswith('arm'):
                install_cmd = "sudo apt update && sudo apt install -y python3-numpy"
            else:
                install_cmd = "pip install numpy"
        elif module_name == "torch":
            if sys.platform == "linux" and os.uname().machine.startswith('arm'):
                install_cmd = "pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
            else:
                install_cmd = "pip install torch torchvision"
        elif module_name == "shapely":
            if sys.platform == "linux" and os.uname().machine.startswith('arm'):
                install_cmd = "sudo apt update && sudo apt install -y python3-shapely\n\nOR\n\npip3 install shapely"
            else:
                install_cmd = "pip install shapely"
        else:
            install_cmd = f"pip install {module_name}\n\nOr to install all dependencies:\npip install -r requirements.txt"
        
        # Create a simple formatted box to display the error
        print("\n" + "╭" + "─" * 78 + "╮")
        print("│ " + "ERROR: MODULE NOT FOUND".center(78) + " │")
        print("│ " + "─" * 78 + " │")
        print("│ " + error_message.ljust(78) + " │")
        print("│ " + "─" * 78 + " │")
        print("│ " + "To fix this error, run:".ljust(78) + " │")
        for line in install_cmd.split('\n'):
            print("│ " + line.ljust(78) + " │")
            
        # Add a one-line shortcut for all dependencies
        if module_name in ["cv2", "numpy", "torch", "shapely"]:
            if sys.platform == "linux" and os.uname().machine.startswith('arm'):
                print("│ " + "─" * 78 + " │")
                print("│ " + "QUICK FIX FOR RASPBERRY PI:".ljust(78) + " │")
                print("│ " + "sudo apt update && sudo apt install -y python3-opencv python3-numpy".ljust(78) + " │")
                print("│ " + "python3-shapely python3-pip && pip3 install torch torchvision".ljust(78) + " │")
        
        print("╰" + "─" * 78 + "╯")
        sys.exit(1)
    except KeyboardInterrupt:
        # Handle user interruption gracefully
        print("\n\n" + "╭" + "─" * 78 + "╮")
        print("│ " + "PROCESS INTERRUPTED BY USER".center(78) + " │")
        print("╰" + "─" * 78 + "╯")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        # For other unhandled exceptions, provide a generic error message
        error_message = str(e)
        possible_solution = ""
        
        # Try to provide helpful solutions for common errors
        if "permission" in error_message.lower():
            if sys.platform == "win32":
                possible_solution = "Run as Administrator or check file permissions"
            else:
                possible_solution = "Try: chmod +x main.py && sudo ./main.py"
        elif "disk" in error_message.lower() or "space" in error_message.lower():
            possible_solution = "Check available disk space and write permissions"
        elif "network" in error_message.lower() or "connection" in error_message.lower():
            possible_solution = "Check your internet connection"
        elif "import" in error_message.lower():
            possible_solution = "Run: pip install -r requirements.txt"
        elif "memory" in error_message.lower():
            possible_solution = "Try using a smaller image or reduce batch size"
        else:
            possible_solution = "Check requirements with: pip install -r requirements.txt"
        
        print("\n" + "╭" + "─" * 78 + "╮")
        print("│ " + "ERROR: UNHANDLED EXCEPTION".center(78) + " │")
        print("│ " + "─" * 78 + " │")
        
        # Split long error messages
        wrapped_error = []
        for chunk in [error_message[i:i+78] for i in range(0, len(error_message), 78)]:
            wrapped_error.append(chunk)
        
        for line in wrapped_error[:3]:  # Limit to 3 lines to avoid huge error messages
            print("│ " + line.ljust(78) + " │")
        
        if len(wrapped_error) > 3:
            print("│ " + "...".ljust(78) + " │")
        
        print("│ " + "─" * 78 + " │")
        print("│ " + "POSSIBLE SOLUTION:".ljust(78) + " │")
        for sol_line in [possible_solution[i:i+78] for i in range(0, len(possible_solution), 78)]:
            print("│ " + sol_line.ljust(78) + " │")
        print("╰" + "─" * 78 + "╯")
        sys.exit(1)