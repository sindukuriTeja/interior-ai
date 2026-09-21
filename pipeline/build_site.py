#!/usr/bin/env python3
"""Stage 5 — Build the final self-contained catalog page (catalog.html).

Combines analysis + design + products + renders into one beautiful,
self-contained HTML file (inline CSS, no external deps except product images
which load from the retailer CDN). Also writes a small index.html for the
web UI to open.

Usage:
    python3 build_site.py <project_name>
"""
import os
import sys
import html
import json
import hashlib
import urllib.request

from common import project_dir, read_json, set_status, write_json, log

STAGE = "build"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build"]


def local_image(pdir, url, tag):
    """Download a product image into <pdir>/img/ and return a relative path.
    Returns None if the URL is missing or the download fails."""
    if not url or not url.startswith("http"):
        return None
    os.makedirs(os.path.join(pdir, "img"), exist_ok=True)
    ext = ".jpg"
    if ".png" in url:
        ext = ".png"
    fn = f"{tag}{ext}"
    dest = os.path.join(pdir, "img", fn)
    if not os.path.exists(dest):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                with open(dest, "wb") as f:
                    f.write(r.read())
        except Exception as e:
            log(f"image download failed for {tag}: {e}")
            return None
    return f"img/{fn}"

PLATFORM_LABEL = {
    "amazon": "Amazon",
    "walmart": "Walmart",
    "target": "Target",
    "homedepot": "Home Depot",
    "bestbuy": "Best Buy",
}

PLATFORM_COLOR = {
    "amazon": "#FF9900",
    "walmart": "#0071CE",
    "target": "#CC0000",
    "homedepot": "#F96302",
    "bestbuy": "#0046BE",
}


def esc(x):
    return html.escape(str(x)) if x is not None else ""


def money(v, cur="USD"):
    if v is None:
        return "—"
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
    return f"{sym}{v:,.2f}"


def stars(r):
    if not r:
        return ""
    full = int(round(r))
    return "★" * full + "☆" * (5 - full)


def product_card(p, pdir):
    c = p.get("chosen") or {}
    price = c.get("price")
    list_price = c.get("list_price")
    url = c.get("url") or "#"
    img = local_image(pdir, c.get("image"), p["id"]) or (c.get("image") or "")
    plat = c.get("platform", "amazon")
    alt = p.get("alternative")
    alt_html = ""
    if alt and alt.get("url"):
        alt_html = (
            f'<div class="alt">Also on <b style="color:{PLATFORM_COLOR.get(alt.get("platform"))}">'
            f'{esc(PLATFORM_LABEL.get(alt.get("platform"), alt.get("platform")))}</b>: '
            f'{money(alt.get("price"), alt.get("currency"))} '
            f'<a href="{esc(alt.get("url"))}" target="_blank" rel="noopener">view →</a></div>'
        )
    badge = (
        f'<span class="badge" style="background:{PLATFORM_COLOR.get(plat)}">'
        f'{esc(PLATFORM_LABEL.get(plat, plat))}</span>'
    )
    rating = stars(c.get("rating"))
    rating_html = f'<span class="rating">{rating} <small>{c.get("rating") or ""}</small></span>' if c.get("rating") else ""
    discount = ""
    if list_price and price and list_price > price:
        pct = round((1 - price / list_price) * 100)
        discount = f'<span class="discount">-{pct}%</span>'
    subtotal = p.get("subtotal")
    sub_html = f'<div class="subtotal">{money(subtotal)}</div>' if subtotal is not None else ""
    qty = p.get("qty", 1)
    qty_html = f'<span class="qty">× {qty}</span>' if qty > 1 else ""
    return f'''
    <div class="card">
      <div class="card-img">
        <img src="{esc(img)}" alt="{esc(c.get('name'))}" loading="lazy"
             onerror="this.style.display='none'">
        {badge}{discount}
      </div>
      <div class="card-body">
        <div class="card-cat">{esc(p.get('category'))} {rating_html}</div>
        <div class="card-name" title="{esc(c.get('name'))}">{esc(c.get('name'))}</div>
        <div class="price-row">
          <span class="price">{money(price, c.get('currency'))}</span>
          {f'<span class="listprice">{money(list_price, c.get("currency"))}</span>' if list_price and price else ''}
          {qty_html}
        </div>
        {sub_html}
        {alt_html}
        <a class="buy" href="{esc(url)}" target="_blank" rel="noopener">Buy on {esc(PLATFORM_LABEL.get(plat, plat))} →</a>
      </div>
    </div>'''


def build(name):
    pdir = project_dir(name)
    design = read_json(os.path.join(pdir, "design.json"))
    products = read_json(os.path.join(pdir, "products.json"))
    analysis = read_json(os.path.join(pdir, "analysis.json"))
    renders = read_json(os.path.join(pdir, "renders.json")) if os.path.exists(os.path.join(pdir, "renders.json")) else []
    render_map = {r["key"]: r["file"] for r in renders}

    rooms = design["rooms"]
    by_room = {}
    for p in products["products"]:
        by_room.setdefault(p["room"], []).append(p)

    total = products.get("total_cost", 0)
    priced = products.get("priced_items", 0)

    # palette swatches (parse simple color words -> hex approximations)
    palette = design.get("palette", "")
    swatches = parse_palette(design.get("style", "modern"))

    # room sections
    room_sections = ""
    for room in rooms:
        key = room["key"]
        rfile = render_map.get(key)
        img_html = f'<img src="{esc(rfile)}" alt="{esc(room["name"])} render" loading="lazy">' if rfile else '<div class="noimg">render pending</div>'
        cards = "".join(product_card(p, pdir) for p in by_room.get(room["name"], []))
        area = f'{room["area_m2"]:.0f} m²' if room.get("area_m2") else ""
        room_sections += f'''
        <section class="room" id="{esc(key)}">
          <div class="room-head">
            <h2>{esc(room["name"])} {f'<span class="area">{area}</span>' if area else ''}</h2>
            <p class="concept">{esc(room.get("concept"))}</p>
          </div>
          <div class="room-img">{img_html}</div>
          <div class="grid">{cards if cards else '<p class="empty">No products collected for this room.</p>'}</div>
        </section>'''

    # budget table
    budget_rows = ""
    for r, d in products.get("by_room", {}).items():
        budget_rows += f'<tr><td>{esc(r)}</td><td>{d["count"]}</td><td class="num">{money(d["subtotal"])}</td></tr>'
    budget_rows += f'<tr class="total"><td>Total</td><td>{products.get("total_items")}</td><td class="num">{money(total)}</td></tr>'

    # platforms used
    plats = sorted({p["chosen"]["platform"] for p in products["products"] if p.get("chosen")})
    plat_chips = " ".join(
        f'<span class="chip" style="border-color:{PLATFORM_COLOR.get(pl)}">{esc(PLATFORM_LABEL.get(pl, pl))}</span>'
        for pl in plats
    )

    swatch_html = "".join(
        f'<span class="swatch" style="background:{hex_}" title="{name_}"></span>'
        for name_, hex_ in swatches
    )

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(design.get("mood"))} Interior — {esc(name)}</title>
<style>
:root {{
  --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --ink:#f4f5f7;
  --muted:#9aa3b2; --line:#2a2f3a; --accent:#e8b06b; --accent2:#7fb4d8;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  background:var(--bg); color:var(--ink); line-height:1.55; }}
a {{ color:var(--accent2); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.wrap {{ max-width:1200px; margin:0 auto; padding:0 20px; }}
.hero {{ background:linear-gradient(135deg,#141821,#1b2230 60%,#20293a); padding:64px 0 48px; border-bottom:1px solid var(--line); }}
.hero h1 {{ font-size:40px; margin:0 0 8px; font-weight:700; letter-spacing:-.5px; }}
.hero .sub {{ color:var(--muted); font-size:18px; max-width:720px; }}
.meta {{ display:flex; flex-wrap:wrap; gap:14px; margin-top:26px; }}
.meta .pill {{ background:var(--panel); border:1px solid var(--line); padding:10px 16px; border-radius:12px; }}
.meta .pill b {{ display:block; font-size:22px; }}
.meta .pill span {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }}
.swatches {{ display:flex; gap:8px; margin-top:22px; }}
.swatch {{ width:34px; height:34px; border-radius:8px; border:1px solid rgba(255,255,255,.15); }}
.design {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:26px; margin:34px 0; }}
.design h3 {{ margin:0 0 6px; font-size:15px; text-transform:uppercase; letter-spacing:1px; color:var(--accent); }}
.design p {{ margin:6px 0; color:var(--muted); }}
.design .row {{ display:grid; grid-template-columns:120px 1fr; gap:10px; margin:10px 0; }}
.design .row b {{ color:var(--ink); }}
nav.toc {{ position:sticky; top:0; z-index:5; background:rgba(15,17,21,.9); backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line); padding:12px 0; }}
nav.toc .wrap {{ display:flex; gap:10px; flex-wrap:wrap; }}
nav.toc a {{ padding:6px 12px; border:1px solid var(--line); border-radius:20px; color:var(--muted); font-size:14px; }}
nav.toc a:hover {{ color:var(--ink); border-color:var(--accent); text-decoration:none; }}
section.room {{ padding:44px 0; border-bottom:1px solid var(--line); }}
.room-head h2 {{ font-size:30px; margin:0 0 6px; }}
.room-head .area {{ font-size:16px; color:var(--accent); font-weight:500; margin-left:8px; }}
.concept {{ color:var(--muted); max-width:820px; margin:0 0 20px; }}
.room-img {{ border-radius:16px; overflow:hidden; margin-bottom:24px; border:1px solid var(--line); }}
.room-img img {{ width:100%; display:block; aspect-ratio:16/9; object-fit:cover; }}
.noimg {{ height:200px; display:flex; align-items:center; justify-content:center; color:var(--muted); background:var(--panel); }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:18px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; overflow:hidden;
  display:flex; flex-direction:column; transition:transform .15s, border-color .15s; }}
.card:hover {{ transform:translateY(-3px); border-color:#3a4150; }}
.card-img {{ position:relative; background:#0c0e12; aspect-ratio:1/1; }}
.card-img img {{ width:100%; height:100%; object-fit:cover; }}
.badge {{ position:absolute; top:10px; left:10px; color:#fff; font-size:11px; font-weight:700;
  padding:4px 8px; border-radius:6px; letter-spacing:.3px; }}
.discount {{ position:absolute; top:10px; right:10px; background:#e05252; color:#fff; font-size:11px;
  font-weight:700; padding:4px 8px; border-radius:6px; }}
.card-body {{ padding:14px; display:flex; flex-direction:column; gap:6px; flex:1; }}
.card-cat {{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; display:flex; justify-content:space-between; }}
.rating {{ color:var(--accent); letter-spacing:1px; }}
.rating small {{ color:var(--muted); letter-spacing:0; }}
.card-name {{ font-size:14px; font-weight:600; min-height:38px; }}
.price-row {{ display:flex; align-items:baseline; gap:8px; margin-top:2px; }}
.price {{ font-size:20px; font-weight:700; }}
.listprice {{ color:var(--muted); text-decoration:line-through; font-size:13px; }}
.qty {{ color:var(--muted); font-size:13px; }}
.subtotal {{ font-size:12px; color:var(--accent2); }}
.alt {{ font-size:12px; color:var(--muted); margin-top:2px; }}
.buy {{ margin-top:auto; display:block; text-align:center; background:var(--accent); color:#1a1206;
  font-weight:700; padding:10px; border-radius:10px; }}
.buy:hover {{ text-decoration:none; filter:brightness(1.05); }}
.empty {{ color:var(--muted); }}
.budget {{ background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:26px; margin:40px 0; }}
.budget h2 {{ margin:0 0 16px; font-size:24px; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }}
td.num, th.num {{ text-align:right; }}
tr.total td {{ font-weight:700; font-size:18px; border-top:2px solid var(--accent); border-bottom:none; }}
.chips {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:18px; }}
.chip {{ border:1px solid; border-radius:20px; padding:6px 14px; font-size:13px; }}
footer {{ padding:40px 0; color:var(--muted); font-size:13px; text-align:center; }}
.disclaimer {{ font-size:12px; color:var(--muted); margin-top:10px; }}
@media (max-width:600px) {{ .hero h1{{font-size:30px;}} .grid{{grid-template-columns:repeat(2,1fr);}} }}
</style>
</head>
<body>
<div class="hero">
  <div class="wrap">
    <h1>{esc(design.get("mood", "Interior Design"))}</h1>
    <div class="sub">A complete interior design and shopping plan for your space — every product sourced
      from real stores with live prices and buy links. {esc(palette)}</div>
    <div class="meta">
      <div class="pill"><b>{f'{design.get("total_area_m2"):.0f}' if design.get("total_area_m2") else "—"}</b><span>Area (m²)</span></div>
      <div class="pill"><b>{design.get("bedrooms") or "—"}</b><span>Bedrooms</span></div>
      <div class="pill"><b>{design.get("bathrooms") or "—"}</b><span>Bathrooms</span></div>
      <div class="pill"><b>{products.get("total_items")}</b><span>Products</span></div>
      <div class="pill"><b>{money(total)}</b><span>Est. Total</span></div>
    </div>
    <div class="swatches">{swatch_html}</div>
  </div>
</div>
<nav class="toc"><div class="wrap">
  <a href="#budget">Budget</a>
  {"".join(f'<a href="#{esc(r["key"])}">{esc(r["name"])}</a>' for r in rooms)}
</div></nav>
<div class="wrap">
  <div class="design">
    <h3>Design Concept</h3>
    <div class="row"><b>Style</b><span>{esc(design.get("style"))} — {esc(design.get("mood"))}</span></div>
    <div class="row"><b>Palette</b><span>{esc(palette)}</span></div>
    <div class="row"><b>Materials</b><span>{esc(design.get("materials"))}</span></div>
    <div class="row"><b>Lighting</b><span>{esc(design.get("lighting"))}</span></div>
    {f'<div class="row"><b>Features</b><span>{esc(", ".join(design.get("features", [])))}</span></div>' if design.get("features") else ''}
  </div>
  {room_sections}
  <div class="budget" id="budget">
    <h2>Budget &amp; Where to Buy</h2>
    <table>
      <thead><tr><th>Room</th><th>Items</th><th class="num">Subtotal</th></tr></thead>
      <tbody>{budget_rows}</tbody>
    </table>
    <div class="chips">{plat_chips}</div>
    <p class="disclaimer">Prices are live estimates from retailer listings at the time of generation and may change.
      {priced}/{products.get("total_items")} items have a confirmed price. Click any product to open it on the retailer's site.</p>
  </div>
</div>
<footer>Generated by Interior AI · {esc(name)} · {len(rooms)} rooms · {products.get("total_items")} products</footer>
</body>
</html>'''

    out = os.path.join(pdir, "catalog.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_doc)
    # also write an index.html for the web UI
    idx = os.path.join(pdir, "index.html")
    with open(idx, "w", encoding="utf-8") as f:
        f.write(html_doc)
    set_status(name, STAGE, 100, "Catalog page built", STAGE_ORDER)
    log(f"site built: {out}")
    print("OK")


def parse_palette(style):
    return {
        "modern": [("warm white", "#f2efe9"), ("soft grey", "#b9bdc4"), ("walnut", "#6b4a2f"), ("brass", "#c9a227"), ("charcoal", "#2b2f36")],
        "scandinavian": [("crisp white", "#f6f5f1"), ("pale ash", "#d8c7a9"), ("muted sage", "#a9b5a0"), ("wool", "#e8e2d6"), ("slate", "#5b6470")],
        "industrial": [("charcoal", "#2e2e2e"), ("concrete", "#8f8d88"), ("aged leather", "#7a4a2b"), ("steel", "#3a3f45"), ("brick", "#9c4a34")],
        "minimalist": [("off-white", "#f4f1ea"), ("warm sand", "#d9c7a7"), ("stone", "#b8b2a6"), ("wood", "#c9a876"), ("ink", "#22252b")],
        "boho": [("terracotta", "#c56b4a"), ("cream", "#f1e7d3"), ("olive", "#7c7a4e"), ("rust", "#a24a2e"), ("mustard", "#d9a441")],
        "traditional": [("ivory", "#f3efe4"), ("navy", "#22334f"), ("burgundy", "#6e2b34"), ("walnut", "#5a3d28"), ("brass", "#b8860b")],
    }.get(style, [("neutral", "#d8d4cc")])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    build(sys.argv[1])