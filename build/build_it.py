#!/usr/bin/env python3
"""One day of the Italian rail that is actually published as open data.

Usage:
    python3 build/build_it.py <YYYYMMDD> \\
        --trenord trenord.zip --toscana tuscany.zip \\
        --sardegna trenitalia-sardegna.zip --arst arst.zip \\
        --trentino trentino.zip --genova amt-genova.zip \\
        -o data/it-trains.json

This page is smaller than Italy, and the reason is the point of it.

Italy has no national open timetable. Trenitalia -- which runs almost all
of the country's long-distance and most of its regional service -- does not
publish one, and the Mobility Database's only entry filed under "Trenitalia"
covers Sardinia: two lines and 41 stations. Every Frecciarossa, every
Intercity, and the regional networks of Lazio, Campania, Veneto, Piedmont,
Puglia and Sicily are simply absent from open data. What exists is a
handful of regional contracts that happen to publish, and this merges all
of them that carry rail:

  Trenord          Lombardy, the largest by far -- Milan's S-lines, the
                   RE trunk routes and the R branches
  Trenitalia Tosc. Tuscany and the Ligurian/Emilian edges: Firenze-Pisa,
                   Firenze-Arezzo, La Spezia-Parma, Firenze-Siena. The
                   catalogue files this one under "Marche", which is wrong;
                   its routes are unambiguously Tuscan.
  Trenitalia Sard. the Sardinian standard-gauge line
  ARST             the Sardinian narrow gauge -- Sassari-Alghero,
                   Monserrato-Mandas-Isili, Macomer-Nuoro
  Trentino Trasp.  the Trento-Male-Mezzana narrow gauge and the Valsugana
  AMT Genova       the Genova-Casella narrow gauge

Together: about 3,600 trains, against a real Italian figure several times
that. A reader looking at the finished map sees Lombardy lit up, a stripe
across Tuscany and specks in Sardinia -- which is not a picture of Italian
railways but a picture of Italian open data, and the page says so in as
many words.

The date is forced: AMT Genova's feed covers one week, 1-8 June 2026, and
Wednesday 3 June is the only Wednesday in it. Every other feed here covers
that date too.
"""
import argparse, json, os, sys, datetime, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["express", "regional", "suburban", "narrow"]

S_LINE = re.compile(r"^S\d")
RE_LINE = re.compile(r"^RE\d")


def trenord(short, long_):
    """Lombardy's own three tiers, which the short name states outright."""
    if S_LINE.match(short):
        return "suburban"
    if RE_LINE.match(short) or "malpensa" in (short + long_).lower():
        return "express"
    return "regional"


def trentino(short, long_):
    """R35 is the Trento-Male metre-gauge line; R25 is Trenitalia's
    standard-gauge Valsugana service running under a Trentino route id."""
    return "narrow" if short.upper().startswith("R35") else "regional"


def collect(src, ns, date, rule, stops, trips, label_from):
    feed = Feed(src)
    for r in feed.rows("stops.txt"):
        try:
            stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                        float(r["stop_lat"]),
                                        (r.get("stop_name") or "").strip())
        except (ValueError, KeyError):
            continue

    routes = {}
    for r in feed.rows("routes.txt"):
        if (r.get("route_type") or "") != "2":
            continue
        short = (r.get("route_short_name") or "").strip()
        long_ = (r.get("route_long_name") or "").strip()
        routes[r["route_id"]] = (rule(short, long_), short, long_)

    svc = feed.active_services(date)
    n = 0
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        cls, short, long_ = routes[r["route_id"]]
        num = (r.get("trip_short_name") or "").strip()
        # Tuscany's routes have no short name at all, only a corridor as the
        # long name, so there the train number carries the identity.
        name = short or (label_from + " " + num if num else label_from)
        if short and num:
            name = f"{short} {num}"
        trips[ns + r["trip_id"]] = {
            "cls": cls, "name": name,
            "head": (r.get("trip_headsign") or "").strip() or long_,
            "st": [], "shape": ns + r["shape_id"] if r.get("shape_id") else None,
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

    print(f"  {os.path.basename(src)}: {len(routes)} rail routes, {n} trips")
    if n == 0:
        sys.exit(f"{src} contributed no trips on {date}")
    return feed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    for k in ("trenord", "toscana", "sardegna", "arst", "trentino"):
        ap.add_argument("--" + k, required=True)
    # Genova's feed covers a single week, 1-8 June 2026. On its own date it
    # belongs on the map; on any other -- the combined European map runs a
    # week later, so that every other country can share one Wednesday -- it
    # is simply absent, and eighteen trains are the right thing to lose.
    ap.add_argument("--genova")
    ap.add_argument("-o", "--out", default="data/it-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="6.4,36.5,18.7,47.2")
    ap.add_argument("--shape-tol", type=float, default=200.0)
    ap.add_argument("--tmp", default="/tmp/it-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips, feeds = {}, {}, {}
    sources = [
        ("0:", args.trenord,  trenord,                      "Trenord"),
        ("1:", args.toscana,  lambda s, l: "regional",      "R"),
        ("2:", args.sardegna, lambda s, l: "regional",      "R"),
        ("3:", args.arst,     lambda s, l: "narrow",        "ARST"),
        ("4:", args.trentino, trentino,                     "R"),
        ("5:", args.genova,   lambda s, l: "narrow",        "Genova–Casella"),
    ]
    sources = [x for x in sources if x[1]]
    for ns, src, rule, lab in sources:
        feeds[ns] = collect(src, ns, args.date, rule, stops, trips, lab)

    kept = []
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon
                   and minlat <= stops[s][1] <= maxlat for _, s, _, _ in st):
            continue
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
                simp = simplify(pts, args.shape_tol)
                tracks[ns + sid] = (simp, shape_track(simp))
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
           "source": "Trenord; Trenitalia (Toscana, Sardegna); ARST; "
                     "Trentino trasporti; AMT Genova",
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
