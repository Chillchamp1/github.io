#!/usr/bin/env python3
"""Dutch province polygons -> the compact ring format the page draws.

Usage: python3 build/build_geo_nl.py provincie_2025.geojson -o data/nl-geo.json

Source: cartomap/nl (CBS generalized province boundaries, published under
CC-BY via PDOK). All twelve provinces are kept.
"""
import json, argparse

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("-o", "--out", default="data/nl-geo.json")
args = ap.parse_args()

gj = json.load(open(args.src, encoding="utf-8"))
rings = []
for f in gj["features"]:
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polys:
        for ring in poly:
            rings.append([[round(x, 4), round(y, 4)] for x, y in ring])

doc = {"outline": rings, "states": rings}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(rings)} rings, {sum(len(r) for r in rings)} points")
