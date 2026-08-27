#!/usr/bin/env python3
"""One day of Croatian rail, from the HŽPP national feed.

Usage:
    python3 build/build_hr.py <gtfs.zip|dir> <YYYYMMDD> [-o data/hr-trains.json]

HŽ Putnički prijevoz publishes the whole country in one current file: Zagreb
out to Rijeka, Split, Osijek, Vukovar and Varaždin, plus the Istrian line
from Pula that reaches Croatia only through Slovenia. 728 trains on an
ordinary Wednesday, which is what a network this size runs.

Two things the feed does not give, and both shape this file.

**No route geometry.** Trains take the straight line between stops. Along
the Lika line to Split that is a serious understatement of the distance,
because the railway winds where the straight line does not, and the page
says so.

**No train category anywhere.** There is no `route_short_name`, the routes
are named for their corridor ("Zagreb Glavni kolodvor - Split") and
`trip_short_name` is a bare number. So the tier is measured rather than
read, from the shape of each run -- how far it goes and how far apart it
stops. On 10 June 2026 that splits 728 trains into:

    18 intercity   >= 120 km end to end and >= 8 km between stops --
                   Zagreb to Split, Osijek, Vukovar and Rijeka
   235 suburban    < 60 km with a stop under every 2.5 km -- the Zagreb
                   ring out to Harmica, Dugo Selo and Novoselec, and the
                   Split local service to Kaštel Stari
   475 regional    everything else

The thresholds are set where the distribution has room either side of them:
the 90th percentile of trip length is 90 km and the 95th is 143 km, so 120
km cuts through a gap rather than through a cluster.
"""
import argparse, json, os, sys, datetime, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import Feed, hhmmss

CLASSES = ["intercity", "regional", "suburban"]

LONG_KM, LONG_SPACING = 120.0, 8.0
LOCAL_KM, LOCAL_SPACING = 60.0, 2.5


def classify(dist_km, spacing_km):
    if dist_km >= LONG_KM and spacing_km >= LONG_SPACING:
        return "intercity"
    if dist_km < LOCAL_KM and spacing_km < LOCAL_SPACING:
        return "suburban"
    return "regional"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/hr-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="13.2,42.3,19.6,46.7")
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
    trips = {}
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        num = (r.get("trip_short_name") or "").strip()
        trips[r["trip_id"]] = {
            "name": num or "HŽ",
            "head": (r.get("trip_headsign") or "").strip()
                    or routes[r["route_id"]].split(" - ")[-1],
            "st": [],
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

    def km(a, b):
        (x1, y1, _), (x2, y2, _) = stops[a], stops[b]
        k = math.cos(math.radians((y1 + y2) / 2))
        return math.hypot((x2 - x1) * k, y2 - y1) * 111.32

    kept = []
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
        d = km(st[0][1], st[-1][1])
        t["cls"] = classify(d, d / (len(st) - 1))
        kept.append((t, st))
    print(f"trips inside the frame: {len(kept)}")
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
           "source": "HŽ Putnički prijevoz", "note": args.note,
           "stations": stations, "trips": out_trips}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in live:
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
