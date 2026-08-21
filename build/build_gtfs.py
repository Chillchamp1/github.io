#!/usr/bin/env python3
"""Turn a GTFS feed into the compact JSON the animation consumes.

Usage:
    python3 build/build_gtfs.py <gtfs-dir> <YYYYMMDD> [-o data/trains.json]

The feed must contain agency/routes/trips/stops/stop_times plus calendar.txt
and/or calendar_dates.txt. Only rail is kept; buses and urban transit
(S-Bahn, U-Bahn, tram) are dropped -- see CLASSES and DROP below.
"""
import argparse, csv, json, os, sys, datetime, math, re

# Ordered: first pattern that matches a route's name wins.
CLASSES = [
    ("ice",      r"^(ICE|ECE|TGV|RJX?)\b"),
    ("intercity",r"^(IC|EC|D)\b"),
    ("regional", r"^(RE|RB|IRE|IR|MEX|DZ|ALX|BRB|ERB|EVB|HLB|NWB|ODEG|VIA|WFB)\b"),
    ("night",    r"^(NJ|EN|DN|CNL)\b"),
]
DROP = re.compile(r"^(S|U|STR|Bus|Str|Tram|SEV)\b", re.I)

# GTFS route_type values that are urban transit, dropped regardless of name.
DROP_TYPES = {0, 1, 3, 4, 5, 6, 7, 11, 12}


def read(path, name):
    fp = os.path.join(path, name)
    if not os.path.exists(fp):
        return []
    with open(fp, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def classify(route):
    name = (route.get("route_short_name") or route.get("route_long_name") or "").strip()
    if not name or DROP.match(name):
        return None, name
    try:
        if int(route.get("route_type") or 2) in DROP_TYPES:
            return None, name
    except ValueError:
        pass
    for cls, pat in CLASSES:
        if re.match(pat, name):
            return cls, name
    return None, name


def hhmmss(v):
    """GTFS times may exceed 24h for trips running past midnight."""
    try:
        h, m, s = (int(x) for x in v.split(":"))
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def active_services(path, date):
    """service_ids running on `date`, honouring calendar + calendar_dates."""
    d = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:]))
    dow = ["monday", "tuesday", "wednesday", "thursday", "friday",
           "saturday", "sunday"][d.weekday()]
    active = set()
    for r in read(path, "calendar.txt"):
        if r["start_date"] <= date <= r["end_date"] and r.get(dow) == "1":
            active.add(r["service_id"])
    for r in read(path, "calendar_dates.txt"):
        if r["date"] != date:
            continue
        if r["exception_type"] == "1":
            active.add(r["service_id"])
        elif r["exception_type"] == "2":
            active.discard(r["service_id"])
    return active


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date", help="service date, YYYYMMDD")
    ap.add_argument("-o", "--out", default="data/trains.json")
    ap.add_argument("--bbox", default="5.2,46.9,15.9,55.4",
                    help="minLon,minLat,maxLon,maxLat -- a trip is kept if it "
                         "calls at least once inside this box")
    args = ap.parse_args()

    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))
    src = args.gtfs

    stops = {}
    for r in read(src, "stops.txt"):
        try:
            stops[r["stop_id"]] = (float(r["stop_lon"]), float(r["stop_lat"]),
                                   r["stop_name"].strip())
        except (ValueError, KeyError):
            continue

    routes = {}
    for r in read(src, "routes.txt"):
        cls, name = classify(r)
        if cls:
            routes[r["route_id"]] = (cls, name)

    services = active_services(src, args.date)
    trips = {}
    for r in read(src, "trips.txt"):
        if r["service_id"] in services and r["route_id"] in routes:
            cls, name = routes[r["route_id"]]
            trips[r["trip_id"]] = {
                "cls": cls, "name": name,
                "head": (r.get("trip_headsign") or "").strip(), "st": [],
            }

    for r in read(src, "stop_times.txt"):
        t = trips.get(r["trip_id"])
        if t is None or r["stop_id"] not in stops:
            continue
        arr = hhmmss(r.get("arrival_time") or "")
        dep = hhmmss(r.get("departure_time") or "")
        if arr is None and dep is None:
            continue
        arr = arr if arr is not None else dep
        dep = dep if dep is not None else arr
        t["st"].append((int(r["stop_sequence"]), r["stop_id"], arr, dep))

    # Assemble, keeping only trips that actually touch the bbox.
    used, order = {}, []

    def idx(sid):
        if sid not in used:
            used[sid] = len(order)
            order.append(sid)
        return used[sid]

    classes = [c for c, _ in CLASSES]
    out_trips, counts = [], {c: 0 for c in classes}
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon and minlat <= stops[s][1] <= maxlat
                   for _, s, _, _ in st):
            continue
        seq = [[idx(s), a, d] for _, s, a, d in st]
        # Times must be non-decreasing for interpolation to behave.
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i - 1][2]:
                seq[i][1] = seq[i - 1][2]
            if seq[i][2] < seq[i][1]:
                seq[i][2] = seq[i][1]
        out_trips.append({"c": classes.index(t["cls"]), "n": t["name"],
                          "h": t["head"], "s": seq})
        counts[t["cls"]] += 1

    stations = [[round(stops[s][0], 4), round(stops[s][1], 4), stops[s][2]]
                for s in order]

    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    feed = (read(src, "feed_info.txt") or [{}])[0]
    doc = {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "classes": classes,
        "counts": counts,
        "source": feed.get("feed_publisher_name", os.path.basename(os.path.abspath(src))),
        "stations": stations,
        "trips": out_trips,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)

    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in classes:
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
