#!/usr/bin/env python3
"""Turn one or more GTFS feeds into the compact JSON the animation consumes.

Usage:
    python3 build/build_gtfs.py <gtfs-dir> [<gtfs-dir> ...] <YYYYMMDD> [-o data/trains.json]

Several feeds merge into one day: pass e.g. a long-distance feed and a
regional feed covering the same service date. Feed-local IDs never collide
across sources because each feed is namespaced internally.

The feed must contain agency/routes/trips/stops/stop_times plus calendar.txt
and/or calendar_dates.txt. Only rail is kept; buses and urban transit
(S-Bahn, U-Bahn, tram) are dropped -- see CLASSES and DROP below.
"""
import argparse, csv, io, json, os, sys, datetime, math, re, zipfile

csv.field_size_limit(1 << 24)

# Ordered: first pattern that matches a route's name wins.
# (?=[ \d]|$) instead of \b: feeds write both "RE 2083" and "RE1", and a
# plain word boundary never fires between the E and the 1.
CLASSES = [
    ("ice",      r"^(ICE|ECE|TGV|RJX?)(?=[ \d]|$)"),
    ("intercity",r"^(IC|EC|D)(?=[ \d]|$)"),
    ("regional", r"^(IRE|RE|RB|IR|MEX|DZ|ALX|BRB|ERB|EVB|HLB|NWB|ODEG|VIA|WFB)(?=[ \d]|$)"),
    ("night",    r"^(NJ|EN|DN|CNL)(?=[ \d]|$)"),
]
DROP = re.compile(r"^(S|U|STR|Bus|Str|Tram|SEV)(?=[ \d]|$)", re.I)

# GTFS route_type values that are urban transit, dropped regardless of name.
DROP_TYPES = {0, 1, 3, 4, 5, 6, 7, 11, 12}


def read(path, name):
    """Yield rows lazily -- stop_times.txt can run to gigabytes."""
    fp = os.path.join(path, name)
    if not os.path.exists(fp):
        return
    with open(fp, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


class Feed:
    """A GTFS feed held either as a directory or as a zip, streamed row by
    row: the national aggregates run to gigabytes and must never be
    unpacked or held in memory whole."""

    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if path.endswith(".zip") else None
        self.names = set(self.zip.namelist()) if self.zip else set(
            os.listdir(path))

    def rows(self, name):
        if name not in self.names:
            return
        if self.zip:
            with self.zip.open(name) as f:
                yield from csv.DictReader(io.TextIOWrapper(f, "utf-8-sig"))
        else:
            with open(os.path.join(self.path, name), encoding="utf-8-sig",
                      newline="") as f:
                yield from csv.DictReader(f)

    def shapes_dir(self, tmpdir):
        """load_shapes() wants a directory; give it one when we hold a zip."""
        if not self.zip:
            return self.path if "shapes.txt" in self.names else None
        if "shapes.txt" not in self.names:
            return None
        os.makedirs(tmpdir, exist_ok=True)
        out = os.path.join(tmpdir, "shapes.txt")
        if not os.path.exists(out):
            with self.zip.open("shapes.txt") as src, open(out, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
        return tmpdir

    def active_services(self, date):
        d = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:]))
        dow = ["monday", "tuesday", "wednesday", "thursday", "friday",
               "saturday", "sunday"][d.weekday()]
        a = set()
        for r in self.rows("calendar.txt"):
            if r["start_date"] <= date <= r["end_date"] and r.get(dow) == "1":
                a.add(r["service_id"])
        for r in self.rows("calendar_dates.txt"):
            if r.get("date") == date:
                (a.add if r["exception_type"] == "1"
                 else a.discard)(r["service_id"])
        return a


# --------------------------------------------------------------------------
# Route geometry. DELFI ships shapes.txt for essentially every trip, so the
# trains can follow the published track geometry instead of straight lines
# between stops. stop_times carries no shape_dist_traveled, so each stop is
# projected onto its trip's polyline instead.

def load_shapes(path, wanted):
    """shape_id -> [(lon, lat), ...] ordered by point sequence, restricted to
    `wanted` -- shapes.txt alone is a third of a gigabyte."""
    pts = {}
    for r in read(path, "shapes.txt"):
        sid = r.get("shape_id")
        if sid not in wanted:
            continue
        try:
            pts.setdefault(sid, []).append((int(r["shape_pt_sequence"]),
                                            float(r["shape_pt_lon"]),
                                            float(r["shape_pt_lat"])))
        except (ValueError, KeyError):
            continue
    return {sid: [(lon, lat) for _, lon, lat in sorted(v)]
            for sid, v in pts.items() if len(v) >= 2}


def simplify(pts, tol_m):
    """Douglas-Peucker on an equirectangular projection, tolerance in
    meters. A tolerance below the map's meters-per-pixel is invisible."""
    if len(pts) < 3:
        return pts
    k = math.cos(math.radians(pts[len(pts) // 2][1]))
    M = 111320.0
    xs = [(lon * k * M, lat * M) for lon, lat in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = xs[i]
        bx, by = xs[j]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        best, bd = -1, tol_m
        for m in range(i + 1, j):
            px, py = xs[m]
            if l2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / l2
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > bd:
                best, bd = m, d
        if best >= 0:
            keep[best] = True
            stack.append((i, best))
            stack.append((best, j))
    return [p for p, kf in zip(pts, keep) if kf]


def shape_track(pts):
    """Scaled coordinates + cumulative lengths, ready for stop projection."""
    k = math.cos(math.radians(pts[len(pts) // 2][1]))
    xs = [(lon * k, lat) for lon, lat in pts]
    cum = [0.0]
    for i in range(1, len(xs)):
        cum.append(cum[-1] + math.hypot(xs[i][0] - xs[i - 1][0],
                                        xs[i][1] - xs[i - 1][1]))
    return xs, cum, k


def stop_fracs(track, stops_ll, max_off_deg=0.02):
    """Per-mille position of each stop along the polyline. The search only
    walks forward from the previous stop's segment, so a ring line that
    passes the same spot twice lands each stop on the right lap. Returns
    None when a stop sits further than ~2 km off the shape -- that means
    the shape does not belong to this stop sequence."""
    xs, cum, k = track
    total = cum[-1]
    if total <= 0:
        return None
    j0, out = 0, []
    for lon, lat in stops_ll:
        px, py = lon * k, lat
        best_d2 = best_pos = None
        best_j = j0
        for j in range(j0, len(xs) - 1):
            ax, ay = xs[j]
            bx, by = xs[j + 1]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy
            t = 0.0 if l2 == 0 else ((px - ax) * dx + (py - ay) * dy) / l2
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            qx, qy = ax + t * dx, ay + t * dy
            d2 = (px - qx) ** 2 + (py - qy) ** 2
            if best_d2 is None or d2 < best_d2:
                best_d2 = d2
                best_pos = cum[j] + t * math.hypot(dx, dy)
                best_j = j
        if best_d2 is None or best_d2 > max_off_deg * max_off_deg:
            return None
        out.append(best_pos)
        j0 = best_j
    fr, prev = [], 0
    for pos in out:
        v = min(1000, round(1000 * pos / total))
        if v < prev:
            v = prev
        prev = v
        fr.append(v)
    return fr


def enc_shape(pts):
    """Flat delta-encoded ints at 1e-4 degrees: first pair absolute."""
    out, plon, plat = [], 0, 0
    for lon, lat in pts:
        il, ia = round(lon * 1e4), round(lat * 1e4)
        out.append(il - plon)
        out.append(ia - plat)
        plon, plat = il, ia
    return out


NIGHT_NAME = re.compile(r"^(NJ|EN|DN|CNL)(?=[ \d]|$)")
# DELFI names most NightJet and EuroNight runs by their long-distance line
# number with an N suffix -- 12N Basel-Berlin, 91N Amsterdam-Wien -- and only
# a couple of partner-operated legs literally "NJ". Without this they land in
# intercity: 41 of the 54 night services were drawn as orange IC trains.
# Scoped to route_type 102, where every N-suffixed line is a night service.
NIGHT_LINE = re.compile(r"^\d+N$")
REGIONAL_NAME = re.compile(r"^(IRE|RE|RB|MEX)(?=[ \d]|$)")
NOISE_NAME = re.compile(r"^(AST|ALT|SEV|EV|Bus|Schiff|RUF)", re.I)


def classify(route):
    """Type-first where the feed uses extended route types (DELFI), name-first
    for plain type-2 feeds. Returns (class, display_name) or (None, name)."""
    name = (route.get("route_short_name") or route.get("route_long_name") or "").strip()
    if not name or DROP.match(name):
        return None, name
    try:
        rt = int(route.get("route_type") or 2)
    except ValueError:
        rt = 2
    # 2 = rail; 100-117 = extended rail. 109 is S-Bahn, 200+ coach/bus/etc.
    if rt != 2 and not (100 <= rt <= 117):
        return None, name
    if rt in DROP_TYPES or rt == 109:
        return None, name
    if NIGHT_NAME.match(name) or rt == 105:          # 105 = sleeper rail
        return "night", name
    if rt == 101:                                    # high-speed rail
        return ("regional", name) if REGIONAL_NAME.match(name) else ("ice", name)
    if rt == 102 and NIGHT_LINE.match(name):
        return "night", name
    if rt == 102:                                    # long-distance rail
        for cls, pat in CLASSES:
            if re.match(pat, name):
                return cls, name
        return "intercity", name
    for cls, pat in CLASSES:
        if re.match(pat, name):
            return cls, name
    if rt in (103, 106) and not NOISE_NAME.match(name):
        return "regional", name                      # (inter)regional rail
    return None, name


def hhmmss(v):
    """GTFS times may exceed 24h for trips running past midnight."""
    try:
        h, m, s = (int(x) for x in v.split(":"))
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def active_services(path, date):
    """service_ids running on `date`, honouring calendar + calendar_dates."""
    d = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:]))
    dow = ["monday", "tuesday", "wednesday", "thursday", "friday",
           "saturday", "sunday"][d.weekday()]
    active = set()
    for r in read(path, "calendar.txt"):
        if r["start_date"] <= date <= r["end_date"] and r.get(dow) == "1":
            active.add(r["service_id"])
    for r in read(path, "calendar_dates.txt"):
        if r["date"] != date:
            continue
        if r["exception_type"] == "1":
            active.add(r["service_id"])
        elif r["exception_type"] == "2":
            active.discard(r["service_id"])
    return active


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gtfs", nargs="+",
                    help="one or more GTFS directories, merged onto one day")
    ap.add_argument("date", help="service date, YYYYMMDD")
    ap.add_argument("-o", "--out", default="data/trains.json")
    ap.add_argument("--note", default="",
                    help="free-text provenance note carried into the JSON")
    ap.add_argument("--bbox", default="5.2,46.9,15.9,55.4",
                    help="minLon,minLat,maxLon,maxLat -- a trip is kept if it "
                         "calls at least once inside this box")
    ap.add_argument("--shape-tol", type=float, default=200.0,
                    help="shape simplification tolerance in meters; "
                         "0 disables shapes entirely")
    args = ap.parse_args()

    minlon, minlat, maxlon, maxlat = (float(x) for x in args.bbox.split(","))

    stops, trips = {}, {}
    for fi, src in enumerate(args.gtfs):
        ns = f"{fi}:"          # feed-local IDs must not collide across feeds
        for r in read(src, "stops.txt"):
            try:
                stops[ns + r["stop_id"]] = (float(r["stop_lon"]),
                                            float(r["stop_lat"]),
                                            r["stop_name"].strip())
            except (ValueError, KeyError):
                continue

        routes = {}
        for r in read(src, "routes.txt"):
            cls, name = classify(r)
            if cls:
                routes[r["route_id"]] = (cls, name)

        services = active_services(src, args.date)
        feed_trips = 0
        for r in read(src, "trips.txt"):
            if r["service_id"] in services and r["route_id"] in routes:
                cls, name = routes[r["route_id"]]
                trips[ns + r["trip_id"]] = {
                    "cls": cls, "name": name,
                    "head": (r.get("trip_headsign") or "").strip(), "st": [],
                    "shape": ns + r["shape_id"] if r.get("shape_id") else None,
                }
                feed_trips += 1
        print(f"  {src}: {feed_trips} active trips")

        for r in read(src, "stop_times.txt"):
            t = trips.get(ns + r["trip_id"])
            if t is None or ns + r["stop_id"] not in stops:
                continue
            arr = hhmmss(r.get("arrival_time") or "")
            dep = hhmmss(r.get("departure_time") or "")
            if arr is None and dep is None:
                continue
            arr = arr if arr is not None else dep
            dep = dep if dep is not None else arr
            t["st"].append((int(r["stop_sequence"]), ns + r["stop_id"], arr, dep))

    # Route geometry: load only the shapes the kept trips reference, then
    # simplify each once. Projection results are cached per (shape, stop
    # sequence) -- DELFI runs dozens of trips over the same pattern.
    tracks = {}
    if args.shape_tol > 0:
        for fi, src in enumerate(args.gtfs):
            ns = f"{fi}:"
            wanted = {t["shape"][len(ns):] for t in trips.values()
                      if t["shape"] and t["shape"].startswith(ns)}
            raw = load_shapes(src, wanted)
            for sid, pts in raw.items():
                simp = simplify(pts, args.shape_tol)
                tracks[ns + sid] = (simp, shape_track(simp))
        print(f"  shapes: {len(tracks)} loaded and simplified")

    # Assemble, keeping only trips that actually touch the bbox.
    used, order, coord_key = {}, [], {}

    def idx(sid):
        """Feeds carry one stop per platform; merge to one station per
        (name, ~100 m cell) so the map draws each station once."""
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

    classes = [c for c, _ in CLASSES]
    out_shapes, shape_out_idx, frac_cache = [], {}, {}
    out_trips, counts = [], {c: 0 for c in classes}
    matched = 0
    for t in trips.values():
        st = sorted(t["st"])
        if len(st) < 2:
            continue
        if not any(minlon <= stops[s][0] <= maxlon and minlat <= stops[s][1] <= maxlat
                   for _, s, _, _ in st):
            continue
        seq = [[idx(s), a // 60, d // 60] for _, s, a, d in st]

        path = None
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
                path = [shape_out_idx[t["shape"]], fr]
                matched += 1
        # Times must be non-decreasing for interpolation to behave.
        for i in range(1, len(seq)):
            if seq[i][1] < seq[i - 1][2]:
                seq[i][1] = seq[i - 1][2]
            if seq[i][2] < seq[i][1]:
                seq[i][2] = seq[i][1]
        name = t["name"]
        # Bare line numbers ("17", "12N") mean nothing on hover; give them
        # their category's prefix.
        if name.isdigit() or (t["cls"] == "night" and NIGHT_LINE.match(name)):
            name = {"ice": "ICE ", "intercity": "IC ",
                    "night": "NJ "}.get(t["cls"], "") + name
        rec = {"c": classes.index(t["cls"]), "n": name,
               "h": t["head"], "s": seq}
        if path:
            rec["p"] = path
        out_trips.append(rec)
        counts[t["cls"]] += 1

    stations = [[round(stops[s][0], 4), round(stops[s][1], 4), stops[s][2]]
                for s in order]

    d = datetime.date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:]))
    sources = []
    for src in args.gtfs:
        feed = next(iter(read(src, "feed_info.txt")), {})
        sources.append(feed.get("feed_publisher_name",
                                os.path.basename(os.path.abspath(src))))
    doc = {
        "tunit": "min",
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "classes": classes,
        "counts": counts,
        "source": "; ".join(dict.fromkeys(sources)),
        "note": args.note,
        "stations": stations,
        "trips": out_trips,
    }
    if out_shapes:
        doc["shapes"] = out_shapes

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)

    print(f"{args.out}: {len(out_trips)} trips, {len(stations)} stations, "
          f"{len(out_shapes)} shapes ({matched} trips on tracks), "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for c in classes:
        print(f"  {c:<10} {counts[c]}")


if __name__ == "__main__":
    main()
