"""
log/logger.py

Logging configuration for SimASM.

Usage:
    from simasm.log.logger import get_logger, LOG

    logger = get_logger(__name__)
    logger.info("Starting process")

    # Toggle logging
    LOG.disable()   # Turn off all logging
    LOG.enable()    # Turn on logging
    LOG.level = "warning"  # Change level globally

    # Check state
    if LOG.enabled:
        print("Logging is on")
"""

import logging
import sys
from typing import Optional, Dict
from pathlib import Path


# =============================================================================
# Log Controller (Singleton)
# =============================================================================

class LogController:
    """
    Central controller for all SimASM logging.

    Usage:
        from simasm.log.logger import LOG

        LOG.enable()
        LOG.disable()
        LOG.level = "debug"
        LOG.to_file = True
        LOG.to_console = True
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._enabled = False
        self._level = "debug"
        self._to_console = True
        self._to_file = False
        self._log_dir: Optional[Path] = None
        self._loggers: Dict[str, logging.Logger] = {}
        self._format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        self._date_format = "%H:%M:%S"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def level(self) -> str:
        return self._level

    @level.setter
    def level(self, value: str):
        self._level = value.lower()
        self._update_all_loggers()

    @property
    def to_console(self) -> bool:
        return self._to_console

    @to_console.setter
    def to_console(self, value: bool):
        self._to_console = value
        if self._enabled:
            self._update_all_loggers()

    @property
    def to_file(self) -> bool:
        return self._to_file

    @to_file.setter
    def to_file(self, value: bool):
        self._to_file = value
        if self._enabled:
            self._update_all_loggers()

    @property
    def log_dir(self) -> Optional[Path]:
        return self._log_dir

    @log_dir.setter
    def log_dir(self, value):
        self._log_dir = Path(value) if value else None

    def enable(self, level: Optional[str] = None):
        """Enable logging."""
        self._enabled = True
        if level:
            self._level = level.lower()
        self._update_all_loggers()

    def disable(self):
        """Disable logging."""
        self._enabled = False
        self._update_all_loggers()

    def _get_level(self) -> int:
        levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }
        return levels.get(self._level, logging.DEBUG)

    def _update_all_loggers(self):
        """Update all registered loggers."""
        for name, logger in self._loggers.items():
            self._configure_logger(logger, name)

    def _configure_logger(self, logger: logging.Logger, name: str):
        """Configure a single logger based on current settings."""
        # Clear existing handlers
        logger.handlers.clear()

        if not self._enabled:
            logger.addHandler(logging.NullHandler())
            logger.setLevel(logging.CRITICAL + 1)  # effectively disable
            return

        logger.setLevel(self._get_level())
        formatter = logging.Formatter(self._format, datefmt=self._date_format)

        if self._to_console:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(formatter)
            handler.setLevel(self._get_level())
            logger.addHandler(handler)

        if self._to_file and self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            filepath = self._log_dir / f"{name.replace('.', '_')}.log"
            handler = logging.FileHandler(filepath, mode='a')
            handler.setFormatter(formatter)
            handler.setLevel(self._get_level())
            logger.addHandler(handler)

        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

    def register(self, name: str) -> logging.Logger:
        """Register and configure a logger."""
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.propagate = False
        self._loggers[name] = logger
        self._configure_logger(logger, name)
        return logger


# Singleton instance
LOG = LogController()


# =============================================================================
# Public API
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the given module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Hello")
    """
    return LOG.register(name)


def enable_logging(level: str = "debug", to_console: bool = True, to_file: bool = False, log_dir: Optional[str] = None):
    """
    Enable logging with specified settings.

    Args:
        level: Log level (debug, info, warning, error, critical)
        to_console: Log to stderr
        to_file: Log to files
        log_dir: Directory for log files
    """
    LOG._to_console = to_console
    LOG._to_file = to_file
    if log_dir:
        LOG._log_dir = Path(log_dir)
    LOG.enable(level)


def disable_logging():
    """Disable all logging."""
    LOG.disable()
