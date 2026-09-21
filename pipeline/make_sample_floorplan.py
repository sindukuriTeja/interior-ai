#!/usr/bin/env python3
"""Generate a realistic 2D architectural floor plan (PNG) for the demo.

Draws a 2-bed apartment: living room, kitchen, 2 bedrooms, bath, balcony.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1200
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)

def font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()

F_ROOM = font(34)
F_DIM = font(22)
F_TITLE = font(40)

# ---- outer walls (thick) ----
wall = 14
ox, oy = 120, 140          # outer top-left
ow, oh = 1300, 820         # outer size
d.rectangle([ox, oy, ox + ow, oy + oh], outline="black", width=wall)

# ---- interior walls ----
# Vertical wall at x=760 splitting left (living+kitchen) from right (beds+bath)
vx = ox + 640
d.line([(vx, oy), (vx, oy + 300)], fill="black", width=10)          # top part
d.line([(vx, oy + 380), (vx, oy + oh)], fill="black", width=10)     # bottom part (door gap 300-380)
# Horizontal wall in left zone at y=oy+470 (kitchen | living)
hy = oy + 470
d.line([(ox, hy), (ox + 250, hy)], fill="black", width=10)
d.line([(ox + 330, hy), (vx, hy)], fill="black", width=10)
# Right zone: horizontal wall at y=oy+430 (bed1 | bed2)
hy2 = oy + 430
d.line([(vx + 80, hy2), (ox + ow, hy2)], fill="black", width=10)
# Vertical wall in right zone at x=vx+220 (bath | beds)
bx = vx + 220
d.line([(bx, hy2), (bx, oy + oh)], fill="black", width=10)

# ---- doors (arcs) ----
def door(x, y, r=70, start=0, end=90):
    d.arc([x - r, y - r, x + r, y + r], start, end, fill="#555", width=3)
    d.line([(x, y), (x + r, y)], fill="#555", width=3)

door(vx, oy + 300, 70, 90, 180)     # main hall door gap
door(ox + 250, hy, 60, 0, 90)       # kitchen door
door(vx + 80, hy2, 60, 90, 180)     # bed1 door
door(bx, hy2, 60, 0, 90)            # bath door
door(ox + ow - 120, oy, 70, 0, 90)     # bedroom 2 door (top wall, swings inward)

# ---- windows (double line on outer wall) ----
def window_h(x1, x2, y):
    d.line([(x1, y - 8), (x2, y - 8)], fill="#2b6cb0", width=5)
    d.line([(x1, y + 8), (x2, y + 8)], fill="#2b6cb0", width=5)

def window_v(x, y1, y2):
    d.line([(x - 8, y1), (x - 8, y2)], fill="#2b6cb0", width=5)
    d.line([(x + 8, y1), (x + 8, y2)], fill="#2b6cb0", width=5)

window_h(ox + 150, ox + 550, oy)           # living room top window
window_h(ox + 100, ox + 400, oy + oh)      # living room bottom window
window_v(ox + ow, oy + 80, oy + 350)       # bed1 right window (vertical)
window_h(ox + 900, ox + 1200, oy + oh)     # bed2 bottom window

# balcony (dashed, below living)
d.rectangle([ox + 100, oy + oh + 10, ox + 600, oy + oh + 90], outline="#888", width=3)
d.text((ox + 250, oy + oh + 35), "BALCONY", fill="#555", font=F_DIM)

# ---- room labels ----
d.text((ox + 130, oy + 180), "LIVING ROOM", fill="black", font=F_ROOM)
d.text((ox + 150, oy + 540), "KITCHEN", fill="black", font=F_ROOM)
d.text((bx + 40, oy + 500), "BATH", fill="black", font=F_DIM)
d.text((vx + 130, oy + 150), "BEDROOM 1", fill="black", font=F_ROOM)
d.text((bx + 60, oy + 520), "BEDROOM 2", fill="black", font=F_ROOM)

# ---- dimension marks ----
d.line([(ox, oy - 40), (ox + ow, oy - 40)], fill="#999", width=2)
d.text((ox + 580, oy - 70), "12.0 m", fill="#666", font=F_DIM)
d.line([(ox - 40, oy), (ox - 40, oy + oh)], fill="#999", width=2)
d.text((ox - 90, oy + 380), "8.2 m", fill="#666", font=F_DIM)

# title
d.text((ox, oy + oh + 110), "FLOOR PLAN  |  2 BED APARTMENT  (~95 m2)", fill="black", font=F_TITLE)

out = "/opt/sandbox/workspace/interior-ai/projects/demo/floorplan.png"
import os
os.makedirs(os.path.dirname(out), exist_ok=True)
img.save(out)
print("saved", out)