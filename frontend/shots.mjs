/**
 * Batched visual inspection.
 *
 * Captures every designed surface at desktop and mobile in one run, and reports
 * anything the page tells us is wrong: console errors, failed requests, and
 * horizontal overflow of the body (the single most common responsive defect).
 *
 *   node shots.mjs
 */
import { mkdirSync } from "node:fs";

import { chromium } from "playwright";

// Override for a deployed environment:
//   WEB=https://... API=https://.../api node shots.mjs
const WEB = process.env.WEB || "http://localhost:5173";
const API = process.env.API || "http://127.0.0.1:5000/api";
const OUT = "shots";

const VIEWPORTS = {
  desktop: { width: 1440, height: 1000 },
  mobile: { width: 390, height: 844 },
};

async function tokenFor(email) {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: "DemoPassword123!" }),
  });
  if (!res.ok) throw new Error(`login failed for ${email}: ${res.status}`);
  return (await res.json()).token;
}

async function firstSlug() {
  const res = await fetch(`${API}/feed/trending`);
  return (await res.json()).articles[0].slug;
}

const problems = [];

async function shoot(browser, { name, path, viewport, token, full = true }) {
  const context = await browser.newContext({
    viewport: VIEWPORTS[viewport],
    deviceScaleFactor: 2,
  });

  if (token) {
    await context.addInitScript((t) => {
      localStorage.setItem("nrs.token", t);
    }, token);
  }

  const page = await context.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      // React's dev-mode router future-flag notices are not defects.
      if (!text.includes("React Router Future Flag")) {
        problems.push(`[console] ${name}/${viewport}: ${text.slice(0, 160)}`);
      }
    }
  });
  page.on("pageerror", (err) =>
    problems.push(`[crash] ${name}/${viewport}: ${err.message.slice(0, 160)}`),
  );
  page.on("requestfailed", (req) =>
    problems.push(`[request] ${name}/${viewport}: ${req.url().slice(0, 100)}`),
  );

  await page.goto(`${WEB}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(700); // let the one authored animation settle

  // Horizontal overflow.
  //
  // Measured on body, not documentElement: Chromium's documentElement
  // .scrollWidth counts content inside overflow containers that the user can
  // never scroll the page to, so it reports a table-in-a-scroller as a page
  // defect. body.scrollWidth is what actually decides whether the page scrolls.
  const overflow = await page.evaluate(
    () => document.body.scrollWidth - document.documentElement.clientWidth,
  );
  if (overflow > 1) {
    problems.push(`[overflow] ${name}/${viewport}: page scrolls ${overflow}px sideways`);
  }

  // Elements wider than the viewport *that nothing can scroll*: the real cause
  // of sideways drift, and of content clipped with no way to reach it.
  const wide = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const scrollableAncestor = (el) => {
      let n = el.parentElement;
      while (n && n !== document.documentElement) {
        const ox = getComputedStyle(n).overflowX;
        if (ox === "auto" || ox === "scroll" || ox === "hidden") return true;
        n = n.parentElement;
      }
      return false;
    };
    return [...document.querySelectorAll("*")]
      .filter((el) => el.getBoundingClientRect().width > vw + 1 && !scrollableAncestor(el))
      .slice(0, 4)
      .map((el) => `${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ")[0]}`);
  });
  if (wide.length) {
    problems.push(`[wide] ${name}/${viewport}: ${wide.join(", ")}`);
  }

  // Text that would fail WCAG AA. Cheap to check here, expensive to find later.
  const contrast = await page.evaluate(() => {
    const lum = (rgb) => {
      const [r, g, b] = rgb.map((v) => {
        const s = v / 255;
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const parse = (c) => (c.match(/\d+/g) || []).slice(0, 3).map(Number);
    const bgOf = (el) => {
      let n = el;
      while (n && n !== document.documentElement) {
        const bg = getComputedStyle(n).backgroundColor;
        if (bg && !bg.includes("rgba(0, 0, 0, 0)")) return parse(bg);
        n = n.parentElement;
      }
      return [255, 255, 255];
    };
    const bad = [];
    for (const el of document.querySelectorAll("p,span,a,li,dt,dd,td,th,h1,h2,h3,label,button")) {
      if (!el.textContent.trim() || el.children.length) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") continue;
      const size = parseFloat(cs.fontSize);
      const weight = Number(cs.fontWeight) || 400;
      const large = size >= 24 || (size >= 18.66 && weight >= 700);
      const l1 = lum(parse(cs.color));
      const l2 = lum(bgOf(el));
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      if (ratio < (large ? 3 : 4.5)) {
        bad.push(`${el.tagName.toLowerCase()}.${(el.className || "").toString().split(" ")[0]} ${ratio.toFixed(2)}`);
      }
    }
    return [...new Set(bad)].slice(0, 4);
  });
  if (contrast.length) {
    problems.push(`[contrast] ${name}/${viewport}: ${contrast.join(", ")}`);
  }

  await page.screenshot({
    path: `${OUT}/${name}-${viewport}.png`,
    fullPage: full,
  });

  await context.close();
}

const run = async () => {
  mkdirSync(OUT, { recursive: true });

  const slug = await firstSlug();
  const contributor = await tokenFor("veteran@newsrelease.test");
  const editor = await tokenFor("editor.tech@newsrelease.test");
  const reader = await tokenFor("reader@newsrelease.test");

  const targets = [
    { name: "1-home", path: "/" },
    { name: "2-article", path: `/articles/${slug}` },
    { name: "3-about", path: "/about" },
    { name: "4-search", path: "/search?q=renewable" },
    { name: "5-login", path: "/login" },
    { name: "6-register", path: "/register" },
    { name: "7-dashboard", path: "/dashboard", token: contributor },
    { name: "8-review", path: "/review", token: editor },
    { name: "9-home-signedin", path: "/", token: reader },
    { name: "10-notfound", path: "/nope" },
  ];

  const browser = await chromium.launch();
  for (const target of targets) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      await shoot(browser, { ...target, viewport });
      process.stdout.write(".");
    }
  }
  await browser.close();

  console.log(`\n\ncaptured ${targets.length * 2} screenshots into ${OUT}/\n`);

  if (problems.length === 0) {
    console.log("no console errors, failed requests, or overflow detected.");
  } else {
    console.log(`${problems.length} problem(s):\n`);
    for (const p of [...new Set(problems)]) console.log("  " + p);
  }
};

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
