#!/usr/bin/env python3
"""One day of Austrian rail, from the ÖBB passenger feed.

Usage:
    python3 build/build_at.py <gtfs.zip|dir> <YYYYMMDD> [-o data/at-trains.json]

**This is a 2024 timetable, and that has to be said first.** The only
openly mirrored ÖBB feed runs 10 December 2023 to 14 December 2024 -- one
annual timetable period, complete, with route geometry and 8,562 stops, and
then it stops. Austria's current data lives behind the national access
point at `data.mobilitaetsverbuende.at`, which is not reachable from this
build. Wednesday 21 August 2024 is an ordinary summer weekday inside the
feed's strongest stretch: 6,049 trains. The page says the year out loud,
the way the British one does.

What it is, though, is the whole country: ÖBB Personenverkehr plus
Montafonerbahn and the City Airport Train, from Bregenz to Nickelsdorf.

Classification comes from `trip_short_name`, which carries ÖBB's own
category as a prefix. The route table does not -- its `route_short_name` is
a route-group code (A, D, S, REX) that mixes railjets in with everything
else its group happens to contain -- so the train number is the honest
source. Measured on 21 August 2024:

    S    2750 trains    21 km    2.3 km between stops
    R    1349 trains    24 km    2.7 km
    REX  1150 trains    53 km    5.1 km
    RJX    78 trains   288 km   37.8 km
    NJ     65 trains   221 km   51.3 km

REX and CJX -- Regionalexpress and Cityjet Xpress -- are drawn as regional,
not intercity. They are Austria's equivalent of a German RE, and a German
RE is regional on every other page here; promoting them would make the
Austrian long-distance network look three times the size it is.
"""
import argparse, json, os, sys, datetime, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["express", "intercity", "regional", "sbahn", "night"]

CATEGORY = {
    "RJX": "express", "RJ": "express", "ICE": "express", "WB": "express",
    "IC": "intercity", "EC": "intercity", "ECB": "intercity", "D": "intercity",
    "NJ": "night", "EN": "night",
    "REX": "regional", "CJX": "regional", "R": "regional", "RX": "regional",
    "S": "sbahn", "CAT": "sbahn", "SP": "sbahn", "ER": "sbahn",
    "RR": "sbahn", "ATB": "sbahn",
}


def classify(num, fallback):
    """ÖBB's category prefix on the train number; the route-group letter
    only decides when a trip carries no number at all."""
    m = re.match(r"^([A-Za-zÄÖÜ]+)", (num or "").strip())
    if m:
        c = CATEGORY.get(m.group(1).upper())
        if c:
            return c
    m = re.match(r"^([A-Za-zÄÖÜ]+)", (fallback or "").strip())
    if m:
        c = CATEGORY.get(m.group(1).upper())
        if c:
            return c
    return "regional"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/at-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="9.3,46.2,17.4,49.3")
    ap.add_argument("--shape-tol", type=float, default=200.0)
    ap.add_argument("--tmp", default="/tmp/at-shapes")
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

    # route_type 2 only: the feed's 109 bus routes are ÖBB Postbus, which is
    # a coach network, and the Vienna U-Bahn is not in this file at all.
    routes = {}
    for r in feed.rows("routes.txt"):
        if (r.get("route_type") or "") != "2":
            continue
        routes[r["route_id"]] = ((r.get("route_short_name") or "").strip(),
                                 (r.get("route_long_name") or "").strip())
    print(f"stops: {len(stops)}, rail routes: {len(routes)}")

    svc = feed.active_services(args.date)
    trips = {}
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        short, long_ = routes[r["route_id"]]
        num = (r.get("trip_short_name") or "").strip()
        trips[r["trip_id"]] = {
            "cls": classify(num, short), "name": num or short,
            "head": (r.get("trip_headsign") or "").strip() or long_,
            "st": [], "shape": r.get("shape_id") or None,
        }
    print(f"candidate trips: {len(trips)}")

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
        if not t["head"]:
            t["head"] = stops[st[-1][1]][2]
        kept.append((t, st))
    print(f"trips touching Austria: {len(kept)}")
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
           "source": "ÖBB Personenverkehr (Mobility Database mirror)",
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
