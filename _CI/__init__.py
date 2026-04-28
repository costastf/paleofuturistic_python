"""Root CI package — shared constants and utilities for the template test harness."""

import logging
import os
import stat
from pathlib import Path

PROJECT_ROOT_DIRECTORY = next(
    parent for parent in Path(__file__).resolve().parents if (parent / '_CI').is_dir()
)
INVOKE_LOGGING_LEVEL = os.environ.get('INVOKE_LOGGING_LEVEL') or 'INFO'


def validate_log_level(level: str) -> int:
    """Validate a log level string, returning the numeric level (INFO if invalid)."""
    levels = ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET')
    level = level.upper()
    return getattr(logging, level) if level in levels else logging.INFO


def make_file_executable(filename: Path) -> None:
    """Add the executable bit to a file."""
    filename.chmod(filename.stat().st_mode | stat.S_IEXEC)


def emojize_message(message: str, success: bool = True) -> str:
    """Wrap a message with status emojis."""
    prefix, suffix = ('✅', '👍') if success else ('❌', '👎')
    return f'{prefix}  {message} {suffix}'
