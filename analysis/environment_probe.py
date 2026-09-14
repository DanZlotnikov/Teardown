"""Capture the local runtime relevant to reproducibility and local-model feasibility."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def command(args: list[str], timeout: int = 10) -> dict:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return {"available": True, "exit_code": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"available": False, "error": "command not found"}
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"timed out after {timeout}s"}


def get_json(url: str, timeout: int = 5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"available": True, "value": json.loads(response.read())}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def windows_hardware() -> dict:
    if os.name != "nt":
        return {}
    script = (
        "$c=Get-CimInstance Win32_ComputerSystem;"
        "$p=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "[pscustomobject]@{manufacturer=$c.Manufacturer;model=$c.Model;"
        "ram_bytes=[int64]$c.TotalPhysicalMemory;cpu=$p.Name;"
        "cores=$p.NumberOfCores;logical_processors=$p.NumberOfLogicalProcessors}|ConvertTo-Json -Compress"
    )
    result = command(["powershell", "-NoProfile", "-Command", script])
    if result.get("exit_code") == 0 and result.get("stdout"):
        return json.loads(result["stdout"])
    return {"probe_error": result}


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("results/environment.json"))
    args = parser.parse_args()
    report = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": {"version": sys.version, "executable": sys.executable},
        "hardware": windows_hardware(),
        "nvidia": command(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]),
        "docker_client": command(["docker", "--version"]),
        "docker_daemon": command(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=8),
        "ollama_version": get_json("http://127.0.0.1:11434/api/version"),
        "ollama_models": get_json("http://127.0.0.1:11434/api/tags"),
    }
    atomic_json(args.output, report)
    print(json.dumps({"output": str(args.output), "ollama_available": report["ollama_version"]["available"], "docker_daemon_exit_code": report["docker_daemon"].get("exit_code")}, sort_keys=True))


if __name__ == "__main__":
    main()
