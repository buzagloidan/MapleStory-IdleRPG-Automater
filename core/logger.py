"""
Logging configuration for the bot.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

try:
    import colorlog
    HAS_COLORLOG = True
except ImportError:
    HAS_COLORLOG = False


def setup_logger(
    name: str = "maple_bot",
    level: str = "info",
    log_to_file: bool = True,
    max_log_files: int = 5,
) -> logging.Logger:
    """
    Set up a configured logger with optional color output and file logging.
    
    Args:
        name: Logger name
        level: Log level (debug, info, warning, error)
        log_to_file: Whether to also log to a file
        max_log_files: Keep only this many most recent bot_*.log files (0 = keep all)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Set level
    level_map = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        'error': logging.ERROR
    }
    logger.setLevel(level_map.get(level.lower(), logging.INFO))
    
    # Console handler with colors
    if HAS_COLORLOG:
        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    else:
        console_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler: always under project directory
    logger._log_file_path = None
    if log_to_file:
        try:
            # Project root = parent of directory containing this file (core/)
            project_root = Path(__file__).resolve().parent.parent
            log_dir = project_root / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            file_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            # Timestamped log (one per run)
            log_file = log_dir / f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
            logger._log_file_path = str(log_file.resolve())
            # Prune old logs: keep only the max_log_files most recent
            if max_log_files > 0:
                try:
                    bot_logs = sorted(
                        log_dir.glob("bot_*.log"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    for old in bot_logs[max_log_files:]:
                        old.unlink(missing_ok=True)
                except OSError:
                    pass
        except Exception as e:
            import traceback
            print(f"Warning: Could not create log file: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
    
    return logger

