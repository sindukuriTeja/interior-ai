#!/usr/bin/env python3
"""Stage 3 — Collect REAL products (price, image, buy link) for the shopping list.

For every item in design.json it:
  1. searches the primary platform (usually Amazon) via the ecommerce skill,
  2. searches a second platform (Walmart / Target / Home Depot) for an
     alternative, so each product shows up on Amazon AND another store,
  3. picks the best priced, rated result and builds a clean buy link.

Results are written to products.json incrementally (resumable) and searches
are cached in search_cache.json so re-runs are cheap.

Usage:
    python3 collect.py <project_name>
"""
import os
import sys
import time

from common import project_dir, read_json, run_skill, set_status, write_json, log

STAGE = "collect"
STAGE_ORDER = ["analyze", "design", "collect", "render", "build"]

PLATFORMS = {
    "amazon": "amazon_search",
    "walmart": "walmart_search",
    "target": "target_search",
    "homedepot": "homedepot_search",
    "bestbuy": "bestbuy_search",
}

# Which second platform to show an alternative on, by category.
def other_platform(platform, category):
    cat = (category or "").lower()
    if platform != "homedepot" and any(k in cat for k in ("plumbing", "vanity", "shower")):
        return "homedepot"
    if any(k in cat for k in ("appliance", "cookware", "coffee", "toaster")):
        return "walmart"
    # furniture / lighting / decor / textiles -> target (or walmart)
    return "target"


def clean_amazon_url(asin):
    return f"https://www.amazon.com/dp/{asin}" if asin else None


def pick_best(results):
    """Choose the best result: must have a price; prefer high rating, lower price."""
    good = [r for r in results if r.get("price") is not None]
    if not good:
        return None
    def score(r):
        rating = r.get("rating") or 0
        return (-(rating or 0), r.get("price") or 0)
    good.sort(key=score)
    return good[0]


def search(query, platform, num_results=5, cache=None):
    key = f"{platform}::{query}"
    if cache is not None and key in cache:
        return cache[key]
    api = PLATFORMS.get(platform, "amazon_search")
    res = run_skill("ecommerce.ecommerce_search_api", {
        "search_term": query,
        "platform": api,
        "num_results": num_results,
    })
    data = res.get("data", {})
    results = data.get("results", []) or []
    if cache is not None:
        cache[key] = results
    return results


def norm_product(r, platform, query):
    asin = r.get("asin")
    url = r.get("url")
    if platform == "amazon" and asin:
        url = clean_amazon_url(asin)
    elif url and "amazon.com" in url and asin:
        url = clean_amazon_url(asin)
    return {
        "name": r.get("name"),
        "price": r.get("price"),
        "list_price": r.get("list_price"),
        "currency": r.get("currency", "USD"),
        "rating": r.get("rating"),
        "image": r.get("thumbnail"),
        "url": url,
        "asin": asin,
        "brand": r.get("brand"),
        "platform": platform,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    name = sys.argv[1]
    pdir = project_dir(name)
    design = read_json(os.path.join(pdir, "design.json"))
    items = design["shopping_list"]

    cache_path = os.path.join(pdir, "search_cache.json")
    cache = read_json(cache_path) if os.path.exists(cache_path) else {}
    out_path = os.path.join(pdir, "products.json")
    products = read_json(out_path) if os.path.exists(out_path) else []
    done = {p["id"] for p in products}

    total = len(items)
    for i, item in enumerate(items):
        pid = f"{item['room'][:3].lower()}-{i:02d}"
        if pid in done:
            continue
        set_status(name, STAGE, int(100 * i / total),
                   f"Collecting {i+1}/{total}: {item['name']}", STAGE_ORDER)

        primary = item.get("platform", "amazon")
        alt_plat = other_platform(primary, item.get("category"))

        rec = {
            "id": pid,
            "room": item["room"],
            "category": item.get("category", ""),
            "design_name": item["name"],
            "qty": item.get("qty", 1),
            "chosen": None,
            "alternative": None,
        }

        # primary platform
        try:
            res = search(item["query"], primary, 5, cache)
            best = pick_best(res)
            if best:
                rec["chosen"] = norm_product(best, primary, item["query"])
        except Exception as e:
            log(f"primary search failed for {item['name']}: {e}")

        # alternative platform (skip if same as primary)
        if alt_plat != primary:
            try:
                res2 = search(item["query"], alt_plat, 1, cache)
                best2 = pick_best(res2)
                if best2:
                    rec["alternative"] = norm_product(best2, alt_plat, item["query"])
            except Exception as e:
                log(f"alt search failed for {item['name']}: {e}")

        # fallback buy link if no priced product found
        if not rec["chosen"]:
            rec["chosen"] = {
                "name": item["name"],
                "price": None,
                "image": None,
                "url": f"https://www.amazon.com/s?k={item['query'].replace(' ', '+')}",
                "platform": "amazon",
                "rating": None,
                "asin": None,
                "brand": None,
                "currency": "USD",
                "list_price": None,
            }

        # If the primary result has no price but the alternative does, promote
        # the alternative to be the chosen product.
        if rec["chosen"].get("price") is None and rec.get("alternative") and rec["alternative"].get("price") is not None:
            rec["chosen"], rec["alternative"] = rec["alternative"], rec["chosen"]

        if rec["chosen"] and rec["chosen"].get("price") is not None:
            rec["subtotal"] = round(rec["chosen"]["price"] * rec["qty"], 2)
        else:
            rec["subtotal"] = None
        products.append(rec)

        # incremental save
        write_json(out_path, products)
        write_json(cache_path, cache)
        time.sleep(0.3)

    # summary
    priced = [p for p in products if p.get("subtotal") is not None]
    total_cost = round(sum(p["subtotal"] for p in priced), 2)
    summary = {
        "total_items": len(products),
        "priced_items": len(priced),
        "total_cost": total_cost,
        "by_room": {},
        "products": products,
    }
    for p in products:
        r = p["room"]
        d = summary["by_room"].setdefault(r, {"count": 0, "subtotal": 0.0})
        d["count"] += 1
        if p.get("subtotal") is not None:
            d["subtotal"] = round(d["subtotal"] + p["subtotal"], 2)
    write_json(out_path, summary)
    set_status(name, STAGE, 100,
               f"Collected {len(priced)}/{len(products)} products — total ${total_cost:,.2f}", STAGE_ORDER)
    log(f"collect complete: {len(priced)}/{len(products)} priced, total ${total_cost:,.2f}")
    print("OK")


if __name__ == "__main__":
    main()