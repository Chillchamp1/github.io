#!/usr/bin/env python3
"""Landmass for the combined Germany + Benelux + Switzerland map.

Usage:
    python3 build/build_geo_eu.py countries-10m.json -o data/eu-geo.json

All shapes come from world-atlas countries-10m.json -- Natural Earth 1:10M,
public domain, TopoJSON decoded here as in the other geo builders. The
three networks' own countries are the land; their neighbours are drawn as
the thin interior lines, so the borders that the trains cross are visible
without any of them looking like the edge of the world.
"""
import json, argparse

ap = argparse.ArgumentParser()
ap.add_argument("world")
ap.add_argument("-o", "--out", default="data/eu-geo.json")
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


# The networks themselves, then everyone whose border they touch.
HOME = {"Germany", "Netherlands", "Belgium", "Luxembourg", "Switzerland"}
NEIGHBOURS = {"France", "Austria", "Czechia", "Czech Republic", "Poland",
              "Denmark", "Italy", "Liechtenstein", "Slovenia",
              "United Kingdom"}
BOX = (1.0, 44.5, 17.5, 56.5)


def rings_for(names):
    out = []
    for g in topo["objects"]["countries"]["geometries"]:
        if g.get("properties", {}).get("name") not in names:
            continue
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        for poly in polys:
            for ring in poly:
                pts = ring_coords(ring)
                lons = [p[0] for p in pts]
                lats = [p[1] for p in pts]
                if max(lons) < BOX[0] or min(lons) > BOX[2] \
                   or max(lats) < BOX[1] or min(lats) > BOX[3]:
                    continue          # overseas territories and far islands
                if max(lons)-min(lons) + max(lats)-min(lats) < 0.05:
                    continue
                out.append([[round(x, 4), round(y, 4)] for x, y in pts])
    return out


outline = rings_for(HOME)
states = outline + rings_for(NEIGHBOURS)

doc = {"outline": outline, "states": states}
with open(args.out, "w") as f:
    json.dump(doc, f, separators=(",", ":"))
print(f"{args.out}: {len(outline)} home rings + {len(states)-len(outline)} "
      f"neighbour rings, {sum(len(r) for r in states)} points")
