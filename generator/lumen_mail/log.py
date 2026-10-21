"""Messages for people and for the systemd journal.

Every message goes to stderr. When stderr is the journal stream of a systemd service (systemd
sets $JOURNAL_STREAM to "<device>:<inode>" of that stream), each line gets a "<N>" syslog
priority prefix, which journald turns into the PRIORITY field. The sync unit sets
LogLevelMax=notice, so info lines (and systemd's own "Starting"/"Finished" lines for the unit)
are dropped there and a run with nothing to do leaves no trace in the journal, while a restore,
a rebuild (notice) and every failure (warning, error) are kept.

Outside the journal, warnings and errors are prefixed with "warning: " and "error: ".
"""

from __future__ import annotations

import io
import os
import sys
from typing import TextIO

PRIORITY = {"error": 3, "warning": 4, "notice": 5, "info": 6, "debug": 7}


def stderr_is_journal(stream: TextIO | None = None) -> bool:
    value = os.environ.get("JOURNAL_STREAM", "")
    if not value:
        return False
    stream = stream or sys.stderr
    try:
        dev, ino = (int(part) for part in value.split(":", 1))
        st = os.fstat(stream.fileno())
    except (ValueError, OSError, AttributeError, io.UnsupportedOperation):
        return False
    return (st.st_dev, st.st_ino) == (dev, ino)


class Log:
    def __init__(self, quiet: bool = False, verbose: bool = False, stream: TextIO | None = None):
        self.quiet = quiet
        self.verbose = verbose
        self._stream = stream
        self.journal = stderr_is_journal(stream)

    @property
    def stream(self) -> TextIO:
        return self._stream or sys.stderr

    def emit(self, level: str, message: str) -> None:
        prio = PRIORITY[level]
        if prio >= PRIORITY["debug"] and not self.verbose:
            return
        if prio >= PRIORITY["info"] and self.quiet:
            return
        for line in message.splitlines() or [""]:
            if self.journal:
                text = f"<{prio}>{line}"
            elif level in ("error", "warning"):
                text = f"{level}: {line}"
            else:
                text = line
            print(text, file=self.stream)
        self.stream.flush()

    def error(self, message: str) -> None:
        self.emit("error", message)

    def warning(self, message: str) -> None:
        self.emit("warning", message)

    def notice(self, message: str) -> None:
        self.emit("notice", message)

    def info(self, message: str) -> None:
        self.emit("info", message)

    def debug(self, message: str) -> None:
        self.emit("debug", message)
