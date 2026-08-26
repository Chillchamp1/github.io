#!/usr/bin/env python3
"""One day of Czech rail — the two regions that publish it.

Usage:
    python3 build/build_cz.py <YYYYMMDD> --pid <pid.zip> --jmk <idsjmk.zip> \\
        [-o data/cz-trains.json]

Czechia has no national open timetable either. Ceske drahy publishes none,
and the Mobility Database's Czech section is Prague, Olomouc, Liberec, South
Moravia and a national *bus* feed. Olomouc and Liberec are tram and bus
only. What is left is two integrated regional systems, and between them they
carry real railways rather than city transit:

  PID      Prague and the whole Stredocesky kraj -- the Esko suburban
           network plus the R lines out to Beroun, Kolin and Kladno
  IDS JMK  the Jihomoravsky kraj -- Brno's S network out to Breclav,
           Znojmo, Vyskov and the Slovak border at Myjava

Together about 3,900 trains: Bohemia around Prague and Moravia around Brno,
with the country between them empty because nobody publishes it. Trams,
metro, trolleybuses and buses are dropped from both; only route_type 2
survives.

Classification comes from the line prefix, which both systems use the same
way: S is the suburban network, R is a rychlik running through the region,
and everything else -- PID's U lines in the north-west, the odd unlettered
working -- is regional.

Only PID ships route geometry, so Bohemian trains follow the track and
Moravian ones interpolate between stops.
"""
import argparse, json, os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["express", "regional", "suburban"]


def classify(short):
    s = short.strip().upper()
    if s.startswith("S"):
        return "suburban"
    if s.startswith("R"):
        return "express"
    return "regional"


def collect(src, ns, date, stops, trips):
    feed = Feed(src)
    for r in feed.rows("stops.txt"):
        try:
            stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                        float(r["stop_lat"]),
                                        (r.get("stop_name") or "").strip())
        except (ValueError, KeyError):
            continue

    routes = {}
    for r in feed.rows("routes.txt"):
        if (r.get("route_type") or "") != "2":
            continue
        short = (r.get("route_short_name") or "").strip()
        routes[r["route_id"]] = (classify(short), short,
                                 (r.get("route_long_name") or "").strip())

    svc = feed.active_services(date)
    n = 0
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        cls, short, long_ = routes[r["route_id"]]
        num = (r.get("trip_short_name") or "").strip()
        trips[ns + r["trip_id"]] = {
            "cls": cls, "name": " ".join(x for x in [short, num] if x) or short,
            "head": (r.get("trip_headsign") or "").strip() or long_,
            "st": [], "shape": ns + r["shape_id"] if r.get("shape_id") else None,
        }
        n += 1

    for r in feed.rows("stop_times.txt"):
        t = trips.get(ns + r.get("trip_id", ""))
        if t is None or ns + r.get("stop_id", "") not in stops:
            continue
        a = hhmmss(r.get("arrival_time") or "")
        dp = hhmmss(r.get("departure_time") or "")
        if a is None and dp is None:
            continue
        a = a if a is not None else dp
        dp = dp if dp is not None else a
        t["st"].append((int(r["stop_sequence"]), ns + r["stop_id"], a, dp))

    print(f"  {os.path.basename(src)}: {len(routes)} rail routes, {n} trips")
    if n == 0:
        sys.exit(f"{src} contributed no trips on {date}")
    return feed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--pid", required=True)
    ap.add_argument("--jmk", required=True)
    ap.add_argument("-o", "--out", default="data/cz-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="11.9,48.4,19.0,51.2")
    ap.add_argument("--shape-tol", type=float, default=200.0)
    ap.add_argument("--tmp", default="/tmp/cz-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips, feeds = {}, {}, {}
    sources = [("p:", args.pid), ("j:", args.jmk)]
    for ns, src in sources:
        feeds[ns] = collect(src, ns, args.date, stops, trips)

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
    print(f"trips inside the frame: {len(kept)}")

    tracks = {}
    if args.shape_tol > 0:
        for ns, src in sources:
            wanted = {t["shape"][len(ns):] for t, _ in kept
                      if t["shape"] and t["shape"].startswith(ns)}
            sdir = feeds[ns].shapes_dir(os.path.join(args.tmp, ns.rstrip(":")))
            if not (sdir and wanted):
                continue
            for sid, pts in load_shapes(sdir, wanted).items():
                simp = simplify(pts, args.shape_tol)
                tracks[ns + sid] = (simp, shape_track(simp))
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
           "source": "PID (Praha, Středočeský kraj) and IDS JMK (Jihomoravský kraj)",
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
