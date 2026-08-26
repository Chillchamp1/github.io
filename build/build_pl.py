#!/usr/bin/env python3
"""One day of Polish rail, from the national aggregate of all thirteen operators.

Usage:
    python3 build/build_pl.py <gtfs.zip|dir> <YYYYMMDD> [-o data/pl-trains.json]

Poland has no single state-published GTFS the way Germany has DELFI. What it
has is better than it sounds: PKP PLK, the infrastructure manager, publishes
the national train register, and Mikolaj Kuranowski merges it with every
operator's own feed into one file covering PKP Intercity, PolRegio, all six
voivodeship railways, Arriva, Lodzka Kolej Aglomeracyjna, both SKM suburban
operators, and the two Czech open-access carriers. Thirteen agencies, one
service date, with route geometry.

Classification does not go by operator or by line name, because in Poland
neither is reliable -- Koleje Slaskie brands its regional lines S1, S4, S5
exactly like a suburban railway, and PolRegio runs both stopping and
express services under one route. It goes by `plk_category_code`, the
official PKP PLK train category the feed carries per trip:

  express    EIP (Pendolino), EIC, Ex        -- the premium long-distance brands
  intercity  IC, EC, TLK, ICN, MP, IC+
  regional   Os, R, RE, RP, OsP and every voivodeship railway's own codes
  night      EN                              -- EuroNight
  sbahn      SKM Warszawa, PKP SKM Trojmiasto -- classified by operator, since
             these two genuinely are urban railways and their category codes
             (S1, S4) collide with Koleje Slaskie's regional branding

A trip whose category changes en route carries a combined code -- "EC/IC",
"EN/IC", "BUS/R" -- so the code is split and the highest-ranking token wins:
a train that is a EuroNight for part of its run is a night train.

Rail replacement buses (route_type 3, category ZKA/BUS) are dropped, the same
way the German page drops SEV.
"""
import argparse, json, os, sys, datetime, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["express", "intercity", "regional", "sbahn", "night"]

SKM_AGENCIES = {"SKM Warszawa", "PKP SKM Trójmiasto"}
EXPRESS = {"EIP", "EIC", "Ex"}
INTERCITY = {"IC", "EC", "TLK", "ICN", "MP", "IC+"}


def classify(cat, agency):
    """Category code first, operator only where the code cannot decide."""
    if agency in SKM_AGENCIES:
        return "sbahn"
    toks = [t for t in cat.replace(" ", "/").split("/") if t]
    if not toks:
        return "regional"
    if all(t == "BUS" for t in toks):
        return None
    if "EN" in toks:
        return "night"
    if any(t in EXPRESS for t in toks):
        return "express"
    if any(t in INTERCITY for t in toks):
        return "intercity"
    return "regional"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs")
    ap.add_argument("date")
    ap.add_argument("-o", "--out", default="data/pl-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="14.0,48.9,24.3,54.9",
                    help="a trip is kept if it calls at least once inside")
    ap.add_argument("--shape-tol", type=float, default=200.0)
    ap.add_argument("--tmp", default="/tmp/pl-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    feed = Feed(args.gtfs)

    stops = {}
    for r in feed.rows("stops.txt"):
        try:
            stops[r["stop_id"]] = (float(r["stop_lon"]), float(r["stop_lat"]),
                                   (r.get("stop_name") or "").strip())
        except (ValueError, KeyError):
            continue
    print(f"stops: {len(stops)}")

    agency = {a["agency_id"]: (a.get("agency_name") or "").strip()
              for a in feed.rows("agency.txt")}
    routes = {}
    for r in feed.rows("routes.txt"):
        if (r.get("route_type") or "") != "2":     # 3 = rail replacement bus
            continue
        routes[r["route_id"]] = (
            agency.get(r.get("agency_id", ""), ""),
            (r.get("route_short_name") or r.get("route_long_name") or "").strip())
    print(f"rail routes: {len(routes)}")

    svc = feed.active_services(args.date)
    print(f"services active on {args.date}: {len(svc)}")

    trips, by_cat = {}, collections.Counter()
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        ag, line = routes[r["route_id"]]
        cat = (r.get("plk_category_code") or "").strip()
        cls = classify(cat, ag)
        if cls is None:
            continue
        by_cat[cat or "(none)"] += 1
        # The train number is what a Polish traveller reads off the board;
        # PLK also names a good third of them ("LATARNIK", "MAZOWSZE").
        num = (r.get("plk_train_number") or "").strip()
        name = (r.get("plk_train_name") or "").strip().title()
        label = " ".join(x for x in [cat.split("/")[0] or line, num] if x)
        if name:
            label += f" “{name}”"
        trips[r["trip_id"]] = {
            "cls": cls, "name": label or line,
            "head": (r.get("trip_headsign") or "").strip(), "st": [],
            "shape": r.get("shape_id") or None,
        }
    print(f"candidate trips: {len(trips)}")
    print("  top categories:", by_cat.most_common(8))

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
           "source": "PKP PLK via mkuran.pl/gtfs (Polish Trains aggregate)",
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
