#!/usr/bin/env python3
"""One day of everything on rails around New York, from five agency feeds.

Usage:
    python3 build/build_ny.py <feed-dir> <YYYYMMDD> [-o data/ny-trains.json]

<feed-dir> holds the agency GTFS zips or directories, named subway, lirr,
mnr, njt (see FEEDS). Four classes:
  subway    NYC Subway and the Staten Island Railway
  commuter  Long Island Rail Road, Metro-North, NJ Transit rail
  path      PATH, when a current feed is present
  light     NJ Transit light rail (Hudson-Bergen, Newark, River Line)

Everything is one time zone here, so unlike the national US page no clock
shifting is needed. Route geometry comes from each feed's shapes.txt.
"""
import argparse, csv, io, json, os, re, sys, datetime, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["subway", "commuter", "path", "light"]

# feed key -> (filename stem, default class for its rail routes)
FEEDS = [("subway", "subway"), ("lirr", "commuter"), ("mnr", "commuter"),
         ("njt", "commuter"), ("path", "path")]


def classify(route, default):
    """Rail only. Light rail rides in the NJ Transit feed as route_type 0."""
    try:
        rt = int(route.get("route_type") or -1)
    except ValueError:
        return None
    if rt == 0:
        return "light"
    if rt in (1, 2):
        return default if default != "light" else "commuter"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feeds", help="directory holding subway/lirr/mnr/njt zips")
    ap.add_argument("date", help="service date, YYYYMMDD")
    ap.add_argument("-o", "--out", default="data/ny-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-74.60,40.28,-72.90,41.60",
                    help="a trip is kept if it calls at least once inside")
    ap.add_argument("--shape-tol", type=float, default=30.0)
    ap.add_argument("--tmp", default="/tmp/ny-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips, tracks = {}, {}, {}
    for key, default in FEEDS:
        path = None
        for cand in (f"{args.feeds}/{key}.zip", f"{args.feeds}/{key}"):
            if os.path.exists(cand):
                path = cand
                break
        if path is None:
            print(f"  {key}: not present, skipped")
            continue
        feed = Feed(path)
        ns = key + ":"

        for r in feed.rows("stops.txt"):
            try:
                stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                            float(r["stop_lat"]),
                                            (r.get("stop_name") or "").strip())
            except (ValueError, KeyError):
                continue

        routes = {}
        for r in feed.rows("routes.txt"):
            cls = classify(r, default)
            if cls:
                routes[r["route_id"]] = (
                    cls, (r.get("route_short_name")
                          or r.get("route_long_name") or "").strip())

        svc = feed.active_services(args.date)
        n = 0
        for r in feed.rows("trips.txt"):
            if r.get("service_id") in svc and r.get("route_id") in routes:
                cls, name = routes[r["route_id"]]
                trips[ns + r["trip_id"]] = {
                    "cls": cls, "name": name,
                    "head": (r.get("trip_headsign") or "").strip(), "st": [],
                    "shape": ns + r["shape_id"] if r.get("shape_id") else None,
                }
                n += 1
        print(f"  {key}: {n} active trips on {args.date}")
        if n == 0:
            continue

        for r in feed.rows("stop_times.txt"):
            t = trips.get(ns + r.get("trip_id", ""))
            if t is None or ns + r.get("stop_id", "") not in stops:
                continue
            a, dp = hhmmss(r.get("arrival_time") or ""), hhmmss(
                r.get("departure_time") or "")
            if a is None and dp is None:
                continue
            a = a if a is not None else dp
            dp = dp if dp is not None else a
            t["st"].append((int(r["stop_sequence"]), ns + r["stop_id"], a, dp))

        if args.shape_tol > 0:
            wanted = {t["shape"][len(ns):] for t in trips.values()
                      if t["shape"] and t["shape"].startswith(ns)}
            sdir = feed.shapes_dir(os.path.join(args.tmp, key))
            if sdir and wanted:
                for sid, pts in load_shapes(sdir, wanted).items():
                    simp = simplify(pts, args.shape_tol)
                    tracks[ns + sid] = (simp, shape_track(simp))

    print(f"shapes: {len(tracks)} loaded and simplified")

    used, order, coord_key = {}, [], {}

    def idx(sid):
        if sid in used:
            return used[sid]
        lon, lat, name = stops[sid]
        key = (name, round(lon, 3), round(lat, 3))
        if key in coord_key:
            used[sid] = coord_key[key]
        else:
            used[sid] = coord_key[key] = len(order)
            order.append(sid)
        return used[sid]

    out_shapes, shape_out_idx, frac_cache = [], {}, {}
    out_trips, counts, matched = [], {c: 0 for c in CLASSES}, 0
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
        seq = [[idx(s), a // 60, dp // 60] for _, s, a, dp in st]
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i - 1][2]:
                seq[i][1] = seq[i - 1][2]
            if seq[i][2] < seq[i][1]:
                seq[i][2] = seq[i][1]
        rec = {"c": CLASSES.index(t["cls"]), "n": t["name"],
               "h": t["head"], "s": seq}
        if t["shape"] in tracks:
            ck = (t["shape"], tuple(s for _, s, _, _ in st))
            if ck not in frac_cache:
                frac_cache[ck] = stop_fracs(tracks[t["shape"]][1],
                                            [stops[s][:2] for _, s, _, _ in st])
            fr = frac_cache[ck]
            if fr is not None:
                if t["shape"] not in shape_out_idx:
                    shape_out_idx[t["shape"]] = len(out_shapes)
                    out_shapes.append(enc_shape(tracks[t["shape"]][0]))
                rec["p"] = [shape_out_idx[t["shape"]], fr]
                matched += 1
        out_trips.append(rec)
        counts[t["cls"]] += 1

    stations = [[round(stops[s][0], 4), round(stops[s][1], 4), stops[s][2]]
                for s in order]

    # A class nobody runs today (PATH, whose open feed has expired) would
    # otherwise sit in the legend as a permanent zero.
    kept = [c for c in CLASSES if counts[c]]
    if kept != CLASSES:
        remap = {CLASSES.index(c): i for i, c in enumerate(kept)}
        for rec in out_trips:
            rec["c"] = remap[rec["c"]]
        counts = {c: counts[c] for c in kept}

    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": kept, "counts": counts,
           "source": "MTA, Metro-North, LIRR, NJ Transit", "note": args.note,
           "stations": stations, "trips": out_trips}
    if out_shapes:
        doc["shapes"] = out_shapes
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{len(out_shapes)} shapes ({matched} on tracks), "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in kept:
        print(f"  {c:<9} {counts[c]}")


if __name__ == "__main__":
    main()
