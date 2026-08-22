#!/usr/bin/env python3
"""Berlin's city boundary -> the compact ring format the page draws.

Usage: python3 build/build_geo_berlin.py 2_hoch.geo.json -o data/berlin-geo.json

Source: isellsoap/deutschlandGeoJSON state boundaries (Unlicense). Only
Berlin's ring is kept: at city scale it IS the map -- the city fills as
land against the darker Brandenburg outside, the same figure-ground trick
the national pages use for sea versus land.
"""
import json, argparse

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("-o", "--out", default="data/berlin-geo.json")
args = ap.parse_args()

gj = json.load(open(args.src, encoding="utf-8"))
rings = []
for f in gj["features"]:
    if f["properties"].get("name") != "Berlin":
        continue
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polys:
        for ring in poly:
            rings.append([[round(x, 4), round(y, 4)] for x, y in ring])

doc = {"outline": rings, "states": rings}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(rings)} rings, {sum(len(r) for r in rings)} points")
