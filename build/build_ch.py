#!/usr/bin/env python3
"""One day of Swiss rail, from the national SKI+/SBB open timetable.

Usage:
    python3 build/build_ch.py <gtfs.zip|dir> <YYYYMMDD> [-o data/ch-trains.json]

Switzerland publishes one aggregate feed for every operator in the country,
which makes the classification purely type-driven:

  ice       101 high-speed (TGV) + 102 IC/EC
  ir        103 InterRegio
  regional  106 regional (R, RE)
  sbahn     109 S-Bahn
  mountain  107 panorama (Glacier/Bernina Express) + 116 rack railway
  night     105 sleeper

Trams, the Lausanne metro, funiculars, gondolas, boats and buses are left
out, matching the Germany page's rule that a national map shows trains.
Rack railways stay in: half the point of Swiss rail is that it climbs.
"""
import argparse, json, os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["ice", "ir", "regional", "sbahn", "mountain", "night"]
BY_TYPE = {101: "ice", 102: "ice", 103: "ir", 106: "regional",
           109: "sbahn", 107: "mountain", 116: "mountain", 105: "night"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/ch-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="5.5,45.6,10.8,48.0",
                    help="a trip is kept if it calls at least once inside")
    ap.add_argument("--shape-tol", type=float, default=150.0)
    ap.add_argument("--tmp", default="/tmp/ch-shapes")
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
    print(f"stops: {len(stops)}")

    routes = {}
    for r in feed.rows("routes.txt"):
        try:
            rt = int(r.get("route_type") or -1)
        except ValueError:
            continue
        cls = BY_TYPE.get(rt)
        if cls:
            routes[r["route_id"]] = (
                cls, (r.get("route_short_name")
                      or r.get("route_long_name") or "").strip())
    print(f"rail routes: {len(routes)}")

    svc = feed.active_services(args.date)
    print(f"services active on {args.date}: {len(svc)}")

    trips = {}
    for r in feed.rows("trips.txt"):
        if r.get("service_id") in svc and r.get("route_id") in routes:
            cls, name = routes[r["route_id"]]
            trips[r["trip_id"]] = {
                "cls": cls, "name": name,
                "head": (r.get("trip_headsign") or "").strip(), "st": [],
                "shape": r.get("shape_id") or None,
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
        kept.append((t, st))
    print(f"trips inside the frame: {len(kept)}")

    tracks = {}
    if args.shape_tol > 0:
        sdir = feed.shapes_dir(args.tmp)
        wanted = {t["shape"] for t, _ in kept if t["shape"]}
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
           "source": "SKI+ / SBB (opentransportdata.swiss)", "note": args.note,
           "stations": stations, "trips": out_trips}
    if out_shapes:
        doc["shapes"] = out_shapes
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{len(out_shapes)} shapes ({matched} on tracks), "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in live:
        print(f"  {c:<9} {counts[c]}")


if __name__ == "__main__":
    main()
