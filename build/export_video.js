#!/usr/bin/env node
/* Render index.html to a portrait MP4 for phones and social posts.
 *
 *   node build/export_video.js [--seconds 60] [--fps 30] [--start 12:00]
 *                              [--width 540] [--height 960] [--scale 2]
 *                              [--out day.mp4]
 *
 * Needs playwright (any recent Chromium) and ffmpeg on PATH; if ffmpeg is
 * missing, `pip install imageio-ffmpeg` supplies one and this script finds it.
 *
 * Playback is not recorded in real time -- the page is paused and the scrubber
 * is stepped one frame at a time, so every frame lands on an exact simulated
 * minute no matter how long the render takes. Frames go out as JPEG because
 * PNG encoding at 1080x1920 costs more per frame than the page takes to draw.
 */
const {chromium} = require("playwright");
const {execFileSync, spawnSync} = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");

const argv = process.argv.slice(2);
const arg = (name, dflt) => {
  const i = argv.indexOf("--" + name);
  return i === -1 ? dflt : argv[i + 1];
};
const SECONDS = Number(arg("seconds", 60));
const FPS     = Number(arg("fps", 30));
const WIDTH   = Number(arg("width", 540));    /* CSS px; x scale = pixels */
const HEIGHT  = Number(arg("height", 960));
const SCALE   = Number(arg("scale", 2));
/* Clock time the day opens on, HH:MM. Omit to start where the page does,
   at the quietest minute of the night. */
const START   = arg("start", "");
const OUT     = path.resolve(arg("out", "german-rail-day.mp4"));
const PAGE    = path.resolve(arg("page", path.join(__dirname, "..", "index.html")));

/* ffmpeg from PATH, else the one imageio-ffmpeg bundles. */
function ffmpeg(){
  if (spawnSync("ffmpeg", ["-version"], {stdio:"ignore"}).status === 0) return "ffmpeg";
  try {
    return execFileSync("python3",
      ["-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
      {encoding:"utf8"}).trim();
  } catch {
    throw new Error("no ffmpeg: install it, or `pip install imageio-ffmpeg`");
  }
}

(async () => {
  const FF = ffmpeg();
  const N = Math.round(FPS * SECONDS), DAY = 86400, STEP = DAY / N;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "railframes-"));

  const browser = await chromium.launch();
  const page = await browser.newPage({viewport:{width:WIDTH, height:HEIGHT},
                                      deviceScaleFactor:SCALE});
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  await page.goto("file://" + PAGE);
  await page.waitForTimeout(1500);
  /* The scroll hint belongs to the page, not to the picture. */
  await page.addStyleTag({content:"#hint{display:none!important}"});
  await page.$eval("#play", el => el.click());        /* pause */
  let start = await page.evaluate(
    () => Number(document.getElementById("scrub").value));
  if (START){
    const [h, m] = START.split(":").map(Number);
    if (!Number.isFinite(h) || !Number.isFinite(m))
      throw new Error(`--start wants HH:MM, got ${START}`);
    start = ((h*3600 + m*60) % 86400 + 86400) % 86400;
  }

  const clip = {x:0, y:0, width:WIDTH, height:HEIGHT};
  const t0 = Date.now();
  let simT = 0, frames = 0;
  for (let i = 0; i < N * 2 && simT < DAY; i++){
    await page.$eval("#scrub", (el, v) => {
      el.value = v;
      el.dispatchEvent(new Event("input", {bubbles:true}));
    }, Math.round((start + simT) % DAY));
    await page.evaluate(() => new Promise(r => requestAnimationFrame(r)));
    await page.screenshot({path:path.join(dir, `f${String(frames).padStart(5,"0")}.jpg`),
                           type:"jpeg", quality:92, clip});
    frames++;
    let mult = 1;
    if (WARP > 0){
      const n = await page.$eval("#running", el => parseInt(el.textContent) || 0);
      if (n < WARP) mult = 20;
    }
    simT += STEP * mult;
    if (frames % 100 === 0){
      const per = (Date.now()-t0)/frames;
      process.stdout.write(
        `  ${frames} frames, day ${(100*simT/DAY).toFixed(0)}%  ${per.toFixed(0)} ms/frame\n`);
    }
  }
  await browser.close();
  if (errs.length) process.stdout.write("page errors: " + errs.join(" | ") + "\n");

  /* yuv420p + High@4.0 + faststart is the combination phone players and the
     social sites all accept; crf 20 keeps the one-pixel train dots intact. */
  execFileSync(FF, ["-hide_banner", "-loglevel", "error", "-y",
    "-framerate", String(FPS), "-i", path.join(dir, "f%05d.jpg"),
    "-c:v", "libx264", "-preset", "slow", "-crf", "20",
    "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
    "-movflags", "+faststart", OUT], {stdio:"inherit"});
  fs.rmSync(dir, {recursive:true, force:true});

  const mb = (fs.statSync(OUT).size/1e6).toFixed(1);
  process.stdout.write(
    `${OUT}: ${WIDTH*SCALE}x${HEIGHT*SCALE}, ${SECONDS}s at ${FPS} fps, ${mb} MB\n`);
})();
