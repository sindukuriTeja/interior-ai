"""Shared helpers for the Interior AI pipeline.

Each pipeline stage is a standalone script that reads/writes JSON files inside
a project directory, so stages can run independently or be chained:

    analyze.py -> design.py -> collect.py -> render.py -> build_site.py

Project layout:
    projects/<name>/
        input.<ext>          # uploaded floor plan image or video
        frames/              # extracted video frames (video input only)
        analysis.json        # room layout + measurements from vision AI
        design.json          # design concept + shopping list
        products.json        # collected real products (prices, links)
        renders/             # generated interior render images
        catalog.html         # final self-contained catalog page
        status.json          # pipeline progress (polled by the web UI)
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS = os.path.join(ROOT, "projects")


def project_dir(name):
    d = os.path.join(PROJECTS, name)
    os.makedirs(d, exist_ok=True)
    return d


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def status_path(name):
    return os.path.join(project_dir(name), "status.json")


def set_status(name, stage, progress, message, stage_order=None):
    path = status_path(name)
    data = {}
    if os.path.exists(path):
        try:
            data = read_json(path)
        except Exception:
            data = {}
    stages = data.get("stages", {})
    stages[stage] = {
        "progress": progress,
        "message": message,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data["stages"] = stages
    data["current_stage"] = stage
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if stage_order:
        data["stage_order"] = stage_order
    write_json(path, data)


def run_skill(agent_function, payload, timeout=300):
    """Call a pokee-skill function and return the parsed JSON result."""
    cmd = ["pokee-skill", agent_function]
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"pokee-skill {agent_function} failed: {proc.stderr.strip()[:500]}"
        )
    out = proc.stdout.strip()
    # Some wrappers print a log line before the JSON; find the first '{'.
    start = out.find("{")
    if start < 0:
        raise RuntimeError(f"no JSON in skill output: {out[:300]}")
    return json.loads(out[start:])


def log(msg):
    print(f"[interior-ai] {msg}", flush=True)