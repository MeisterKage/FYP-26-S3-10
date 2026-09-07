/**
 * Restyle the technical report and user manual to match FYP-26-S3-10_PDD.docx,
 * then render each to PDF.
 *
 * Three things happen that a plain browser print will not do:
 *
 *   1. The authored stylesheet is swapped for docs/pdd-style.css — Arial, black,
 *      US Letter, 1in margins, the PDD's own heading sizes.
 *   2. A contents page is built from the navigation rail, then the PDF is
 *      rendered once, read back to find which page each heading landed on, and
 *      rendered again with the real page numbers filled in.
 *   3. Mermaid is injected, because the diagrams are authored as
 *      <pre class="mermaid"> for the artifact host and nothing draws them in a
 *      local file.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const DOCS = "D:/Shawn/Claude Code/FYP/docs";
const OUT = path.join(DOCS, "pdf");
fs.mkdirSync(OUT, { recursive: true });

const CSS = fs.readFileSync(path.join(DOCS, "pdd-style.css"), "utf8");
const MERMAID = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js";

/* Black on white, matching the PDD. */
const MERMAID_CFG = {
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "loose",
  fontFamily: "Arial, Helvetica, sans-serif",
  themeVariables: {
    background: "#ffffff", primaryColor: "#ffffff", primaryTextColor: "#000000",
    primaryBorderColor: "#000000", secondaryColor: "#f3f3f3", tertiaryColor: "#fafafa",
    lineColor: "#333333", textColor: "#000000", mainBkg: "#ffffff", nodeBorder: "#000000",
    clusterBkg: "#fafafa", clusterBorder: "#767676", edgeLabelBackground: "#ffffff",
    fontSize: "13px",
    actorBkg: "#ffffff", actorBorder: "#000000", actorTextColor: "#000000",
    signalColor: "#333333", signalTextColor: "#000000",
    labelBoxBkgColor: "#f3f3f3", labelBoxBorderColor: "#767676",
    labelTextColor: "#000000", loopTextColor: "#000000",
    activationBkgColor: "#f3f3f3", activationBorderColor: "#333333",
    sequenceNumberColor: "#ffffff",
    sectionBkgColor: "#fafafa", altSectionBkgColor: "#ffffff", sectionBkgColor2: "#f3f3f3",
    taskBkgColor: "#dddddd", taskBorderColor: "#333333", taskTextColor: "#000000",
    taskTextOutsideColor: "#000000", taskTextDarkColor: "#000000",
    activeTaskBkgColor: "#8a8a8a", activeTaskBorderColor: "#000000",
    doneTaskBkgColor: "#f3f3f3", doneTaskBorderColor: "#767676",
    critBkgColor: "#555555", critBorderColor: "#000000",
    gridColor: "#c8c8c8", todayLineColor: "#000000", labelColor: "#000000",
  },
};

const JOBS = [
  { file: "technical-report.html", pdf: "FYP-26-S3-10 Technical Report.pdf" },
  { file: "user-manual.html",      pdf: "FYP-26-S3-10 User Manual.pdf" },
];

/* -- 1. rewrite the HTML --------------------------------------------------- */

function restyle(file) {
  const p = path.join(DOCS, file);
  let h = fs.readFileSync(p, "utf8");

  // Arial is a system font; the webfont links are now dead weight.
  h = h.replace(/<link rel="preconnect"[^>]*>\s*/g, "");
  h = h.replace(/<link rel="stylesheet" href="https:\/\/fonts\.googleapis[^>]*>\s*/g, "");

  // Swap the authored stylesheet for the PDD-matched one.
  const a = h.indexOf("<style>"), b = h.indexOf("</style>");
  if (a < 0 || b < 0) throw new Error("no <style> block in " + file);
  h = h.slice(0, a) + "<style>\n" + CSS + "\n</style>" + h.slice(b + 8);

  // Build a printed contents page from the navigation rail, if not already there.
  if (!h.includes('class="contents-page"')) {
    const nav = h.match(/<nav class="toc"[\s\S]*?<\/nav>/);
    if (nav) {
      const entries = [...nav[0].matchAll(
        /<a(?:\s+class="(top)")?\s+href="(#[^"]+)"[^>]*>(?:<span class="n">([^<]*)<\/span>)?([\s\S]*?)<\/a>/g,
      )].map((m) => {
        const label = m[4].replace(/<[^>]*>/g, "").trim();
        const num = (m[3] || "").trim();
        const isTop = m[1] === "top";
        const depth = isTop ? 1 : (label.match(/^\d+\.\d+\.\d+/) ? 3 : 2);
        return { href: m[2], num, label, depth };
      }).filter((e) => e.label);

      const rows = entries.map((e) => {
        const text = e.num ? `${e.num}. ${e.label}` : e.label;
        return `      <li class="lvl${e.depth}"><a href="${e.href}">` +
               `<span class="lbl">${text}</span>` +
               `<span class="dots"></span>` +
               `<span class="pg" data-pg-for="${e.href.slice(1)}">—</span></a></li>`;
      }).join("\n");

      const page =
        `\n  <section class="contents-page">\n` +
        `    <h2>Contents</h2>\n` +
        `    <ol class="contents-list">\n${rows}\n    </ol>\n` +
        `  </section>\n`;

      const anchor = h.indexOf("</header>");
      if (anchor > 0) h = h.slice(0, anchor + 9) + page + h.slice(anchor + 9);
    }
  }

  fs.writeFileSync(p, h);
  return p;
}

/* -- 2. render ------------------------------------------------------------- */

async function render(browser, srcPath, outPath) {
  const page = await browser.newPage({ viewport: { width: 1100, height: 1400 } });
  await page.goto("file:///" + srcPath.replace(/\\/g, "/"), { waitUntil: "networkidle" });

  const blocks = await page.locator("pre.mermaid").count();
  if (blocks) {
    await page.addScriptTag({ url: MERMAID });
    await page.evaluate(async (cfg) => {
      mermaid.initialize(cfg);
      await mermaid.run({ querySelector: "pre.mermaid" });
    }, MERMAID_CFG);
  }
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(900);

  await page.pdf({
    path: outPath,
    format: "Letter",
    printBackground: true,
    margin: { top: "1in", bottom: "1in", left: "1in", right: "1in" },
    displayHeaderFooter: true,
    headerTemplate: `<div style="font:8pt Arial;color:#666;width:100%;padding:0 1in;">
      <span style="float:left">FYP-26-S3-10</span></div>`,
    footerTemplate: `<div style="font:9pt Arial;color:#000;width:100%;padding:0 1in;text-align:center;">
      <span class="pageNumber"></span></div>`,
  });
  await page.close();
  return blocks;
}

/* -- 3. read page numbers back out of the PDF ------------------------------ */

async function pageNumbers(pdfPath, ids, srcPath) {
  const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const data = new Uint8Array(fs.readFileSync(pdfPath));
  const doc = await pdfjs.getDocument({ data, useSystemFonts: true }).promise;

  // Punctuation is normalised on both sides. The stylesheet writes the full stop
  // in "1. Introduction" as generated content, so a needle built from the markup
  // alone would read "1 Introduction" and never match the rendered text.
  const norm = (t) => t.replace(/[.,:;]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();

  const html = fs.readFileSync(srcPath, "utf8");
  const wanted = ids.map((id) => {
    const m = html.match(new RegExp(`<h([2-5])[^>]*id="${id}"[^>]*>([\\s\\S]*?)</h\\1>`));
    if (!m) return { id, needle: null };
    const num = (m[2].match(/<span class="n">([^<]*)<\/span>/) || [, ""])[1].trim();
    const label = m[2].replace(/<[^>]*>/g, "").replace(num, "").trim();
    return { id, needle: norm(num + " " + label), label };
  });

  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const content = await (await doc.getPage(i)).getTextContent();
    pages.push(norm(content.items.map((it) => it.str).join(" ")));
  }

  // The contents page lists every heading too, so find where it ends and search
  // only the body after it. A contents page is one holding many entries at once.
  let lastToc = 0;
  pages.forEach((flat, idx) => {
    const hits = wanted.filter((w) => w.needle && flat.includes(w.needle)).length;
    if (hits >= 6) lastToc = idx + 1;
  });

  // Headings appear in document order, so a page number can never go backwards.
  // Walking forward and never re-searching earlier pages is what stops the tail
  // of the contents list — too short to be detected as a contents page — from
  // claiming the last few sections.
  const found = {};
  let floor = lastToc + 1;
  for (const w of wanted) {
    if (!w.needle) continue;
    for (let i = floor; i <= pages.length; i++) {
      if (pages[i - 1].includes(w.needle)) {
        found[w.id] = i;
        floor = i;
        break;
      }
    }
  }
  await doc.cleanup?.();
  return found;
}

/* -- run ------------------------------------------------------------------- */

const browser = await chromium.launch();

for (const job of JOBS) {
  const src = restyle(job.file);
  const out = path.join(OUT, job.pdf);

  const blocks = await render(browser, src, out);

  // Which pages did the headings land on?
  const html = fs.readFileSync(src, "utf8");
  const ids = [...html.matchAll(/data-pg-for="([^"]+)"/g)].map((m) => m[1]);
  let filled = 0;
  if (ids.length) {
    const pages = await pageNumbers(out, ids, src);
    let updated = html;
    for (const id of ids) {
      const n = pages[id];
      if (!n) continue;
      updated = updated.replace(
        new RegExp(`(<span class="pg" data-pg-for="${id}">)[^<]*(</span>)`),
        `$1${n}$2`,
      );
      filled += 1;
    }
    fs.writeFileSync(src, updated);
    await render(browser, src, out);   // second pass, numbers in place
  }

  const mb = fs.statSync(out).size / 1024 / 1024;
  console.log(
    `${job.pdf.padEnd(40)} ${mb.toFixed(2)} MB   diagrams:${blocks}   contents:${filled}/${ids.length}`,
  );
}

await browser.close();
