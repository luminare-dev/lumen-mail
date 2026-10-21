"""Run the LESS compiler (compile.mjs under Node, or a stand-in for tests).

The command is "node <package>/compile.mjs" by default. LUMEN_MAIL_COMPILER (or --compiler)
replaces it with any command that speaks the same JSON protocol on stdin/stdout; the tests use a
small Python stand-in so they run without Node.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .sources import Sources
from .util import LumenError

DEFAULT_TIMEOUT = 600
# The compile runs on a small, busy host: cap the V8 heap unless the caller chose a limit.
DEFAULT_NODE_OPTIONS = "--max-old-space-size=320"


class CompileError(LumenError):
    exit_code = 4


@dataclass
class CompileJob:
    entry: Path
    css: Path
    min: Path


def compiler_command(sources: Sources, override: str | None = None, node: str | None = None) -> list[str]:
    override = override or os.environ.get("LUMEN_MAIL_COMPILER")
    if override:
        return shlex.split(override)
    node = node or os.environ.get("LUMEN_MAIL_NODE") or "node"
    return [node, str(sources.compile_script)]


def run_compiler(command: list[str], jobs: list[CompileJob], node_modules: Path,
                 timeout: int = DEFAULT_TIMEOUT) -> dict:
    payload = {
        "node_modules": str(node_modules),
        "jobs": [{"entry": str(j.entry), "css": str(j.css), "min": str(j.min)} for j in jobs],
    }
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", DEFAULT_NODE_OPTIONS)
    try:
        proc = subprocess.run(command, input=json.dumps(payload), capture_output=True, text=True,
                              timeout=timeout, env=env, check=False)
    except FileNotFoundError as exc:
        raise CompileError(f"cannot start the compiler {command[0]!r} (is Node installed?)") from exc
    except subprocess.TimeoutExpired as exc:
        raise CompileError(f"the compiler did not finish within {timeout} s") from exc
    lines = [line for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    try:
        result = json.loads(lines[-1]) if lines else None
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict):
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
        raise CompileError(f"the compiler failed (exit {proc.returncode}) without a readable result", tail)
    if not result.get("ok"):
        where = result.get("file") or "?"
        if result.get("line"):
            where += f":{result['line']}"
        raise CompileError(f"LESS compilation failed: {result.get('error')}", [f"at {where}"])
    return result
