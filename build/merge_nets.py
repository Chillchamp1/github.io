#!/usr/bin/env python3
"""Fold finished country datasets into the combined European map.

Usage:
    python3 build/merge_nets.py \\
        --base data/eu-trains.json --base2 data/eu-trains-2.json \\
        --add /tmp/eucomb/pl.json:pl --add /tmp/eucomb/dk.json:dk \\
        --add /tmp/eucomb/ib.json:ib --add /tmp/eucomb/it.json:it \\
        -o data/eu-trains.json --out2 data/eu-trains-2.json

`build_eu.py` merges GTFS feeds; this merges the compact JSON the page
already consumes. Poland, Denmark, Iberia and Italy each have a builder
that reads their own sources, classifies by their own conventions and has
been checked against their own page. Re-reading fourteen more GTFS files
inside build_eu.py would duplicate all of that and give the same answer;
running each builder on the shared date and concatenating the results does
not.

The shared date is what makes the combined map mean anything: a train in
Poland and a train in Portugal are at the same minute of the same
Wednesday. 10 June 2026 is the one date every source covers -- DELFI is
valid to 13 June, Poland's feed is a 30-day window opening on 4 June, and
Renfe Cercanias is a 30-day window opening on 3 June. Two costs are
accepted for it and stated on the page: 10 June is Portugal's national day,
so CP runs 868 trains instead of 1,362, and AMT Genova's feed covers only
1-8 June, so the eighteen Genova-Casella trains are absent.

Each country's classes fold onto the combined five. The choices worth
defending:

  Polish EIP and EIC are genuine long distance and become `ice`; the two
  SKM suburban operators join `regional`, where German S-Bahn already is.
  Spanish Cercanias likewise.

  Italian `express` -- Trenord's RE lines -- becomes `regional`, not
  `intercity`. A German RE is regional on this map and an RE13 to Milano
  is the same kind of train; promoting it would invent a long-distance
  network for the one country that has none in open data.

  Italian narrow gauge joins `mountain`, alongside the Swiss rack railways.

  Czech R lines -- rychliky running through a region -- become `intercity`;
  the Esko S networks join `regional`. British operators are already sorted
  into tiers by build_uk.py, so intercity stays intercity and the Overground,
  Merseyrail and TfL Rail join `regional` with every other suburban railway
  on this map.

Cross-source duplicates are merged the way build_eu.py merges them, and for
the same reason: an EC Hamburg-Copenhagen is in DELFI and in Rejseplanen,
a Berlin-Warszawa EC is in DELFI and in the Polish register, a
Barcelona-Paris TGV is in Renfe's file and in SNCF's. Long distance matches
on line name, destination and roughly-when; regional matches on geography,
because line names repeat across countries. Only ever across sources.
"""
import argparse, json, os, re, subprocess, sys

CLASSES = ["ice", "intercity", "regional", "mountain", "night"]
LONG_DISTANCE = {"ice", "intercity", "night"}

CLASS_MAP = {
    "pl": {"express": "ice", "intercity": "intercity", "regional": "regional",
           "sbahn": "regional", "night": "night"},
    "dk": {"intercity": "intercity", "regional": "regional",
           "sbahn": "regional", "night": "night"},
    "ib": {"highspeed": "ice", "intercity": "intercity",
           "regional": "regional", "cercanias": "regional"},
    "it": {"express": "regional", "regional": "regional",
           "suburban": "regional", "narrow": "mountain"},
    "uk": {"intercity": "intercity", "regional": "regional",
           "suburban": "regional", "night": "night"},
    "cz": {"express": "intercity", "regional": "regional",
           "suburban": "regional"},
}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def rejoin(core, delta):
    """Undo split_layers: the delta's stations and shapes continue the
    core's indices, so this is two concatenations and a trip list."""
    d = dict(core)
    d["stations"] = core["stations"] + delta["stations"]
    d["trips"] = core["trips"] + delta["trips"]
    sh = (core.get("shapes") or []) + (delta.get("shapes") or [])
    if sh:
        d["shapes"] = sh
    counts = dict(core.get("countsAll") or core.get("counts") or {})
    for k, v in (delta.get("counts") or {}).items():
        counts.setdefault(k, v)
    d["counts"] = counts
    for k in ("defer", "countsAll"):
        d.pop(k, None)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--base2", help="the base's deferred layer, if it is split")
    ap.add_argument("--add", action="append", default=[], metavar="PATH:TAG",
                    help="a country dataset and its class-map tag")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--out2", help="write the deferred layer here too")
    ap.add_argument("--defer", nargs="+", default=["regional", "mountain"])
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    base = json.load(open(args.base, encoding="utf-8"))
    if args.base2:
        base = rejoin(base, json.load(open(args.base2, encoding="utf-8")))
    if base["classes"] != CLASSES:
        sys.exit(f"base classes {base['classes']} are not {CLASSES}")

    stations, trips, shapes = [], [], list(base.get("shapes") or [])
    coord_key = {}

    def station(rec):
        """One station per (name, ~100 m cell), shared across countries --
        a border station published by both sides must not become two dots."""
        key = (rec[2], round(rec[0], 3), round(rec[1], 3))
        if key not in coord_key:
            coord_key[key] = len(stations)
            stations.append(rec)
        return coord_key[key]

    def absorb(d, tag, cmap):
        st_remap = [station(s) for s in d["stations"]]
        sh_off = len(shapes)
        shapes.extend(d.get("shapes") or [])
        n = 0
        for t in d["trips"]:
            cls = cmap[d["classes"][t["c"]]]
            rec = {"c": CLASSES.index(cls), "n": t.get("n", ""),
                   "h": t.get("h", ""), "src": tag,
                   "s": [[st_remap[s[0]], s[1], s[2]] for s in t["s"]]}
            if "p" in t:
                rec["p"] = [t["p"][0] + sh_off, t["p"][1]]
            trips.append(rec)
            n += 1
        print(f"  {tag}: {n} trips, {len(d['stations'])} stations "
              f"({d.get('date')})")

    absorb(base, "eu", {c: c for c in CLASSES})
    dates = {base.get("date")}
    for spec in args.add:
        path, _, tag = spec.rpartition(":")
        if tag not in CLASS_MAP:
            sys.exit(f"no class map for {tag!r}")
        d = json.load(open(path, encoding="utf-8"))
        dates.add(d.get("date"))
        absorb(d, tag, CLASS_MAP[tag])
    print(f"before dedup: {len(trips)} trips, {len(stations)} stations")

    LONG_SLACK, REG_SLACK = 20 * 60, 3 * 60
    cell = lambda i: (round(stations[i][0], 2), round(stations[i][1], 2))

    def key_of(t):
        cls = CLASSES[t["c"]]
        if cls in LONG_DISTANCE:
            return ("L", cls, norm(t["n"]), norm(stations[t["s"][-1][0]][2])), \
                   LONG_SLACK
        return ("R", cls, cell(t["s"][0][0]), cell(t["s"][-1][0])), REG_SLACK

    seen, merged, uniq = {}, 0, []
    for t in trips:
        k, slack = key_of(t)
        dep = t["s"][0][2] * 60
        hit = None
        for dep0, at in seen.get(k, []):
            if abs(dep0 - dep) <= slack and uniq[at]["src"] != t["src"]:
                hit = at
                break
        if hit is not None:
            merged += 1
            if len(t["s"]) > len(uniq[hit]["s"]):
                uniq[hit] = t
            continue
        seen.setdefault(k, []).append((dep, len(uniq)))
        uniq.append(t)
    print(f"cross-source duplicates merged: {merged} -> {len(uniq)} trips")

    # Stations nothing calls at any more (a merged duplicate's own copy) are
    # dropped, and the indices closed up: they would draw as dots with no
    # trains and inflate the payload.
    live, remap = [], {}
    for t in uniq:
        for s in t["s"]:
            if s[0] not in remap:
                remap[s[0]] = len(live)
                live.append(stations[s[0]])
            s[0] = remap[s[0]]
    used_sh, sh_remap = [], {}
    for t in uniq:
        if "p" in t:
            if t["p"][0] not in sh_remap:
                sh_remap[t["p"][0]] = len(used_sh)
                used_sh.append(shapes[t["p"][0]])
            t["p"][0] = sh_remap[t["p"][0]]
    for t in uniq:
        t.pop("src", None)

    counts = {c: 0 for c in CLASSES}
    for t in uniq:
        counts[CLASSES[t["c"]]] += 1

    doc = {"tunit": "min", "date": base["date"], "weekday": base["weekday"],
           "classes": CLASSES, "counts": counts,
           "source": base.get("source", ""), "note": args.note or base.get("note", ""),
           "stations": live, "trips": uniq}
    if used_sh:
        doc["shapes"] = used_sh
    json.dump(doc, open(args.out, "w", encoding="utf-8"),
              separators=(",", ":"), ensure_ascii=False)
    print(f"{args.out}: {len(uniq)} trips, {len(live)} stations, "
          f"{len(used_sh)} shapes, {os.path.getsize(args.out)/1e6:.2f} MB")
    for c in CLASSES:
        print(f"  {c:<10} {counts[c]}")

    if args.out2:
        subprocess.run([sys.executable,
                        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "split_layers.py"),
                        args.out, "--defer", *args.defer,
                        "-o", args.out, "--out2", args.out2], check=True)


if __name__ == "__main__":
    main()
