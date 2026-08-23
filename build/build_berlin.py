#!/usr/bin/env python3
"""One day of everything that runs on rails in Berlin, from the DELFI GTFS.

Usage:
    python3 build/build_berlin.py <gtfs-dir> <YYYYMMDD> [-o data/berlin-trains.json]

Unlike the national builder this one KEEPS the urban modes -- that is the
point of the page. Five classes:
  fern   long-distance (ICE/IC/EC/FLX/NJ...)   route_type 101/102 or name
  regio  RE/RB and friends                      route_type 103/106 or name
  sbahn  S-Bahn                                 route_type 109
  ubahn  U-Bahn                                 route_type 400-402 or 1
  tram   trams, incl. Metrotram                 route_type 0 or 900
Buses, ferries and dial-a-ride stay excluded. A trip is kept if it calls
inside the Berlin/Potsdam box at least once, so an ICE bound for Munich is
drawn leaving the frame, exactly like the international trains on the
Germany page.
"""
import argparse, csv, json, os, re, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import load_shapes, simplify, shape_track, stop_fracs, enc_shape

CLASSES = ["fern", "regio", "sbahn", "ubahn", "tram"]
FERN  = re.compile(r"^(ICE|ECE|TGV|RJX?|IC|EC|D|NJ|EN|FLX)(?=[ \d]|$)")
REGIO = re.compile(r"^(IRE|RE|RB|MEX|ODEG|NEB|HANS)(?=[ \d]|$)")
NOISE = re.compile(r"^(AST|ALT|SEV|EV|Bus|Schiff|RUF|F\d)", re.I)


def classify(r):
    name = (r.get("route_short_name") or r.get("route_long_name") or "").strip()
    if not name or NOISE.match(name):
        return None, name
    try:
        rt = int(r.get("route_type") or -1)
    except ValueError:
        return None, name
    if rt == 109:
        return "sbahn", name
    if rt in (1, 400, 401, 402):
        return "ubahn", name
    if rt in (0, 900):
        return "tram", name
    if rt in (101, 102, 105) or (rt in (2, 103, 106) and FERN.match(name)):
        return "fern", name
    if rt in (103, 106) or (rt == 2 and REGIO.match(name)):
        return "regio", name
    return None, name


def read(path, name):
    fp = os.path.join(path, name)
    if not os.path.exists(fp):
        return
    with open(fp, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            yield {(k or "").strip(): (v or "").strip() for k, v in r.items()}


def hhmmss(v):
    try:
        h, m, s = (int(x) for x in v.split(":"))
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/berlin-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="13.05,52.30,13.79,52.70")
    ap.add_argument("--shape-tol", type=float, default=25.0,
                    help="shape simplification tolerance in meters; city zoom "
                         "sits near 70 m/px, so 25 m is invisible")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))
    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    dow = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][d.weekday()]

    active = set()
    for r in read(args.gtfs, "calendar.txt"):
        if r["start_date"] <= args.date <= r["end_date"] and r.get(dow) == "1":
            active.add(r["service_id"])
    for r in read(args.gtfs, "calendar_dates.txt"):
        if r["date"] == args.date:
            (active.add if r["exception_type"] == "1" else active.discard)(r["service_id"])

    routes = {}
    for r in read(args.gtfs, "routes.txt"):
        cls, name = classify(r)
        if cls:
            routes[r["route_id"]] = (cls, name)

    stops = {}
    for r in read(args.gtfs, "stops.txt"):
        try:
            stops[r["stop_id"]] = (float(r["stop_lon"]), float(r["stop_lat"]),
                                   r["stop_name"])
        except (ValueError, KeyError):
            continue

    trips = {}
    for r in read(args.gtfs, "trips.txt"):
        if r["service_id"] in active and r["route_id"] in routes:
            cls, name = routes[r["route_id"]]
            trips[r["trip_id"]] = {"cls": cls, "name": name,
                                   "head": r.get("trip_headsign", ""), "st": [],
                                   "shape": r.get("shape_id") or None}
    print(f"candidate trips nationwide: {len(trips)}")

    for r in read(args.gtfs, "stop_times.txt"):
        t = trips.get(r.get("trip_id", ""))
        if t is None or r.get("stop_id") not in stops:
            continue
        a, dp = hhmmss(r.get("arrival_time", "")), hhmmss(r.get("departure_time", ""))
        if a is None and dp is None:
            continue
        a = a if a is not None else dp
        dp = dp if dp is not None else a
        t["st"].append((int(r["stop_sequence"]), r["stop_id"], a, dp))

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

    # Only trips already known to touch the box need geometry -- shapes.txt
    # is nationwide, so first find the kept trips, then load their shapes.
    kept = []
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon and minlat <= stops[s][1] <= maxlat
                   for _, s, _, _ in st):
            continue
        kept.append((t, st))

    tracks = {}
    if args.shape_tol > 0:
        wanted = {t["shape"] for t, _ in kept if t["shape"]}
        for sid, pts in load_shapes(args.gtfs, wanted).items():
            simp = simplify(pts, args.shape_tol)
            tracks[sid] = (simp, shape_track(simp))
        print(f"shapes: {len(tracks)} loaded and simplified")

    out_shapes, shape_out_idx, frac_cache = [], {}, {}
    out_trips, counts, matched = [], {c: 0 for c in CLASSES}, 0
    for t, st in kept:
        seq = [[idx(s), a // 60, dp // 60] for _, s, a, dp in st]
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i-1][2]: seq[i][1] = seq[i-1][2]
            if seq[i][2] < seq[i][1]:   seq[i][2] = seq[i][1]
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
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": CLASSES, "counts": counts,
           "source": "DELFI e.V.", "note": args.note,
           "stations": stations, "trips": out_trips}
    if out_shapes:
        doc["shapes"] = out_shapes
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{len(out_shapes)} shapes ({matched} trips on tracks), "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in CLASSES:
        print(f"  {c:6} {counts[c]}")

if __name__ == "__main__":
    main()
