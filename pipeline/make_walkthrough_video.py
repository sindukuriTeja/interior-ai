#!/usr/bin/env python3
"""Make a fake 'walkthrough' video: slow pan+zoom across the floor plan image."""
import av
import math
from PIL import Image

SRC = "/opt/sandbox/workspace/interior-ai/projects/demo/floorplan.png"
OUT = "/opt/sandbox/workspace/interior-ai/projects/demo-walkthrough/input.mp4"

W, H = 1280, 720
FPS = 24
DUR = 8  # seconds
N = FPS * DUR

img = Image.open(SRC).convert("RGB")
iw, ih = img.size
# upscale the plan so we have room to pan
scale = max(W / iw, H / ih) * 1.35
big = img.resize((int(iw * scale), int(ih * scale)))
bw, bh = big.size

c = av.open(OUT, mode="w")
stream = c.add_stream("libx264", rate=FPS)
stream.width, stream.height = W, H
stream.pix_fmt = "yuv420p"
stream.options = {"crf": "23", "preset": "fast"}

for i in range(N):
    t = i / N
    # ease-in-out pan left->right, slight zoom in->out
    e = 0.5 - 0.5 * math.cos(math.pi * t)
    zoom = 1.0 + 0.15 * e
    cw, ch = int(bw / zoom), int(bh / zoom)
    max_x, max_y = bw - cw, bh - ch
    x = int(max_x * e)
    y = int(max_y * 0.5 * (1 - e))
    crop = big.crop((x, y, x + cw, y + ch)).resize((W, H))
    frame = av.VideoFrame.from_image(crop)
    for packet in stream.encode(frame):
        c.mux(packet)

for packet in stream.encode():
    c.mux(packet)
c.close()
print(f"wrote {OUT}: {N} frames @ {FPS}fps = {DUR}s")