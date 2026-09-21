#!/usr/bin/env python3
"""Stage 6 — Build the PDF report (report.pdf) for the project.

Generates a markdown report from design.json + products.json and converts it
to PDF with the md2pdf CLI (first-class supported tool).

Usage:
    python3 report.py <project_name>
"""
import os
import subprocess
import sys

from common import project_dir, read_json, set_status, log

STAGE = "build"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build"]

PLATFORM_LABEL = {
    "amazon": "Amazon", "walmart": "Walmart", "target": "Target",
    "homedepot": "Home Depot", "bestbuy": "Best Buy",
}


def money(v, cur="USD"):
    if v is None:
        return "—"
    sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
    return f"{sym}{v:,.2f}"


def build_md(name, design, products):
    L = []
    L.append(f"# Interior Design & Shopping Report")
    L.append(f"## {design.get('mood', 'Interior Design')} — {name}")
    L.append("")
    total = products.get("total_cost", 0)
    area = design.get("total_area_m2")
    area_str = f"{area:.0f} m²" if area else "—"
    L.append(f"**Style:** {design.get('style')}  ")
    L.append(f"**Area:** {area_str}  ")
    L.append(f"**Bedrooms:** {design.get('bedrooms') or '—'}   **Bathrooms:** {design.get('bathrooms') or '—'}  ")
    L.append(f"**Products:** {products.get('total_items')}  ")
    L.append(f"**Estimated total:** **{money(total)}**")
    L.append("")
    L.append("### Design Concept")
    L.append(f"- **Palette:** {design.get('palette')}")
    L.append(f"- **Materials:** {design.get('materials')}")
    L.append(f"- **Lighting:** {design.get('lighting')}")
    L.append("")
    L.append("---")
    L.append("")

    by_room = {}
    for p in products["products"]:
        by_room.setdefault(p["room"], []).append(p)

    for room in design["rooms"]:
        items = by_room.get(room["name"], [])
        if not items:
            continue
        L.append(f"## {room['name']}")
        if room.get("concept"):
            L.append(f"_{room['concept']}_")
            L.append("")
        L.append("| # | Product | Qty | Price | Subtotal | Where | Link |")
        L.append("|---|---------|-----|-------|----------|-------|------|")
        for i, p in enumerate(items, 1):
            c = p.get("chosen") or {}
            url = c.get("url") or "#"
            plat = PLATFORM_LABEL.get(c.get("platform"), c.get("platform", ""))
            L.append(
                f"| {i} | {c.get('name') or p['design_name']} | {p.get('qty',1)} "
                f"| {money(c.get('price'), c.get('currency'))} | {money(p.get('subtotal'))} "
                f"| {plat} | [buy]({url}) |"
            )
            alt = p.get("alternative")
            if alt and alt.get("url"):
                L.append(
                    f"| | ↳ also on {PLATFORM_LABEL.get(alt.get('platform'), alt.get('platform'))} "
                    f"| | {money(alt.get('price'), alt.get('currency'))} | | | [view]({alt['url']}) |"
                )
        L.append("")

    L.append("---")
    L.append("")
    L.append("## Budget Summary")
    L.append("")
    L.append("| Room | Items | Subtotal |")
    L.append("|------|-------|----------|")
    for r, d in products.get("by_room", {}).items():
        L.append(f"| {r} | {d['count']} | {money(d['subtotal'])} |")
    L.append(f"| **Total** | **{products.get('total_items')}** | **{money(total)}** |")
    L.append("")
    L.append(f"*Prices are live estimates from retailer listings at the time of generation "
             f"and may change. {products.get('priced_items')}/{products.get('total_items')} "
             f"items have a confirmed price.*")
    return "\n".join(L)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    name = sys.argv[1]
    pdir = project_dir(name)
    design = read_json(os.path.join(pdir, "design.json"))
    products = read_json(os.path.join(pdir, "products.json"))

    md = build_md(name, design, products)
    md_path = os.path.join(pdir, "report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    pdf_path = os.path.join(pdir, "report.pdf")
    proc = subprocess.run(["md2pdf", md_path, "-o", pdf_path],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not os.path.exists(pdf_path):
        log(f"md2pdf failed: {proc.stderr[-300:]}")
        raise RuntimeError("PDF generation failed")
    set_status(name, STAGE, 100, "Catalog + PDF report built", STAGE_ORDER)
    log(f"report built: {pdf_path}")
    print("OK")


if __name__ == "__main__":
    main()