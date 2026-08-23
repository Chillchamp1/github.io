#!/usr/bin/env python3
"""One day of London's rail transit, from the UK Bus Open Data Service.

Usage:
    python3 build/build_london.py <bods.zip> <YYYYMMDD> [-o data/london-trains.json]

BODS is Britain's national aggregate. Despite the name it carries the
Underground, the DLR and Tramlink alongside the buses, and it is the only
*current* open GTFS that does.

National Rail is a second feed and a second date. Its timetable is
published through Rail Delivery Group channels that need registration; the
newest openly mirrored copy is an ATOC-derived snapshot whose calendar
runs out in July 2021. Passing --nr adds those operators -- Overground,
Thameslink, Southeastern, Southern, South Western, Greater Anglia,
Crossrail, c2c, Chiltern, the airport expresses and the intercity
operators calling at the London termini -- drawn from their 2021 weekday
timetable against the current Underground. The mixed date is stated on
the page, in the legend and in the data notes, because a viewer cannot be
expected to infer it.

Four classes, picked by operator rather than by bbox so that the Tyne and
Wear Metro and the other British tramways in the same files stay out:
  nr    National Rail (2021 timetable)
  tube  London Underground
  dlr   Docklands Light Railway
  tram  London Tramlink
"""
import argparse, json, os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["nr", "tube", "dlr", "tram"]
BY_AGENCY = {
    "London Underground (TfL)": "tube",
    "London Docklands Light Railway - TfL": "dlr",
    "London Tramlink": "tram",
}
# The National Rail feed carries the Underground and the Tyne and Wear Metro
# too; both are covered better elsewhere or belong to another city.
NR_SKIP = {"London Underground", "Nexus (Tyne & Wear Metro)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/london-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-0.62,51.25,0.34,51.72")
    ap.add_argument("--shape-tol", type=float, default=20.0)
    ap.add_argument("--tmp", default="/tmp/london-shapes")
    ap.add_argument("--nr", help="National Rail GTFS (ATOC-derived snapshot)")
    ap.add_argument("--nr-date", help="service date inside the NR feed's own "
                                      "validity window, YYYYMMDD")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips = {}, {}
    sources = [("b:", args.gtfs, args.date, False)]
    if args.nr:
        if not args.nr_date:
            sys.exit("--nr needs --nr-date: the NR snapshot has its own window")
        sources.append(("n:", args.nr, args.nr_date, True))

    for ns, path, date, is_nr in sources:
        feed = Feed(path)
        agencies = {a["agency_id"]: (a.get("agency_name") or "").strip()
                    for a in feed.rows("agency.txt")}
        routes = {}
        for r in feed.rows("routes.txt"):
            name = agencies.get(r.get("agency_id"), "")
            if is_nr:
                # Heavy rail only: the same file carries coaches, ferries and
                # rail-replacement buses under their operators' names.
                cls = ("nr" if r.get("route_type") == "2"
                       and name not in NR_SKIP else None)
            else:
                cls = BY_AGENCY.get(name)
            if cls:
                routes[r["route_id"]] = (
                    cls, (r.get("route_short_name")
                          or r.get("route_long_name") or name).strip())

        svc = feed.active_services(date)
        n0 = len(trips)
        for r in feed.rows("trips.txt"):
            if r.get("service_id") in svc and r.get("route_id") in routes:
                cls, name = routes[r["route_id"]]
                trips[ns + r["trip_id"]] = {
                    "cls": cls, "name": name,
                    "head": (r.get("trip_headsign") or "").strip(), "st": [],
                    "shape": ns + r["shape_id"] if r.get("shape_id") else None,
                }
        print(f"  {os.path.basename(path)} on {date}: "
              f"{len(svc)} services, {len(trips)-n0} trips")

        for r in feed.rows("stops.txt"):
            try:
                stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                            float(r["stop_lat"]),
                                            (r.get("stop_name") or "").strip())
            except (ValueError, KeyError):
                continue

        for r in feed.rows("stop_times.txt"):
            t = trips.get(ns + r.get("trip_id", ""))
            if t is None or ns + r.get("stop_id", "") not in stops:
                continue
            a, dp = hhmmss(r.get("arrival_time") or ""), hhmmss(
                r.get("departure_time") or "")
            if a is None and dp is None:
                continue
            a = a if a is not None else dp
            dp = dp if dp is not None else a
            t["st"].append((int(r["stop_sequence"]), ns + r["stop_id"], a, dp))

    print(f"candidate trips: {len(trips)}, stops: {len(stops)}")
    if not trips:
        sys.exit("no trips on that date")

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

    # Neither source publishes shapes for these operators -- BODS leaves
    # shape_id empty on the rail trips and the NR snapshot has no shapes.txt
    # at all -- so London's trains run straight between stations.
    tracks = {}

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
    src = "Bus Open Data Service (BODS), Department for Transport"
    if args.nr:
        nd = args.nr_date
        src += f"; National Rail (ATOC snapshot, {nd[:4]}-{nd[4:6]}-{nd[6:]})"
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": live, "counts": counts, "source": src,
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
        print(f"  {c:<6} {counts[c]}")


if __name__ == "__main__":
    main()
