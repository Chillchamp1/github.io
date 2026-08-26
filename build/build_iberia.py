#!/usr/bin/env python3
"""One day of Iberian rail: Renfe, FGC and CP merged onto a single date.

Usage:
    python3 build/build_iberia.py <YYYYMMDD> \\
        --renfe    renfe-av-ld-md.zip \\
        --cercanias renfe-cercanias.zip \\
        --fgc      fgc.zip \\
        --cp       cp.zip \\
        -o data/iberia-trains.json

There is no Iberian equivalent of DELFI or Rejseplanen; the peninsula's rail
arrives in four separate files with four different conventions, and two of
them are malformed in the same specific way.

**The padding.** Renfe exports both of its feeds as fixed-width text with
the field separators left in. `route_id` carries trailing spaces in
routes.txt but not in trips.txt, and the last column of every file has its
*header* padded with three hundred spaces -- so a plain csv.DictReader ends
up with a key called "end_date" followed by a paragraph of whitespace, and
`row["end_date"]` raises KeyError. Read naively, Renfe Cercanias joins zero
of its 121,941 trips to a route and the whole Madrid, Barcelona, Valencia
and Sevilla suburban network silently disappears. Every key and value is
stripped on the way in; that is the entire fix, and without it this file
would have shipped an empty map that looked plausible.

**The date.** The four feeds overlap in one narrow window -- Renfe
Cercanias is a 30-day snapshot running 3 June to 2 July 2026 -- and inside
it the traffic is not flat. 10 June is Portugal's national day and CP drops
to 868 trains; 24 June is Sant Joan and Sao Joao and FGC halves. Wednesday
3 June 2026 is the one date on which all four feeds are at or within a
hair of their maximum, which is why it is the date this map shows.

Classes are unified across the four:

  highspeed  AVE, AVLO, AVANT, Euromed, Alvia, and CP's Alfa Pendular
  intercity  Renfe Intercity and Trenceltas, CP Intercidades
  regional   Media Distancia, Regional, Regional Expres, Proximidad,
             CP InterRegional and Regional
  cercanias  Renfe Cercanias, FGC's suburban lines, CP's urban lines

FGC's Barcelona-Valles metro lines (route_type 1) and its funiculars and
the Montserrat rack railway (route_type 7) are left out, on the rule the
Swiss and Danish pages use: suburban railway yes, metro and funicular no.
"""
import argparse, csv, io, json, os, sys, datetime, zipfile, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["highspeed", "intercity", "regional", "cercanias"]

RENFE_HS = {"AVE", "AVLO", "AVE INT", "AVANT", "AVANT EXP", "EUROMED", "ALVIA"}
RENFE_IC = {"INTERCITY", "TRENCELTA", "CHARTER"}
CP_HS = {"AP"}
CP_IC = {"IC"}


class StripFeed(Feed):
    """A Feed that strips every key and value. See the module docstring:
    Renfe's two exports are fixed-width padded and join nothing without it."""

    def rows(self, name):
        for r in super().rows(name):
            yield {(k or "").strip(): (v or "").strip()
                   for k, v in r.items() if k is not None}


def renfe_class(short):
    s = short.upper()
    if s in RENFE_HS:
        return "highspeed"
    if s in RENFE_IC:
        return "intercity"
    return "regional"


def cp_class(short, rtype):
    if rtype == "109":
        return "cercanias"
    s = short.upper()
    if s in CP_HS:
        return "highspeed"
    if s in CP_IC:
        return "intercity"
    return "regional"


def collect(src, ns, date, rule, keep_types, stops, trips):
    """Read one feed into the shared stop and trip tables under prefix `ns`."""
    feed = StripFeed(src)
    for r in feed.rows("stops.txt"):
        try:
            stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                        float(r["stop_lat"]),
                                        (r.get("stop_name") or "").strip())
        except (ValueError, KeyError):
            continue

    routes = {}
    for r in feed.rows("routes.txt"):
        rt = r.get("route_type") or ""
        if rt not in keep_types:
            continue
        short = (r.get("route_short_name") or r.get("route_long_name") or "").strip()
        routes[r["route_id"]] = (rule(short, rt), short)

    svc = feed.active_services(date)
    n = 0
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        cls, short = routes[r["route_id"]]
        num = (r.get("trip_short_name") or "").strip().lstrip("0")
        trips[ns + r["trip_id"]] = {
            "cls": cls, "name": " ".join(x for x in [short, num] if x),
            "head": (r.get("trip_headsign") or "").strip(), "st": [],
            "shape": ns + r["shape_id"] if r.get("shape_id") else None,
        }
        n += 1

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

    print(f"  {os.path.basename(src)}: {len(routes)} routes, {n} trips on {date}")
    if n == 0:
        sys.exit(f"{src} contributed no trips on {date} -- wrong date, or the "
                 f"padding fix stopped working")
    return feed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--renfe", required=True, help="AV / larga / media distancia")
    ap.add_argument("--cercanias", required=True)
    ap.add_argument("--fgc", required=True)
    ap.add_argument("--cp", required=True, help="Comboios de Portugal")
    ap.add_argument("-o", "--out", default="data/iberia-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="-9.8,35.9,4.6,44.0")
    ap.add_argument("--shape-tol", type=float, default=200.0)
    ap.add_argument("--tmp", default="/tmp/iberia-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips, feeds = {}, {}, {}
    sources = [
        ("0:", args.renfe,     lambda s, rt: renfe_class(s), {"2"}),
        ("1:", args.cercanias, lambda s, rt: "cercanias",    {"2"}),
        ("2:", args.fgc,       lambda s, rt: "cercanias",    {"2"}),
        ("3:", args.cp,        cp_class,                     {"2", "109"}),
    ]
    for ns, src, rule, keep in sources:
        feeds[ns] = collect(src, ns, args.date, rule, keep, stops, trips)

    kept = []
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
        # Renfe's long-distance export carries no trip_headsign at all, so
        # the destination is taken from the last stop -- "AVE 3092" alone
        # tells a reader nothing.
        if not t["head"]:
            t["head"] = stops[st[-1][1]][2]
        kept.append((t, st))
    print(f"trips inside the frame: {len(kept)}")

    tracks = {}
    if args.shape_tol > 0:
        for ns, src, _, _ in sources:
            wanted = {t["shape"][len(ns):] for t, _ in kept
                      if t["shape"] and t["shape"].startswith(ns)}
            sdir = feeds[ns].shapes_dir(os.path.join(args.tmp, ns.rstrip(":")))
            if not (sdir and wanted):
                continue
            for sid, pts in load_shapes(sdir, wanted).items():
                tracks[ns + sid] = None
                simp = simplify(pts, args.shape_tol)
                tracks[ns + sid] = (simp, shape_track(simp))
        tracks = {k: v for k, v in tracks.items() if v}
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
           "source": "Renfe (AV/LD/MD and Cercanías), FGC, CP — Comboios de Portugal",
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
