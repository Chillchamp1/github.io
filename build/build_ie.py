#!/usr/bin/env python3
"""One day of Irish rail, from the Transport for Ireland feed.

Usage:
    python3 build/build_ie.py <gtfs.zip|dir> <YYYYMMDD> [-o data/ie-trains.json]

Ireland publishes a single national rail feed through the National
Transport Authority and it is a small, tidy thing: one operator, nineteen
routes, 2,552 trains a week, route geometry for all of them. That is the
whole of Iarnród Éireann -- Dublin to Belfast, Cork, Galway, Sligo, Tralee,
Westport and Waterford, plus the Dublin and Cork suburban networks. Nothing
is missing; the network really is this size.

The feed's own `route_short_name` is nearly useless -- fourteen of the
nineteen routes are called "rail" -- but `trip_short_name` carries the
class as its first letter, and the letters separate cleanly when measured:

    A   249 trains   132 km   19.0 km between stops    InterCity
    E   199 trains    27 km    1.0 km between stops    DART
    P   220 trains    23 km    3.2 km between stops    Commuter
    D   211 trains    23 km    3.1 km between stops    Commuter (diesel)

A is unmistakably long distance, E is the Dublin electric suburban line
with a stop every kilometre, and P and D have the same profile as each
other -- P is the Dublin diesel commuter fleet, D the Cork and Limerick
one. They are drawn as one class because the data says they are one kind
of train, whatever the depot.

Trips numbered BUS are rail-replacement coaches running under a rail route
id. Two of them run on an ordinary Wednesday and they are dropped: this map
draws trains.
"""
import argparse, json, os, sys, datetime, re, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["intercity", "commuter", "dart"]

LETTER = {"A": "intercity", "E": "dart", "P": "commuter", "D": "commuter",
          "B": "commuter"}


def classify(short):
    """The leading letter of the train number, which is the operator's own
    fleet code. BUS is a coach, not a train, and returns None."""
    m = re.match(r"^([A-Za-z]+)", short.strip())
    if not m:
        return "commuter"
    tok = m.group(1).upper()
    if tok == "BUS":
        return None
    return LETTER.get(tok, "commuter")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/ie-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-11.0,51.2,-5.2,55.6")
    ap.add_argument("--shape-tol", type=float, default=200.0)
    ap.add_argument("--tmp", default="/tmp/ie-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    feed = Feed(args.gtfs)
    stops = {}
    for r in feed.rows("stops.txt"):
        try:
            stops[r["stop_id"]] = (float(r["stop_lon"]), float(r["stop_lat"]),
                                   (r.get("stop_name") or "").strip())
        except (ValueError, KeyError):
            continue

    routes = {}
    for r in feed.rows("routes.txt"):
        if (r.get("route_type") or "") != "2":
            continue
        routes[r["route_id"]] = (r.get("route_long_name") or "").strip()
    print(f"stops: {len(stops)}, rail routes: {len(routes)}")

    svc = feed.active_services(args.date)
    trips, coaches = {}, 0
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        num = (r.get("trip_short_name") or "").strip()
        cls = classify(num)
        if cls is None:
            coaches += 1
            continue
        trips[r["trip_id"]] = {
            "cls": cls, "name": num or "Irish Rail",
            "head": (r.get("trip_headsign") or "").strip()
                    or routes[r["route_id"]],
            "st": [], "shape": r.get("shape_id") or None,
        }
    print(f"candidate trips: {len(trips)} ({coaches} replacement coaches dropped)")

    for r in feed.rows("stop_times.txt"):
        t = trips.get(r.get("trip_id", ""))
        if t is None or r.get("stop_id") not in stops:
            continue
        a, dp = hhmmss(r.get("arrival_time") or ""), hhmmss(
            r.get("departure_time") or "")
        if a is None and dp is None:
            continue
        a = a if a is not None else dp
        dp = dp if dp is not None else a
        t["st"].append((int(r["stop_sequence"]), r["stop_id"], a, dp))

    kept = []
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
        kept.append((t, st))
    print(f"trips inside the frame: {len(kept)}")
    if not kept:
        sys.exit(f"no trips on {args.date} -- wrong date for this feed?")

    tracks = {}
    if args.shape_tol > 0:
        wanted = {t["shape"] for t, _ in kept if t["shape"]}
        sdir = feed.shapes_dir(args.tmp)
        if sdir and wanted:
            for sid, pts in load_shapes(sdir, wanted).items():
                simp = simplify(pts, args.shape_tol)
                tracks[sid] = (simp, shape_track(simp))
    print(f"shapes: {len(tracks)}")

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
    for t, st in kept:
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

    live = [c for c in CLASSES if counts[c]]
    if live != CLASSES:
        remap = {CLASSES.index(c): i for i, c in enumerate(live)}
        for rec in out_trips:
            rec["c"] = remap[rec["c"]]
        counts = {c: counts[c] for c in live}

    stations = [[round(stops[s][0], 4), round(stops[s][1], 4), stops[s][2]]
                for s in order]
    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": live, "counts": counts,
           "source": "Transport for Ireland / Iarnród Éireann",
           "note": args.note, "stations": stations, "trips": out_trips}
    if out_shapes:
        doc["shapes"] = out_shapes
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{len(out_shapes)} shapes ({matched} on tracks), "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in live:
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
