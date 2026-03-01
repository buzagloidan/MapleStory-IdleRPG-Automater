"""
MapleStory Idle Bot - Automated party quest runner.
Smart detection based on available templates.
"""
import random
import time
import sys
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable
import logging
from pathlib import Path

_parent_dir = str(Path(__file__).parent.parent)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from core.adb_controller import ADBController
from core.screen_capture import ScreenCapture
from core.template_matcher import TemplateMatcher, MatchResult
from core.input_handler import InputHandler


class BotState(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPED = auto()


class MapleStoryIdleBot:
    """
    MapleStory Idle Bot - Freestyle detection.
    
    Templates:
    - app_button: Open the game
    - main_menu: Menu button (top-right)
    - pq_button: Party Quest button
    - sleepywood/ludibrium/orbis: Quest selection
    - start_queue: Start queue button
    - in_queue: Waiting in queue
    - stop_queue: Cancel queue button
    - confirm: OK/Confirm (PRIORITY!)
    - loading_screen, loading_screen2, loading_screen3, loading_screen4, loading_screen5: Game loading
    - sleepywood_wave_1, sleepywood_wave_2, sleepywood_wave_3: In PQ (Sleepywood waves)
    - ludibrium_wave_11, ludibrium_wave_22, ludibrium_wave_33: In PQ (Ludibrium waves)
    - orbis_wave_1, orbis_wave_2, orbis_wave_3: In PQ (Orbis waves)
    - clear: PQ complete indicator (triggers PQ finish)
    - failed: PQ failed mid-run indicator (triggers recovery)
    - red_alert: Boss red attack indicator (wave 3 only) - triggers immediate double-jump
    - jump: Jump button for avoiding attacks
    """
    
    POSITIONS = {
        "center": (480, 270),
        "main_menu": (900, 50),
        "pq_button": (480, 400),
        "sleepywood": (300, 350),
        "ludibrium": (480, 350),
        "orbis": (660, 350),
        "start_queue": (480, 450),
        "stop_queue": (750, 480),
        "confirm": (480, 400),
    }
    
    def __init__(self, adb: ADBController, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        self.adb = adb
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        
        self.screen = ScreenCapture(adb, logger)
        self.matcher = TemplateMatcher(
            templates_dir=config.get("templates_dir", "templates/maple_story_idle"),
            logger=logger
        )
        self.input = InputHandler(adb, logger)
        
        # State
        self.state = BotState.IDLE
        self.running = False
        self.paused = False
        
        # Stats
        self.pq_runs = 0
        self.queue_timeouts = 0
        self.start_time: Optional[datetime] = None
        
        # Config
        self.queue_timeout = config.get("queue-timeout", 30)  # seconds
        self.quest_choice = config.get("quest-choice", "sleepywood")
        
        # Tracking
        self.queue_start_time: Optional[datetime] = None
        self.in_queue = False
        self.in_pq = False
        self.current_wave = 0
        
        # Watchdog - restart if stuck for too long
        self.stuck_timeout = config.get("stuck-timeout", 120)  # 2 minutes default
        self.soft_stuck_timeout = self.stuck_timeout // 2  # 1 minute default (half of stuck timeout)
        self.last_activity_time: Optional[datetime] = None
        self.soft_recovery_attempted = False  # Track if we already tried soft recovery
        self.restarts = 0
        self.recoveries = 0
        
        # Track consecutive queue timeouts (to detect connection loss, etc.)
        self.consecutive_queue_timeouts = 0
        self.max_consecutive_timeouts = config.get("max-queue-timeouts", 5)  # Restart after 5 consecutive timeouts
        
        # Track time since last PQ entry (force restart if too long)
        # Progressive timeout: 7.5min → 15min (cap)
        self.last_pq_entry_time: Optional[datetime] = None
        self.pq_timeout_levels = [450, 900]  # 7.5min, 15min
        self.current_pq_timeout_level = 0  # Index into pq_timeout_levels
        
        # Random actions (jump during PQ)
        self.random_actions = config.get("random-jump", True)
        self.jump_interval = config.get("jump-interval", 30)  # Jump every 30 seconds
        self.last_jump_time: Optional[datetime] = None
        
        # Hard reset tracking
        self.hard_resets = 0
        
        # Game package name for force-stop
        self.game_package = config.get("game-package", "com.nexon.maplem.global")
        
        # Callbacks
        self.on_state_change: Optional[Callable] = None
        self.on_stats_update: Optional[Callable] = None
        self.on_log: Optional[Callable] = None
        
        # Duplicate log prevention
        self.last_log_message: Optional[str] = None
    
    def _log(self, msg: str):
        # Skip duplicate consecutive messages
        if msg == self.last_log_message:
            return
        self.last_log_message = msg
        
        self.logger.info(msg)
        if self.on_log:
            self.on_log(msg)
    
    def _update_stats(self):
        if self.on_stats_update:
            status = "IN PQ" if self.in_pq else ("QUEUED" if self.in_queue else "RUNNING")
            self.on_stats_update({
                "pq_runs": self.pq_runs,
                "runtime": str(datetime.now() - self.start_time).split('.')[0] if self.start_time else "00:00:00",
                "state": status
            })
    
    def _activity(self):
        """Mark that meaningful activity happened (resets stuck timer)."""
        self.last_activity_time = datetime.now()
        self.soft_recovery_attempted = False  # Reset soft recovery flag
    
    def _check_stuck(self, screen) -> bool:
        """
        Multi-tier stuck detection:
        - Too long without PQ entry (5 min): Force restart
        - At 1/3 timeout (1 min): Try soft recovery - scan for any actionable template
        - At full timeout (3 min): Hard restart - close and reopen app
        Returns True if action was taken.
        """
        if self.last_activity_time is None:
            self._activity()
            return False
        
        # Check if too long without entering a PQ - needs hard reset
        # Progressive timeout: 7.5min → 15min (cap)
        if self.last_pq_entry_time:
            current_timeout = self.pq_timeout_levels[self.current_pq_timeout_level]
            time_without_pq = (datetime.now() - self.last_pq_entry_time).total_seconds()
            if time_without_pq >= current_timeout:
                self._log(f"!!! NO PQ FOR {int(time_without_pq)}s ({int(time_without_pq/60)}min) - Hard reset !!!")
                self._hard_reset_app()
                return True
        
        elapsed = (datetime.now() - self.last_activity_time).total_seconds()
        
        # TIER 2: Hard stuck - full restart
        if elapsed >= self.stuck_timeout:
            self._log(f"!!! HARD STUCK for {int(elapsed)}s - Restarting app !!!")
            self._restart_app()
            return True
        
        # TIER 1: Soft stuck - try recovery
        if elapsed >= self.soft_stuck_timeout and not self.soft_recovery_attempted:
            self._log(f"!!! SOFT STUCK for {int(elapsed)}s - Attempting recovery !!!")
            self.soft_recovery_attempted = True
            if self._try_recovery(screen):
                return True
        
        return False
    
    def _try_recovery(self, screen) -> bool:
        """
        Actively scan for ANY actionable template and act on it.
        Used when soft stuck to try to get unstuck.
        Returns True if an action was taken.
        """
        self.recoveries += 1
        self._log(f"Recovery #{self.recoveries} - Scanning all templates...")
        
        # Reset PQ state in case we're stuck thinking we're in PQ
        if self.in_pq:
            self._log("Resetting PQ state...")
            self.in_pq = False
            self.current_wave = 0
        
        # List of templates to check and their actions
        # Priority order: most important first
        actionable_templates = [
            ("lost_connection", "click"),  # Connection lost popup - click OK
            ("exit", "click"),  # Exit button - close popup/dialog
            ("event", "click"),  # Event popup - close it
            ("leave_party", "click"),  # Leave party if accidentally joined
            ("clear", "click"),
            ("confirm", "click"),
            ("start_queue", "click"),
            (self.quest_choice, "click"),  # Quest selection (sleepywood/ludibrium)
            ("pq_button", "click"),
            ("main_menu", "click"),
            ("app_button", "click"),
            ("stop_queue", "click"),  # Cancel queue if stuck in queue
        ]
        
        for template, action in actionable_templates:
            match = self.matcher.find(screen, template)
            if match:
                self._log(f"Recovery: Found '{template}' - clicking!")
                self.input.tap_center(match)
                self._activity()  # Mark progress
                time.sleep(1)
                return True
        
        # Nothing found - tap center as last resort
        self._log("Recovery: No template found, tapping center...")
        self.input.tap(*self.POSITIONS["center"])
        time.sleep(1)
        return False
    
    def _restart_app(self):
        """Close app and reset state to start fresh."""
        self.restarts += 1
        self._log(f"Restart #{self.restarts} - Closing app...")
        
        # Press back multiple times to exit any screen
        for _ in range(5):
            self.input.press_back()
            time.sleep(0.3)
        
        # Press home to ensure we're out
        self.input.press_home()
        time.sleep(1)
        
        # Reset state (but NOT last_pq_entry_time - only actual PQ entry resets that)
        self.in_pq = False
        self.in_queue = False
        self.current_wave = 0
        self.queue_start_time = None
        self.consecutive_queue_timeouts = 0
        # NOTE: Don't reset last_pq_entry_time here - allows escalation to hard reset
        
        # Mark activity to reset timer
        self._activity()
        self._log("App closed. Will restart from app_button detection...")
        time.sleep(2)
    
    def _hard_reset_app(self):
        """Force-stop app via ADB and restart. Used when soft restart doesn't work."""
        self.hard_resets += 1
        self._log(f"!!! HARD RESET #{self.hard_resets} - Killing app via Recent Apps !!!")
        
        # Step 1: Press home to exit any frozen screen
        self.input.press_home()
        time.sleep(1)
        
        # Step 2: Open Recent Apps (keycode 187 = KEYCODE_APP_SWITCH)
        self.adb.key_event(187)
        self._log("Opened Recent Apps")
        time.sleep(1)
        
        # Step 3: Look for "Clear All" button using template
        screen = self.screen.capture(use_cache=False)
        if screen is not None:
            clear_all = self.matcher.find(screen, "clear_all")
            if clear_all:
                self.input.tap_center(clear_all)
                self._log("Clicked CLEAR ALL")
                time.sleep(1)
            else:
                self._log("CLEAR ALL not found - tapping common position")
                # Common position for Clear All in BlueStacks (bottom center area)
                self.input.tap(480, 500)
                time.sleep(1)
        
        # Step 4: Press home to exit recents
        self.input.press_home()
        time.sleep(1)
        
        # Step 5: Also send force-stop just to be sure
        try:
            self.adb.shell(f"am force-stop {self.game_package}")
        except:
            pass
        
        time.sleep(1)
        
        # Reset all state
        self.in_pq = False
        self.in_queue = False
        self.current_wave = 0
        self.queue_start_time = None
        self.consecutive_queue_timeouts = 0
        self.last_pq_entry_time = datetime.now()
        
        # Increase timeout level: 7.5min → 15min (cap)
        if self.current_pq_timeout_level < len(self.pq_timeout_levels) - 1:
            self.current_pq_timeout_level += 1
        next_timeout = self.pq_timeout_levels[self.current_pq_timeout_level]
        
        # Mark activity to reset timer
        self._activity()
        self._log(f"Apps cleared. Next PQ timeout: {next_timeout//60}min. Looking for app_button...")
        time.sleep(2)
    
    def start(self):
        self._log("=" * 40)
        self._log("  MapleStory Idle Bot")
        self._log("=" * 40)
        self._log(f"Quest: {self.quest_choice}")
        self._log(f"Queue timeout: {self.queue_timeout}s")
        self._log(f"Stuck timeout: {self.stuck_timeout}s")
        
        self.running = True
        self.start_time = datetime.now()
        self.state = BotState.RUNNING
        self._activity()  # Initialize activity timer
        self.last_pq_entry_time = datetime.now()  # Initialize PQ entry timer
        
        if self.on_state_change:
            self.on_state_change(self.state)
        
        loaded = self.matcher.preload_templates()
        self._log(f"Loaded {loaded} templates")
        
        try:
            while self.running:
                if self.paused:
                    time.sleep(0.3)
                    continue
                self._tick()
                time.sleep(0.2)
        except Exception as e:
            self._log(f"Error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        self.running = False
        self.state = BotState.STOPPED
        if self.on_state_change:
            self.on_state_change(self.state)
        self._log(f"Stopped. Runs: {self.pq_runs}, Timeouts: {self.queue_timeouts}")
    
    def pause(self):
        self.paused = True
    
    def resume(self):
        self.paused = False
    
    def _tick(self):
        """Main tick - detect and act."""
        self._update_stats()
        
        screen = self.screen.capture(use_cache=False)
        if screen is None:
            return
        
        # HIGHEST PRIORITY: Check for lost connection popup
        if self._check_and_click(screen, "lost_connection"):
            self._log("!!! LOST CONNECTION - Clicking OK !!!")
            self._activity()
            # Reset state since connection was lost
            self.in_pq = False
            self.in_queue = False
            self.current_wave = 0
            self.consecutive_queue_timeouts = 0
            time.sleep(2)
            return
        
        # Check for event popup and close it
        if self._check_and_click(screen, "event"):
            self._log("Event popup - closing")
            time.sleep(1)
            return
        
        # Check if accidentally in party mode - leave to get back on track
        if self._check_and_click(screen, "leave_party"):
            self._log("In party mode - leaving party")
            time.sleep(1)
            return
        
        # Check if stuck and try recovery or restart
        if self._check_stuck(screen):
            return
        
        # === IN PQ MODE: Only look for waves and clear ===
        if self.in_pq:
            # Being in PQ and actively monitoring = valid activity (prevents false stuck detection)
            self._activity()
            
            # HIGHEST PRIORITY in wave 3: Check for red alert (boss attack)
            # Must check continuously during wave 3 - can appear anytime!
            if self.current_wave == 3:
                self._check_red_alert(screen)
                # Don't return - continue checking but with fast loop
            
            # Check for FAILED screen (PQ failed mid-run!)
            if self.matcher.find(screen, "failed"):
                self._log("!!! PQ FAILED - Recovering !!!")
                self.in_pq = False
                self.current_wave = 0
                self._activity()
                # Click center to dismiss failed screen
                self.input.tap(*self.POSITIONS["center"])
                time.sleep(1.5)
                # Try to click start_queue if visible, otherwise keep clicking center
                new_screen = self.screen.capture(use_cache=False)
                if new_screen is not None:
                    if self._check_and_click(new_screen, "start_queue"):
                        self._log("Restarting queue after failure")
                        self.in_queue = True
                        self.queue_start_time = datetime.now()
                    else:
                        # Try clicking center again to progress
                        self.input.tap(*self.POSITIONS["center"])
                time.sleep(1)
                return
            
            # Check if start_queue is visible while in PQ - means we failed and fail screen passed
            if self._check_and_click(screen, "start_queue"):
                self._log("!!! PQ FAILED (detected via start_queue) - Restarting queue !!!")
                self.in_pq = False
                self.current_wave = 0
                self._activity()
                self.in_queue = True
                self.queue_start_time = datetime.now()
                time.sleep(1)
                return
            
            # Check for CLEAR screen first (PQ complete!)
            if self.matcher.find(screen, "clear"):
                self._log("PQ finished!")
                self.in_pq = False
                self.current_wave = 0
                self.pq_runs += 1
                self.consecutive_queue_timeouts = 0  # Reset on successful PQ
                self._log(f"=== PQ #{self.pq_runs} Complete! ===")
                time.sleep(1)
                return
            
            # Check wave indicators (they only appear briefly at wave start!)
            # current_wave stays sticky - only updates when NEW wave indicator is seen
            wave = self._check_wave(screen)
            if wave > 0 and wave != self.current_wave:
                self._log(f"Wave {wave}")
                self.current_wave = wave
            
            # Wave 3: Check for red alert (boss attack can come anytime)
            if self.current_wave == 3:
                self._check_red_alert(screen)
            
            # Try to jump during PQ (if random_actions enabled)
            self._try_jump(screen)
            
            # Fast loop during PQ to catch brief wave indicators (0.5s)
            # Wave indicators only appear for a few seconds at wave start!
            time.sleep(0.5)
            return
        
        # === NOT IN PQ: Normal detection flow ===
        
        # PRIORITY 1: Check for CONFIRM button (time-sensitive!)
        if self._check_and_click(screen, "confirm"):
            self._log(">>> CONFIRM clicked!")
            self._activity()  # Meaningful event
            time.sleep(1)
            return
        
        # PRIORITY 2: Check if entering PQ (wave indicators)
        wave = self._check_wave(screen)
        if wave > 0:
            self._log(f"Entered PQ! Wave {wave}")
            self.in_pq = True
            self.in_queue = False
            self.current_wave = wave
            self.last_pq_entry_time = datetime.now()  # Reset PQ entry timer
            self.last_jump_time = None  # Reset jump timer for new PQ
            self._activity()  # Meaningful event
            time.sleep(3)
            return
        
        # PRIORITY 3: Handle queue
        if self.in_queue:
            self._handle_queue(screen)
            return
        
        # PRIORITY 4: Detect and act
        self._detect_and_act(screen)
    
    def _check_wave(self, screen) -> int:
        """Check if any wave indicator is visible. Returns wave number or 0."""
        # Different wave templates per quest
        if self.quest_choice == "ludibrium":
            if self.matcher.find(screen, "ludibrium_wave_33"):
                return 3
            if self.matcher.find(screen, "ludibrium_wave_22"):
                return 2
            if self.matcher.find(screen, "ludibrium_wave_11"):
                return 1
        elif self.quest_choice == "orbis":
            if self.matcher.find(screen, "orbis_wave_3"):
                return 3
            if self.matcher.find(screen, "orbis_wave_2"):
                return 2
            if self.matcher.find(screen, "orbis_wave_1"):
                return 1
        elif self.quest_choice == "sleepywood":
            if self.matcher.find(screen, "sleepywood_wave_3"):
                return 3
            if self.matcher.find(screen, "sleepywood_wave_2"):
                return 2
            if self.matcher.find(screen, "sleepywood_wave_1"):
                return 1
        return 0
    
    def _get_queue_template(self) -> str:
        """Get the in_queue template name based on quest choice."""
        return "in_queue_ludi" if self.quest_choice == "ludibrium" else "in_queue"
    
    def _check_and_click(self, screen, template: str) -> bool:
        """Check for template and click if found."""
        match = self.matcher.find(screen, template)
        if match:
            self.input.tap_center(match)
            return True
        return False
    
    def _try_jump(self, screen):
        """
        Try to double-tap jump button during PQ (if random_actions enabled).
        Only jumps every jump_interval seconds.
        """
        if not self.random_actions:
            return
        
        # Check if enough time has passed since last jump
        if self.last_jump_time:
            elapsed = (datetime.now() - self.last_jump_time).total_seconds()
            if elapsed < self.jump_interval:
                return
        
        # Find and double-tap jump button
        match = self.matcher.find(screen, "jump")
        if match:
            self._log("Jumping!")
            self.input.tap_center(match)
            time.sleep(0.1)  # Small delay between taps
            self.input.tap_center(match)
            self.last_jump_time = datetime.now()
    
    def _check_red_alert(self, screen) -> bool:
        """
        Check for red alert (boss red attack) during wave 3.
        Only active during wave 3 (sleepywood) or wave 33 (ludibrium).
        If detected, immediately double-jump to avoid the attack.
        Returns True if red alert was detected and jumped.
        """
        # Only check during wave 3
        if self.current_wave != 3:
            return False
        
        # Check for red_alert template
        red_alert = self.matcher.find(screen, "red_alert")
        if not red_alert:
            return False
        
        # RED ALERT DETECTED! Quick double-jump!
        self._log("!!! RED ALERT - JUMPING !!!")
        
        # Find jump button and double-tap immediately
        jump = self.matcher.find(screen, "jump")
        if jump:
            # Quick double-tap for double-jump
            self.input.tap_center(jump)
            time.sleep(0.05)  # Very short delay for faster response
            self.input.tap_center(jump)
            self.last_jump_time = datetime.now()  # Update jump timer
            return True
        else:
            self._log("Jump button not found!")
            return False
    
    def _handle_queue(self, screen):
        """Handle being in queue."""
        # Check timeout
        if self.queue_start_time:
            elapsed = (datetime.now() - self.queue_start_time).total_seconds()
            
            if elapsed >= self.queue_timeout:
                self._log(f"Queue timeout ({self.queue_timeout}s)! Canceling...")
                self.queue_timeouts += 1
                self.consecutive_queue_timeouts += 1
                
                # Check if too many consecutive timeouts (probably connection lost or stuck)
                if self.consecutive_queue_timeouts >= self.max_consecutive_timeouts:
                    self._log(f"!!! {self.consecutive_queue_timeouts} consecutive queue timeouts - Restarting app !!!")
                    self._restart_app()
                    return
                
                self._cancel_queue(screen)
                return
            
            if int(elapsed) % 10 == 0 and int(elapsed) > 0:
                self._log(f"Queue: {int(elapsed)}s / {self.queue_timeout}s")
        
        # Check if still in queue
        if self.matcher.find(screen, self._get_queue_template()):
            return
        
        # Check if PQ started (wave visible)
        if self._check_wave(screen):
            self._log("PQ starting!")
            self.in_queue = False
            self.in_pq = True
            self.consecutive_queue_timeouts = 0  # Reset on successful PQ entry
            self.last_pq_entry_time = datetime.now()  # Reset PQ entry timer
            self.last_jump_time = None  # Reset jump timer for new PQ
            self._activity()  # Real progress!
            return
        
        # Stop/cancel button visible = still on queue screen (avoid flip-flop with _detect_and_act)
        if self.matcher.find(screen, "stop_queue"):
            return
        
        # Not in queue anymore
        self._log("Left queue")
        self.in_queue = False
        self._detect_and_act(screen)
    
    def _cancel_queue(self, screen):
        """Cancel the queue."""
        self.in_queue = False
        
        if self._check_and_click(screen, "stop_queue"):
            self._log("Clicked stop queue")
            time.sleep(1)
            return
        
        self.input.tap(*self.POSITIONS["stop_queue"])
        time.sleep(0.3)
        self.input.press_back()
        time.sleep(1)
    
    def _detect_and_act(self, screen):
        """Detect where we are and take action."""
        
        # Loading screen - wait (but check frequently to catch wave indicators!)
        if (self.matcher.find(screen, "loading_screen") or
            self.matcher.find(screen, "loading_screen2") or
            self.matcher.find(screen, "loading_screen3") or
            self.matcher.find(screen, "loading_screen4") or
            self.matcher.find(screen, "loading_screen5")):
            self._log("Loading...")
            self._activity()  # Loading is progress
            time.sleep(1)  # Check every 1 second to catch wave transition
            return
        
        # In queue - track it
        if self.matcher.find(screen, self._get_queue_template()):
            if not self.in_queue:
                self._log("Now in queue!")
                self.in_queue = True
                self.queue_start_time = datetime.now()
                self._activity()  # Entering queue is progress
            return
        
        # Start queue button - click it
        if self._check_and_click(screen, "start_queue"):
            self._log("Clicking START QUEUE")
            self._activity()  # Button click is progress
            time.sleep(1)
            self.in_queue = True
            self.queue_start_time = datetime.now()
            return
        
        # Quest selection - select quest
        quest = self.quest_choice
        if self.matcher.find(screen, quest):
            self._log(f"Selecting {quest}...")
            self._check_and_click(screen, quest)
            self._activity()  # Quest selection is progress
            time.sleep(1)
            return
        
        # PQ button - click it
        if self._check_and_click(screen, "pq_button"):
            self._log("Clicking PQ button")
            self._activity()  # Button click is progress
            time.sleep(1)
            return
        
        # Main menu button - open menu
        if self._check_and_click(screen, "main_menu"):
            self._log("Opening main menu")
            self._activity()  # Button click is progress
            time.sleep(2.5)  # Wait for menu animation (game can be laggy)
            return
        
        # App button - open game
        if self._check_and_click(screen, "app_button"):
            self._log("Opening game")
            self._activity()  # Opening game is progress
            time.sleep(3)
            return
        
        # Stop queue visible - we're in queue
        if self.matcher.find(screen, "stop_queue"):
            self._log("In queue (stop visible)")
            self.in_queue = True
            self._activity()  # Queue detected is progress
            if not self.queue_start_time:
                self.queue_start_time = datetime.now()
            return
        
        # Nothing recognized - tap center (check again soon in case wave appears)
        self._log("Unknown screen, tapping...")
        self.input.tap(*self.POSITIONS["center"])
        time.sleep(2)  # Check again in 2 seconds to catch wave transitions
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "state": self.state.name,
            "pq_runs": self.pq_runs,
            "queue_timeouts": self.queue_timeouts,
            "recoveries": self.recoveries,
            "restarts": self.restarts,
            "hard_resets": self.hard_resets,
            "runtime": str(datetime.now() - self.start_time).split('.')[0] if self.start_time else "00:00:00",
            "in_queue": self.in_queue,
            "in_pq": self.in_pq,
            "current_wave": self.current_wave,
            "running": self.running
        }
