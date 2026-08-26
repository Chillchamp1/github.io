#!/usr/bin/env python3
"""One day of Danish rail, from the national Rejseplanen aggregate.

Usage:
    python3 build/build_dk.py <gtfs.zip|dir> <YYYYMMDD> [-o data/dk-trains.json]

Rejseplanen is Denmark's single national journey planner and publishes one
GTFS covering every operator in the country -- 26 agencies, 36,799 stops,
most of it buses. What is kept here is rail: DSB's long-distance and
regional trains, GoCollective (the former Arriva Tog) across Jutland, the
eleven Lokaltog private railways on Zealand, Midttrafik's and NT's local
lines, the Öresundståg that Skanetrafiken runs across the bridge into
Sweden, Snalltaget's night trains to Stockholm and Berlin, and the
Copenhagen S-tog.

Classification is by operator and line name, since only the S-tog carries
an extended route type:

  intercity  DSB IC, ICL (Lyn), ECE (EuroCity Express to Hamburg),
             RJ (the Railjet through to Dresden and Prague)
  regional   DSB RE and every local operator, the Öresundstag included
  sbahn      DSB S-tog -- route_type 109, lines A B Bx C E F H
  night      Snalltaget

The Copenhagen metro and the Aarhus, Odense and Hovedstaden light rail are
left out, the same way the Swiss map keeps S-Bahn but drops trams and the
Lausanne metro. The metro alone would be 47,000 trips -- three times every
train in the country -- and it is not what a national rail map is about.

One quirk of the feed worth knowing about: GoCollective files thirteen
thousand Jutland train trips under a single route numbered "030", which is
not a line anybody travels on. Where a short name is a bare number like
that, the operator's name is shown instead.
"""
import argparse, json, os, sys, datetime, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["intercity", "regional", "sbahn", "night"]

INTERCITY = {"IC", "ICL", "ECE", "RJ", "EC"}
# Operators whose own name is more use than their route number.
ANONYMOUS = {"GoCollective", "Midttrafik", "NT", "Snälltåget AB"}
OPERATOR_LABEL = {"Skånetrafiken": "Öresundståg", "Snälltåget AB": "Snälltåget"}


def classify(agency, short, rtype):
    if rtype == "109":
        return "sbahn"
    if agency == "Snälltåget AB":
        return "night"
    if agency == "DSB" and short in INTERCITY:
        return "intercity"
    return "regional"


def label(agency, short):
    """A line number only where it is a line somebody can ask for."""
    if agency in OPERATOR_LABEL:
        return OPERATOR_LABEL[agency]
    if agency in ANONYMOUS and (short.isdigit() or not short):
        return agency
    return short or agency


def clean(name):
    """Every Danish station is written "Roskilde St."; the suffix is on all
    of them, so it distinguishes nothing and only costs label width."""
    n = name.strip()
    return n[:-4].strip() if n.endswith(" St.") else n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/dk-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="8.0,54.4,15.4,57.9",
                    help="a trip is kept if it calls at least once inside")
    ap.add_argument("--shape-tol", type=float, default=150.0)
    ap.add_argument("--tmp", default="/tmp/dk-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    feed = Feed(args.gtfs)

    stops = {}
    for r in feed.rows("stops.txt"):
        try:
            stops[r["stop_id"]] = (float(r["stop_lon"]), float(r["stop_lat"]),
                                   clean(r.get("stop_name") or ""))
        except (ValueError, KeyError):
            continue
    print(f"stops: {len(stops)}")

    agency = {a["agency_id"]: (a.get("agency_name") or "").strip()
              for a in feed.rows("agency.txt")}
    routes, by_op = {}, collections.Counter()
    for r in feed.rows("routes.txt"):
        rt = (r.get("route_type") or "")
        if rt not in ("2", "109"):        # 1 = metro, 0 = light rail, 3 = bus
            continue
        ag = agency.get(r.get("agency_id", ""), "")
        short = (r.get("route_short_name") or "").strip()
        routes[r["route_id"]] = (classify(ag, short, rt), label(ag, short))
        by_op[ag] += 1
    print(f"rail routes: {len(routes)} across {len(by_op)} operators")

    svc = feed.active_services(args.date)
    print(f"services active on {args.date}: {len(svc)}")

    trips = {}
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        cls, name = routes[r["route_id"]]
        trips[r["trip_id"]] = {
            "cls": cls, "name": name,
            "head": clean(r.get("trip_headsign") or ""), "st": [],
            "shape": r.get("shape_id") or None,
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
        kept.append((t, st))
    print(f"trips inside the frame: {len(kept)}")
    if not kept:
        sys.exit(f"no trips on {args.date} -- wrong date for this feed?")

    tracks = {}
    if args.shape_tol > 0:
        sdir = feed.shapes_dir(args.tmp)
        wanted = {t["shape"] for t, _ in kept if t["shape"]}
        if sdir and wanted:
            for sid, pts in load_shapes(sdir, wanted).items():
                simp = simplify(pts, args.shape_tol)
                tracks[sid] = (simp, shape_track(simp))
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
    doc = {"tunit": "min", "date": d.isoformat(), "weekday": d.strftime("%A"),
           "classes": live, "counts": counts,
           "source": "Rejseplanen (Danish national aggregate)",
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
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
