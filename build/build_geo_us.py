#!/usr/bin/env python3
"""Lower-48 state polygons -> the compact ring format the page draws.

Usage: python3 build/build_geo_us.py us-states.json -o data/us-geo.json

Source: PublicaMundi/MappingAPI us-states.json (US Census geometry, public
domain). Alaska, Hawaii and Puerto Rico are dropped: no feed in the bundle
serves them, and Alaska alone would double the frame for empty space.
The page fills and strokes the same rings, so unlike Germany there is no
separate national outline -- state borders carry the whole shape.
"""
import json, sys, argparse

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("-o", "--out", default="data/us-geo.json")
args = ap.parse_args()

DROP = {"Alaska", "Hawaii", "Puerto Rico"}
gj = json.load(open(args.src))
rings = []
for f in gj["features"]:
    if f["properties"].get("name") in DROP:
        continue
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polys:
        for ring in poly:
            rings.append([[round(x, 2), round(y, 2)] for x, y in ring])

doc = {"outline": rings, "states": rings}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(rings)} rings, {sum(len(r) for r in rings)} points")
