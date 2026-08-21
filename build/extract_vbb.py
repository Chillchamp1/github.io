#!/usr/bin/env python3
"""Extract the rail-regional slice of the 2016 VBB GTFS from git history.

The VBB feed was published on GitHub (derhuerst/vbb-gtfs, CC BY 3.0) and later
deleted from the working tree, but the full CSVs remain as plain blobs in git
history. Commit 53995ef (2016-04-27) is valid 2016-04-21 .. 2016-12-10.

Usage:
    git clone --filter=blob:none --no-checkout \
        https://github.com/derhuerst/vbb-gtfs <clone>
    python3 build/extract_vbb.py <clone> <outdir> [--commit 53995ef]

Writes a minimal GTFS directory containing only RE/RB/IRE rail routes (VBB
route_type 100), ready for build_gtfs.py. Blobs are fetched on demand, so the
clone stays small; stop_times.txt is streamed and never fully materialised.
"""
import argparse, csv, io, os, re, subprocess, sys

RAIL_NAME = re.compile(r"^(RE|RB|IRE)\d*$")


def git_show(repo, commit, path):
    return subprocess.run(["git", "-C", repo, "show", f"{commit}:{path}"],
                          capture_output=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clone", help="clone of derhuerst/vbb-gtfs")
    ap.add_argument("outdir")
    ap.add_argument("--commit", default="53995ef")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    def rows(name):
        return csv.DictReader(io.TextIOWrapper(
            io.BytesIO(git_show(args.clone, args.commit, name)), "utf-8-sig"))

    def write(name, keep):
        out = list(keep)
        with open(os.path.join(args.outdir, name), "w", newline="",
                  encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=out[0].keys())
            w.writeheader(); w.writerows(out)
        return out

    routes = write("routes.txt",
                   (r for r in rows("routes.txt")
                    if RAIL_NAME.match((r["route_short_name"] or "").strip())
                    and r["route_type"] == "100"))
    rids = {r["route_id"] for r in routes}
    trips = write("trips.txt",
                  (r for r in rows("trips.txt") if r["route_id"] in rids))
    tids = {t["trip_id"] for t in trips}

    # stop_times is ~200 MB in history; stream it.
    proc = subprocess.Popen(
        ["git", "-C", args.clone, "show", f"{args.commit}:stop_times.txt"],
        stdout=subprocess.PIPE)
    rd = csv.reader(io.TextIOWrapper(proc.stdout, "utf-8-sig"))
    hdr = next(rd); ti = hdr.index("trip_id"); n = 0
    with open(os.path.join(args.outdir, "stop_times.txt"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(hdr)
        for row in rd:
            if row[ti] in tids:
                w.writerow(row); n += 1
    proc.wait()

    for name in ("stops.txt", "agency.txt", "calendar.txt",
                 "calendar_dates.txt"):
        with open(os.path.join(args.outdir, name), "wb") as f:
            f.write(git_show(args.clone, args.commit, name))

    with open(os.path.join(args.outdir, "feed_info.txt"), "w",
              encoding="utf-8") as f:
        f.write("feed_publisher_name,feed_publisher_url,feed_lang\n"
                "\"VBB GTFS (CC BY 3.0), 2016 snapshot\","
                "https://github.com/derhuerst/vbb-gtfs,de\n")

    print(f"{args.outdir}: {len(routes)} routes, {len(trips)} trips, "
          f"{n} stop_times")


if __name__ == "__main__":
    main()
