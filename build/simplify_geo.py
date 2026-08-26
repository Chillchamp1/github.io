#!/usr/bin/env python3
"""Thin a basemap's rings with Douglas-Peucker, in place.

Usage:
    python3 build/simplify_geo.py data/pl-geo.json \
        --outline-tol 400 --states-tol 600

build_geo_countries.py decodes Natural Earth at full 1:10m detail and does
not thin it itself. That is fine for one or two countries; asked for two
dozen -- everything from Iceland to Turkey and North Africa, which this
country's neighbours as well -- a dozen of them for Poland, two dozen for
the air map -- it runs to tens of thousands of points, most of it coastal
wiggle invisible at the zoom the map actually renders at. The home country
(filled) keeps a little more detail than the neighbours (thin border lines
only), hence two tolerances.
"""
import argparse, json, math


def simplify(pts, tol_m):
    if len(pts) < 3:
        return pts
    k = math.cos(math.radians(pts[len(pts) // 2][1]))
    M = 111320.0
    xs = [(lon * k * M, lat * M) for lon, lat in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = xs[i]
        bx, by = xs[j]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        best, bd = -1, tol_m
        for m in range(i + 1, j):
            px, py = xs[m]
            if l2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / l2
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > bd:
                best, bd = m, d
        if best >= 0:
            keep[best] = True
            stack.append((i, best))
            stack.append((best, j))
    return [p for p, kf in zip(pts, keep) if kf]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("geo")
    ap.add_argument("--outline-tol", type=float, default=400.0)
    ap.add_argument("--states-tol", type=float, default=600.0)
    args = ap.parse_args()

    d = json.load(open(args.geo, encoding="utf-8"))
    before = sum(len(r) for r in d["outline"]) + sum(len(r) for r in d["states"])
    d["outline"] = [[[round(x, 4), round(y, 4)] for x, y in simplify(r, args.outline_tol)]
                    for r in d["outline"]]
    d["states"] = [[[round(x, 4), round(y, 4)] for x, y in simplify(r, args.states_tol)]
                   for r in d["states"]]
    after = sum(len(r) for r in d["outline"]) + sum(len(r) for r in d["states"])
    json.dump(d, open(args.geo, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"{args.geo}: {before} -> {after} points ({after/before:.0%})")


if __name__ == "__main__":
    main()
