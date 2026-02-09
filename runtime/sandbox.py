"""
Venv-based isolated execution sandbox.

Note:
- This enforces process-level isolation using a dedicated virtual environment.
- Full filesystem/network isolation requires containerization and host controls.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None  # type: ignore[assignment]


@dataclass
class SandboxSession:
    session_id: str
    root_dir: Path
    venv_dir: Path
    python_bin: Path
    pip_bin: Path


@dataclass
class SandboxExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    memory_kb: int


class SandboxConfig(BaseModel):
    root_dir: str = ".dwc/sandboxes"
    base_python: str = sys.executable
    timeout_seconds: int = 180
    preserve_session: bool = False
    inherit_env: bool = True
    env_allowlist: List[str] = Field(
        default_factory=lambda: [
            "AWS_REGION",
            "AWS_DEFAULT_REGION",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        ]
    )


class VenvSandbox:
    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        self.config = config or SandboxConfig()
        self.root_dir = Path(self.config.root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self, workflow_name: str) -> SandboxSession:
        safe_name = "".join(char if char.isalnum() or char == "_" else "_" for char in workflow_name)
        session_id = f"{safe_name}-{uuid.uuid4().hex[:12]}"
        session_root = self.root_dir / session_id
        venv_dir = session_root / "venv"
        session_root.mkdir(parents=True, exist_ok=True)

        subprocess.run(
            [self.config.base_python, "-m", "venv", str(venv_dir)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        bin_dir = "Scripts" if os.name == "nt" else "bin"
        python_bin = venv_dir / bin_dir / ("python.exe" if os.name == "nt" else "python")
        pip_bin = venv_dir / bin_dir / ("pip.exe" if os.name == "nt" else "pip")
        if not python_bin.exists():
            raise RuntimeError("Sandbox python binary not found after virtualenv creation.")

        return SandboxSession(
            session_id=session_id,
            root_dir=session_root,
            venv_dir=venv_dir,
            python_bin=python_bin,
            pip_bin=pip_bin,
        )

    def install_requirements(
        self, session: SandboxSession, requirements: Optional[List[str]]
    ) -> None:
        if not requirements:
            return
        command = [
            str(session.pip_bin),
            "install",
            "--disable-pip-version-check",
            "--no-input",
            *requirements,
        ]
        subprocess.run(
            command,
            cwd=str(session.root_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def run_script(
        self,
        session: SandboxSession,
        script_path: str,
        input_payload: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> SandboxExecutionResult:
        command = [str(session.python_bin), script_path]
        payload = json.dumps(input_payload or {})
        timeout = timeout_seconds or self.config.timeout_seconds

        env = {}
        if self.config.inherit_env:
            env.update(os.environ)
        else:
            for key in self.config.env_allowlist:
                if key in os.environ:
                    env[key] = os.environ[key]

        rss_before = self._memory_kb()
        start = time.time()
        try:
            completed = subprocess.run(
                command,
                cwd=str(session.root_dir),
                input=payload,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
            )
            duration_ms = int((time.time() - start) * 1000)
            rss_after = self._memory_kb()
            return SandboxExecutionResult(
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=duration_ms,
                memory_kb=max(0, rss_after - rss_before),
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start) * 1000)
            rss_after = self._memory_kb()
            return SandboxExecutionResult(
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=(exc.stderr or "") + "\nTimeoutExpired",
                duration_ms=duration_ms,
                memory_kb=max(0, rss_after - rss_before),
            )

    def cleanup(self, session: SandboxSession) -> None:
        if self.config.preserve_session:
            return
        shutil.rmtree(session.root_dir, ignore_errors=True)

    @staticmethod
    def _memory_kb() -> int:
        if resource is None:
            return 0
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return int(usage.ru_maxrss)
