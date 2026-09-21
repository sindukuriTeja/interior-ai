#!/usr/bin/env python3
"""Stage 4 — Generate beautiful interior render images, one per room.

Uses the pokee image_gen skill. Each room gets a photorealistic render built
from the design style (palette, materials, lighting) + the room's concept.
Images are saved to renders/<key>.jpg and recorded in renders.json.

Usage:
    python3 render.py <project_name>
"""
import os
import sys
import time

import requests

from common import project_dir, read_json, run_skill, set_status, write_json, log

STAGE = "render"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build"]

ROOM_RENDER = {
    "living": "a spacious modern living room, low-profile sofa with layered area rug, accent armchair, warm wood coffee table, floor lamp, large windows with soft daylight, layered warm-white lighting, statement wall art",
    "kitchen": "a bright open kitchen with clean work surfaces, a central island with pendant lights, natural wood cabinets, matte finishes, quality cookware on open shelves, a coffee machine, warm inviting atmosphere",
    "bedroom": "a calm serene bedroom, queen bed with layered soft bedding on a soft rug, matching nightstands with warm bedside lamps, a dresser, blackout curtains, single wall art piece, soft natural light",
    "bath": "a small spa-like bathroom, clean vanity with a backlit mirror, rainfall shower, soft towels, neutral tones, bright even lighting, feels larger and calmer",
    "balcony": "a cozy balcony with a rattan lounge chair, small side table, potted plants and greenery, outdoor rug, morning light, relaxed outdoor living",
    "hall": "a welcoming entry hall, slim console table with a round wall mirror, a fiddle leaf fig plant, warm lighting, clean uncluttered transition space",
}

STYLE_FLAVOR = {
    "modern": "warm modern style, warm whites and soft greys with walnut wood and brushed brass accents, oak flooring, boucle and linen textures",
    "scandinavian": "scandinavian style, crisp white and pale ash with muted sage, light oak, wool and linen, airy and bright",
    "industrial": "industrial style, charcoal and concrete grey with aged leather and blackened steel, exposed brick, reclaimed wood",
    "minimalist": "minimalist style, off-white and warm sand, smooth plaster, light wood and stone, calm and uncluttered",
    "boho": "bohemian style, terracotta cream olive and rust, rattan, jute, kilim patterns, dried botanicals",
    "traditional": "traditional elegant style, ivory navy and burgundy, rich walnut, marble, velvet and brass",
}


def save_image(res, dest):
    """Save the generated image to dest. public_url may be an http URL or a
    local path; file_name is a pokee-storage (local) path."""
    data = res.get("data", {})
    url = data.get("public_url")
    fname = data.get("file_name")
    # 1) local path (public_url pointing at the filesystem)
    for cand in [url, fname]:
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
    log(f"warning: could not save render for {dest} (url={url}, file={fname})")
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    name = sys.argv[1]
    pdir = project_dir(name)
    design = read_json(os.path.join(pdir, "design.json"))
    style = design.get("style", "modern")
    flavor = STYLE_FLAVOR.get(style, STYLE_FLAVOR["modern"])

    out_dir = os.path.join(pdir, "renders")
    os.makedirs(out_dir, exist_ok=True)
    renders_path = os.path.join(pdir, "renders.json")
    renders = read_json(renders_path) if os.path.exists(renders_path) else []
    have = {r["key"] for r in renders}

    rooms = design["rooms"]
    total = len(rooms)
    for i, room in enumerate(rooms):
        key = room["key"]
        if key in have:
            continue
        set_status(name, STAGE, int(100 * i / total),
                   f"Rendering {room['name']}… ({i+1}/{total})", STAGE_ORDER)
        prompt = (
            f"Photorealistic interior design render, {ROOM_RENDER.get(key, 'a well designed room')}. "
            f"{flavor}. High-end architectural visualization, professional interior photography, "
            "soft natural light, ultra detailed, 8k."
        )
        dest = os.path.join(out_dir, f"{key}.jpg")
        try:
            res = run_skill("image_gen.generate_or_edit_image_using_generative_ai", {
                "mode": "create_a_new_image_from_description",
                "prompt": prompt,
                "aspect_ratio": "16:9",
            }, timeout=300)
            ok = save_image(res, dest)
            if ok:
                renders.append({"key": key, "name": room["name"], "file": f"renders/{key}.jpg",
                                "prompt": prompt})
                write_json(renders_path, renders)
                log(f"rendered {key}")
        except Exception as e:
            log(f"render failed for {key}: {e}")
        time.sleep(0.5)

    set_status(name, STAGE, 100, f"Rendered {len(renders)}/{total} rooms", STAGE_ORDER)
    log(f"render complete: {len(renders)}/{total}")
    print("OK")


if __name__ == "__main__":
    main()