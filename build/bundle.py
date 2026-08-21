#!/usr/bin/env python3
"""Inline the generated JSON payloads into index.html.

Keeping the data inside the page means the site is a single file with no
fetch, so it works from GitHub Pages, from a local file:// open, and from
anywhere else without a server or CORS headers.

Usage:  python3 build/bundle.py [-d data/trains.json] [-g data/germany.json] [-p index.html]
"""
import argparse, os, re, sys

BLOCKS = [("timetable", "/*DATA_START*/", "/*DATA_END*/"),
          ("basemap",   "/*GEO_START*/",  "/*GEO_END*/")]


def inject(page, start, end, path, label):
    payload = open(path, encoding="utf-8").read().strip()
    # A literal </script> inside the JSON would close the host tag early.
    payload = payload.replace("</", "<\\/")
    if start not in page or end not in page:
        sys.exit(f"missing {start} ... {end} markers")
    page = re.sub(re.escape(start) + ".*?" + re.escape(end),
                  start + payload + end, page, count=1, flags=re.S)
    print(f"  {label}: {len(payload)/1000:.0f} kB from {path}")
    return page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--data", default="data/trains.json")
    ap.add_argument("-g", "--geo", default="data/germany.json")
    ap.add_argument("-p", "--page", default="index.html")
    args = ap.parse_args()

    page = open(args.page, encoding="utf-8").read()
    for path, (label, start, end) in zip([args.data, args.geo], BLOCKS):
        page = inject(page, start, end, path, label)
    open(args.page, "w", encoding="utf-8").write(page)
    print(f"{args.page}: {os.path.getsize(args.page)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
