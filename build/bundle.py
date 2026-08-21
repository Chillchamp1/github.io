#!/usr/bin/env python3
"""Inline data/trains.json into index.html.

Keeping the data inside the page means the site is a single file with no
fetch, so it works from GitHub Pages, from a local file:// open, and from
anywhere else without a server or CORS headers.

Usage:  python3 build/bundle.py [-d data/trains.json] [-p index.html]
"""
import argparse, os, re, sys

START, END = "/*DATA_START*/", "/*DATA_END*/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--data", default="data/trains.json")
    ap.add_argument("-p", "--page", default="index.html")
    args = ap.parse_args()

    payload = open(args.data, encoding="utf-8").read().strip()
    # A literal </script> inside the JSON would close the host tag early.
    payload = payload.replace("</", "<\\/")

    page = open(args.page, encoding="utf-8").read()
    if START not in page or END not in page:
        sys.exit(f"{args.page}: missing {START} ... {END} markers")

    page = re.sub(
        re.escape(START) + ".*?" + re.escape(END),
        START + payload + END,
        page, count=1, flags=re.S,
    )
    open(args.page, "w", encoding="utf-8").write(page)
    print(f"{args.page}: {os.path.getsize(args.page)/1e6:.2f} MB "
          f"({len(payload)/1e6:.2f} MB of data inlined)")


if __name__ == "__main__":
    main()
