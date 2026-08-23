#!/usr/bin/env python3
"""Basemaps for the New York, Switzerland and London pages.

Usage:
    python3 build/build_geo_new.py ny     <us-atlas-dir>          -o data/ny-geo.json
    python3 build/build_geo_new.py ch     <natural-earth-geojson> -o data/ch-geo.json
    python3 build/build_geo_new.py london <uk-geojson> <ne-geojson> -o data/london-geo.json

All three emit the same {"outline": rings, "states": rings} the page draws:
"outline" is the land/figure layer, "states" the fainter division lines.

  ny      US Census counties (us-atlas 1:10M, public domain) around the
          harbour -- at metro scale the county lines double as the shape of
          Manhattan, Long Island and the Jersey shore.
  ch      Natural Earth 1:10M: Switzerland's cantons as divisions, the
          country ring as outline, and the big lakes, because Swiss rail
          runs along the water and the map is unreadable without it.
  london  ONS local authority districts for the Greater London boroughs,
          plus the Thames from Natural Earth.
"""
import argparse, json, math, os, sys


def rings_of(geom):
    polys = ([geom["coordinates"]] if geom["type"] == "Polygon"
             else geom["coordinates"] if geom["type"] == "MultiPolygon" else [])
    for poly in polys:
        for ring in poly:
            yield ring


def lines_of(geom):
    if geom["type"] == "LineString":
        yield geom["coordinates"]
    elif geom["type"] == "MultiLineString":
        yield from geom["coordinates"]


def thin(ring, tol_deg, keep_min=4):
    """Drop points closer together than the tolerance; rings shorter than
    keep_min points survive untouched so small islands do not vanish."""
    if len(ring) <= keep_min:
        return [[round(x, 4), round(y, 4)] for x, y in ring]
    out = [ring[0]]
    for p in ring[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol_deg:
            out.append(p)
    out.append(ring[-1])
    return [[round(x, 4), round(y, 4)] for x, y in out]


def inside(ring, box):
    lon0, lat0, lon1, lat1 = box
    return any(lon0 <= x <= lon1 and lat0 <= y <= lat1 for x, y in ring)


def topo_feature(topo, layer):
    """Decode a TopoJSON object into GeoJSON-ish features, no library."""
    tf = topo.get("transform")
    sx, sy = (tf["scale"] if tf else (1, 1))
    ox, oy = (tf["translate"] if tf else (0, 0))

    def arc(i):
        rev = i < 0
        if rev:
            i = ~i
        pts, x, y = [], 0, 0
        for dx, dy in topo["arcs"][i]:
            if tf:
                x += dx
                y += dy
                pts.append([x * sx + ox, y * sy + oy])
            else:
                pts.append([dx, dy])
        return pts[::-1] if rev else pts

    def ring(idxs):
        out = []
        for i in idxs:
            seg = arc(i)
            out.extend(seg if not out else seg[1:])
        return out

    for g in topo["objects"][layer]["geometries"]:
        t = g.get("type")
        if t == "Polygon":
            yield g.get("properties", {}), [ring(r) for r in g["arcs"]]
        elif t == "MultiPolygon":
            yield g.get("properties", {}), [ring(r) for poly in g["arcs"]
                                            for r in poly]


def build_ny(src):
    """us-atlas counties-10m TopoJSON -> the counties around the harbour."""
    topo = json.load(open(os.path.join(src, "counties-10m.json")))
    box = (-74.90, 40.10, -72.60, 41.80)
    outline, states = [], []
    for props, rings in topo_feature(topo, "counties"):
        for r in rings:
            if not inside(r, box):
                continue
            t = thin(r, 0.0012)
            if len(t) >= 4:
                outline.append(t)
    # One layer here: the county lines are the coastline as well.
    return {"outline": outline, "states": outline}


def build_ch(ne):
    """Natural Earth: Swiss cantons, the country ring, and the lakes."""
    prov = json.load(open(os.path.join(
        ne, "ne_10m_admin_1_states_provinces_lakes.geojson"), encoding="utf-8"))
    cantons = []
    for f in prov["features"]:
        p = f["properties"]
        if (p.get("iso_a2") or p.get("adm0_a3")) not in ("CH", "CHE"):
            continue
        for r in rings_of(f["geometry"]):
            t = thin(r, 0.004)
            if len(t) >= 4:
                cantons.append(t)

    countries = json.load(open(os.path.join(
        ne, "ne_10m_admin_0_countries_lakes.geojson"), encoding="utf-8"))
    box = (5.0, 45.2, 11.5, 48.4)
    outline = []
    for f in countries["features"]:
        p = f["properties"]
        if p.get("ADM0_A3") not in ("CHE", "LIE", "AUT", "FRA", "DEU", "ITA"):
            continue
        for r in rings_of(f["geometry"]):
            if not inside(r, box):
                continue
            t = thin(r, 0.004)
            if len(t) >= 4:
                outline.append(t)

    lakes = json.load(open(os.path.join(ne, "ne_10m_lakes_europe.geojson"),
                           encoding="utf-8"))
    lakebox = (5.5, 45.6, 10.9, 48.0)
    water = []
    for f in lakes["features"]:
        for r in rings_of(f["geometry"]):
            if not inside(r, lakebox):
                continue
            t = thin(r, 0.002)
            if len(t) >= 4:
                water.append(t)
    print(f"  cantons {len(cantons)} rings, borders {len(outline)}, "
          f"lakes {len(water)}")
    return {"outline": outline, "states": cantons + water}


def build_london(uk, ne):
    """Greater London's boroughs, with the Thames drawn through them."""
    lad = json.load(open(os.path.join(uk, "json", "administrative", "gb",
                                      "lad.json"), encoding="utf-8"))
    box = (-0.60, 51.24, 0.35, 51.73)
    boroughs = []
    for f in lad["features"]:
        name = (f["properties"].get("LAD13NM")
                or f["properties"].get("lad13nm") or "")
        for r in rings_of(f["geometry"]):
            if not inside(r, box):
                continue
            t = thin(r, 0.0015)
            if len(t) >= 4:
                boroughs.append(t)
    rivers = json.load(open(os.path.join(
        ne, "ne_10m_rivers_lake_centerlines.geojson"), encoding="utf-8"))
    thames = []
    for f in rivers["features"]:
        nm = (f["properties"].get("name") or "")
        if "Thames" not in nm:
            continue
        for line in lines_of(f["geometry"]):
            seg = [p for p in line if box[0] <= p[0] <= box[2]
                   and box[1] <= p[1] <= box[3]]
            t = thin(seg, 0.0008)
            if len(t) >= 2:
                thames.append(t)
    print(f"  boroughs {len(boroughs)} rings, Thames {len(thames)} lines")
    return {"outline": boroughs, "states": boroughs + thames}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["ny", "ch", "london"])
    ap.add_argument("src", nargs="+")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    doc = ({"ny": lambda: build_ny(args.src[0]),
            "ch": lambda: build_ch(args.src[0]),
            "london": lambda: build_london(args.src[0], args.src[1])}
           [args.which])()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    pts = sum(len(r) for r in doc["outline"]) + sum(len(r) for r in doc["states"])
    print(f"{args.out}: {len(doc['outline'])}+{len(doc['states'])} rings, "
          f"{pts} points, {os.path.getsize(args.out)/1e3:.0f} kB")


if __name__ == "__main__":
    main()
