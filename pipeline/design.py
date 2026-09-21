#!/usr/bin/env python3
"""Stage 2 — Turn the analyzed layout into a full interior design + shopping list.

Reads analysis.json and writes design.json containing, per room:
  - a design concept (palette, materials, lighting, mood)
  - a list of products to source (name, category, search query, platform, qty)

The product list is what the next stage (collect.py) turns into real, priced
products. Room types are matched case-insensitively, so this works for any
layout the vision stage detects.

Usage:
    python3 design.py <project_name> [style]
    styles: modern | scandinavian | industrial | minimalist | boho | traditional
"""
import os
import sys

from common import project_dir, read_json, set_status, write_json, log

STAGE = "design"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build"]

# Per-style palette / material vocabulary.
STYLES = {
    "modern": {
        "mood": "clean, warm modern",
        "palette": "warm whites, soft greys, walnut wood, brushed brass accents",
        "materials": "oak flooring, matte lacquer, boucle and linen, glass",
        "lighting": "layered warm-white LED, recessed spots + statement pendants",
    },
    "scandinavian": {
        "mood": "bright, airy, hygge",
        "palette": "crisp white, pale ash, muted sage, natural wool",
        "materials": "light oak, wool textiles, linen, pale stone",
        "lighting": "soft diffused daylight, paper pendants, warm floor lamps",
    },
    "industrial": {
        "mood": "raw, urban, characterful",
        "palette": "charcoal, concrete grey, aged leather, blackened steel",
        "materials": "exposed brick, concrete, reclaimed wood, metal",
        "lighting": "edison bulbs, black metal pendants, warm task light",
    },
    "minimalist": {
        "mood": "calm, uncluttered, precise",
        "palette": "off-white, warm sand, single muted accent",
        "materials": "smooth plaster, light wood, stone, fine metal",
        "lighting": "hidden cove lighting, minimal fixtures, even glow",
    },
    "boho": {
        "mood": "relaxed, layered, global",
        "palette": "terracotta, cream, olive, rust and mustard accents",
        "materials": "rattan, jute, kilim, macrame, dried botanicals",
        "lighting": "woven pendant, string lights, brass table lamps",
    },
    "traditional": {
        "mood": "elegant, classic, comfortable",
        "palette": "ivory, navy, burgundy, rich walnut",
        "materials": "walnut, marble, velvet, brass, drapery",
        "lighting": "crystal and brass pendants, warm sconces",
    },
}

# Room-type -> products. Each product: name, category, query, platform, qty.
# Platform is a hint for collect.py (amazon | walmart | homedepot | target).
ROOM_PRODUCTS = {
    "living": [
        {"name": "3-Seater Sofa", "category": "Seating", "query": "modern 3 seater fabric sofa", "platform": "amazon", "qty": 1},
        {"name": "Armchair", "category": "Seating", "query": "modern accent armchair", "platform": "amazon", "qty": 1},
        {"name": "Coffee Table", "category": "Tables", "query": "modern wooden coffee table", "platform": "amazon", "qty": 1},
        {"name": "TV Console / Media Unit", "category": "Storage", "query": "modern tv stand media console", "platform": "amazon", "qty": 1},
        {"name": "Area Rug", "category": "Textiles", "query": "large living room area rug", "platform": "amazon", "qty": 1},
        {"name": "Floor Lamp", "category": "Lighting", "query": "modern floor lamp", "platform": "amazon", "qty": 1},
        {"name": "Wall Art (set of 3)", "category": "Decor", "query": "abstract wall art set of 3", "platform": "amazon", "qty": 1},
        {"name": "Table Lamp", "category": "Lighting", "query": "modern ceramic table lamp", "platform": "amazon", "qty": 2},
    ],
    "kitchen": [
        {"name": "Kitchen Island / Cart", "category": "Furniture", "query": "kitchen island cart with wheels", "platform": "amazon", "qty": 1},
        {"name": "Bar Stools (set of 2)", "category": "Seating", "query": "modern bar stools set of 2", "platform": "amazon", "qty": 1},
        {"name": "Cookware Set", "category": "Cookware", "query": "stainless steel cookware set", "platform": "amazon", "qty": 1},
        {"name": "Toaster", "category": "Appliance", "query": "2 slice stainless steel toaster", "platform": "amazon", "qty": 1},
        {"name": "Coffee Machine", "category": "Appliance", "query": "espresso coffee machine", "platform": "amazon", "qty": 1},
        {"name": "Dining Table (4-seat)", "category": "Tables", "query": "modern 4 person dining table", "platform": "amazon", "qty": 1},
        {"name": "Dining Chairs (set of 4)", "category": "Seating", "query": "modern dining chairs set of 4", "platform": "amazon", "qty": 1},
        {"name": "Pendant Light", "category": "Lighting", "query": "kitchen island pendant light", "platform": "amazon", "qty": 2},
        {"name": "Cutting Boards + Utensils", "category": "Cookware", "query": "wooden cutting board set utensils", "platform": "amazon", "qty": 1},
    ],
    "bedroom": [
        {"name": "Queen Bed Frame + Mattress", "category": "Bed", "query": "queen bed frame with mattress", "platform": "amazon", "qty": 1},
        {"name": "Duvet + Pillow Set", "category": "Bedding", "query": "queen duvet cover set 4 pieces", "platform": "amazon", "qty": 1},
        {"name": "Nightstand", "category": "Storage", "query": "modern bedside table nightstand", "platform": "amazon", "qty": 2},
        {"name": "Bedside Lamp", "category": "Lighting", "query": "modern bedside table lamp", "platform": "amazon", "qty": 2},
        {"name": "Wardrobe / Dresser", "category": "Storage", "query": "modern dresser chest of drawers", "platform": "amazon", "qty": 1},
        {"name": "Bedroom Rug", "category": "Textiles", "query": "soft bedroom rug", "platform": "amazon", "qty": 1},
        {"name": "Blackout Curtains", "category": "Textiles", "query": "blackout curtains panel set", "platform": "amazon", "qty": 1},
        {"name": "Wall Art", "category": "Decor", "query": "bedroom wall art print", "platform": "amazon", "qty": 1},
    ],
    "bath": [
        {"name": "Bathroom Vanity + Sink", "category": "Vanity", "query": "modern bathroom vanity with sink", "platform": "homedepot", "qty": 1},
        {"name": "Shower Head", "category": "Plumbing", "query": "rainfall shower head", "platform": "amazon", "qty": 1},
        {"name": "Towel Set", "category": "Textiles", "query": "bath towel set 6 pieces", "platform": "amazon", "qty": 1},
        {"name": "Bathroom Mirror with Light", "category": "Lighting", "query": "backlit bathroom mirror", "platform": "amazon", "qty": 1},
        {"name": "Bath Mat", "category": "Textiles", "query": "non slip bath mat", "platform": "amazon", "qty": 1},
        {"name": "Towel Rack + Accessories", "category": "Accessories", "query": "bathroom towel rack set", "platform": "amazon", "qty": 1},
    ],
    "balcony": [
        {"name": "Outdoor Lounge Chair", "category": "Outdoor", "query": "outdoor rattan lounge chair", "platform": "amazon", "qty": 1},
        {"name": "Outdoor Side Table", "category": "Outdoor", "query": "outdoor side table", "platform": "amazon", "qty": 1},
        {"name": "Potted Plants (set)", "category": "Decor", "query": "indoor outdoor potted plants set", "platform": "amazon", "qty": 1},
        {"name": "Outdoor Rug", "category": "Outdoor", "query": "outdoor area rug", "platform": "amazon", "qty": 1},
    ],
}

# Which room-key a detected room name maps to.
def room_key(name):
    n = name.lower()
    if "living" in n or "lounge" in n or "sitting" in n:
        return "living"
    if "kitchen" in n or "dining" in n:
        return "kitchen"
    if "bedroom" in n or "bed room" in n or "master" in n:
        return "bedroom"
    if "bath" in n or "shower" in n or "wc" in n or "toilet" in n:
        return "bath"
    if "balcony" in n or "terrace" in n or "patio" in n:
        return "balcony"
    if "hall" in n or "entry" in n or "foyer" in n or "corridor" in n:
        return "hall"
    return None

HALL_PRODUCTS = [
    {"name": "Console Table", "category": "Furniture", "query": "modern entryway console table", "platform": "amazon", "qty": 1},
    {"name": "Wall Mirror", "category": "Decor", "query": "round wall mirror", "platform": "amazon", "qty": 1},
    {"name": "Indoor Plant", "category": "Decor", "query": "fiddle leaf fig plant", "platform": "amazon", "qty": 1},
]

ROOM_CONCEPTS = {
    "living": "The living room is the social heart of the home. A low-profile sofa anchors the space with a layered rug beneath, balanced by an accent armchair and a warm wood coffee table. Lighting is layered — recessed spots for general light, a floor lamp for reading, and a statement pendant over the seating. Soft textiles and one or two art pieces keep it relaxed.",
    "kitchen": "The kitchen balances function and warmth. A clean work surface runs along the wall with an island or cart for casual dining, topped by pendant lights. Quality cookware and a good coffee machine make it a place to gather. Natural wood and matte finishes keep it from feeling cold.",
    "bedroom": "Each bedroom is a calm retreat. A quality bed with layered bedding sits on a soft rug, flanked by matching nightstands and warm bedside lamps. A dresser provides storage, blackout curtains protect sleep, and a single art piece adds personality without clutter.",
    "bath": "The bathroom reads like a small spa. A clean vanity with a lit mirror, a rainfall shower, and soft towels create a calm, functional space. Neutral tones and good lighting make the room feel larger and brighter.",
    "balcony": "The balcony extends the living space outdoors. A comfortable lounge chair, a small side table, and greenery turn it into a quiet spot for morning coffee. An outdoor rug defines the seating area.",
    "hall": "The entry hall is a welcoming transition. A slim console table with a mirror and a single plant makes a first impression without crowding the space.",
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    name = sys.argv[1]
    style = sys.argv[2].lower() if len(sys.argv) > 2 else "modern"
    if style not in STYLES:
        style = "modern"

    pdir = project_dir(name)
    analysis = read_json(os.path.join(pdir, "analysis.json"))
    set_status(name, STAGE, 20, f"Designing {style} concept…", STAGE_ORDER)

    s = STYLES[style]
    rooms_out = []
    shopping = []
    seen = set()

    for room in analysis.get("rooms", []):
        key = room_key(room.get("name", ""))
        if key is None:
            continue
        if key in seen:
            # e.g. a second bedroom — keep its real name, add a full set of products
            products = list(ROOM_PRODUCTS[key])
            label = room.get("name", f"{key.title()} 2")
        else:
            products = list(ROOM_PRODUCTS.get(key, []))
            label = room.get("name", key.title())
            seen.add(key)
        if key == "hall":
            products = list(HALL_PRODUCTS)

        for p in products:
            p = dict(p)
            p["room"] = label
            shopping.append(p)

        rooms_out.append({
            "name": label,
            "key": key,
            "area_m2": room.get("area_m2"),
            "description": room.get("description", ""),
            "concept": ROOM_CONCEPTS.get(key, ""),
            "product_count": len(products),
        })

    # Ensure at least a living + bedroom if vision missed rooms.
    if not any(r["key"] == "living" for r in rooms_out):
        for p in ROOM_PRODUCTS["living"]:
            p = dict(p); p["room"] = "Living Room"; shopping.append(p)
        rooms_out.append({"name": "Living Room", "key": "living", "area_m2": None,
                          "description": "", "concept": ROOM_CONCEPTS["living"],
                          "product_count": len(ROOM_PRODUCTS["living"])})

    design = {
        "project": name,
        "style": style,
        "mood": s["mood"],
        "palette": s["palette"],
        "materials": s["materials"],
        "lighting": s["lighting"],
        "total_area_m2": analysis.get("total_area_m2"),
        "bedrooms": analysis.get("bedrooms"),
        "bathrooms": analysis.get("bathrooms"),
        "features": analysis.get("features", []),
        "rooms": rooms_out,
        "shopping_list": shopping,
    }
    write_json(os.path.join(pdir, "design.json"), design)
    set_status(name, STAGE, 100, f"Design complete — {len(shopping)} products across {len(rooms_out)} rooms", STAGE_ORDER)
    log(f"design complete: {len(rooms_out)} rooms, {len(shopping)} products ({style})")
    print("OK")


if __name__ == "__main__":
    main()