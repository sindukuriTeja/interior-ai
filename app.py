#!/usr/bin/env python3
"""Interior AI — web platform.

Upload a floor plan (image) or video, pick a style, and the pipeline runs:
analyze -> design -> collect (real products) -> render (AI images) -> build
(a beautiful catalog page + PDF report).

Run:
    python3 app.py            # http://localhost:8090
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.join(ROOT, "pipeline")
sys.path.insert(0, PIPELINE)

from flask import Flask, jsonify, render_template, request, send_from_directory

from common import PROJECTS, project_dir, read_json, set_status, write_json, log

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB uploads

UPLOADS = os.path.join(ROOT, "uploads")
os.makedirs(UPLOADS, exist_ok=True)

STAGE_ORDER = ["analyze", "design", "collect", "render", "build", "video_out"]
STAGE_LABEL = {
    "analyze": "Analyzing floor plan",
    "design": "Creating design concept",
    "collect": "Collecting real products & prices",
    "render": "Generating interior renders",
    "build": "Building your catalog",
    "video_out": "Creating your designed video",
}

_running = {}  # name -> thread


def safe_name(s):
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-").lower()
    return s or "project"


def run_pipeline(name, input_file, style):
    # hard stages: a failure stops the pipeline
    hard = [
        ("analyze", ["analyze.py", name, input_file]),
        ("design", ["design.py", name, style]),
        ("collect", ["collect.py", name]),
        ("render", ["render.py", name]),
        ("build", ["build_site.py", name]),
        ("report", ["report.py", name]),
    ]
    # soft stages: a failure is recorded but the pipeline still completes
    # (the catalog + PDF are already ready at this point)
    soft = [
        ("video_out", ["video_out.py", name]),
    ]
    hard_stages = {s for s, _ in hard}
    try:
        for stage, args in hard + soft:
            set_status(name, stage, 0, f"Starting {STAGE_LABEL[stage]}…", STAGE_ORDER)
            log(f"[{name}] running stage {stage}")
            proc = subprocess.run(
                ["python3", os.path.join(PIPELINE, args[0])] + args[1:],
                capture_output=True, text=True, timeout=3600,
            )
            if proc.returncode != 0:
                set_status(name, stage, 100,
                           f"Stage {stage} failed: {proc.stderr.strip()[-300:]}", STAGE_ORDER)
                write_json(os.path.join(project_dir(name), "error.json"),
                           {"stage": stage, "stderr": proc.stderr[-2000:]})
                log(f"[{name}] stage {stage} FAILED")
                if stage in hard_stages:
                    return  # hard stage failed — stop
                log(f"[{name}] soft stage {stage} failed — continuing")
            else:
                log(f"[{name}] stage {stage} done")
        set_status(name, "done", 100, "Complete — your catalog is ready", STAGE_ORDER)
        log(f"[{name}] pipeline complete")
    except Exception as e:
        write_json(os.path.join(project_dir(name), "error.json"), {"error": str(e)})
        log(f"[{name}] pipeline error: {e}")
    finally:
        _running.pop(name, None)


@app.route("/")
def index():
    projects = []
    if os.path.isdir(PROJECTS):
        for d in sorted(os.listdir(PROJECTS)):
            p = os.path.join(PROJECTS, d)
            if not os.path.isdir(p):
                continue
            st = read_json(os.path.join(p, "status.json")) if os.path.exists(os.path.join(p, "status.json")) else {}
            analysis = read_json(os.path.join(p, "analysis.json")) if os.path.exists(os.path.join(p, "analysis.json")) else {}
            projects.append({
                "name": d,
                "current_stage": st.get("current_stage"),
                "updated_at": st.get("updated_at"),
                "done": st.get("current_stage") == "done",
                "input_type": analysis.get("input_type", "image"),
                "has_video": os.path.exists(os.path.join(p, "output.mp4")),
            })
    return render_template("index.html", projects=projects,
                           styles=["modern", "scandinavian", "industrial", "minimalist", "boho", "traditional"])


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    style = request.form.get("style", "modern")
    if not f or not f.filename:
        return jsonify({"error": "No file uploaded"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
                   ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"):
        return jsonify({"error": f"Unsupported file type {ext}"}), 400
    name = safe_name(request.form.get("name") or f"project-{int(time.time())}")
    # ensure unique
    base, i = name, 1
    while os.path.exists(os.path.join(PROJECTS, name)):
        name = f"{base}-{i}"
        i += 1
    pdir = project_dir(name)
    dest = os.path.join(pdir, f"input{ext}")
    f.save(dest)
    write_json(os.path.join(pdir, "meta.json"), {"style": style, "input_file": f"input{ext}"})
    if name not in _running:
        t = threading.Thread(target=run_pipeline, args=(name, dest, style), daemon=True)
        t.start()
        _running[name] = t
    return jsonify({"ok": True, "project": name})


@app.route("/project/<name>/status")
def status(name):
    p = os.path.join(PROJECTS, name)
    if not os.path.isdir(p):
        return jsonify({"error": "not found"}), 404
    st = read_json(os.path.join(p, "status.json")) if os.path.exists(os.path.join(p, "status.json")) else {}
    err = read_json(os.path.join(p, "error.json")) if os.path.exists(os.path.join(p, "error.json")) else None
    return jsonify({
        "project": name,
        "stages": st.get("stages", {}),
        "stage_order": STAGE_ORDER,
        "current_stage": st.get("current_stage"),
        "done": st.get("current_stage") == "done",
        "error": err,
        "has_catalog": os.path.exists(os.path.join(p, "catalog.html")),
        "has_video": os.path.exists(os.path.join(p, "output.mp4")),
    })


@app.route("/project/<name>/catalog")
def catalog(name):
    p = os.path.join(PROJECTS, name)
    if not os.path.isdir(p):
        return "not found", 404
    return send_from_directory(p, "catalog.html")


@app.route("/project/<name>/renders/<path:fname>")
def renders(name, fname):
    return send_from_directory(os.path.join(PROJECTS, name, "renders"), fname)


@app.route("/project/<name>/input")
def input_file(name):
    p = os.path.join(PROJECTS, name)
    meta = read_json(os.path.join(p, "meta.json")) if os.path.exists(os.path.join(p, "meta.json")) else {}
    f = meta.get("input_file", "input.png")
    is_video = os.path.splitext(f)[1].lower() in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")
    # for video inputs, serve a preview frame if we have one
    if is_video and os.path.exists(os.path.join(p, "input_preview.jpg")):
        return send_from_directory(p, "input_preview.jpg")
    return send_from_directory(p, f)


@app.route("/project/<name>/report.pdf")
def report(name):
    p = os.path.join(PROJECTS, name)
    if not os.path.isdir(p):
        return "not found", 404
    return send_from_directory(p, "report.pdf")


@app.route("/project/<name>/output.mp4")
def output_video(name):
    p = os.path.join(PROJECTS, name)
    if not os.path.isdir(p):
        return "not found", 404
    return send_from_directory(p, "output.mp4")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8090))
    log(f"Interior AI running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)