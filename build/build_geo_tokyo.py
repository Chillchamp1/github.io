#!/usr/bin/env python3
"""Kanto-area prefecture polygons -> the compact ring format the page draws.

Usage: python3 build/build_geo_tokyo.py japan.geojson -o data/tokyo-geo.json

Source: dataofjapan/land japan.geojson (prefecture boundaries, MIT-listed
repo, geometry from Japan's National Land Numerical Information). Only the
prefectures the network touches are kept, and only rings that intersect a
Kanto bounding box -- Tokyo's Pacific islands are administratively Tokyo
but 300 km off the map. 4-decimal coordinates: Tokyo Bay's shape is the
whole point of this basemap.
"""
import json, argparse

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("-o", "--out", default="data/tokyo-geo.json")
args = ap.parse_args()

KEEP = ("Tokyo", "Kanagawa", "Chiba", "Saitama", "Ibaraki",
        "Tochigi", "Gunma", "Yamanashi", "Shizuoka")
BOX = (137.8, 34.4, 141.2, 37.2)   # lon0, lat0, lon1, lat1

gj = json.load(open(args.src, encoding="utf-8"))
rings = []
for f in gj["features"]:
    if not any(k in f["properties"].get("nam", "") for k in KEEP):
        continue
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polys:
        for ring in poly:
            lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
            if max(lons) < BOX[0] or min(lons) > BOX[2] \
               or max(lats) < BOX[1] or min(lats) > BOX[3]:
                continue
            if max(lons)-min(lons) + max(lats)-min(lats) < 0.02:
                continue                     # islet
            rings.append([[round(x, 4), round(y, 4)] for x, y in ring])

doc = {"outline": rings, "states": rings}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(rings)} rings, {sum(len(r) for r in rings)} points")
