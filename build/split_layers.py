#!/usr/bin/env python3
"""Split a dataset into a core that paints at once and a bulk that follows.

Usage:
    python3 build/split_layers.py data/eu-trains.json --defer regional \\
        -o data/eu-trains.json --out2 data/eu-trains-2.json

The combined map is 68,000 trains and 3.6 MB gzipped, most of it regional
services -- the small green ones. Waiting for all of it before the first
frame is the wrong trade: the long-distance spine is a twentieth of the
bytes and is what the map reads as at first glance.

So the deferred classes move to a second file. The page draws the core
immediately, fetches the rest in the background and merges it in. Nothing
is dropped; the small trains simply arrive a moment later.

The second file is a delta, not a dataset: its stations are only the ones
the core never mentions, and its station and shape indices continue where
the core's leave off, so merging is two concatenations.
"""
import argparse, json, os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--defer", nargs="+", required=True,
                    help="class names to move into the second file")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--out2", required=True)
    args = ap.parse_args()

    d = json.load(open(args.src, encoding="utf-8"))
    classes = d["classes"]
    defer = {classes.index(c) for c in args.defer if c in classes}
    if not defer:
        raise SystemExit(f"none of {args.defer} in {classes}")

    core = [t for t in d["trips"] if t["c"] not in defer]
    rest = [t for t in d["trips"] if t["c"] in defer]

    # Stations the core needs keep their indices; the rest are renumbered to
    # follow them, so the page can simply concatenate the two lists.
    core_st, remap = [], {}
    for t in core:
        for s in t["s"]:
            if s[0] not in remap:
                remap[s[0]] = len(core_st)
                core_st.append(s[0])
    n_core = len(core_st)
    extra_st = []
    for t in rest:
        for s in t["s"]:
            if s[0] not in remap:
                remap[s[0]] = n_core + len(extra_st)
                extra_st.append(s[0])
    for t in d["trips"]:
        for s in t["s"]:
            s[0] = remap[s[0]]

    # Same treatment for route geometry.
    shapes = d.get("shapes") or []
    core_sh, sh_remap = [], {}
    for t in core:
        if "p" in t and t["p"][0] not in sh_remap:
            sh_remap[t["p"][0]] = len(core_sh)
            core_sh.append(t["p"][0])
    n_core_sh = len(core_sh)
    extra_sh = []
    for t in rest:
        if "p" in t and t["p"][0] not in sh_remap:
            sh_remap[t["p"][0]] = n_core_sh + len(extra_sh)
            extra_sh.append(t["p"][0])
    for t in d["trips"]:
        if "p" in t:
            t["p"][0] = sh_remap[t["p"][0]]

    st = d["stations"]
    counts = d.get("counts", {})
    head = {k: v for k, v in d.items()
            if k not in ("trips", "stations", "shapes", "counts")}

    doc1 = dict(head)
    doc1["counts"] = {c: counts.get(c, 0) for c in classes
                      if classes.index(c) not in defer}
    doc1["stations"] = [st[i] for i in core_st]
    doc1["trips"] = core
    if core_sh:
        doc1["shapes"] = [shapes[i] for i in core_sh]
    doc1["defer"] = os.path.basename(args.out2)
    # The full counts belong on the first file: the legend should promise
    # the whole day from the first frame, not grow a row when the rest lands.
    doc1["countsAll"] = counts

    doc2 = {"tunit": head.get("tunit", "min"), "classes": classes,
            "counts": {c: counts.get(c, 0) for c in classes
                       if classes.index(c) in defer},
            "stations": [st[i] for i in extra_st], "trips": rest}
    if extra_sh:
        doc2["shapes"] = [shapes[i] for i in extra_sh]

    for path, doc in ((args.out, doc1), (args.out2, doc2)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
        print(f"{path}: {len(doc['trips'])} trips, "
              f"{len(doc['stations'])} stations, "
              f"{len(doc.get('shapes', []))} shapes, "
              f"{os.path.getsize(path)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
