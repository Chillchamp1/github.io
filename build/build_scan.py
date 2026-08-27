#!/usr/bin/env python3
"""One day of Swedish and Norwegian rail on a single date.

Usage:
    python3 build/build_scan.py <YYYYMMDD> \\
        --se trafiklab-gtfs-sverige-2.zip --no entur-aggregated.zip \\
        [-o data/scan-trains.json]

Two national aggregates, both current, drawn together because the railway
is: Öresundståg runs Copenhagen–Malmö–Göteborg, SJ runs Stockholm–Oslo, and
the night trains cross both borders. Denmark is a page of its own and joins
them on the combined European map.

The two feeds classify in completely different ways, and each is taken at
its own word.

**Sweden** uses the extended GTFS route types properly, so the tier is
simply read off: 101 high speed, 102 long distance, 106 regional. Two
operators are moved out of the type their file gives them, because the type
is about the vehicle and this map is about the journey -- Arlanda Express
is filed as high speed but is a 37 km airport shuttle, and Snälltåget's
620 km Malmö–Stockholm run is a night train. SL's Stockholm pendeltåg,
filed regional, stops every 2.1 km and is drawn as suburban with every
other commuter railway here. The Stockholm tunnelbana is route type 401 and
stays out, on the rule the whole atlas uses: suburban railway yes, metro no.

**Norway** puts everything under type 100 and states the tier in the line
code instead -- F fjerntog, RE regionekspress, R regiontog, L lokaltog,
FLY the Gardermoen airport express -- with type 105 for the sleepers.
Measured on Wednesday 10 June 2026, F runs 363 km with 26 km between stops
and L runs 25 km with 1.5 km, so the codes mean what they say.

RE and RX are drawn as regional rather than intercity, the same decision
the Austrian page makes about REX: a regional express is a regional train
with fewer stops, and promoting it would invent a long-distance network.

Sweden ships no route geometry and Norway does, so Norwegian trains follow
the track and Swedish ones interpolate between stops.

Öresundståg, Snälltåget and SJ's Oslo trains appear in both files, under
different numbers -- Oslo–Göteborg is "393" to Trafiklab and "RE20" to
Entur. They are merged on where they start and end and when, not on what
they are called, because the names disagree by construction.
"""
import argparse, json, os, sys, datetime, re, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gtfs import (Feed, hhmmss, load_shapes, simplify, shape_track,
                        stop_fracs, enc_shape)

CLASSES = ["highspeed", "intercity", "regional", "suburban", "night"]
LONG_DISTANCE = {"highspeed", "intercity", "night"}
RAIL = {"2"} | {str(x) for x in range(100, 118)}

SE_BY_TYPE = {"101": "highspeed", "102": "intercity", "103": "intercity",
              "106": "regional", "105": "night", "100": "regional"}
SE_BY_AGENCY = {"Arlanda Express": "suburban", "SL": "suburban",
                "Snälltåget": "night", "Snälltåget AB": "night"}

NO_BY_PREFIX = {"F": "intercity", "RE": "regional", "RX": "regional",
                "R": "regional", "L": "suburban", "FLY": "suburban"}
NO_BY_AGENCY = {"Snälltåget": "night"}


def se_class(rtype, agency):
    return SE_BY_AGENCY.get(agency) or SE_BY_TYPE.get(rtype, "regional")


def no_class(rtype, agency, short):
    if rtype == "105":
        return "night"
    if agency in NO_BY_AGENCY:
        return NO_BY_AGENCY[agency]
    if rtype == "106":
        return "intercity"          # Öresundståg, running in from Sweden
    m = re.match(r"^([A-Za-z]+)", (short or "").strip())
    if m:
        # RE and FLY must be tested before R and F, longest token first.
        tok = m.group(1).upper()
        for k in sorted(NO_BY_PREFIX, key=len, reverse=True):
            if tok == k:
                return NO_BY_PREFIX[k]
    if rtype == "102":
        return "intercity"
    return "regional"


def collect(src, ns, date, rule, stops, trips):
    feed = Feed(src)
    for r in feed.rows("stops.txt"):
        try:
            stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                        float(r["stop_lat"]),
                                        (r.get("stop_name") or "").strip())
        except (ValueError, KeyError):
            continue

    agency = {(a.get("agency_id") or "").strip(): (a.get("agency_name") or "").strip()
              for a in feed.rows("agency.txt")}
    routes = {}
    for r in feed.rows("routes.txt"):
        rt = (r.get("route_type") or "").strip()
        if rt not in RAIL:
            continue
        ag = agency.get((r.get("agency_id") or "").strip(), "")
        short = (r.get("route_short_name") or "").strip()
        routes[r["route_id"]] = (rule(rt, ag, short), short or ag,
                                 (r.get("route_long_name") or "").strip())

    svc = feed.active_services(date)
    n = 0
    for r in feed.rows("trips.txt"):
        if r.get("service_id") not in svc or r.get("route_id") not in routes:
            continue
        cls, short, long_ = routes[r["route_id"]]
        num = (r.get("trip_short_name") or "").strip()
        trips[ns + r["trip_id"]] = {
            "cls": cls, "name": " ".join(x for x in [short, num] if x) or short,
            "head": (r.get("trip_headsign") or "").strip() or long_,
            "st": [], "shape": ns + r["shape_id"] if r.get("shape_id") else None,
            "src": ns,
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
    ap.add_argument("--se", required=True, help="Trafiklab GTFS Sverige 2")
    ap.add_argument("--no", dest="no_", required=True, help="Entur aggregate")
    ap.add_argument("-o", "--out", default="data/scan-trains.json")
    ap.add_argument("--note", default="")
    ap.add_argument("--bbox", default="4.0,54.8,32.0,71.5")
    ap.add_argument("--shape-tol", type=float, default=300.0)
    ap.add_argument("--tmp", default="/tmp/scan-shapes")
    args = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips, feeds = {}, {}, {}
    sources = [("s:", args.se, lambda rt, ag, sh: se_class(rt, ag)),
               ("n:", args.no_, no_class)]
    for ns, src, rule in sources:
        feeds[ns] = collect(src, ns, args.date, rule, stops, trips)

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

    # Cross-source duplicates: the same Öresundståg is in both files.
    #
    # Matched on the geography of the endpoints, not on the line name --
    # unlike the European merge, where a cross-border EC keeps its number on
    # both sides of the frontier. Here the two operators label the same train
    # differently: Oslo-Göteborg is "393" in Trafiklab's file and "RE20" in
    # Entur's, and the Malmö-Berlin night train is "300" against "NT". Name
    # matching finds none of the 264 duplicates; endpoints find all of them.
    # The window is five minutes rather than twenty for the same reason it
    # can be: a duplicate is the same departure, not a similar one. The class
    # is deliberately not part of the key -- Entur files Oslo-Göteborg as a
    # regionekspress and Trafiklab as long distance, and it is one train.
    #
    # Trafiklab's own file also carries a train twice when two county
    # authorities both publish it: Kalmar's 8614 is in it as "8614" and as
    # "8614 8614". Inside one file the endpoints alone are not enough --
    # 158 and 118 leave Stockholm for Hallsberg in the same minute and are
    # two portions of a train that splits -- so a same-file merge also
    # requires the train numbers to agree.
    SLACK = 5 * 60
    cell = lambda s: (round(stops[s][0], 2), round(stops[s][1], 2))
    nums = lambda t: frozenset(re.findall(r"\d+", t["name"]))
    seen, merged, uniq = {}, 0, []
    for t, st in kept:
        key = (cell(st[0][1]), cell(st[-1][1]))
        dep, hit = st[0][3], None
        for dep0, at in seen.get(key, []):
            if abs(dep0 - dep) > SLACK:
                continue
            other = uniq[at][0]
            if other["src"] != t["src"] or nums(other) == nums(t):
                hit = at
                break
        if hit is not None:
            merged += 1
            if len(st) > len(uniq[hit][1]):
                uniq[hit] = (t, st)
            continue
        seen.setdefault(key, []).append((dep, len(uniq)))
        uniq.append((t, st))
    kept = uniq
    print(f"duplicate trains merged: {merged} -> {len(kept)} trips")

    tracks = {}
    if args.shape_tol > 0:
        for ns, src, _ in sources:
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
           "source": "Trafiklab GTFS Sverige 2 and Entur (Norway)",
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
