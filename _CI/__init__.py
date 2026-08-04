"""Root CI package — shared constants and utilities for the template test harness."""

import logging
import os
import platform
import shutil
import stat
import subprocess
import webbrowser
from contextlib import suppress
from pathlib import Path

# WSL registers a binfmt handler to run Windows executables. A distro with interop
# disabled has neither name, and then nothing can reach a Windows browser.
WSL_INTEROP_MARKERS = (
    '/proc/sys/fs/binfmt_misc/WSLInterop',
    '/proc/sys/fs/binfmt_misc/WSLInterop-late',
)

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


def is_wsl() -> bool:
    """Return True when running under WSL (detected via /proc/version)."""
    if platform.system() != 'Linux':
        return False
    with suppress(OSError), open('/proc/version', encoding='utf-8') as proc_version:
        return any(marker in proc_version.read().lower() for marker in ('microsoft', 'wsl'))
    return False


def open_in_default_application(target: Path) -> None:
    """Open a local file with the host's default application.

    Off WSL, `webbrowser` handles this. Under WSL it cannot: there is no Linux browser to
    hand the file to, so it has to go to Windows, which needs three accommodations —
    `wslu`'s `wslview` is deprecated and frequently absent (still used when present, so
    existing setups keep working), Windows cannot resolve a Linux path so `wslpath -w`
    translates it, and `cmd.exe` exits non-zero even on success so its status is ignored.

    Mirrors `open_target` in the template's `_CI/tasks/shared.py`. The two are separate
    because this harness does not ship that module; keep them in step.
    """
    if not is_wsl():
        webbrowser.open(target.as_uri())
        return
    if shutil.which('wslview'):
        subprocess.run(['wslview', str(target)], check=False)
        return
    if not any(os.path.exists(marker) for marker in WSL_INTEROP_MARKERS):
        print(f'WSL interop is disabled, so {target} cannot be handed to Windows. Open it manually.')
        return
    translated = subprocess.run(['wslpath', '-w', str(target)], capture_output=True, text=True, check=False)
    windows_path = translated.stdout.strip()
    if translated.returncode != 0 or not windows_path:
        print(f'Could not translate {target} to a Windows path. Open it manually.')
        return
    # The empty '' is `start`'s window-title argument. Without it cmd.exe reads the
    # quoted path as the title and opens nothing.
    subprocess.run(['cmd.exe', '/c', 'start', '', windows_path], check=False)
