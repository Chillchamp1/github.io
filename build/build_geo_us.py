#!/usr/bin/env python3
"""US state polygons -> the compact ring format the page draws.

Usage: python3 build/build_geo_us.py states-10m.json -o data/us-geo.json

Source: topojson/us-atlas states-10m.json (U.S. Census Bureau 1:10M
cartographic boundaries, shoreline-clipped; ISC/public-domain data). It is
TopoJSON, so this decodes the quantised delta-encoded arcs directly rather
than pulling in a library. Alaska, Hawaii and Puerto Rico are dropped: no
feed in the bundle serves them, and Alaska alone would double the frame.
Tiny offshore islets are dropped too -- at map scale they are noise.

The page fills and strokes the same rings, so there is no separate national
outline; shared state borders drawn twice land on the same pixels.
"""
import json, argparse

ap = argparse.ArgumentParser()
ap.add_argument("src")
ap.add_argument("-o", "--out", default="data/us-geo.json")
args = ap.parse_args()

topo = json.load(open(args.src))
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

DROP = {"Alaska", "Hawaii", "Puerto Rico"}
rings = []
for g in topo["objects"]["states"]["geometries"]:
    if g.get("properties", {}).get("name") in DROP:
        continue
    polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
    for poly in polys:
        for ring in poly:
            pts = ring_coords(ring)
            lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
            if max(lons)-min(lons) + max(lats)-min(lats) < 0.05:
                continue                      # offshore islet
            # Four decimals (~11 m), matching the other basemaps: at three
            # the coastline visibly staircases once the map is zoomed in.
            rings.append([[round(x, 4), round(y, 4)] for x, y in pts])

doc = {"outline": rings, "states": rings}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(rings)} rings, {sum(len(r) for r in rings)} points")
