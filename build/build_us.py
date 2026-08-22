#!/usr/bin/env python3
"""Assemble one service day of US passenger rail from many GTFS feeds.

Usage:
    python3 build/build_us.py <feeds-dir> <YYYYMMDD> [-o data/us-trains.json]

Differences from the German builder (build_gtfs.py):
- one feed per operator, so category comes from the feed and Amtrak's own
  taxonomy, not from route-name regexes;
- the US spans four time zones, so every feed's times are shifted to
  Eastern using its agency_timezone -- the page shows one clock;
- only route_type 2 (mainline rail) is kept anywhere: light rail, subways,
  streetcars and buses inside the commuter feeds are dropped.
"""
import argparse, csv, io, json, os, sys, datetime, zipfile
from zoneinfo import ZoneInfo

# filename fragment -> (category or "amtrak" for per-route taxonomy)
FEEDS = {
    "amtrak-gtfs-11":              "amtrak",
    "brightline":                  "intercity",
    "metra-gtfs-2854":             "regional",
    "long-island-rail-road-gtfs-507": "regional",
    "metro-north-railroad-mnr":    "regional",
    "nj-transit-gtfs-509":         "regional",
    "southeastern-pennsylvania":   "regional",
    "massachusetts-bay":           "regional",
    "caltrain":                    "regional",
    "north-county-transit-district-nctd-gtfs-14": "regional",
    "sound-transit-gtfs-268":      "regional",
    "maryland-transit-administration-gtfs-468": "regional",
    "hartford-line":               "regional",
    "sunrail":                     "regional",
    "south-shore-line":            "regional",
    "sonoma-marin":                "regional",
    "utah-transit-authority-uta-gtfs-170": "regional",
    "dallas-area-rapid-transit":   "regional",
    "regional-transportation-district-rtd-gtfs-178": "regional",
    "trimet":                      "regional",
    "nashville":                   "regional",
}

# Amtrak's overnight long-distance network, by route_long_name.
AMTRAK_NIGHT = {
    "Auto Train", "California Zephyr", "Cardinal", "Coast Starlight",
    "Crescent", "Empire Builder", "Lake Shore Limited", "Silver Meteor",
    "Silver Star", "Floridian", "Southwest Chief", "Sunset Limited",
    "Texas Eagle", "City of New Orleans", "Capitol Limited",
}

CLASSES = ["ice", "intercity", "regional", "night"]


def rows(Z, name):
    try:
        with Z.open(name) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                yield {(k or "").strip(): (v or "").strip() for k, v in r.items()}
    except KeyError:
        return


def hhmmss(v):
    try:
        h, m, s = (int(x) for x in v.split(":"))
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feeds_dir")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/us-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-125.5,24.2,-66.4,49.8")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))
    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    dow = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][d.weekday()]
    noon = datetime.datetime(d.year, d.month, d.day, 12)
    et_off = noon.replace(tzinfo=ZoneInfo("America/New_York")).utcoffset()

    zips = sorted(os.listdir(args.feeds_dir))
    stops, trips = {}, {}
    for frag, mode in FEEDS.items():
        match = [z for z in zips if frag in z and z.endswith(".zip")]
        if len(match) != 1:
            sys.exit(f"feed fragment {frag!r} matched {match!r}")
        Z = zipfile.ZipFile(os.path.join(args.feeds_dir, match[0]))
        ns = frag + ":"

        ag = list(rows(Z, "agency.txt"))
        tzname = ag[0].get("agency_timezone") or "America/New_York"
        loc_off = noon.replace(tzinfo=ZoneInfo(tzname)).utcoffset()
        shift = int((et_off - loc_off).total_seconds())   # add to local secs

        for r in rows(Z, "stops.txt"):
            try:
                stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                            float(r["stop_lat"]),
                                            r["stop_name"])
            except (ValueError, KeyError):
                continue

        routes = {}
        for r in rows(Z, "routes.txt"):
            if r.get("route_type") != "2":
                continue
            long = r.get("route_long_name", "")
            short = r.get("route_short_name", "")
            if mode == "amtrak":
                if "Acela" in long or "Acela" in short:
                    cls = "ice"
                elif long in AMTRAK_NIGHT:
                    cls = "night"
                else:
                    cls = "intercity"
            else:
                cls = mode
            routes[r["route_id"]] = (cls, short or long)

        active = set()
        for r in rows(Z, "calendar.txt"):
            if r.get("start_date","") <= args.date <= r.get("end_date","") \
               and r.get(dow) == "1":
                active.add(r["service_id"])
        for r in rows(Z, "calendar_dates.txt"):
            if r.get("date") == args.date:
                (active.add if r.get("exception_type") == "1"
                 else active.discard)(r["service_id"])

        feed_trips = 0
        for r in rows(Z, "trips.txt"):
            if r.get("service_id") in active and r.get("route_id") in routes:
                cls, name = routes[r["route_id"]]
                label = name
                if mode == "amtrak" and r.get("trip_short_name"):
                    label = f"{name} {r['trip_short_name']}"
                trips[ns + r["trip_id"]] = {
                    "cls": cls, "name": label,
                    "head": r.get("trip_headsign",""), "st": [], "shift": shift,
                }
                feed_trips += 1

        for r in rows(Z, "stop_times.txt"):
            t = trips.get(ns + r.get("trip_id",""))
            if t is None or ns + r.get("stop_id","") not in stops:
                continue
            arr, dep = hhmmss(r.get("arrival_time","")), hhmmss(r.get("departure_time",""))
            if arr is None and dep is None:
                continue
            arr = arr if arr is not None else dep
            dep = dep if dep is not None else arr
            t["st"].append((int(r["stop_sequence"]), ns + r["stop_id"],
                            arr + t["shift"], dep + t["shift"]))
        print(f"  {match[0][:58]:60} {feed_trips:5} trips  shift {shift//3600:+d}h")

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
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon and minlat <= stops[s][1] <= maxlat
                   for _, s, _, _ in st):
            continue
        seq = [[idx(s), a // 60, dp // 60] for _, s, a, dp in st]
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i-1][2]: seq[i][1] = seq[i-1][2]
            if seq[i][2] < seq[i][1]:   seq[i][2] = seq[i][1]
        out_trips.append({"c": CLASSES.index(t["cls"]), "n": t["name"],
                          "h": t["head"], "s": seq})
        counts[t["cls"]] += 1

    stations = [[round(stops[s][0], 4), round(stops[s][1], 4), stops[s][2]]
                for s in order]
    doc = {
        "tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
        "classes": CLASSES, "counts": counts,
        "source": "Amtrak and 20 commuter rail agencies via the Mobility Database",
        "note": args.note, "stations": stations, "trips": out_trips,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in CLASSES:
        print(f"  {c:10} {counts[c]}")

if __name__ == "__main__":
    main()
