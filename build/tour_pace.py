#!/usr/bin/env python3
"""How fast do the trains actually move on screen during the tour?

    node build/export_tour.js --timeline /tmp/tl.json
    python3 build/tour_pace.py /tmp/tl.json data/eu-trains.json \\
            data/eu-trains-2.json --width 720 --height 1280 [--alpha 0.5]

"Too slow" is a judgement about pixels, not about the clock. A wide shot and
a close-up can run the same simulated minutes per second and look nothing
alike: at the whole-Europe frame a 200 km/h train crosses a handful of
pixels a second, and over Berlin an S-Bahn crosses fifty. So this measures
the thing the eye actually judges -- the median speed, in pixels per second,
of the dots inside the frame -- by walking the same dataset the film draws
and stepping it by one video second at each point along the route.

With --alpha it also proposes a fix. Apparent speed is proportional to the
clock rate, so multiplying the rate by (target/measured) would flatten the
film to one constant speed. That turns out to be too much: a constant speed
spends so little clock over Berlin that the close-up drifts out of the
evening peak entirely. alpha scales the correction -- 0 leaves the film
alone, 1 flattens it completely -- and the whole day is renormalised to fit
so the film still starts at midnight and ends at 23:59. It prints the clock
column to paste back into the KEYS table in export_tour.js.
"""
import argparse, json, math, statistics


def load(paths):
    core = json.load(open(paths[0], encoding="utf-8"))
    st, trips = list(core["stations"]), list(core["trips"])
    for p in paths[1:]:
        d = json.load(open(p, encoding="utf-8"))
        st += d["stations"]
        trips += d["trips"]
    return st, trips


def where(st, s, m):
    """A train's position part-way between two stops, or None if it is not
    under way. Straight lines between stops: this is a speed measurement,
    and the geometry a train follows does not change how far it gets."""
    if s[0][2] > m or s[-1][1] < m:
        return None
    for i in range(1, len(s)):
        if m <= s[i][1]:
            a, b = s[i - 1], s[i]
            dep, arr = a[2], b[1]
            f = 0.0 if arr <= dep else max(0.0, min(1.0, (m - dep) / (arr - dep)))
            pa, pb = st[a[0]], st[b[0]]
            return pa[0] + (pb[0] - pa[0]) * f, pa[1] + (pb[1] - pa[1]) * f
    return None


def measure(st, trips, k, W, H, full):
    """Median pixel speed of the dots inside this frame. The latitude the
    frame covers follows from its aspect and the projection, the same way
    the page works it out, so a portrait cut is measured as a portrait cut
    and not as a landscape one lying on its side."""
    span = k["span"] or full
    sx = W / span
    half_lon = span / 2
    half_lat = span * math.cos(math.radians(k["lat"])) / (W / H) / 2
    m0, m1 = k["sec"] / 60.0, (k["sec"] + k["rate"]) / 60.0
    sp = []
    for t in trips:
        a0 = where(st, t["s"], m0)
        if a0 is None:
            continue
        if abs(a0[0] - k["lon"]) > half_lon or abs(a0[1] - k["lat"]) > half_lat:
            continue
        a1 = where(st, t["s"], m1)
        if a1 is None:
            continue
        sp.append(((a1[0] - a0[0]) ** 2 + (a1[1] - a0[1]) ** 2) ** 0.5 * sx)
    return (statistics.median(sp), len(sp)) if sp else (None, 0)


def hm(sec):
    m = int(round(sec / 60))
    return f"{m // 60 % 24:02d}:{m % 60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("data", nargs="+")
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=1280)
    ap.add_argument("--full", type=float, default=20.5,
                    help="the network's own frame width, for span-0 keys")
    ap.add_argument("--alpha", type=float, nargs="*", default=None,
                    help="0 measures only; 1 flattens the film to one speed. "
                         "Several values compare them; the last is printed "
                         "as a clock column.")
    ap.add_argument("--keys", type=float, nargs="*", default=[],
                    help="video seconds to print a proposed clock time for")
    args = ap.parse_args()

    tl = json.load(open(args.timeline, encoding="utf-8"))
    st, trips = load(args.data)
    print(f"{len(trips)} trips, {len(st)} stations, {len(tl)} samples\n")

    rows = []
    for k in tl:
        if k["rate"] <= 0:
            continue
        px, n = measure(st, trips, k, args.width, args.height, args.full)
        if px:
            rows.append((k, px, n))

    px = [r[1] for r in rows]
    print(f"as it stands: median {min(px):.1f} to {max(px):.1f} px/s, "
          f"a {max(px)/min(px):.0f}x spread")
    for k, p, n in rows[::8]:
        print(f"  {k['t']:>6.1f}s  {hm(k['sec'])}  span {k['span'] or args.full:>6.2f}  "
              f"{k['rate']/60:>5.1f} min/s  {p:>6.1f} px/s  {n:>5} trains")
    if not args.alpha:
        return

    # Apparent speed is linear in the clock rate, so this is the rate that
    # would hit `target` exactly, damped by alpha and renormalised so the
    # film still covers one whole day.
    dt = rows[1][0]["t"] - rows[0][0]["t"]
    day = 24 * 3600 - 60
    for alpha in args.alpha:
        w = [k["rate"] / p ** alpha for k, p, _ in rows]
        scale = day / sum(x * dt for x in w)
        rate = [x * scale for x in w]
        newpx = [rows[i][1] * rate[i] / rows[i][0]["rate"]
                 for i in range(len(rows))]
        clock, at_t = 0.0, {}
        for i, (k, _, _) in enumerate(rows):
            at_t[round(k["t"], 3)] = clock
            clock += rate[i] * dt
        print(f"\nalpha {alpha}: median {min(newpx):.1f} to {max(newpx):.1f} "
              f"px/s, a {max(newpx)/min(newpx):.0f}x spread")
        if alpha != args.alpha[-1]:
            for t in args.keys:
                near = min(at_t, key=lambda x: abs(x - t))
                print(f"    {t:>5.0f}s -> {hm(at_t[near])}", end="")
            print()
            continue
        for i in range(0, len(rows), 8):
            k = rows[i][0]
            print(f"  {k['t']:>6.1f}s  {hm(at_t[round(k['t'],3)])}  "
                  f"span {k['span'] or args.full:>6.2f}  {rate[i]/60:>5.1f} min/s  "
                  f"{newpx[i]:>6.1f} px/s")
        if args.keys:
            print("\nclock column for KEYS:")
            for t in args.keys:
                near = min(at_t, key=lambda x: abs(x - t))
                print(f'  [{t:>3.0f}, "{hm(at_t[near])}", ...]')
            print(f"  film ends at {hm(clock)}")


if __name__ == "__main__":
    main()
