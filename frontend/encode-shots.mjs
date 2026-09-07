/**
 * Re-encode the manual's screenshots for print.
 *
 * The first pass was wrong twice over. It capped height at 1500px, which for a
 * full-page capture 8000px tall meant the *height* limit set the scale and the
 * image came out 538px wide — then JPEG at quality 0.62 on top. Placed in a
 * 6.5in column that is roughly 80dpi with visible artefacts.
 *
 * This pass instead:
 *   - crops a very tall capture to a legible aspect rather than shrinking the
 *     whole page into a column, since a 4000px-tall page reduced to 6.5in is
 *     unreadable at any encoding quality;
 *   - scales to a real print resolution — 1800px across a 6.5in column is
 *     ~277dpi, and 760px across the 2.6in phone column is ~290dpi;
 *   - encodes at quality 0.88.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const SHOTS = "shots";
const OUT = "shots-encoded.json";

// Desktop figures run the full 6.5in column; phone figures are capped at 2.6in.
const DESKTOP_W = 1800;
const PHONE_W = 760;

// How tall a figure may be relative to its width before it is cropped. A
// desktop screen is landscape; cropping to 1.45 keeps the top of the page,
// which is what each figure is actually illustrating.
const DESKTOP_MAX_ASPECT = 1.45;
const PHONE_MAX_ASPECT = 2.05;

const PICK = [
  "5-login-desktop", "6-register-desktop", "1-home-desktop", "2-article-desktop",
  "3-about-desktop", "4-search-desktop", "9-home-signedin-desktop", "bell",
  "discussion", "extras", "report", "account", "pricing",
  "7-dashboard-desktop", "editor-desktop", "richtext", "earnings",
  "8-review-desktop", "flagged", "corrections", "moderation", "disputes",
  "admin-overview", "admin-accounts", "admin-applications", "admin-editors",
  "admin-categories", "admin-scoring", "admin-logs",
  "1-home-mobile", "7-dashboard-mobile", "2-article-mobile",
];

const browser = await chromium.launch();
const page = await browser.newPage();
const out = {};
let total = 0;

for (const name of PICK) {
  const file = path.join(SHOTS, name + ".png");
  if (!fs.existsSync(file)) {
    console.log("  MISSING", name);
    continue;
  }
  const phone = name.includes("mobile");
  const src = "data:image/png;base64," + fs.readFileSync(file).toString("base64");

  const res = await page.evaluate(
    async ({ src, targetW, maxAspect }) => {
      const img = new Image();
      img.src = src;
      await img.decode();

      // Crop from the top when the capture is far taller than it is wide.
      const cropH = Math.min(img.height, Math.round(img.width * maxAspect));
      const cropped = cropH < img.height;

      const scale = Math.min(targetW / img.width, 1);
      const w = Math.round(img.width * scale);
      const h = Math.round(cropH * scale);

      const c = document.createElement("canvas");
      c.width = w;
      c.height = h;
      const cx = c.getContext("2d");
      cx.imageSmoothingQuality = "high";
      cx.fillStyle = "#fff";
      cx.fillRect(0, 0, w, h);
      cx.drawImage(img, 0, 0, img.width, cropH, 0, 0, w, h);
      return { data: c.toDataURL("image/jpeg", 0.88), w, h, cropped, srcW: img.width };
    },
    {
      src,
      targetW: phone ? PHONE_W : DESKTOP_W,
      maxAspect: phone ? PHONE_MAX_ASPECT : DESKTOP_MAX_ASPECT,
    },
  );

  out[name] = res.data;
  total += res.data.length;
  const dpi = Math.round(res.w / (phone ? 2.6 : 6.5));
  console.log(
    `  ${name.padEnd(24)} ${String(res.w).padStart(4)}x${String(res.h).padEnd(4)}` +
      ` ${String(dpi).padStart(3)}dpi ${String(Math.round(res.data.length / 1024)).padStart(4)}KB` +
      (res.cropped ? "  cropped" : ""),
  );
}

await browser.close();
fs.writeFileSync(OUT, JSON.stringify(out));
console.log(`\n${Object.keys(out).length} images, ${(total / 1024 / 1024).toFixed(2)} MB`);
