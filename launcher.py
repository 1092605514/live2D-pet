#!/usr/bin/env python3
"""
喵酱 Live2D Desktop Pet — Unified Launcher

Usage:
    python launcher.py              Start everything (backend + pet, PySide6)
    python launcher.py pet          Start just the pet (PySide6)
    python launcher.py electron     Start just the pet (Electron)
    python launcher.py backend      Start just the backend
    python launcher.py test         Run full test suite
    python launcher.py test fast    Run unit tests only (skip e2e)
    python launcher.py test e2e     Run end-to-end tests only
    python launcher.py status       Check what services are running
    python launcher.py install      Check dependencies
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OPEN_LLM_VTUBER_DIR = BASE_DIR.parent / "Open-LLM-VTuber"
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
VENV_UV = BASE_DIR / ".venv" / "Scripts" / "uv.exe"

BACKEND_URL = "http://localhost:12393"
OLLAMA_URL = "http://localhost:11434"


# ═══════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════

def _info(msg: str):
    print(f"  [.] {msg}")

def _ok(msg: str):
    print(f"  [OK] {msg}")

def _warn(msg: str):
    print(f"  [!] {msg}")

def _err(msg: str):
    print(f"  [ERR] {msg}")


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    """Quick HTTP health check."""
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def _find_uv() -> str:
    """Locate `uv` executable."""
    # Check venv first
    if VENV_UV.exists():
        return str(VENV_UV)
    # Then PATH
    import shutil
    return shutil.which("uv") or "uv"


def _find_python() -> str:
    """Locate project Python (venv preferred, with health check)."""
    if VENV_PYTHON.exists():
        try:
            subprocess.run(
                [str(VENV_PYTHON), "-c", "pass"],
                capture_output=True, timeout=5, check=True,
            )
            return str(VENV_PYTHON)
        except Exception as e:
            _warn(f"venv python broken ({e}), falling back to system")
    return sys.executable


# ═══════════════════════════════════════════════════════════════
# Checks
# ═══════════════════════════════════════════════════════════════

def cmd_status():
    """Check what's running."""
    print(f"\n  {'='*45}")
    print(f"  喵酱 Live2D Desktop Pet — Status")
    print(f"  {'='*45}\n")

    # Ollama
    ollama_ok = _http_ok(f"{OLLAMA_URL}/api/tags", timeout=3)
    (_ok if ollama_ok else _err)("Ollama" + (" running" if ollama_ok else " NOT running"))

    # Backend
    bk_ok = _http_ok(BACKEND_URL)
    (_ok if bk_ok else _err)("Backend (Open-LLM-VTuber)" + (" running" if bk_ok else " NOT running"))

    if bk_ok:
        # Try to get model info
        try:
            import urllib.request
            with urllib.request.urlopen(f"{BACKEND_URL}/status", timeout=3) as r:
                data = json.loads(r.read())
                _info(f"  LLM model: {data.get('current_model', 'unknown')}")
        except Exception:
            pass

    # Venv
    venv_ok = VENV_PYTHON.exists()
    (_ok if venv_ok else _err)("Python venv" + (" found" if venv_ok else " MISSING — run 'python launcher.py install'"))

    # Dependencies
    if venv_ok:
        try:
            import PySide6
            _ok("PySide6 installed")
        except ImportError:
            _err("PySide6 NOT installed — run 'python launcher.py install'")
    else:
        _err("Cannot check PySide6 — venv missing")

    print()


def cmd_install():
    """Check and install dependencies."""
    print(f"\n  {'='*45}")
    print(f"  喵酱 Live2D Desktop Pet — Install Dependencies")
    print(f"  {'='*45}\n")

    # Check pip install
    pkgs = ["PySide6>=6.6.0", "pynput>=1.7.0"]
    _info(f"Installing: {', '.join(pkgs)}")
    try:
        subprocess.check_call(
            [str(VENV_PYTHON), "-m", "pip", "install", "--quiet"] + pkgs
        )
        _ok("Dependencies installed")
    except Exception as e:
        _err(f"Install failed: {e}")
        return 1

    # Check node_modules for Electron
    node_dir = BASE_DIR / "node_modules"
    if not node_dir.is_dir():
        _info("Installing Electron dependencies...")
        try:
            subprocess.check_call(
                ["npm", "install"],
                cwd=str(BASE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _ok("Node dependencies installed")
        except Exception:
            _warn("npm install skipped (not needed for PySide6 mode)")
    else:
        _ok("Node dependencies present")

    print()
    return 0


# ═══════════════════════════════════════════════════════════════
# Backend
# ═══════════════════════════════════════════════════════════════

BACKEND_PROC: Optional["subprocess.Popen"] = None


def cmd_backend():
    """Start the Open-LLM-VTuber backend if not running."""
    global BACKEND_PROC

    print(f"\n  {'='*45}")
    print(f"  喵酱 Live2D Desktop Pet — Backend")
    print(f"  {'='*45}\n")

    if _http_ok(BACKEND_URL):
        _ok("Backend already running")
        return 0

    if not OPEN_LLM_VTUBER_DIR.is_dir():
        _err(f"Open-LLM-VTuber not found at {OPEN_LLM_VTUBER_DIR}")
        return 1

    _info("Starting backend...")
    env = os.environ.copy()
    env["NO_PROXY"] = "localhost,127.0.0.1,::1,.local"
    env["no_proxy"] = "localhost,127.0.0.1,::1,.local"

    uv = _find_uv()
    flags = 0
    if sys.platform == "win32":
        try:
            import subprocess as sp
            flags = sp.CREATE_NO_WINDOW | sp.DETACHED_PROCESS
        except AttributeError:
            pass

    BACKEND_PROC = subprocess.Popen(
        [uv, "run", "run_server.py"],
        cwd=str(OPEN_LLM_VTUBER_DIR),
        env=env,
        creationflags=flags,
    )

    # Poll until ready
    _info("Waiting for backend...")
    for i in range(30):
        time.sleep(1)
        if _http_ok(BACKEND_URL):
            _ok(f"Backend ready ({i+1}s)")
            return 0
        if i % 5 == 4:
            _info(f"  still waiting... ({i+1}s)")

    _err("Backend failed to start within 30s")
    return 1


# ═══════════════════════════════════════════════════════════════
# Pet
# ═══════════════════════════════════════════════════════════════

def cmd_pet():
    """Launch the PySide6 pet."""
    python = _find_python()
    _info(f"Starting pet (PySide6)...")
    # ── Load .env for secure keys ──
    env = os.environ.copy()
    dotenv_path = BASE_DIR / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())
    subprocess.run([python, str(BASE_DIR / "main.py")], cwd=str(BASE_DIR), env=env)


def cmd_electron():
    """Launch the Electron pet."""
    node_dir = BASE_DIR / "node_modules"
    if not (node_dir / "electron" / "dist" / "electron.exe").exists():
        _warn("Electron not installed. Running npm install...")
        subprocess.check_call(
            ["npm", "install"],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
        )
    _info("Starting pet (Electron)...")
    subprocess.run(["npx", "electron", "."], cwd=str(BASE_DIR))


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════

def cmd_test(mode: str = "all"):
    """Run tests."""
    python = _find_python()

    pytest_args = [str(python), "-m", "pytest", "tests/"]

    if mode == "fast":
        pytest_args.extend(["-k", "not e2e", "-v"])
    elif mode == "e2e":
        pytest_args.extend(["-k", "e2e", "-v"])
    else:
        pytest_args.append("-v")

    print(f"\n  {'='*45}")
    print(f"  喵酱 Live2D Desktop Pet — Tests ({mode})")
    print(f"  {'='*45}\n")

    result = subprocess.run(pytest_args, cwd=str(BASE_DIR))
    print()
    return result.returncode


# ═══════════════════════════════════════════════════════════════
# Start (everything)
# ═══════════════════════════════════════════════════════════════

def cmd_start():
    """Start backend + pet."""
    rc = cmd_backend()
    if rc != 0:
        _warn("Backend may not be ready. Proceeding anyway...")

    print(f"\n  {'='*45}")
    print(f"  喵酱 Live2D Desktop Pet — Launching Pet")
    print(f"  {'='*45}\n")

    cmd_pet()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="喵酱 Live2D Desktop Pet — Unified Launcher",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="start",
        choices=["start", "pet", "electron", "backend", "test", "status", "install"],
        help="Command to run (default: start)",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        help="Test mode: all / fast / e2e (only for 'test' command)",
    )

    args = parser.parse_args()

    # ── Run command ──
    cmds = {
        "status": lambda: cmd_status(),
        "install": lambda: cmd_install(),
        "backend": lambda: cmd_backend(),
        "pet": lambda: cmd_pet(),
        "electron": lambda: cmd_electron(),
        "test": lambda: cmd_test(args.mode if args.mode else "all"),
        "start": lambda: cmd_start(),
    }

    rc = cmds[args.command]()
    sys.exit(rc if rc else 0)


if __name__ == "__main__":
    main()
