#!/usr/bin/env python3
"""Turn Germany GeoJSON into the compact ring arrays the basemap draws.

Usage:
    python3 build/build_geo.py <outline.geo.json> <states.geo.json> [-o data/germany.json]

Coordinates are rounded to three decimals (about 70 m at this latitude), which
is far finer than a background outline needs and keeps the payload small.
"""
import argparse, json, os


def rings(path, min_points=6):
    """Every exterior ring in the file, as [[lon,lat], ...]."""
    out = []
    for feat in json.load(open(path, encoding="utf-8"))["features"]:
        geom = feat.get("geometry") or {}
        polys = (geom.get("coordinates") or [])
        if geom.get("type") == "Polygon":
            polys = [polys]
        elif geom.get("type") != "MultiPolygon":
            continue
        for poly in polys:
            if not poly:
                continue
            ring = [[round(float(x), 3), round(float(y), 3)] for x, y in poly[0]]
            # Drop consecutive duplicates created by the rounding.
            dedup = [ring[0]]
            for p in ring[1:]:
                if p != dedup[-1]:
                    dedup.append(p)
            if len(dedup) >= min_points:
                out.append(dedup)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outline")
    ap.add_argument("states")
    ap.add_argument("-o", "--out", default="data/germany.json")
    args = ap.parse_args()

    doc = {"outline": rings(args.outline), "states": rings(args.states)}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"))

    pts = sum(len(r) for r in doc["outline"]) + sum(len(r) for r in doc["states"])
    print(f"{args.out}: {len(doc['outline'])} outline + {len(doc['states'])} state "
          f"rings, {pts} points, {os.path.getsize(args.out)/1000:.0f} kB")


if __name__ == "__main__":
    main()
