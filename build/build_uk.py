#!/usr/bin/env python3
"""One day of British rail, from the National Rail timetable.

Usage:
    python3 build/build_uk.py <gtfs.zip|dir> <YYYYMMDD> [-o data/uk-trains.json]

The London page says British open data carries no National Rail, and for
the source it uses -- the Bus Open Data Service -- that is still true: BODS
is 1.3 GB of 13,327 bus routes, 348 coach routes, and metros and trams. Not
one heavy-rail operator.

This is a different file. The Mobility Database lists it under "Chiltern
Railways", which is how it went unnoticed: open it and there are
twenty-seven National Rail operators inside, 3,004 stations and 176,591
trips -- the whole British network, Penzance to Thurso.

Two things about it have to be said plainly.

**It is a 2021 timetable.** The calendar runs December 2020 to December
2021, and the station list dates it precisely: Worcestershire Parkway
(opened February 2020), Horden (June 2020) and Bow Street (February 2021)
are all present, while Soham (December 2021) and Marsh Barton (2023) are
not. Wednesday 9 June 2021 is an ordinary mid-week day inside the strongest
part of that year -- 20,268 trains, against roughly 22,000 on a normal
pre-pandemic weekday.

**The operator names are older than the timetable.** The feed's agency
table still says South West Trains, London Midland, East Coast and Virgin
Trains, franchises that had ended by 2019. The timetable is 2021; the
agency table simply was not refreshed with it. OPERATOR_2021 renames them
to who was actually running those trains on the day drawn.

Classification is by operator, because British operators are franchises
with a shape: Grand Central's median trip is 385 km with 17 km between
stops, London Overground's is 14 km with 1 km between stops. Three
operators are genuinely mixed -- Great Western runs Paddington to Penzance
and Thames Valley locals under one name -- so within those a trip is
promoted to intercity when it goes at least 150 km at 10 km or more per
stop, which catches the Cornish sleeper-hauled expresses without touching
a Slough stopper.
"""
import argparse, json, os, sys, datetime, math, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import Feed, hhmmss

CLASSES = ["intercity", "regional", "suburban", "night"]

# Who was actually running these trains in June 2021.
OPERATOR_2021 = {
    "South West Trains": "South Western Railway",
    "London Midland": "West Midlands Trains",
    "East Coast": "LNER",
    "Virgin Trains": "Avanti West Coast",
    "First Great Western": "Great Western Railway",
    "Arriva Trains Wales": "Transport for Wales",
    "Abellio Greater Anglia": "Greater Anglia",
    "First TransPennine Express": "TransPennine Express",
    "East Midlands Trains": "East Midlands Railway",
    "First Hull Trains": "Hull Trains",
    "Northern Rail": "Northern",
    "Crossrail": "TfL Rail",
    "Serco Caledonian Sleeper": "Caledonian Sleeper",
    "Nexus (Tyne & Wear Metro)": "Tyne and Wear Metro",
}

INTERCITY = {"LNER", "Avanti West Coast", "CrossCountry", "TransPennine Express",
             "Grand Central", "Hull Trains", "East Midlands Railway"}
SUBURBAN = {"London Overground", "Merseyrail", "TfL Rail", "Island Line",
            "Heathrow Express", "Heathrow Connect", "Gatwick Express"}
NIGHT = {"Caledonian Sleeper"}
# Franchises that run both ends of the market under one name.
MIXED = {"Great Western Railway", "Greater Anglia", "Chiltern Railways",
         "West Midlands Trains", "Transport for Wales"}
LONG_KM, LONG_SPACING = 150.0, 10.0


def classify(op, dist_km, spacing_km):
    if op in NIGHT:
        return "night"
    if op in INTERCITY:
        return "intercity"
    if op in SUBURBAN:
        return "suburban"
    if op in MIXED and dist_km >= LONG_KM and spacing_km >= LONG_SPACING:
        return "intercity"
    return "regional"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/uk-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-8.3,49.8,2.1,59.0")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    feed = Feed(args.gtfs)

    # 422 of the 3,004 entries in stops.txt sit at 0,0 with no coordinates.
    # Ten of them are called at on a weekday, and they are exactly the newest
    # stations: Worcestershire Parkway, Horden, Bow Street, Kenilworth,
    # Meridian Water, Reading Green Park, Warrington West -- added to the
    # timetable and never given a position. Dropped rather than guessed: a
    # train then runs through without a marked call, which interpolates
    # correctly between its neighbours, where 541 trips teleporting to the
    # Gulf of Guinea would not.
    stops, nowhere = {}, 0
    for r in feed.rows("stops.txt"):
        try:
            lon, lat = float(r["stop_lon"]), float(r["stop_lat"])
        except (ValueError, KeyError):
            continue
        if abs(lon) < 0.01 and abs(lat) < 0.01:
            nowhere += 1
            continue
        stops[r["stop_id"]] = (lon, lat, (r.get("stop_name") or "").strip())
    print(f"stops: {len(stops)} ({nowhere} dropped for having no coordinates)")

    agency = {a["agency_id"]: OPERATOR_2021.get((a.get("agency_name") or "").strip(),
                                                (a.get("agency_name") or "").strip())
              for a in feed.rows("agency.txt")}
    # route_type 2 only: the Underground, the Glasgow Subway and the Tyne and
    # Wear Metro are type 1 and stay out, on the rule every national map here
    # uses -- suburban railway yes, metro no.
    routes = {}
    for r in feed.rows("routes.txt"):
        if (r.get("route_type") or "") != "2":
            continue
        routes[r["route_id"]] = agency.get(r.get("agency_id", ""), "")
    print(f"rail routes: {len(routes)} across {len(set(routes.values()))} operators")

    svc = feed.active_services(args.date)
    trips = {}
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        trips[r["trip_id"]] = {"op": routes[r["route_id"]], "st": []}
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

    kept, by_op = [], collections.Counter()
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
        d = km(st[0][1], st[-1][1])
        t["cls"] = classify(t["op"], d, d / max(1, len(st) - 1))
        # No line names in this feed -- routes are "GW:RDG->GTW" -- so the
        # operator and the destination are what a hover can honestly say.
        t["name"] = t["op"]
        t["head"] = stops[st[-1][1]][2]
        by_op[t["op"]] += 1
        kept.append((t, st))
    print(f"trips inside the frame: {len(kept)}")
    for op, n in by_op.most_common():
        print(f"    {op:<26} {n}")
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
           "source": "National Rail timetable (Mobility Database mirror)",
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
