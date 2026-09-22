#!/usr/bin/env python3
"""Stage 7 — Turn the INPUT video into a DESIGNED output video.

This is the "video in -> designed video out" stage. It:

  1. reads the design concept (style, palette, materials, lighting) from
     design.json,
  2. picks N evenly-spaced frames from the input video (or the single input
     image, for image projects),
  3. uses the image_gen AI to transform each frame: the SAME room, same
     walls/windows/perspective, but now fully furnished and styled,
  4. composes the designed frames into a smooth walkthrough video
     (slow Ken Burns pan/zoom + crossfades) matching the input duration.

Output: <project>/output.mp4  (+ designed_frames/ and video_out.json).

Usage:
    python3 video_out.py <project_name> [--frames 4]
"""
import argparse
import json
import math
import os
import sys

from common import project_dir, read_json, run_skill, set_status, write_json, log

STAGE = "video_out"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build", "video_out"]

VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v")

STYLE_FLAVOR = {
    "modern": "warm modern style, warm whites and soft greys with walnut wood and brushed brass accents, oak flooring, boucle and linen textures",
    "scandinavian": "scandinavian style, crisp white and pale ash with muted sage, light oak, wool and linen, airy and bright",
    "industrial": "industrial style, charcoal and concrete grey with aged leather and blackened steel, exposed brick, reclaimed wood",
    "minimalist": "minimalist style, off-white and warm sand, smooth plaster, light wood and stone, calm and uncluttered",
    "boho": "bohemian style, terracotta cream olive and rust, rattan, jute, kilim patterns, dried botanicals",
    "traditional": "traditional elegant style, ivory navy and burgundy, rich walnut, marble, velvet and brass",
}


def design_prompt(design):
    style = design.get("style", "modern")
    flavor = STYLE_FLAVOR.get(style, STYLE_FLAVOR["modern"])
    return (
        "Transform this empty, undecorated room into a fully furnished, professionally "
        "designed interior. " + flavor + ". "
        f"Palette: {design.get('palette')}. Materials: {design.get('materials')}. "
        f"Lighting: {design.get('lighting')}. "
        "Keep the room's architecture EXACTLY the same — same walls, windows, doors, "
        "floor shape, camera angle and perspective. Only add furniture, decor, plants, "
        "lighting fixtures, rugs and styling. If the frame shows a specific room type "
        "(living room, kitchen, bedroom, bathroom, balcony, hallway), furnish it "
        "appropriately for that room. Photorealistic interior photography, soft natural "
        "light, ultra detailed, 8k."
    )


def extract_frames(video_path, out_dir, n):
    """Extract n evenly-spaced frames from a video with PyAV."""
    import av
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    frames = []
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        total = float(stream.frames or 0)
        duration = float(stream.duration * stream.time_base) if stream.duration else 0.0
        fps = float(stream.average_rate or 24)
        if total <= 0:
            total = max(1, int(duration * fps))
        picks = sorted(set(int(total * i / n) for i in range(n)))
        wanted = set(picks)
        idx = 0
        for frame in container.decode(stream):
            if idx in wanted:
                img = frame.to_image()
                p = os.path.join(out_dir, f"frame_{idx:04d}.jpg")
                img.save(p, quality=90)
                frames.append(p)
            idx += 1
            if len(frames) >= len(picks):
                break
    return frames, fps, duration


def save_image(res, dest):
    """Save a generated/edited image from an image_gen result to dest.
    public_url may be an http URL or a local path; file_name is a
    pokee-storage (local) path. Same strategy as render.py."""
    import requests

    data = res.get("data", {})
    url = data.get("public_url")
    fname = data.get("file_name")
    # 1) local path (public_url pointing at the filesystem)
    for cand in (url, fname):
        if cand and not cand.startswith("http") and os.path.exists(cand):
            with open(cand, "rb") as f:
                blob = f.read()
            with open(dest, "wb") as f:
                f.write(blob)
            return True
    # 2) http(s) URL
    if url and url.startswith("http"):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                with open(dest, "wb") as f:
                    f.write(r.content)
                return True
        except Exception as e:
            log(f"warning: http download failed: {e}")
    # 3) search common local roots for file_name
    if fname:
        for base in ["/opt/sandbox/workspace", "/opt/sandbox/workspace/uploads",
                     "/opt/sandbox/workspace/pokee_skill_outputs"]:
            p = os.path.join(base, fname)
            if os.path.exists(p):
                with open(p, "rb") as f:
                    blob = f.read()
                with open(dest, "wb") as f:
                    f.write(blob)
                return True
    log(f"warning: could not save designed frame for {dest} (url={url}, file={fname})")
    return False


def center_crop(img, tw, th):
    """Center-crop img to the target aspect ratio tw:th, then resize."""
    from PIL import Image
    w, h = img.size
    target = tw / th
    cur = w / h
    if cur > target:
        nw = int(h * target)
        x = (w - nw) // 2
        img = img.crop((x, 0, x + nw, h))
    else:
        nh = int(w / target)
        y = (h - nh) // 2
        img = img.crop((0, y, w, y + nh))
    return img.resize((tw, th), Image.LANCZOS)


def ken_burns(img, w, h, zoom, cx, cy):
    """Slow pan/zoom: crop a (w/zoom, h/zoom) window centered at (cx, cy)
    (fractions of the image), then resize to (w, h)."""
    from PIL import Image
    cw, ch = w / zoom, h / zoom
    x = cx * w - cw / 2
    y = cy * h - ch / 2
    x = max(0.0, min(x, w - cw))
    y = max(0.0, min(y, h - ch))
    return img.crop((int(x), int(y), int(x + cw), int(y + ch))).resize((w, h), Image.LANCZOS)


def build_video(frame_paths, out_path, width, height, fps, duration, crossfade=0.6):
    """Compose the designed frames into a walkthrough video:
    each frame gets a slow Ken Burns pan/zoom segment, with crossfades
    between consecutive segments. Encoded with PyAV (libx264)."""
    import av
    from PIL import Image

    n = len(frame_paths)
    total_frames = max(n, int(round(duration * fps)))
    seg_frames = total_frames // n
    cf = max(1, int(round(crossfade * fps)))

    imgs = [center_crop(Image.open(p).convert("RGB"), width, height) for p in frame_paths]

    # per-segment Ken Burns params: alternate zoom-in / zoom-out, gentle pans
    segs = []
    for i in range(n):
        if i % 2 == 0:
            segs.append((1.0, 1.12, 0.42, 0.5, 0.58, 0.5))   # zoom in, drift right
        else:
            segs.append((1.12, 1.0, 0.58, 0.5, 0.42, 0.5))   # zoom out, drift left

    c = av.open(out_path, mode="w")
    stream = c.add_stream("libx264", rate=int(round(fps)))
    stream.width, stream.height = width, height
    stream.pix_fmt = "yuv420p"
    stream.options = {"crf": "20", "preset": "fast"}

    for f in range(total_frames):
        i = min(f // seg_frames, n - 1)
        j = f - i * seg_frames
        seg_len = seg_frames if i < n - 1 else total_frames - i * seg_frames
        t = j / max(1, seg_len - 1)
        e = 0.5 - 0.5 * math.cos(math.pi * t)  # ease-in-out
        z0, z1, x0, x1, y0, y1 = segs[i]
        img = ken_burns(imgs[i], width, height, z0 + (z1 - z0) * e,
                        x0 + (x1 - x0) * e, y0 + (y1 - y0) * e)
        # crossfade into the next segment
        if i < n - 1 and j >= seg_len - cf:
            a = (j - (seg_len - cf)) / max(1, cf)
            z0b, z1b, x0b, x1b, y0b, y1b = segs[i + 1]
            nxt = ken_burns(imgs[i + 1], width, height, z0b, x0b, y0b)
            img = Image.blend(img, nxt, a)
        for packet in stream.encode(av.VideoFrame.from_image(img)):
            c.mux(packet)

    for packet in stream.encode():
        c.mux(packet)
    c.close()
    log(f"wrote {out_path}: {total_frames} frames @ {fps}fps = {total_frames / fps:.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--frames", type=int, default=4,
                    help="how many frames to design (default 4, max 8)")
    args = ap.parse_args()
    name = args.name
    n_frames = max(1, min(args.frames, 8))

    pdir = project_dir(name)
    design = read_json(os.path.join(pdir, "design.json")) if os.path.exists(
        os.path.join(pdir, "design.json")) else {"style": "modern"}
    prompt = design_prompt(design)

    # find the input
    meta = read_json(os.path.join(pdir, "meta.json")) if os.path.exists(
        os.path.join(pdir, "meta.json")) else {}
    input_file = meta.get("input_file")
    candidates = [input_file] if input_file else []
    for ext in VIDEO_EXTS + (".png", ".jpg", ".jpeg", ".webp"):
        candidates.append(f"input{ext}")
    src = next((os.path.join(pdir, c) for c in candidates
                if c and os.path.exists(os.path.join(pdir, c))), None)
    if src is None:
        raise RuntimeError("no input file found for project " + name)
    is_video = os.path.splitext(src)[1].lower() in VIDEO_EXTS

    out_dir = os.path.join(pdir, "designed_frames")
    os.makedirs(out_dir, exist_ok=True)
    meta_path = os.path.join(pdir, "video_out.json")
    meta_out = read_json(meta_path) if os.path.exists(meta_path) else {"frames": []}
    done = {f["src"] for f in meta_out["frames"]}

    # 1) pick source frames
    if is_video:
        set_status(name, STAGE, 5, "Extracting frames from input video…", STAGE_ORDER)
        src_frames, fps, duration = extract_frames(src, os.path.join(pdir, "frames"), n_frames)
        fps = max(12, min(30, fps))
        duration = max(4.0, duration)
    else:
        set_status(name, STAGE, 5, "Preparing input image…", STAGE_ORDER)
        src_frames = [src]
        fps, duration = 24, 8.0

    # 2) design each frame (resumable)
    for i, sf in enumerate(src_frames):
        tag = os.path.splitext(os.path.basename(sf))[0]
        dest = os.path.join(out_dir, f"designed_{tag}.jpg")
        if tag in done and os.path.exists(dest):
            log(f"frame {tag} already designed — skipping")
            continue
        set_status(name, STAGE, 10 + int(75 * i / len(src_frames)),
                   f"Designing frame {i + 1}/{len(src_frames)} with AI…", STAGE_ORDER)
        log(f"designing frame {tag}")
        res = run_skill("image_gen.generate_or_edit_image_using_generative_ai", {
            "mode": "create_a_new_image_from_existing_images",
            "input_images": [sf],
            "prompt": prompt,
            "aspect_ratio": "16:9",
        }, timeout=300)
        if not save_image(res, dest):
            raise RuntimeError(f"AI design failed for frame {tag}")
        meta_out["frames"].append({"src": tag, "designed": f"designed_frames/designed_{tag}.jpg"})
        write_json(meta_path, meta_out)

    # 3) compose the output video
    set_status(name, STAGE, 90, "Composing designed walkthrough video…", STAGE_ORDER)
    # output resolution: 720p 16:9 (designed frames are generated at 16:9)
    width, height = 1280, 720
    out_path = os.path.join(pdir, "output.mp4")
    designed = [os.path.join(pdir, f["designed"]) for f in meta_out["frames"]]
    build_video(designed, out_path, width, height, fps, duration)

    meta_out["output"] = "output.mp4"
    meta_out["prompt"] = prompt
    meta_out["style"] = design.get("style", "modern")
    meta_out["duration"] = round(total if (total := duration) else duration, 2)
    write_json(meta_path, meta_out)

    set_status(name, STAGE, 100, "Designed video ready — output.mp4", STAGE_ORDER)
    log(f"video_out complete: {out_path}")
    print("OK")


if __name__ == "__main__":
    main()