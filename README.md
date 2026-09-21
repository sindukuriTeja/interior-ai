# Interior AI — Floor Plan to Furnished Home

Upload a **floor plan (image) or a video** → get a complete interior design with
**real products, live prices, and buy links** from Amazon, Walmart, Target, and
Home Depot, presented as a beautiful catalog page + a PDF report.

## How it works (the pipeline)

```
input (floor plan image / video)
        │
        ▼
 1. analyze.py   vision AI reads the layout → rooms, areas, features
        │
        ▼
 2. design.py    maps rooms → a full design concept + shopping list
        │
        ▼
 3. collect.py   searches each product on Amazon + a 2nd platform,
                 picks the best priced/rated real product, builds buy links
        │
        ▼
 4. render.py    generates a photorealistic AI render for each room
        │
        ▼
 5. build_site.py  builds a self-contained beautiful catalog page (catalog.html)
        │
        ▼
 6. report.py    builds a PDF report (report.pdf) with the full product list + budget
```

Each stage is a standalone script that reads/writes JSON inside
`projects/<name>/`, so they can run independently, are resumable, and the
whole thing can be driven by the web app or by hand.

## Run the web platform

```bash
cd interior-ai
python3 app.py            # → http://localhost:8090
```

1. Drop a floor plan image or video.
2. Pick a style (modern, scandinavian, industrial, minimalist, boho, traditional).
3. Watch live progress, then open your catalog.

## Run the pipeline by hand

```bash
cd interior-ai/pipeline
python3 analyze.py  myproj /path/to/floorplan.png
python3 design.py   myproj modern
python3 collect.py  myproj
python3 render.py   myproj
python3 build_site.py myproj
python3 report.py   myproj
```

Outputs land in `interior-ai/projects/myproj/`:
- `catalog.html` — the beautiful catalog page
- `report.pdf`   — the PDF product list + budget
- `renders/`     — AI interior renders
- `products.json`, `design.json`, `analysis.json` — intermediate data

## Notes
- Product prices are **live** from retailer listings at generation time and may change.
- Amazon is the primary source (most complete data); a second platform is shown
  as an alternative for most items.
- Video input: evenly-spaced frames are extracted and the clearest is analyzed.
  The catalog shows a **🎬 Video** / **🖼 Image** badge so you can see what fed the design.

## Included demos
- `demo/` — a floor-plan **image** run (6 rooms, 43 products).
- `demo-walkthrough/` — a **video** walkthrough run (5 rooms, 39 products). Open
  `demo-walkthrough/catalog.html` in a browser to see the video-input result.