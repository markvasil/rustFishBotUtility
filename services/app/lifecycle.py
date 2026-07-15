from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional


def terminate_process(proc: Optional[subprocess.Popen], *, label: str = "process") -> None:
    if proc is None or proc.poll() is not None:
        return

    pid = proc.pid
    try:
        proc.terminate()
        proc.wait(timeout=3)
        return
    except Exception:
        pass

    try:
        proc.kill()
        proc.wait(timeout=2)
        return
    except Exception:
        pass

    if sys.platform == "win32" and pid:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass


def force_exit(code: int = 0) -> None:
    """Гарантированно завершить процесс приложения."""
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)
