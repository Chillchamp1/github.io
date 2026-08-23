#!/usr/bin/env python3
"""One day of rail across Germany, the Benelux and Switzerland, on one map.

Usage:
    python3 build/build_eu.py <YYYYMMDD> --de <delfi> --nl <ovapi.zip> ...
                              [--es <eurostar.zip>] [-o data/eu-trains.json]

The point of this map is the border. Each national page draws its own
country and lets international trains leave the frame; here the frames are
joined, so a Zurich-Hamburg EuroCity is one dot for its whole run.

That only works because the four sources share a service date: DELFI is
valid to 13 June 2026 and the Luxembourg feed from 6 May, so Wednesday
10 June 2026 sits inside every window. No mixing of dates.

Cross-border trains appear in two feeds -- the same EuroCity is in DELFI
and in the Swiss aggregate -- so long-distance services are deduplicated
on (class, line name, first departure, origin), keeping the copy that
carries more stops. Regional line names repeat across countries ("S1"
runs in half of Europe), so only long-distance classes are ever merged.

Five classes, folded from the three national schemes:
  ice        ICE, TGV, Eurostar, EC/IC 101+102
  intercity  IC, InterRegio, Intercity
  regional   RE, RB, Sprinter, stoptrein, R, S-Bahn
  mountain   Swiss rack railways and panorama expresses
  night      NightJet, EuroNight, European Sleeper
"""
import argparse, json, os, sys, datetime, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape, active_services)
from build_gtfs import classify as classify_de
from build_nl import classify as classify_nl

CLASSES = ["ice", "intercity", "regional", "mountain", "night"]

# Swiss route types, then folded onto the shared five.
CH_BY_TYPE = {101: "ice", 102: "ice", 103: "intercity", 106: "regional",
              109: "regional", 107: "mountain", 116: "mountain", 105: "night"}
# Only these are ever deduplicated across feeds.
LONG_DISTANCE = {"ice", "intercity", "night"}


def norm(name):
    """Line names for matching: "ICE 71" and "ice71" are the same train."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def classify_ch(route):
    try:
        rt = int(route.get("route_type") or -1)
    except ValueError:
        return None, ""
    cls = CH_BY_TYPE.get(rt)
    name = (route.get("route_short_name")
            or route.get("route_long_name") or "").strip()
    return cls, name


def classify_es(route):
    """Eurostar's feed is one operator and all of it is high-speed."""
    return "ice", (route.get("route_short_name")
                   or route.get("route_long_name") or "Eurostar").strip()


def read_source(ns, path, kind, date, stops, trips):
    """Pull one feed's active trips and stops into the shared dictionaries."""
    feed = Feed(path)
    routes = {}
    for r in feed.rows("routes.txt"):
        if kind == "de":
            cls, name = classify_de(r)
        elif kind == "nl":
            cls = classify_nl(r.get("route_short_name"),
                              r.get("route_long_name"), r.get("route_type"))
            name = (r.get("route_short_name")
                    or r.get("route_long_name") or "").strip()
        elif kind == "ch":
            cls, name = classify_ch(r)
        elif kind.startswith("fr_"):
            # The French feeds are already split by service type, so which
            # file a route came from is its class. Night trains hide among
            # the Intercités under plain line numbers and are promoted later
            # by the hours they keep.
            cls = {"fr_ter": "regional", "fr_tgv": "ice",
                   "fr_ic": "intercity"}[kind] if r.get("route_type") == "2" \
                else None
            name = (r.get("route_short_name")
                    or r.get("route_long_name") or "").strip()
        else:
            cls, name = classify_es(r)
        if cls:
            routes[r["route_id"]] = (cls, name)

    svc = active_services(path, date) if kind == "de" else None
    if svc is None:
        svc = set()
        d = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:]))
        dow = ["monday","tuesday","wednesday","thursday","friday",
               "saturday","sunday"][d.weekday()]
        for r in feed.rows("calendar.txt"):
            if r.get("start_date","") <= date <= r.get("end_date","") \
               and r.get(dow) == "1":
                svc.add(r["service_id"])
        for r in feed.rows("calendar_dates.txt"):
            if r.get("date") == date:
                (svc.add if r.get("exception_type") == "1"
                 else svc.discard)(r["service_id"])

    for r in feed.rows("stops.txt"):
        try:
            lon, lat = float(r["stop_lon"]), float(r["stop_lat"])
        except (ValueError, KeyError):
            continue
        # The null-island guard that OVapi taught us, kept for every feed.
        if not (-6.0 <= lon <= 20.0 and 40.0 <= lat <= 58.0):
            continue
        if abs(lon) < 0.01 and abs(lat) < 0.01:
            continue
        stops[ns + r["stop_id"]] = (lon, lat, (r.get("stop_name") or "").strip())

    n0 = len(trips)
    for r in feed.rows("trips.txt"):
        if r.get("service_id") in svc and r.get("route_id") in routes:
            cls, name = routes[r["route_id"]]
            label = name
            if kind == "nl" and r.get("trip_short_name"):
                label = f"{name} {r['trip_short_name']}"
            trips[ns + r["trip_id"]] = {
                "cls": cls, "name": label, "src": kind,
                "head": (r.get("trip_headsign") or "").strip(), "st": [],
                "shape": ns + r["shape_id"] if r.get("shape_id") else None,
            }
    added = len(trips) - n0

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
    print(f"  {kind}: {added} trips from {os.path.basename(path)}")
    return feed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--de", required=True, help="DELFI feed (dir or zip)")
    ap.add_argument("--nl", nargs="+", required=True,
                    help="OVapi, SNCB, Luxembourg, European Sleeper")
    ap.add_argument("--ch", required=True, help="Swiss SKI+/SBB feed")
    ap.add_argument("--es", help="Eurostar international feed")
    ap.add_argument("--fr", nargs=3, metavar=("TER", "TGV", "IC"),
                    help="SNCF's three feeds; they carry a 2025 timetable "
                         "and so need their own date")
    ap.add_argument("--fr-date", help="service date for the French feeds")
    ap.add_argument("-o", "--out", default="data/eu-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="2.0,45.5,16.2,55.6")
    ap.add_argument("--shape-tol", type=float, default=300.0,
                    help="German route geometry; the combined payload is the "
                         "landing page, so it is simplified harder than the "
                         "Germany map's own 50 m")
    ap.add_argument("--no-shapes", action="store_true")
    ap.add_argument("--tmp", default="/tmp/eu-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips = {}, {}
    de_feed = read_source("d:", args.de, "de", args.date, stops, trips)
    for i, z in enumerate(args.nl):
        read_source(f"n{i}:", z, "nl", args.date, stops, trips)
    read_source("c:", args.ch, "ch", args.date, stops, trips)
    if args.es:
        read_source("e:", args.es, "es", args.date, stops, trips)
    if args.fr:
        if not args.fr_date:
            sys.exit("--fr needs --fr-date: the SNCF mirrors are a 2025 feed")
        for ns, path, kind in zip(("f0:", "f1:", "f2:"), args.fr,
                                  ("fr_ter", "fr_tgv", "fr_ic")):
            read_source(ns, path, kind, args.fr_date, stops, trips)
    print(f"candidate trips: {len(trips)}, stops: {len(stops)}")

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

    # The same international train is published by both countries it runs
    # through, and the two copies rarely agree exactly: departure minutes
    # drift by a minute or two and one feed lists stops the other skips.
    # Match on line, destination and roughly-when, then keep the fuller
    # itinerary. Only long-distance is ever merged -- regional line numbers
    # like "S1" repeat across borders and would collapse real trains.
    SLACK = 20 * 60
    seen, merged, uniq = {}, 0, []
    for t, st in kept:
        if t["cls"] in LONG_DISTANCE:
            key = (t["cls"], norm(t["name"]), norm(stops[st[-1][1]][2]))
            dep = st[0][3]
            hit = None
            for dep0, at in seen.get(key, []):
                if abs(dep0 - dep) <= SLACK:
                    hit = at
                    break
            if hit is not None:
                merged += 1
                if len(st) > len(uniq[hit][1]):
                    uniq[hit] = (t, st)
                continue
            seen.setdefault(key, []).append((dep, len(uniq)))
        uniq.append((t, st))
    print(f"cross-border duplicates merged: {merged} -> {len(uniq)} trips")

    tracks = {}
    if not args.no_shapes and args.shape_tol > 0:
        sdir = de_feed.shapes_dir(args.tmp)
        wanted = {t["shape"][2:] for t, _ in uniq
                  if t["shape"] and t["shape"].startswith("d:")}
        if sdir and wanted:
            for sid, pts in load_shapes(sdir, wanted).items():
                simp = simplify(pts, args.shape_tol)
                tracks["d:" + sid] = (simp, shape_track(simp))
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
    for t, st in uniq:
        seq = [[idx(s), a // 60, dp // 60] for _, s, a, dp in st]
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i-1][2]:
                seq[i][1] = seq[i-1][2]
            if seq[i][2] < seq[i][1]:
                seq[i][2] = seq[i][1]
        cls = t["cls"]
        # An Intercités still rolling at two in the morning is a night train,
        # whatever its line number says.
        if t["src"].startswith("fr_") and cls == "intercity" \
           and st[0][3] <= 26*3600 <= st[-1][2]:
            cls = "night"
        rec = {"c": CLASSES.index(cls), "n": t["name"],
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
    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": CLASSES, "counts": counts,
           "source": "DELFI e.V.; OVapi/NDOV, SNCB/NMBS, Luxembourg, European "
                     "Sleeper; SKI+/SBB" + ("; Eurostar" if args.es else "")
                     + ("; SNCF (TER, TGV, Intercités)" if args.fr else ""),
           "note": args.note, "stations": stations, "trips": out_trips}
    if out_shapes:
        doc["shapes"] = out_shapes
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{len(out_shapes)} shapes ({matched} on tracks), "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in CLASSES:
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
