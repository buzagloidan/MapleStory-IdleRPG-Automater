"""
Modern GUI Launcher for MapleStory Idle Bot.
Clean, minimalistic light theme.
"""
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import logging
import sys

# Add parent directory to path for imports
_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    import customtkinter as ctk
    HAS_GUI = True
except ImportError:
    HAS_GUI = False
    print("GUI dependencies not installed. Run: pip install customtkinter")

try:
    from PIL import Image
except ImportError:
    pass

# Import bot components (absolute imports after path setup)
from core.adb_controller import ADBController
from core.logger import setup_logger
from config import ConfigManager
from games.maple_story_idle import MapleStoryIdleBot, BotState


class BotLauncher:
    """
    Modern GUI launcher for the MapleStory Idle Bot.
    Clean, minimalistic light theme.
    """
    
    # Clean light color scheme
    COLORS = {
        "bg": "#fafafa",
        "card": "#ffffff",
        "border": "#e5e7eb",
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "success": "#16a34a",
        "success_hover": "#15803d",
        "danger": "#dc2626",
        "danger_hover": "#b91c1c",
        "warning": "#f59e0b",
        "text": "#1f2937",
        "text_secondary": "#6b7280",
        "text_muted": "#9ca3af",
        "input_bg": "#f9fafb",
        "log_bg": "#f3f4f6",
    }
    
    def __init__(self):
        if not HAS_GUI:
            raise ImportError("customtkinter is required for GUI")
        
        # Configure appearance - LIGHT mode
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        
        # Create main window
        self.root = ctk.CTk()
        self.root.title("MapleStory : Idle RPG Automater")
        self.root.geometry("520x680")
        self.root.minsize(480, 620)
        self.root.configure(fg_color=self.COLORS["bg"])
        
        # Set window icon
        icon_path = Path(__file__).parent.parent / "favicon.ico"
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path))
        
        # Bot components
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()
        self.logger = setup_logger(
            "maple_bot",
            self.config.get("loglevel", "info"),
            log_to_file=True,
            max_log_files=self.config.get("max-log-files", 5),
        )
        
        self.adb: Optional[ADBController] = None
        self.bot: Optional[MapleStoryIdleBot] = None
        self.bot_thread: Optional[threading.Thread] = None
        
        # State
        self.connected = False
        self.running = False
        
        # Build UI
        self._create_ui()
    
    def _create_ui(self):
        """Build the user interface."""
        # Main container with padding
        self.main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Connection Card (includes ADB Port + status)
        self._create_connection_card()
        
        # Settings Card
        self._create_settings_card()
        
        # Log Card (expanded, above stats)
        self._create_log_card()
        
        # Stats Card (at bottom)
        self._create_stats_card()
    
    def _create_connection_card(self):
        """Create connection settings card with status."""
        card = ctk.CTkFrame(
            self.main_frame, 
            fg_color=self.COLORS["card"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"]
        )
        card.pack(fill="x", pady=(0, 10))
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=14)
        
        # Row with port, connect button, and status
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        
        ctk.CTkLabel(
            row, 
            text="ADB",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.COLORS["text"]
        ).pack(side="left")
        
        self.port_entry = ctk.CTkEntry(
            row, 
            width=70, 
            height=34,
            font=ctk.CTkFont(size=12),
            fg_color=self.COLORS["input_bg"],
            border_color=self.COLORS["border"],
            text_color=self.COLORS["text"]
        )
        self.port_entry.insert(0, str(self.config.get("adb", {}).get("port", 5555)))
        self.port_entry.pack(side="left", padx=(10, 0))
        
        self.connect_btn = ctk.CTkButton(
            row,
            text="Connect",
            width=90,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=self.COLORS["primary"],
            hover_color=self.COLORS["primary_hover"],
            text_color="white",
            corner_radius=6,
            command=self._toggle_connection
        )
        self.connect_btn.pack(side="left", padx=(8, 0))
        
        # Status on the right
        self.status_badge = ctk.CTkLabel(
            row,
            text="● Disconnected",
            font=ctk.CTkFont(size=11),
            text_color=self.COLORS["text_muted"]
        )
        self.status_badge.pack(side="right")
    
    def _create_settings_card(self):
        """Create settings card."""
        card = ctk.CTkFrame(
            self.main_frame,
            fg_color=self.COLORS["card"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"]
        )
        card.pack(fill="x", pady=(0, 10))
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=14)
        
        # Quest Selection row
        quest_row = ctk.CTkFrame(inner, fg_color="transparent")
        quest_row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            quest_row,
            text="Quest",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLORS["text"]
        ).pack(side="left")
        
        self.quest_var = ctk.StringVar(value="sleepywood")
        
        self.sleepy_btn = ctk.CTkButton(
            quest_row,
            text="Sleepywood",
            width=100,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=self.COLORS["primary"],
            hover_color=self.COLORS["primary_hover"],
            text_color="white",
            corner_radius=6,
            command=lambda: self._select_quest("sleepywood")
        )
        self.sleepy_btn.pack(side="left", padx=(12, 0))
        
        self.ludi_btn = ctk.CTkButton(
            quest_row,
            text="Ludibrium",
            width=100,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=self.COLORS["input_bg"],
            hover_color=self.COLORS["border"],
            text_color=self.COLORS["text_secondary"],
            corner_radius=6,
            command=lambda: self._select_quest("ludibrium")
        )
        self.ludi_btn.pack(side="left", padx=(6, 0))
        
        self.orbis_btn = ctk.CTkButton(
            quest_row,
            text="Orbis",
            width=100,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color=self.COLORS["input_bg"],
            hover_color=self.COLORS["border"],
            text_color=self.COLORS["text_secondary"],
            corner_radius=6,
            command=lambda: self._select_quest("orbis")
        )
        self.orbis_btn.pack(side="left", padx=(6, 0))
        
        # Options row
        options_row = ctk.CTkFrame(inner, fg_color="transparent")
        options_row.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(
            options_row,
            text="Timeout",
            font=ctk.CTkFont(size=11),
            text_color=self.COLORS["text_secondary"]
        ).pack(side="left")
        
        self.timeout_entry = ctk.CTkEntry(
            options_row,
            width=45,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color=self.COLORS["input_bg"],
            border_color=self.COLORS["border"],
            text_color=self.COLORS["text"]
        )
        self.timeout_entry.insert(0, "30")
        self.timeout_entry.pack(side="left", padx=(6, 0))
        
        ctk.CTkLabel(
            options_row,
            text="s",
            font=ctk.CTkFont(size=11),
            text_color=self.COLORS["text_muted"]
        ).pack(side="left", padx=(3, 0))
        
        # Jump checkbox on right
        self.jump_var = ctk.BooleanVar(value=True)
        self.jump_check = ctk.CTkCheckBox(
            options_row,
            text="Jump in PQ",
            variable=self.jump_var,
            font=ctk.CTkFont(size=11),
            text_color=self.COLORS["text_secondary"],
            fg_color=self.COLORS["primary"],
            hover_color=self.COLORS["primary_hover"],
            border_color=self.COLORS["border"],
            checkmark_color="white",
            width=20,
            height=20
        )
        self.jump_check.pack(side="right")
        
        # Start Button
        self.start_btn = ctk.CTkButton(
            inner,
            text="Start Bot",
            height=40,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.COLORS["success"],
            hover_color=self.COLORS["success_hover"],
            text_color="white",
            corner_radius=6,
            command=self._toggle_bot
        )
        self.start_btn.pack(fill="x")
        self.start_btn.configure(state="disabled")
    
    def _create_log_card(self):
        """Create expanded log output card."""
        card = ctk.CTkFrame(
            self.main_frame,
            fg_color=self.COLORS["card"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"]
        )
        card.pack(fill="both", expand=True, pady=(0, 10))
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=14)
        
        # Header with title and clear button
        header = ctk.CTkFrame(inner, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        
        ctk.CTkLabel(
            header,
            text="Log",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.COLORS["text"]
        ).pack(side="left")
        
        clear_btn = ctk.CTkButton(
            header,
            text="Clear",
            width=45,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color=self.COLORS["input_bg"],
            hover_color=self.COLORS["border"],
            text_color=self.COLORS["text_secondary"],
            corner_radius=4,
            command=self._clear_log
        )
        clear_btn.pack(side="right")
        
        # Log text area
        self.log_text = ctk.CTkTextbox(
            inner,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=self.COLORS["log_bg"],
            text_color=self.COLORS["text"],
            corner_radius=6,
            border_width=1,
            border_color=self.COLORS["border"]
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        
        # Initial message
        self._log("Ready. Set BlueStacks to 960×540 with ADB enabled.")
    
    def _create_stats_card(self):
        """Create stats display card at bottom."""
        card = ctk.CTkFrame(
            self.main_frame,
            fg_color=self.COLORS["card"],
            corner_radius=10,
            border_width=1,
            border_color=self.COLORS["border"]
        )
        card.pack(fill="x")
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)
        
        # Stats in a row
        stats_row = ctk.CTkFrame(inner, fg_color="transparent")
        stats_row.pack(fill="x")
        
        # Configure grid - 4 columns now
        stats_row.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # PQ Runs
        self._create_stat_item(stats_row, 0, "Runs", "runs_label", "0", self.COLORS["primary"])
        
        # Runtime
        self._create_stat_item(stats_row, 1, "Time", "time_label", "00:00:00", self.COLORS["text"])
        
        # Avg time per PQ
        self._create_stat_item(stats_row, 2, "Avg/PQ", "avg_label", "--:--", self.COLORS["text_secondary"])
        
        # State
        self._create_stat_item(stats_row, 3, "Status", "state_label", "Idle", self.COLORS["success"])
    
    def _create_stat_item(self, parent, col, title, attr_name, value, color):
        """Create a stat display item."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=0, column=col, sticky="nsew", padx=2)
        
        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=10),
            text_color=self.COLORS["text_muted"]
        ).pack()
        
        label = ctk.CTkLabel(
            frame,
            text=value,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=color
        )
        label.pack()
        
        setattr(self, attr_name, label)
    
    def _select_quest(self, quest: str):
        """Select quest type."""
        self.quest_var.set(quest)
        selected = {"fg_color": self.COLORS["primary"], "text_color": "white"}
        unselected = {"fg_color": self.COLORS["input_bg"], "text_color": self.COLORS["text_secondary"]}
        self.sleepy_btn.configure(**selected if quest == "sleepywood" else unselected)
        self.ludi_btn.configure(**selected if quest == "ludibrium" else unselected)
        self.orbis_btn.configure(**selected if quest == "orbis" else unselected)
    
    def _toggle_connection(self):
        """Toggle ADB connection."""
        if self.connected:
            self._disconnect()
        else:
            self._connect()
    
    def _connect(self):
        """Connect to BlueStacks."""
        try:
            port = int(self.port_entry.get())
        except ValueError:
            self._log("Error: Invalid port")
            return
        
        self._log(f"Connecting to port {port}...")
        
        self.adb = ADBController(port=port, logger=self.logger)
        if self.adb.connect():
            self.connected = True
            self.status_badge.configure(
                text="● Connected",
                text_color=self.COLORS["success"]
            )
            self.connect_btn.configure(
                text="Disconnect",
                fg_color=self.COLORS["danger"],
                hover_color=self.COLORS["danger_hover"]
            )
            self.start_btn.configure(state="normal")
            self._log("Connected!")
            
            res = self.adb.get_screen_resolution()
            if res:
                self._log(f"Resolution: {res[0]}×{res[1]}")
                if res != (960, 540):
                    self._log("Warning: Expected 960×540")
        else:
            self._log("Error: Connection failed")
    
    def _disconnect(self):
        """Disconnect from BlueStacks."""
        if self.running:
            self._stop_bot()
        
        if self.adb:
            self.adb.disconnect()
        
        self.connected = False
        self.status_badge.configure(
            text="● Disconnected",
            text_color=self.COLORS["text_muted"]
        )
        self.connect_btn.configure(
            text="Connect",
            fg_color=self.COLORS["primary"],
            hover_color=self.COLORS["primary_hover"]
        )
        self.start_btn.configure(state="disabled")
        self._log("Disconnected")
    
    def _toggle_bot(self):
        """Toggle bot running state."""
        if self.running:
            self._stop_bot()
        else:
            self._start_bot()
    
    def _start_bot(self):
        """Start the bot."""
        if not self.connected:
            return
        
        try:
            timeout = int(self.timeout_entry.get())
        except ValueError:
            timeout = 30
        
        bot_config = {
            "queue-timeout": timeout,
            "quest-choice": self.quest_var.get(),
            "random-jump": self.jump_var.get(),
            "templates_dir": str(Path(__file__).parent.parent / "templates" / "maple_story_idle")
        }
        
        self.bot = MapleStoryIdleBot(self.adb, bot_config, self.logger)
        self.bot.on_state_change = self._on_state_change
        self.bot.on_stats_update = self._on_stats_update
        self.bot.on_log = self._on_bot_log
        
        self.bot_thread = threading.Thread(target=self.bot.start, daemon=True)
        self.bot_thread.start()
        
        self.running = True
        self.start_btn.configure(
            text="Stop Bot",
            fg_color=self.COLORS["danger"],
            hover_color=self.COLORS["danger_hover"]
        )
        self._log(f"Started: {self.quest_var.get().title()}")
    
    def _stop_bot(self):
        """Stop the bot."""
        if self.bot:
            self.bot.stop()
        
        self.running = False
        self.start_btn.configure(
            text="Start Bot",
            fg_color=self.COLORS["success"],
            hover_color=self.COLORS["success_hover"]
        )
        self.state_label.configure(text="Stopped", text_color=self.COLORS["text_muted"])
    
    def _on_state_change(self, state: BotState):
        """Handle bot state change."""
        def update():
            color = self.COLORS["success"] if state == BotState.RUNNING else self.COLORS["text_muted"]
            self.state_label.configure(text=state.name.title(), text_color=color)
        self.root.after(0, update)
    
    def _on_stats_update(self, stats: Dict):
        """Handle stats update."""
        def update():
            if "pq_runs" in stats:
                self.runs_label.configure(text=str(stats["pq_runs"]))
            if "runtime" in stats:
                self.time_label.configure(text=stats["runtime"])
                
                # Calculate avg time per PQ
                pq_runs = stats.get("pq_runs", 0)
                if pq_runs > 0:
                    runtime_str = stats["runtime"]
                    try:
                        # Parse runtime (HH:MM:SS or H:MM:SS)
                        parts = runtime_str.split(":")
                        total_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                        avg_seconds = total_seconds // pq_runs
                        avg_min = avg_seconds // 60
                        avg_sec = avg_seconds % 60
                        self.avg_label.configure(text=f"{avg_min}:{avg_sec:02d}")
                    except:
                        self.avg_label.configure(text="--:--")
                else:
                    self.avg_label.configure(text="--:--")
                    
            if "state" in stats:
                state = stats["state"]
                color = self.COLORS["primary"] if state == "IN PQ" else (
                    self.COLORS["warning"] if state == "QUEUED" else self.COLORS["success"]
                )
                self.state_label.configure(text=state, text_color=color)
        self.root.after(0, update)
    
    def _on_bot_log(self, message: str):
        """Handle log message from bot (called from bot thread)."""
        self.root.after(0, lambda m=message: self._log(m))
    
    def _log(self, message: str):
        """Add message to log (must be called from main thread)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{timestamp}  {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    
    def _clear_log(self):
        """Clear the log."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
    
    def run(self):
        """Run the application."""
        self.root.mainloop()


def main():
    """Main entry point."""
    if not HAS_GUI:
        print("Error: customtkinter required. Install: pip install customtkinter")
        return
    
    app = BotLauncher()
    app.run()


if __name__ == "__main__":
    main()
