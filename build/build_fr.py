#!/usr/bin/env python3
"""One day of French passenger rail, from SNCF's three open timetables.

Usage:
    python3 build/build_fr.py <YYYYMMDD> --ter <zip> --tgv <zip> --ic <zip>
                              [-o data/fr-trains.json]

SNCF publishes TER, TGV and Intercités as separate GTFS feeds. The copies
reachable from this build environment are the Mobility Database mirrors,
and they carry a January-April 2025 timetable: SNCF's own hosts and the
French national access point are both unreachable here. So this map is
built on a real Wednesday inside the feed's own validity window rather
than on a recent date -- one consistent day, plainly labelled, instead of
a 2025 schedule pretending to be today's.

The TGV mirror's window is the tightest, ending 21 February 2025, so the
date has to sit inside that.

  tgv        TGV, Ouigo, Lyria, Eurostar
  intercity  Intercités
  regional   TER
  night      Intercités de Nuit

Paris comes from a fourth feed. SNCF's own Transilien mirror is a 2019
snapshot, too old to draw, but Ile-de-France Mobilites publishes the whole
region and its mirror is current -- 31 May to 2 July 2026 -- so the RER and
Transilien arrive on a 2026 Wednesday while the rest of the country is on
its 2025 one. Two dated layers on one clock is a real compromise, and the
page says so; an empty Paris was the bigger lie. Only heavy rail is taken
from it: the Metro and the trams are a city network, not this map.
"""
import argparse, json, os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import Feed, hhmmss

CLASSES = ["tgv", "intercity", "regional", "night"]

# Two different trains do not share an origin, a destination and a
# departure minute. Wide enough to survive a timetable drifting between
# the two dates, narrow enough not to swallow a real neighbour.
DEDUP_SLACK = 5 * 60


def classify(kind, route):
    """The feeds are already split by service type, so the file a route
    comes from is the classification. Night trains are the exception: they
    ride inside the Intercités feed under plain line numbers -- 770B is
    Paris Austerlitz to Nice -- so they are found later, by the hours they
    keep rather than by their name."""
    if route.get("route_type") != "2":
        return None, ""
    name = (route.get("route_short_name")
            or route.get("route_long_name") or "").strip()
    return kind, name


# A service still rolling at two in the morning is a night train, whatever
# the feed calls it. GTFS keeps counting past 24:00, so this catches the
# Intercités de Nuit and leaves the last suburban runs of the evening alone.
NIGHT_AT = 26 * 3600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--ter", required=True)
    ap.add_argument("--tgv", required=True)
    ap.add_argument("--ic", required=True)
    ap.add_argument("--idf", help="Ile-de-France Mobilites feed (RER, "
                                  "Transilien); it needs its own date")
    ap.add_argument("--idf-date", help="service date for the Paris feed")
    ap.add_argument("-o", "--out", default="data/fr-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-5.4,41.2,9.8,51.4")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))
    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    dow = ["monday","tuesday","wednesday","thursday","friday",
           "saturday","sunday"][d.weekday()]

    sources = [("t:", args.ter, "regional", args.date, dow),
               ("g:", args.tgv, "tgv", args.date, dow),
               ("i:", args.ic, "intercity", args.date, dow)]
    if args.idf:
        if not args.idf_date:
            sys.exit("--idf needs --idf-date: the Paris mirror is a 2026 feed")
        pd = datetime.date(int(args.idf_date[:4]), int(args.idf_date[4:6]),
                           int(args.idf_date[6:]))
        sources.append(("p:", args.idf, "regional", args.idf_date,
                        ["monday","tuesday","wednesday","thursday","friday",
                         "saturday","sunday"][pd.weekday()]))

    stops, trips = {}, {}
    for ns, path, kind, sdate, sdow in sources:
        feed = Feed(path)
        active = set()
        for r in feed.rows("calendar.txt"):
            if r.get("start_date","") <= sdate <= r.get("end_date","") \
               and r.get(sdow) == "1":
                active.add(r["service_id"])
        for r in feed.rows("calendar_dates.txt"):
            if r.get("date") == sdate:
                (active.add if r.get("exception_type") == "1"
                 else active.discard)(r["service_id"])

        routes = {}
        for r in feed.rows("routes.txt"):
            cls, name = classify(kind, r)
            if cls:
                routes[r["route_id"]] = (cls, name)

        for r in feed.rows("stops.txt"):
            try:
                lon, lat = float(r["stop_lon"]), float(r["stop_lat"])
            except (ValueError, KeyError):
                continue
            if abs(lon) < 0.01 and abs(lat) < 0.01:
                continue
            stops[ns + r["stop_id"]] = (lon, lat,
                                        (r.get("stop_name") or "").strip())

        n0 = len(trips)
        for r in feed.rows("trips.txt"):
            if r.get("service_id") in active and r.get("route_id") in routes:
                cls, name = routes[r["route_id"]]
                label = name
                if r.get("trip_short_name"):
                    label = f"{name} {r['trip_short_name']}".strip()
                trips[ns + r["trip_id"]] = {
                    "cls": cls, "name": label, "src": ns,
                    "head": (r.get("trip_headsign") or "").strip(), "st": []}
        print(f"  {kind}: {len(trips)-n0} trips, {len(active)} services")

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

    print(f"candidate trips: {len(trips)}, stops: {len(stops)}")

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

    kept = []
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
        kept.append((t, st))

    # SNCF's national TER feed and the Paris one both carry the TER services
    # that run into Ile-de-France, so the same train would be drawn twice.
    # Line names are no help -- both call it "TER" -- but geography is: two
    # different trains do not share an origin, a destination and a departure
    # minute. Only ever matched between two feeds, never inside one.
    cell = lambda sid: (round(stops[sid][0], 2), round(stops[sid][1], 2))
    seen, merged, uniq = {}, 0, []
    for t, st in kept:
        key = (t["cls"], cell(st[0][1]), cell(st[-1][1]))
        dep, hit = st[0][3], None
        for dep0, at in seen.get(key, []):
            if abs(dep0 - dep) <= DEDUP_SLACK and uniq[at][0]["src"] != t["src"]:
                hit = at
                break
        if hit is not None:
            merged += 1
            if len(st) > len(uniq[hit][1]):
                uniq[hit] = (t, st)
            continue
        seen.setdefault(key, []).append((dep, len(uniq)))
        uniq.append((t, st))
    print(f"cross-feed duplicates merged: {merged} -> {len(uniq)} trips")

    out_trips, counts = [], {c: 0 for c in CLASSES}
    for t, st in uniq:
        seq = [[idx(s), a // 60, dp // 60] for _, s, a, dp in st]
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i-1][2]:
                seq[i][1] = seq[i-1][2]
            if seq[i][2] < seq[i][1]:
                seq[i][2] = seq[i][1]
        cls = t["cls"]
        if cls != "regional" and st[0][3] <= NIGHT_AT <= st[-1][2]:
            cls = "night"
        out_trips.append({"c": CLASSES.index(cls), "n": t["name"],
                          "h": t["head"], "s": seq})
        counts[cls] += 1

    live = [c for c in CLASSES if counts[c]]
    if live != CLASSES:
        remap = {CLASSES.index(c): i for i, c in enumerate(live)}
        for rec in out_trips:
            rec["c"] = remap[rec["c"]]
        counts = {c: counts[c] for c in live}

    stations = [[round(stops[s][0], 4), round(stops[s][1], 4), stops[s][2]]
                for s in order]
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": live, "counts": counts,
           "source": "SNCF open data (TER, TGV, Intercités)",
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
