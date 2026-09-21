#!/usr/bin/env python3
"""Stage 1 — Analyze the uploaded floor plan (image) or video.

Video input: extract evenly-spaced frames with PyAV, then analyze the frames.
Image input: analyze the image directly.

Uses the pokee read_image vision skill to extract the room layout, then writes
analysis.json with rooms, dimensions, and a human-readable summary.

Usage:
    python3 analyze.py <project_name> <input_file>
"""
import json
import os
import sys

from common import (
    project_dir,
    read_json,
    run_skill,
    set_status,
    write_json,
    log,
)

STAGE = "analyze"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build"]

ANALYZE_PROMPT = (
    "This is an architectural floor plan of a residential space. "
    "Extract the layout as structured data. For each room give: name, "
    "approximate area in square meters (estimate from the scale/dimensions "
    "shown), and a one-line description of its role. Also report: total "
    "approximate area, number of bedrooms, number of bathrooms, and any "
    "special features (balcony, open kitchen, large windows, etc.). "
    "Return ONLY a JSON object with keys: "
    '{"rooms":[{"name":str,"area_m2":float,"description":str}], '
    '"total_area_m2":float,"bedrooms":int,"bathrooms":int,"features":[str], '
    '"summary":str}'
)


def extract_frames(video_path, out_dir, max_frames=6):
    """Extract up to max_frames evenly-spaced frames from a video."""
    import av

    os.makedirs(out_dir, exist_ok=True)
    frames = []
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        total = float(stream.frames or 0)
        duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
        if total <= 0:
            total = max(1, int(duration * (stream.average_rate or 24)))
        # pick evenly spaced timestamps
        picks = [int(total * i / max_frames) for i in range(max_frames)]
        wanted = set(picks)
        idx = 0
        for frame in container.decode(stream):
            if idx in wanted:
                img = frame.to_image()
                p = os.path.join(out_dir, f"frame_{idx:03d}.jpg")
                img.save(p, quality=88)
                frames.append(p)
            idx += 1
            if len(frames) >= max_frames:
                break
    return frames


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    name, input_file = sys.argv[1], os.path.abspath(sys.argv[2])
    pdir = project_dir(name)
    set_status(name, STAGE, 10, "Analyzing floor plan layout…", STAGE_ORDER)

    ext = os.path.splitext(input_file)[1].lower()
    is_video = ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")

    if is_video:
        log(f"video input — extracting frames from {input_file}")
        frames = extract_frames(input_file, os.path.join(pdir, "frames"))
        log(f"extracted {len(frames)} frames")
        set_status(name, STAGE, 35, f"Extracted {len(frames)} video frames — reading layout…", STAGE_ORDER)
        # analyze the middle frame (usually the clearest plan view)
        target = frames[len(frames) // 2]
        images = [frames[0], target, frames[-1]]
        prompt = (
            "These are frames from a video walkthrough / recording of a floor plan. "
            + ANALYZE_PROMPT
        )
    else:
        target = input_file
        images = [input_file]
        prompt = ANALYZE_PROMPT

    results = []
    for i, img in enumerate(images):
        set_status(name, STAGE, 40 + i * 15, f"Vision AI reading image {i+1}/{len(images)}…", STAGE_ORDER)
        res = run_skill("read_image.read_image", {
            "image_url_or_file_name": img,
            "instructions": prompt,
        })
        text = res.get("data", {}).get("text", "")
        if res.get("data", {}).get("status") == "success" and text:
            results.append(text)

    if not results:
        raise RuntimeError("vision analysis returned no usable text")

    # The vision model returns JSON (possibly wrapped in markdown). Parse the
    # best-looking object; fall back to raw text.
    import re
    layout = None
    for text in results:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            continue
        try:
            candidate = json.loads(m.group(0))
            if "rooms" in candidate:
                layout = candidate
                break
        except json.JSONDecodeError:
            continue

    if layout is None:
        layout = {
            "rooms": [],
            "total_area_m2": None,
            "bedrooms": None,
            "bathrooms": None,
            "features": [],
            "summary": results[0],
            "raw": results,
        }
        log("warning: could not parse structured layout; using raw description")

    layout["input_type"] = "video" if is_video else "image"
    layout["input_file"] = os.path.basename(input_file)
    layout["analyzed_images"] = [os.path.basename(p) for p in images]
    write_json(os.path.join(pdir, "analysis.json"), layout)

    set_status(name, STAGE, 100, "Floor plan analyzed", STAGE_ORDER)
    log(f"analysis complete: {len(layout.get('rooms', []))} rooms, "
        f"~{layout.get('total_area_m2')} m2")
    print("OK")


if __name__ == "__main__":
    main()