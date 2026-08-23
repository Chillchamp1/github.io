#!/usr/bin/env node
/* Render a guided tour of the combined map to MP4.
 *
 *   node build/export_tour.js [--url http://127.0.0.1:8931/index.html]
 *                             [--fps 30] [--width 1280] [--height 720]
 *                             [--scale 1.5] [--crf 20] [--out rail-tour.mp4]
 *
 * Unlike export_video.js, which holds one frame still for a whole day, this
 * moves: a scripted camera flies over France, the Benelux, Switzerland and
 * Germany while the clock runs, lingering on the morning hours when the
 * network fills up and closing in on Berlin, where the city's own map --
 * S-Bahn, U-Bahn and tram, which the national feeds leave out -- fades in
 * over the top.
 *
 * That last part is why there are two passes. The Berlin close-up is
 * rendered a second time against the #berlin network with the identical
 * camera and clock, and ffmpeg cross-fades it onto the base. The overlay
 * frames are opaque, so anything the base drew is covered while they are
 * up: the clock is pinned to the pixel the base pass put it on and runs in
 * both passes, and the on-canvas key is left to change, which is the point
 * -- the legend turns into S-Bahn, U-Bahn and tram as the city appears.
 *
 * Frames are kept under --frames and reused if they are already there, so
 * adjusting one pass does not mean re-rendering the other.
 *
 * The camera is driven through window.railCam, a small hook the page
 * exposes for exactly this; synthesising wheel events could not place a
 * frame precisely enough to interpolate.
 */
const {chromium} = require("playwright");
const {execFileSync, spawnSync} = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");

const argv = process.argv.slice(2);
const arg = (n, d) => { const i = argv.indexOf("--" + n);
                        return i === -1 ? d : argv[i + 1]; };
const URL    = arg("url", "http://127.0.0.1:8931/index.html");
const FPS    = Number(arg("fps", 30));
const WIDTH  = Number(arg("width", 1280));
const HEIGHT = Number(arg("height", 720));
const SCALE  = Number(arg("scale", 1.5));
const CRF    = arg("crf", "20");
const OUT    = path.resolve(arg("out", "rail-tour.mp4"));
const FRAMES = path.resolve(arg("frames",
                 path.join(os.tmpdir(), "rail-tour-frames")));
const FRESH  = argv.includes("--fresh");

/* The route. Each key is [video second, clock "HH:MM", lon, lat, span in
   degrees of longitude]. span 0 means the network's own full frame.
   Time is deliberately uneven -- five morning hours get half the film --
   but it never stops; see CLOCK below. */
const KEYS = [
  [  0, "00:00",  4.9, 48.8, 0    ],   /* the whole picture, empty night   */
  [  7, "03:00",  4.9, 48.8, 0    ],
  [ 15, "05:00",  7.0, 50.0, 12.0 ],   /* leaning in as the day starts     */
  [ 26, "06:15",  6.4, 50.8,  6.0 ],   /* Rhine-Ruhr and the Randstad      */
  [ 38, "07:15",  5.2, 51.6,  3.6 ],   /* the densest corner of Europe     */
  [ 44, "07:45",  6.7, 49.4,  7.5 ],   /* out over the empty Eifel         */
  [ 50, "08:15",  8.2, 47.3,  3.6 ],   /* south to Switzerland             */
  [ 56, "08:40",  5.6, 47.6,  9.0 ],   /* out again, over the Jura         */
  [ 62, "09:00",  3.1, 47.9,  7.0 ],   /* west to the French star          */
  [ 72, "10:30",  4.9, 48.8, 0    ],   /* back out to everything           */
  [ 82, "13:00",  4.9, 48.8, 0    ],
  [ 90, "14:30", 13.40, 52.52, 5.0],   /* the run at Berlin                */
  [ 99, "15:40", 13.40, 52.52, 1.10],  /* city scale: the overlay begins   */
  [110, "17:10", 13.40, 52.51, 0.62],  /* rush hour, closest in            */
  [118, "18:10", 13.40, 52.52, 2.20],  /* pulling back out                 */
  [126, "20:00",  4.9, 48.8, 0    ],   /* the evening, whole again         */
  [136, "23:59",  4.9, 48.8, 0    ],
];
/* Where the Berlin layer is wanted, and the longest cross-fade worth using.
   The window is trimmed at render time to the part of it the city's own
   frame can actually cover -- see the overlay pass. */
const OVERLAY = {start: 96, end: 121, fade: 3.5};

const DUR = KEYS[KEYS.length - 1][0];
const hhmm = s => { const [h, m] = s.split(":").map(Number); return h*3600 + m*60; };

/* Ease so the camera never starts or stops with a jerk. */
const ease = t => t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3)/2;

/* The clock is its own channel and must not be eased. Easing is what makes
   the camera read as a camera, but its slope is zero at every key, so an
   eased clock stops the day dead seventeen times and starts it again --
   time visibly stalling whenever the flight settles. A monotone cubic
   (Fritsch-Carlson) through the same keys fixes that: the rate is
   continuous, it never overshoots, and where the timetable only runs
   forward it never reaches zero. The morning still gets half the film; the
   clock simply keeps going while it does. */
const CLOCK = (() => {
  const x = KEYS.map(k => k[0]), y = KEYS.map(k => hhmm(k[1])), n = x.length;
  const h = [], d = [];
  for (let i = 0; i < n-1; i++){ h.push(x[i+1]-x[i]); d.push((y[i+1]-y[i])/h[i]); }
  const m = new Array(n);
  m[0] = d[0]; m[n-1] = d[n-2];
  for (let i = 1; i < n-1; i++){
    if (d[i-1]*d[i] <= 0){ m[i] = 0; continue; }
    /* Weighted harmonic mean of the neighbouring rates: a short segment
       cannot drag a long one's speed around. */
    const w1 = 2*h[i] + h[i-1], w2 = h[i] + 2*h[i-1];
    m[i] = (w1 + w2) / (w1/d[i-1] + w2/d[i]);
  }
  return tv => {
    if (tv <= x[0]) return y[0];
    if (tv >= x[n-1]) return y[n-1];
    let i = 0; while (i < n-2 && tv >= x[i+1]) i++;
    const t = (tv - x[i]) / h[i], t2 = t*t, t3 = t2*t;
    return (2*t3 - 3*t2 + 1)*y[i] + (t3 - 2*t2 + t)*h[i]*m[i]
         + (-2*t3 + 3*t2)*y[i+1] + (t3 - t2)*h[i]*m[i+1];
  };
})();

function at(tv){
  let i = 0;
  while (i < KEYS.length - 2 && tv >= KEYS[i+1][0]) i++;
  const a = KEYS[i], b = KEYS[i+1];
  const raw = (tv - a[0]) / (b[0] - a[0]);
  const f = ease(Math.max(0, Math.min(1, raw)));
  const sec = CLOCK(tv);
  /* Zoom reads evenly only if it is interpolated multiplicatively; a
     "whole frame" key borrows its partner's span so the flight in and out
     stays smooth instead of snapping. */
  const FULL = 21.0;
  const sa = a[4] || FULL, sb = b[4] || FULL;
  const span = Math.exp(Math.log(sa) + (Math.log(sb) - Math.log(sa)) * f);
  return {
    sec,
    lon: a[2] + (b[2] - a[2]) * f,
    lat: a[3] + (b[3] - a[3]) * f,
    span: (!a[4] && !b[4]) ? 0 : span,
  };
}

function ffmpeg(){
  if (spawnSync("ffmpeg", ["-version"], {stdio:"ignore"}).status === 0) return "ffmpeg";
  return execFileSync("python3",
    ["-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
    {encoding:"utf8"}).trim();
}

async function shoot(page, dir, from, to, label){
  const clip = {x:0, y:0, width:WIDTH, height:HEIGHT};
  const n0 = Math.round(from * FPS);
  const n1 = Math.round(to * FPS);
  const t0 = Date.now();
  let done = 0;
  for (let n = n0; n < n1; n++){
    const out = path.join(dir, `f${String(n).padStart(5,"0")}.jpg`);
    if (fs.existsSync(out)){ done++; continue; }
    const c = at(n / FPS);
    await page.evaluate(([sec, lon, lat, span]) => {
      window.railCam.time(sec);
      window.railCam.camera(lon, lat, span);
      window.railCam.frame();
    }, [c.sec, c.lon, c.lat, c.span]);
    await page.screenshot({path: out, type:"jpeg", quality:92, clip});
    if ((n - n0) % 120 === 0 && n > n0){
      const per = (Date.now()-t0) / (n - n0 - done);
      process.stdout.write(`  ${label} ${n-n0}/${n1-n0} frames, ${per.toFixed(0)} ms/frame\n`);
    }
  }
  if (done) process.stdout.write(`  ${label}: reused ${done} frames\n`);
}

(async () => {
  const FF = ffmpeg();
  const base = path.join(FRAMES, "base"), over = path.join(FRAMES, "over");
  if (FRESH) fs.rmSync(FRAMES, {recursive:true, force:true});
  for (const d of [base, over]) fs.mkdirSync(d, {recursive:true});

  const browser = await chromium.launch();
  const page = await browser.newPage({viewport:{width:WIDTH, height:HEIGHT},
                                      deviceScaleFactor:SCALE});
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));

  /* Base pass: the combined map, whole tour. */
  await page.goto(URL + "#eu");
  await page.waitForFunction(() => document.getElementById("loading").hidden,
                             null, {timeout:180000});
  /* The regional layer arrives after the first paint; the tour is about
     those small trains, so wait for them. */
  await page.waitForFunction(() => window.railCam && window.railCam.deferredLoaded(),
                             null, {timeout:300000});
  await page.evaluate(() => window.railCam.play(false));
  /* Strip the app furniture: the compact on-canvas key stays and is the
     only legend the film needs, and it swaps to Berlin's categories with
     the overlay. */
  await page.addStyleTag({content:
    "#hint,#nets,#meta,#controls,#figbtn,#legend{display:none!important}"});
  await page.waitForTimeout(500);
  process.stdout.write(`base pass: ${Math.round(DUR*FPS)} frames\n`);
  await shoot(page, base, 0, DUR, "base");

  /* Overlay pass: the same window and clock, drawn from Berlin's own
     network. Its frames are opaque, so the base pass's clock would simply
     disappear behind them; instead the clock is pinned to exactly the pixel
     the base put it on and drawn again here. Same face, same minute, so the
     cross-fade does not touch it -- only the count beneath it, which becomes
     Berlin's, along with the key. */
  const hdr = await page.evaluate(() => {
    const h = document.querySelector("header");
    return {left: h.style.left, top: h.style.top};
  });
  await page.addStyleTag({content:
    `header{left:${hdr.left}!important;top:${hdr.top}!important}`});
  await page.evaluate(() => window.railCam.net("berlin", "berlin"));
  await page.waitForFunction(() => document.getElementById("loading").hidden,
                             null, {timeout:180000});
  await page.evaluate(() => window.railCam.play(false));
  await page.waitForTimeout(400);

  /* No network zooms out past its own preset, and Berlin's frame is a
     degree and a quarter wide. Ask for more than that and the overlay pass
     quietly stops following the camera while the base pass keeps pulling
     out, so the two would cross-fade the same city at two different sizes.
     Trim the window to the stretch where they agree instead of trusting a
     hand-set constant to stay true when the route is edited. */
  const bspan = await page.evaluate(() => window.railCam.baseSpan());
  const step = 1/FPS;
  let ovStart = OVERLAY.start, ovEnd = OVERLAY.end;
  while (ovStart < ovEnd && at(ovStart).span > bspan)     ovStart += step;
  while (ovEnd > ovStart && at(ovEnd - step).span > bspan) ovEnd  -= step;
  ovStart = Math.ceil(ovStart*FPS)/FPS;
  ovEnd   = Math.floor(ovEnd*FPS)/FPS;
  const ovDur  = ovEnd - ovStart;
  const ovFade = Math.min(OVERLAY.fade, ovDur/3);
  if (ovDur < 2) throw new Error(
    `the route never comes inside Berlin's ${bspan.toFixed(2)}deg frame`);
  process.stdout.write(
    `overlay pass: ${Math.round(ovDur*FPS)} frames, ` +
    `${ovStart.toFixed(2)}-${ovEnd.toFixed(2)}s inside a ` +
    `${bspan.toFixed(2)}deg frame, ${ovFade.toFixed(2)}s fade\n`);
  await shoot(page, over, ovStart, ovEnd, "berlin");

  await browser.close();
  if (errs.length) process.stdout.write("page errors: " + errs.join(" | ") + "\n");

  /* Two sequences, one cross-fade. The overlay is faded in and out on its
     own alpha and dropped onto the base at the right second. */
  const a = path.join(base, "f%05d.jpg");
  const b = path.join(over, "f%05d.jpg");
  const startN = Math.round(ovStart * FPS);
  execFileSync(FF, ["-hide_banner", "-loglevel", "error", "-y",
    "-framerate", String(FPS), "-i", a,
    "-framerate", String(FPS), "-start_number", String(startN),
    "-t", ovDur.toFixed(3), "-i", b,
    "-filter_complex",
      `[1:v]format=yuva420p,` +
      `fade=t=in:st=0:d=${ovFade.toFixed(3)}:alpha=1,` +
      `fade=t=out:st=${(ovDur - ovFade).toFixed(3)}:d=${ovFade.toFixed(3)}:alpha=1,` +
      `setpts=PTS+${ovStart.toFixed(3)}/TB[ov];` +
      `[0:v][ov]overlay=eof_action=pass:format=auto[v]`,
    "-map", "[v]",
    "-c:v", "libx264", "-preset", "slow", "-crf", CRF, "-tune", "animation",
    "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
    "-movflags", "+faststart", OUT], {stdio:"inherit"});

  const mb = (fs.statSync(OUT).size/1e6).toFixed(1);
  process.stdout.write(
    `${OUT}: ${WIDTH*SCALE}x${HEIGHT*SCALE}, ${DUR}s at ${FPS} fps, ${mb} MB\n`);
})();
