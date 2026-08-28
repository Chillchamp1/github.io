#!/usr/bin/env python3
"""China Railway timetables -> the compact trip format the page draws.

Usage:
    python3 build/build_cn.py raw-timetables.json \\
        --stations raw-stations.json --cities raw-city-coords.json \\
        -o data/cn-trains.json

China publishes no GTFS feed and no open timetable file; the schedule is
queryable one train at a time from the national booking system, and the
input here is a crawl of that. Station coordinates come from a separate
geocoding pass, since the timetable gives names only.
"""
import argparse, collections, datetime, json, math, os, re

# The class letter printed on the train, which is the only tier the source
# gives. Five buckets because the page's palette has five colours, so T
# joins Z as the loco-hauled long-distance pair.
CLASS_OF = {"G": "g", "D": "d", "C": "c", "K": "k", "Z": "zt", "T": "zt"}
CLASSES = ["g", "d", "c", "k", "zt"]

MINUTES_PER_DAY = 1440

# Anything faster is a station geocoded to the wrong province, not a train:
# these are straight-line distances, and track is longer than the straight
# line.
SPEED_LIMIT_KMH = 400

CHINA_BBOX = (73.0, 17.0, 136.0, 54.0)

# Romanisations the gazetteer had none of, from the English Wikipedia
# article each Chinese one links to, or OSM's name:en where there was no
# article. The Uyghur exonyms come from there too -- Yarkant over Shache,
# Kargilik over Yecheng. 三源浦 has neither, so it is plain pinyin. The last
# three are cities the gazetteer left as raw pinyin while a sister station
# carried the exonym, so Wulumuqi and Ürümqi South read as two places.
LATIN_NAMES = {
    "珲春": "Hunchun",          "香格里拉": "Shangri-La",
    "库尔勒": "Korla",           "精河": "Jinghe",
    "博乐": "Bole",             "若羌": "Ruoqiang",
    "鄯善北": "Shanshan North",  "轮台": "Luntai",
    "巴楚": "Maralbexi",        "阿图什": "Artush",
    "叶城": "Kargilik",         "泽普": "Poskam",
    "莎车": "Yarkant",          "英吉沙": "Yengisar",
    "阿克陶": "Akto",            "黑河": "Heihe",
    "长山屯": "Changshantun",    "五台山北": "Wutaishan North",
    "三源浦": "Sanyuanpu",       "乌鲁木齐": "Ürümqi",
    "克拉玛依": "Karamay",       "齐齐哈尔": "Qiqihar",
}

# Stations the geocoding pass could not place at all, each checked against
# the line it sits on. The Kuytun-Tacheng pair carries two stops and the
# whole northwest corner of Xinjiang.
MANUAL_COORDS = {
    "塔城":   [82.9831, 46.6973, "Tacheng"],       # OSM
    "额敏":   [83.5872, 46.5606, "Emin"],          # OSM
    "福海":   [87.4593, 47.1213, "Fuhai"],         # OSM; the gazetteer has only the Yunnan one
    "乌苏":   [84.7153, 44.4077, "Wusu"],          # Wikidata
    "沙湾市": [85.6060, 44.3210, "Shawan"],        # Wikidata
    "精河南": [82.9184, 44.6050, "Jinghe South"],  # Wikidata
    "阿勒泰": [88.0872, 47.7175, "Altay"],         # Wikidata
    "王府":   [124.9997, 44.8794, "Wangfu"],       # Wikidata
    "前山":   [113.5206, 22.2374, "Qianshan"],     # Wikidata; the Zhuhai one, not the Japanese
}

DIRECTIONS = {"北": ("bei", "North"), "南": ("nan", "South"),
              "东": ("dong", "East"),  "西": ("xi", "West")}
ENGLISH_DIRECTION = re.compile(r"\b(North|South|East|West)$")
STATION_SUFFIX = re.compile(r"\s*(railway\s+)?station$", re.I)
TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")


def minutes_of_day(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def inside_china(lon, lat):
    return (CHINA_BBOX[0] <= lon <= CHINA_BBOX[2]
            and CHINA_BBOX[1] <= lat <= CHINA_BBOX[3])


def haversine_km(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 12742 * math.asin(math.sqrt(h))


def join_pinyin_syllables(name):
    """"Wu Lu Mu Qi Zhan" -> "Wulumuqi": place names are written joined, and
    the trailing 站 is the word "station" again."""
    parts = [p for p in name.split() if p.lower() != "zhan"]
    if len(parts) > 1 and all(len(p) <= 6 and p[:1].isupper() for p in parts):
        return parts[0] + "".join(p.lower() for p in parts[1:])
    return " ".join(parts)


def romanise(record):
    for key in ("en", "latin"):
        value = record.get(key)
        if not value:
            continue
        value = re.sub(r"\s+", " ", value).strip()
        value = STATION_SUFFIX.sub("", TRAILING_PAREN.sub("", value)).strip()
        if key == "latin":
            value = join_pinyin_syllables(value)
        if value:
            return value
    return None


def romanisation_quality(record):
    """An exonym beats raw pinyin, which beats nothing: 拉萨 is held twice,
    once as "La Sa" and once as "Lhasa"."""
    if record.get("en"):
        return 2
    if record.get("latin"):
        return 1
    return 0


def expand_direction_suffix(name, label, gazetteer):
    """济南西 is Jinan's west station; 济南 is not Ji's south one.

    The trailing character is a direction only when the stem is itself a
    place, so that is the test rather than a list of exceptions: 无锡东
    splits because 无锡 is in the gazetteer, 丹东 and 淮南 do not."""
    direction = DIRECTIONS.get(name[-1:])
    if not direction or ENGLISH_DIRECTION.search(label) or len(name) < 3:
        return label
    stem_zh = name[:-1]
    if stem_zh not in gazetteer and stem_zh + "站" not in gazetteer:
        return label
    pinyin, word = direction
    stem = label
    if stem.lower().endswith(pinyin) and len(stem) > len(pinyin):
        stem = stem[:-len(pinyin)]
    return f"{stem.rstrip(chr(39) + chr(45) + ' ')} {word}"


def bilingual_label(name, romanisation, gazetteer):
    """北京南 (Beijing South): the Chinese is the name, the rest is a gloss."""
    latin = (LATIN_NAMES.get(name)
             or expand_direction_suffix(name, romanisation or name, gazetteer))
    if not latin or latin == name:
        return name
    return f"{name} ({latin})"


def build_gazetteer(stations, cities):
    """name -> every candidate placement, since station names repeat across
    provinces: a 大安 in Jilin and another by Shenzhen, a 桂林 in Guangxi and
    another in Sichuan. shortest_reading picks between them."""
    gazetteer = collections.defaultdict(list)

    def offer(name, records):
        if isinstance(records, dict):
            records = [records]
        for record in records or []:
            coord = record.get("c")
            if not coord or not inside_china(coord[0], coord[1]):
                continue
            key = (round(coord[0], 3), round(coord[1], 3))
            for i, (lon, lat, label) in enumerate(gazetteer[name]):
                if (round(lon, 3), round(lat, 3)) == key:
                    if romanisation_quality(record) > 0 and not label:
                        gazetteer[name][i] = (lon, lat, romanise(record))
                    break
            else:
                gazetteer[name].append((coord[0], coord[1], romanise(record)))

    for source in (stations, cities):
        for name, records in source.items():
            offer(name, records)
            if name.endswith("站"):
                offer(name[:-1], records)
    return gazetteer


def placements_for(name, gazetteer):
    if name in MANUAL_COORDS:
        lon, lat, label = MANUAL_COORDS[name]
        return [(lon, lat, bilingual_label(name, label, gazetteer))]
    for key in (name, name + "站"):
        if gazetteer.get(key):
            return [(lon, lat, bilingual_label(name, label, gazetteer))
                    for lon, lat, label in gazetteer[key]]
    return []


def shortest_reading(candidates):
    """Choose one placement per stop so the whole run is as short as it can
    be, which is what stops an ambiguous name sending a train to another
    province and back. Exact, since no name has more than four readings."""
    best = [(0.0, None, i) for i in range(len(candidates[0]))]
    backtrack = []
    for step in range(1, len(candidates)):
        previous, current = candidates[step - 1], candidates[step]
        row = []
        for j, place in enumerate(current):
            k = min(range(len(previous)),
                    key=lambda i: best[i][0] + haversine_km(previous[i], place))
            row.append((best[k][0] + haversine_km(previous[k], place), k, j))
        backtrack.append(row)
        best = row
    picks = [min(range(len(best)), key=lambda i: best[i][0])]
    for row in reversed(backtrack):
        picks.append(row[picks[-1]][1])
    return list(reversed(picks))


def accumulate_past_midnight(stops):
    """The source gives time of day only, so each step backwards is another
    midnight crossed. Minutes run past 1440 and past 2880 rather than
    wrapping, which is what lets the page draw a 58-hour sleeper."""
    unrolled, previous, day = [], None, 0
    for name, arrival, departure in stops:
        if previous is not None and arrival + day * MINUTES_PER_DAY < previous:
            day += 1
        arrival += day * MINUTES_PER_DAY
        if departure + day * MINUTES_PER_DAY < arrival:
            day += 1
        departure += day * MINUTES_PER_DAY
        previous = departure
        unrolled.append((name, arrival, departure))
    return unrolled


def enforce_monotonic(sequence):
    for i in range(1, len(sequence)):
        sequence[i][1] = max(sequence[i][1], sequence[i - 1][2])
        sequence[i][2] = max(sequence[i][2], sequence[i][1])
    return sequence


class StationTable:
    """Assigns the indices the trips refer to, collapsing names that share
    a place and a label."""

    def __init__(self):
        self._ids, self.rows = {}, []

    def id_for(self, place):
        lon, lat, label = place
        key = (round(lon, 3), round(lat, 3), label)
        if key not in self._ids:
            self._ids[key] = len(self.rows)
            self.rows.append([round(lon, 4), round(lat, 4), label])
        return self._ids[key]


def read_timetables(raw, gazetteer):
    trains, votes = [], collections.defaultdict(collections.Counter)
    dropped, unplaced = collections.Counter(), collections.Counter()

    for code in sorted(raw):
        record = raw[code]
        if not record or not record.get("stops") or len(record["stops"]) < 2:
            dropped["unusable"] += 1
            continue
        train_class = CLASS_OF.get(code[0].upper())
        if train_class is None:
            dropped["unknown class"] += 1
            continue

        stops, candidates, broken = [], [], False
        for stop in record["stops"]:
            options = placements_for(stop["name"], gazetteer)
            if not options:
                unplaced[stop["name"]] += 1
                continue
            departure = stop.get("dep") or stop.get("arr")
            arrival = stop.get("arr") or stop.get("dep")
            if not departure or not arrival:
                broken = True
                break
            stops.append((stop["name"], minutes_of_day(arrival),
                          minutes_of_day(departure)))
            candidates.append(options)

        if broken:
            dropped["unusable"] += 1
            continue
        if len(stops) < 2:
            dropped["under two placeable stops"] += 1
            continue

        for (name, _, _), pick in zip(stops, shortest_reading(candidates)):
            votes[name][pick] += 1
        trains.append((code, train_class, stops, candidates))

    return trains, votes, dropped, unplaced


def settle_placements(votes):
    """One placement per station, by majority across every train calling
    there, so a name reads the same on all of them."""
    return {name: tally.most_common(1)[0][0] for name, tally in votes.items()}


def impossible_hops(trips, stations):
    """A mis-geocoded station is invisible in a list of names and obvious on
    the map: a train crossing the country between two stops minutes apart."""
    suspects = collections.Counter()
    for trip in trips:
        sequence = trip["s"]
        for i in range(1, len(sequence)):
            hours = (sequence[i][1] - sequence[i - 1][2]) / 60.0
            if hours <= 0:
                continue
            a, b = stations[sequence[i - 1][0]], stations[sequence[i][0]]
            if haversine_km(a, b) / hours > SPEED_LIMIT_KMH:
                suspects[a[2]] += 1
                suspects[b[2]] += 1
    return suspects


def drop_empty_classes(trips, counts):
    live = [c for c in CLASSES if counts[c]]
    if live != CLASSES:
        remap = {CLASSES.index(c): i for i, c in enumerate(live)}
        for trip in trips:
            trip["c"] = remap[trip["c"]]
    return live


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timetables")
    ap.add_argument("--stations", required=True)
    ap.add_argument("--cities", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--date", default="20260726")
    args = ap.parse_args()

    raw = json.load(open(args.timetables, encoding="utf-8"))
    gazetteer = build_gazetteer(
        json.load(open(args.stations, encoding="utf-8")),
        json.load(open(args.cities, encoding="utf-8")))

    trains, votes, dropped, unplaced = read_timetables(raw, gazetteer)
    placement = settle_placements(votes)

    stations = StationTable()
    trips, counts = [], collections.Counter()
    for code, train_class, stops, candidates in trains:
        sequence = []
        for (name, arrival, departure), options in zip(
                accumulate_past_midnight(stops), candidates):
            place = options[min(placement[name], len(options) - 1)]
            sequence.append([stations.id_for(place), arrival, departure])
        enforce_monotonic(sequence)

        terminus = placements_for((raw[code] or {}).get("to", ""), gazetteer)
        trips.append({"c": CLASSES.index(train_class), "n": code,
                      "h": terminus[0][2] if terminus
                           else stations.rows[sequence[-1][0]][2],
                      "s": sequence})
        counts[train_class] += 1

    live = drop_empty_classes(trips, counts)
    day = datetime.date(int(args.date[:4]), int(args.date[4:6]),
                        int(args.date[6:]))
    doc = {"tunit": "min", "date": day.isoformat(),
           "weekday": day.strftime("%A"),
           "classes": live, "counts": {c: counts[c] for c in live},
           "source": "China Railway (12306) published timetables",
           "note": "Source: the per-train stop lists published by China "
                   "Railway's national booking system, crawled 26-28 July "
                   "2026. No service calendar is published, so every train "
                   "is drawn as running on the day shown.",
           "stations": stations.rows, "trips": trips}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)

    print(f"{args.out}: {len(trips)} trips, {len(stations.rows)} stations, "
          f"{os.path.getsize(args.out)/1e6:.2f} MB")
    for train_class in live:
        print(f"  {train_class:<3} {counts[train_class]}")
    print(f"  {sum(1 for t in votes.values() if len(t) > 1)} "
          f"ambiguous names resolved by route")
    print("  dropped: " + ", ".join(f"{n} {reason}"
                                    for reason, n in sorted(dropped.items())))
    if unplaced:
        print(f"  {len(unplaced)} names without coordinates, "
              f"{sum(unplaced.values())} stop events")

    suspects = impossible_hops(trips, stations.rows)
    if suspects:
        print(f"  WARNING: {len(suspects)} stations sit on hops implying more "
              f"than {SPEED_LIMIT_KMH} km/h -- probably geocoded to a "
              f"same-named place elsewhere:")
        for name, n in suspects.most_common(12):
            print(f"    {name}  x{n}")


if __name__ == "__main__":
    main()
