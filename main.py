#!/usr/bin/env python3
"""
MapleStory Idle Bot - Main Entry Point

A bot that automates party quests in MapleStory Idle via BlueStacks.

Usage:
    python main.py          # Launch GUI
    python main.py --cli    # Run in CLI mode
    python main.py --help   # Show help
"""

import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))


def run_gui():
    """Launch the graphical user interface."""
    try:
        from gui.launcher import BotLauncher
        app = BotLauncher()
        app.run()
    except ImportError as e:
        print(f"Error: GUI dependencies not installed: {e}")
        print("Install with: pip install customtkinter pillow")
        sys.exit(1)


def run_cli(args):
    """Run in command-line interface mode."""
    from core.adb_controller import ADBController
    from core.logger import setup_logger
    from config import ConfigManager
    from games.maple_story_idle import MapleStoryIdleBot
    
    # Load configuration
    config_manager = ConfigManager(args.config)
    config = config_manager.load()
    
    # Override with CLI arguments
    if args.port:
        config.setdefault("adb", {})["port"] = args.port
    if args.quest:
        config.setdefault("bot-option", {})["quest-choice"] = args.quest
    if args.solo:
        config.setdefault("bot-option", {})["solo-option"] = True
    
    # Setup logger
    log_level = args.debug and "debug" or config.get("loglevel", "info")
    max_log_files = config.get("max-log-files", 5)
    logger = setup_logger("maple_bot", log_level, max_log_files=max_log_files)
    if getattr(logger, "_log_file_path", None):
        print(f"Log file: {logger._log_file_path}")
    
    # Connect to BlueStacks
    adb_config = config.get("adb", {})
    adb = ADBController(
        host=adb_config.get("host", "127.0.0.1"),
        port=adb_config.get("port", 5555),
        logger=logger
    )
    
    if not adb.connect():
        logger.error("Failed to connect to BlueStacks!")
        logger.error("Make sure:")
        logger.error("  1. BlueStacks is running")
        logger.error("  2. ADB is enabled (Settings > Advanced > Android Debug Bridge)")
        logger.error("  3. The correct port is configured")
        sys.exit(1)
    
    # Create and run bot
    bot_config = config.get("bot-option", {})
    bot_config["templates_dir"] = str(Path(__file__).parent / "templates" / "maple_story_idle")
    
    bot = MapleStoryIdleBot(adb, bot_config, logger)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        bot.stop()
        adb.disconnect()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MapleStory Idle Bot - Automate party quests via BlueStacks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                    # Launch GUI
    python main.py --cli              # Run in CLI mode with default config
    python main.py --cli --port 5555  # Specify ADB port
    python main.py --cli --quest ludibrium --solo  # Ludibrium solo mode

BlueStacks Setup:
    1. Set resolution to 960x540 (Settings > Display)
    2. Set pixel density to 240 DPI
    3. Enable ADB (Settings > Advanced > Android Debug Bridge)
    4. Restart BlueStacks after enabling ADB
        """
    )
    
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in command-line mode (no GUI)"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/settings.yaml",
        help="Path to configuration file (default: config/settings.yaml)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        help="ADB port (default: from config or 5555)"
    )
    parser.add_argument(
        "--quest", "-q",
        choices=["sleepywood", "ludibrium", "zakum", "orbis"],
        help="Party quest to run"
    )
    parser.add_argument(
        "--solo", "-s",
        action="store_true",
        help="Enable solo mode"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    parser.add_argument(
        "--create-config",
        action="store_true",
        help="Create default configuration file and exit"
    )
    
    args = parser.parse_args()
    
    if args.create_config:
        from config import create_default_config
        create_default_config(args.config)
        print(f"Configuration created at: {args.config}")
        sys.exit(0)
    
    if args.cli:
        run_cli(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()

