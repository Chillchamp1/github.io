#!/usr/bin/env python3
"""One day of Slovak rail, from the ZSSK national feed.

Usage:
    python3 build/build_sk.py <gtfs.zip|dir> <YYYYMMDD> [-o data/sk-trains.json]

Slovakia publishes what its neighbour does not: one national timetable,
current, covering every passenger operator on the network. Železničná
spoločnosť Slovensko carries the great majority of it, and beside them run
RegioJet and Leo Express on the Bratislava–Košice trunk and the Trenčianska
elektrická železnica up to Trenčianska Teplá.

There is no route geometry, so trains take the straight line between stops
-- across the Tatras that reads shorter than the railway is, and the page
says so.

The category is in the route's short name, which is the train's own
designation, and the tiers separate exactly as ZSSK sells them (measured on
Wednesday 10 June 2026):

    Os   1558 trains    35 km    2.8 km between stops   osobný -- all stops
    REX   165 trains    54 km    5.3 km                 regionálny expres
    R     133 trains   139 km   12.5 km                 rýchlik
    Ex     38 trains   314 km   19.6 km                 expres
    EC     37 trains   301 km   21.5 km
    rj     26 trains   302 km   36.4 km                 railjet

`R` -- the rýchlik, a fast train that runs the length of a corridor -- is
drawn as intercity, matching how the Czech page treats its own R lines.
"""
import argparse, json, os, sys, datetime, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import Feed, hhmmss

CLASSES = ["express", "intercity", "regional", "night"]

CATEGORY = {
    "RJ": "express", "RJX": "express", "SC": "express",
    "EC": "intercity", "IC": "intercity", "EX": "intercity",
    "LE": "intercity", "R": "intercity", "ZR": "intercity",
    "EN": "night",
    "REX": "regional", "OS": "regional", "RRR": "regional",
}
# route_type 105 is a sleeper whatever it calls itself.
SLEEPER_TYPE = "105"


def classify(short, rtype):
    if rtype == SLEEPER_TYPE:
        return "night"
    m = re.match(r"^([A-Za-zČŠŽ]+)", (short or "").strip())
    return CATEGORY.get(m.group(1).upper(), "regional") if m else "regional"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/sk-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="16.7,47.6,22.7,49.7")
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

    # The feed uses the extended rail types throughout -- 100 railway, 102
    # long distance, 103 inter-regional, 105 sleeper, 106 regional -- and
    # nothing else, so every route in it is a train.
    rail = {"2"} | {str(x) for x in range(100, 118)}
    routes = {}
    for r in feed.rows("routes.txt"):
        rt = (r.get("route_type") or "").strip()
        if rt not in rail:
            continue
        short = (r.get("route_short_name") or "").strip()
        routes[r["route_id"]] = (classify(short, rt), short,
                                 (r.get("route_long_name") or "").strip())
    print(f"stops: {len(stops)}, rail routes: {len(routes)}")

    svc = feed.active_services(args.date)
    trips = {}
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        cls, short, long_ = routes[r["route_id"]]
        trips[r["trip_id"]] = {
            "cls": cls, "name": short or (r.get("trip_short_name") or "").strip(),
            "head": (r.get("trip_headsign") or "").strip() or long_, "st": [],
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
    print(f"trips touching Slovakia: {len(kept)}")
    if not kept:
        sys.exit(f"no trips on {args.date} -- wrong date for this feed?")

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

    out_trips, counts = [], {c: 0 for c in CLASSES}
    for t, st in kept:
        seq = [[idx(s), a // 60, dp // 60] for _, s, a, dp in st]
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i - 1][2]:
                seq[i][1] = seq[i - 1][2]
            if seq[i][2] < seq[i][1]:
                seq[i][2] = seq[i][1]
        out_trips.append({"c": CLASSES.index(t["cls"]), "n": t["name"],
                          "h": t["head"], "s": seq})
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
           "source": "Železničná spoločnosť Slovensko, with RegioJet and Leo Express",
           "note": args.note, "stations": stations, "trips": out_trips}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in live:
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
