#!/usr/bin/env python3
"""One weekday of Greater Tokyo urban rail from the mini-tokyo-3d dataset.

Usage:
    python3 build/build_tokyo.py <mini-tokyo-3d>/data [--asof YYYY-MM-DD] \
        [-o data/tokyo-trains.json]

The dataset (MIT, (c) Akihiko Kusanagi, derived from ODPT open data) stores
one generic Weekday and one SaturdayHoliday pattern per train rather than
dated calendars, so the page shows "one weekday" and the dataset snapshot
date rather than a specific service date.

Notes that shaped this builder:
- ids like "....Weekday.1"/".2" are variant patterns of one physical train;
  the plain ".Weekday" entry wins, else variant .1, so nothing draws twice;
- through-running is expressed as chains of timetables linked by "nt": the
  chain is stitched into one trip so a Tokyu train continuing into the
  subway neither dies at the boundary nor blooms a false origin ring there;
- three classes, by train type: limited expresses and fee-charging liners,
  the rapid/express family, and locals (the mass of the network).
"""
import argparse, json, os, re, sys, datetime

ap = argparse.ArgumentParser()
ap.add_argument("data_dir")
ap.add_argument("--asof", default=datetime.date.today().isoformat())
ap.add_argument("-o", "--out", default="data/tokyo-trains.json")
ap.add_argument("--note", default="")
args = ap.parse_args()

def load(name):
    return json.load(open(os.path.join(args.data_dir, name), encoding="utf-8"))

stations = {}
for s in load("stations.json"):
    if "coord" not in s:
        continue
    t = s.get("title", {})
    stations[s["id"]] = (s["coord"][0], s["coord"][1],
                        t.get("en") or t.get("ja") or s["id"])

ttypes = {}
for t in load("train-types.json"):
    ttypes[t["id"]] = (t.get("title", {}).get("en")
                       or t["id"].rsplit(".", 1)[-1])

CLASSES = ["ltdexp", "express", "local"]
LTD = re.compile(r"LimitedExpress|Liner|RomanceCar", re.I)
def classify(y):
    kind = (y or "").rsplit(".", 1)[-1]
    if LTD.search(kind): return "ltdexp"
    if "Local" in kind:  return "local"
    return "express"

WEEKDAY = re.compile(r"\.Weekday(\.(\d+))?$")

def hm(v):
    h, m = v.split(":")
    return int(h) * 60 + int(m)

# collect weekday timetables, plain pattern beating numbered variants
best = {}
tt_dir = os.path.join(args.data_dir, "train-timetables")
for f in sorted(os.listdir(tt_dir)):
    for t in json.load(open(os.path.join(tt_dir, f), encoding="utf-8")):
        m = WEEKDAY.search(t["id"])
        if not m or not t.get("tt"):
            continue
        variant = int(m.group(2) or 0)
        key = t["t"]
        if key not in best or variant < best[key][0]:
            best[key] = (variant, t)
by_id = {t["id"]: t for _, t in best.values()}
print(f"weekday timetables kept: {len(by_id)}")

# stitch through-running chains: roots are timetables nobody links to
linked = set()
for t in by_id.values():
    for nid in (t.get("nt") or []):
        if nid in by_id:
            linked.add(nid)

def stops_of(t):
    out = []
    for s in t["tt"]:
        sid = s.get("s")
        if sid not in stations:
            continue
        a, d = s.get("a"), s.get("d")
        if a is None and d is None:
            continue
        a = hm(a) if a else hm(d)
        d = hm(d) if d else a
        out.append((sid, a, d))
    return out

trips, counts = [], {c: 0 for c in CLASSES}
order, used, coord_key = [], {}, {}
def idx(sid):
    if sid in used: return used[sid]
    lon, lat, name = stations[sid]
    key = (name, round(lon, 3), round(lat, 3))
    if key in coord_key: used[sid] = coord_key[key]
    else:
        used[sid] = coord_key[key] = len(order)
        order.append(sid)
    return used[sid]

stitched = 0
for t in by_id.values():
    if t["id"] in linked:
        continue                       # will be reached via its chain root
    seq, seen_ids, names, cls_votes = [], set(), [], []
    cur, day = t, 0
    while cur is not None and cur["id"] not in seen_ids:
        seen_ids.add(cur["id"])
        names.append(cur.get("n", ""))
        cls_votes.append(classify(cur.get("y")))
        st = stops_of(cur)
        if st:
            # a chain hopping past midnight keeps time monotonic
            if seq and st[0][1] + day * 1440 < seq[-1][2] - 720:
                day += 1
            for sid, a, d in st:
                a += day * 1440; d += day * 1440
                if seq and sid == seq[-1][0]:
                    seq[-1] = (sid, seq[-1][1], max(seq[-1][2], d))
                else:
                    seq.append((sid, a, d))
        nxt = None
        for nid in (cur.get("nt") or []):
            if nid in by_id: nxt = by_id[nid]; break
        if nxt is not None: stitched += 1
        cur = nxt
    if len(seq) < 2:
        continue
    rows = []
    for sid, a, d in seq:
        if rows and a < rows[-1][2]: a = rows[-1][2]
        if d < a: d = a
        rows.append((idx(sid), a, d))
    cls = cls_votes[0]
    y = t.get("y", "")
    label = (ttypes.get(y) or "").strip()
    nm = t.get("nm")
    if nm: label = (nm[0].get("en") or nm[0].get("ja") or label)
    label = f"{label} {names[0]}".strip()
    head = stations[seq[-1][0]][2]
    trips.append({"c": CLASSES.index(cls), "n": label, "h": head,
                  "s": [[i, a, d] for i, a, d in rows]})
    counts[cls] += 1

stations_out = [[round(stations[s][0], 4), round(stations[s][1], 4),
                 stations[s][2]] for s in order]
doc = {
    "tunit": "min", "date": args.asof, "weekday": "weekday",
    "classes": CLASSES, "counts": counts,
    "source": "mini-tokyo-3d dataset (c) Akihiko Kusanagi, MIT; "
              "derived from ODPT open data",
    "note": args.note, "stations": stations_out, "trips": trips,
}
os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
with open(args.out, "w", encoding="utf-8") as f:
    json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
print(f"{args.out}: {len(trips)} trips ({stitched} chain links stitched), "
      f"{len(stations_out)} stations, {os.path.getsize(args.out)/1e6:.2f} MB")
for c in CLASSES:
    print(f"  {c:8} {counts[c]}")
