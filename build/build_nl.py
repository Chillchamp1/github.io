#!/usr/bin/env python3
"""One day of Benelux rail: the OVapi national GTFS for the Netherlands,
SNCB/NMBS for Belgium, the Luxembourg national feed for CFL, and European
Sleeper's own feed.

Usage:
    python3 build/build_nl.py <ovapi.zip> <es.zip> <YYYYMMDD> [-o data/nl-trains.json]

OVapi aggregates every operator in the Netherlands; route_short_name
carries the service type in plain words, so classification needs no
regex acrobatics:
  ice        ICE, Eurostar, Intercity direct, EuroCity (international &
             high-speed)
  intercity  Intercity
  regional   Sprinter, Stoptrein, Sneltrein
  night      Nightjet, and European Sleeper from its own feed
Metro, tram, bus and ferries are dropped. A trip is kept if it calls in
the Netherlands at least once, so the ICE to Frankfurt and the sleeper
to Praha draw their way off the frame.
"""
import argparse, csv, io, json, os, sys, datetime, zipfile

CLASSES = ["ice", "intercity", "regional", "night"]

def classify(short, long, rtype):
    if rtype == "105":
        return "night"
    # SNCB uses 100/101/103 for rail; OVapi and CFL plain 2. Buses (3, 700)
    # and everything urban fall through to None.
    if rtype not in ("2", "100", "101", "103"):
        return None
    s = (short or long or "").lower()
    if s.startswith(("nightjet", "european sleeper", "nachttrein", "nj ")):
        return "night"
    if s.startswith(("ice", "eurostar", "eur", "est", "intercity direct",
                     "eurocity", "ec ", "thalys", "tha", "tgv", "govolta")):
        return "ice"
    if s.startswith(("intercity", "ic")):
        return "intercity"
    if s.startswith(("sprinter", "stoptrein", "sneltrein",
                     "l", "s", "p", "t", "re", "rb", "ter", "exp", "ext", "trn")):
        return "regional"
    return "regional"          # unnamed rail in a national feed: local

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
    ap.add_argument("zips", nargs="+")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/nl-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="3.30,50.70,7.30,53.60")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))
    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    dow = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][d.weekday()]

    stops, trips = {}, {}
    for fi, zpath in enumerate(args.zips):
        Z = zipfile.ZipFile(zpath)
        ns = f"{fi}:"
        active = set()
        for r in rows(Z, "calendar.txt"):
            if r.get("start_date","") <= args.date <= r.get("end_date","") \
               and r.get(dow) == "1":
                active.add(r["service_id"])
        for r in rows(Z, "calendar_dates.txt"):
            if r.get("date") == args.date:
                (active.add if r.get("exception_type") == "1"
                 else active.discard)(r["service_id"])

        routes = {}
        for r in rows(Z, "routes.txt"):
            cls = classify(r.get("route_short_name"), r.get("route_long_name"),
                           r.get("route_type"))
            if cls:
                name = r.get("route_short_name") or r.get("route_long_name") or ""
                routes[r["route_id"]] = (cls, name.split(" RS")[0].split(" RE")[0])

        for r in rows(Z, "stops.txt"):
            try:
                stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                            float(r["stop_lat"]), r["stop_name"])
            except (ValueError, KeyError):
                continue

        feed_trips = 0
        for r in rows(Z, "trips.txt"):
            if r.get("service_id") in active and r.get("route_id") in routes:
                cls, name = routes[r["route_id"]]
                label = name
                if r.get("trip_short_name"):
                    label = f"{name} {r['trip_short_name']}"
                trips[ns + r["trip_id"]] = {"cls": cls, "name": label,
                                            "head": r.get("trip_headsign",""),
                                            "st": []}
                feed_trips += 1
        for r in rows(Z, "stop_times.txt"):
            t = trips.get(ns + r.get("trip_id",""))
            if t is None or ns + r.get("stop_id","") not in stops:
                continue
            a, dp = hhmmss(r.get("arrival_time","")), hhmmss(r.get("departure_time",""))
            if a is None and dp is None:
                continue
            a = a if a is not None else dp
            dp = dp if dp is not None else a
            t["st"].append((int(r["stop_sequence"]), ns + r["stop_id"], a, dp))
        print(f"  {os.path.basename(zpath)[:50]:52} {feed_trips:6} active rail trips")

    used, order, coord_key = {}, [], {}
    def idx(sid):
        if sid in used: return used[sid]
        lon, lat, name = stops[sid]
        key = (name, round(lon, 3), round(lat, 3))
        if key in coord_key: used[sid] = coord_key[key]
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
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": CLASSES, "counts": counts,
           "source": "OVapi / NDOV national GTFS; European Sleeper",
           "note": args.note, "stations": stations, "trips": out_trips}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in CLASSES:
        print(f"  {c:10} {counts[c]}")

if __name__ == "__main__":
    main()
