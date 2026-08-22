#!/usr/bin/env python3
"""Benelux landmass -> the compact ring format the page draws.

Usage:
    python3 build/build_geo_benelux.py countries-10m.json provincie_2025.geojson \
        -o data/nl-geo.json

Country shapes (Netherlands, Belgium, Luxembourg) come from world-atlas
countries-10m.json -- Natural Earth 1:10M, public domain, TopoJSON decoded
right here. The Dutch province boundaries from cartomap/nl ride along as
the thin interior lines, like states on the US map.
"""
import json, argparse

ap = argparse.ArgumentParser()
ap.add_argument("world")
ap.add_argument("provinces")
ap.add_argument("-o", "--out", default="data/nl-geo.json")
args = ap.parse_args()

topo = json.load(open(args.world))
sx, sy = topo["transform"]["scale"]
tx, ty = topo["transform"]["translate"]
arcs = []
for arc in topo["arcs"]:
    x = y = 0
    pts = []
    for dx, dy in arc:
        x += dx; y += dy
        pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)

def ring_coords(ring):
    out = []
    for idx in ring:
        pts = arcs[idx] if idx >= 0 else arcs[~idx][::-1]
        out.extend(pts if not out else pts[1:])
    return out

KEEP = {"Netherlands", "Belgium", "Luxembourg"}
BOX = (1.5, 48.8, 9.0, 54.2)
outline = []
for g in topo["objects"]["countries"]["geometries"]:
    if g.get("properties", {}).get("name") not in KEEP:
        continue
    polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
    for poly in polys:
        for ring in poly:
            pts = ring_coords(ring)
            lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
            if max(lons) < BOX[0] or min(lons) > BOX[2] \
               or max(lats) < BOX[1] or min(lats) > BOX[3]:
                continue                       # Caribbean municipalities
            if max(lons)-min(lons) + max(lats)-min(lats) < 0.05:
                continue
            outline.append([[round(x, 4), round(y, 4)] for x, y in pts])

states = list(outline)
gj = json.load(open(args.provinces, encoding="utf-8"))
for f in gj["features"]:
    g = f["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    for poly in polys:
        for ring in poly:
            states.append([[round(x, 4), round(y, 4)] for x, y in ring])

doc = {"outline": outline, "states": states}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(outline)} country rings + "
      f"{len(states)-len(outline)} province rings, "
      f"{sum(len(r) for r in states)} points")
