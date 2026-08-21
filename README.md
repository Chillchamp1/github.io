# A Wednesday on the German rail network

A 24-hour time-lapse of every scheduled long-distance train in Germany, drawn
from the published timetable. The background follows the real position of the
sun over central Germany, so the map slides into a navigation-map night as the
simulated day passes.

Open `index.html` — it is self-contained, so a local double-click works as well
as GitHub Pages. No server, no build step, no network calls except the webfont.

## What is on screen

| | |
|---|---|
| **ICE** | high-speed services |
| **IC / EC** | intercity and EuroCity |
| **RE / RB** | regional |
| **Night & international** | NightJet, EuroNight, TGV, Railjet |

Urban transit — S-Bahn, U-Bahn, tram, bus — is filtered out; at national scale
it would bury everything else. Each train carries a 40-minute tail so the
direction of travel reads at a glance. Hover a train for its number and
destination. Space bar toggles playback.

## The data

`data/trains.json` is built from [`fredlockheed/db-fv-gtfs`](https://github.com/fredlockheed/db-fv-gtfs),
an unofficial GTFS conversion of DB's public API by Patrick Brosi. The bundled
extract is **Wednesday 6 March 2019**, a normal midweek day away from holidays
and timetable changes: 713 trains, 565 stations.

**That feed is long-distance only.** It carries just four regional routes, so
the green category is nearly empty — this is a property of the source, not of
the German network, which runs on the order of 20,000 regional services a day.
Regional coverage needs a second feed; see below.

## Rebuilding

```sh
git clone https://github.com/fredlockheed/db-fv-gtfs /tmp/db-fv-gtfs
python3 build/build_gtfs.py /tmp/db-fv-gtfs/2019 20190306 -o data/trains.json
python3 build/bundle.py          # inlines the JSON back into index.html
```

`build_gtfs.py` takes any GTFS feed and any service date. It reads `calendar.txt`
and `calendar_dates.txt`, keeps rail and drops urban transit, and writes a
compact JSON of stations and stop-time sequences. Nothing in `index.html` is
specific to this feed.

### Adding real regional trains

[gtfs.de](https://gtfs.de/en/feeds/) publishes Germany-wide feeds derived from
the DELFI dataset under CC BY-SA 4.0 — `de_rv` is regional rail, `de_fv` is
long distance. Both work with the extractor as-is:

```sh
curl -o de_rv.zip https://download.gtfs.de/germany/rv_free/latest.zip
unzip -d de_rv de_rv.zip
python3 build/build_gtfs.py de_rv 20260826 -o data/trains.json
python3 build/bundle.py
```

The regional feed is far larger, so expect a heavier JSON and thin the trip list
if the animation drops frames. For a current long-distance feed use `de_fv` the
same way — the 2019 extract is bundled only because it is small and reachable
from a sandbox.

## Layout

```
index.html            the whole visualisation, data inlined
data/trains.json      generated extract
build/build_gtfs.py   GTFS -> JSON
build/bundle.py       JSON -> inlined into index.html
```

## Colour

The four categories use the first three slots of a colourblind-safe categorical
palette plus a neutral. The three hues clear all-pairs CVD and normal-vision
separation against *both* the day and the night background; no fourth hue does,
which is why night trains are grey rather than a fourth colour. Text and panels
switch across a narrow band at dusk instead of cross-fading, because fading ink
and its panel through the same mid-grey destroys their contrast.
