/**
 * Render the three FYP deliverables to black-and-white PDF.
 *
 * Two things have to happen that a plain browser print does not do:
 *
 *   1. The Mermaid diagrams are authored as <pre class="mermaid"> because the
 *      artifact host draws them natively. Nothing draws them in a local file, so
 *      Mermaid is injected and run here before printing.
 *   2. The documents inherit the product's one-hue palette. For print the tokens
 *      are remapped to a true greyscale ladder at the same lightness, so the
 *      hierarchy survives a monochrome printer instead of collapsing.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const DOCS = "D:/Shawn/Claude Code/FYP/docs";
const OUT = path.join(DOCS, "pdf");
fs.mkdirSync(OUT, { recursive: true });

const MERMAID = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js";

/* Greyscale ladder matched to the lightness of each original token. */
export const BW = `
  :root, :root[data-theme="dark"], :root:not([data-theme="light"]) {
    --paper:#ffffff !important;
    --canvas:#ffffff !important;
    --sunken:#eeeeee !important;
    --hair:#c8c8c8 !important;
    --rule:#8f8f8f !important;
    --mute:#5f5f5f !important;
    --quiet:#404040 !important;
    --body:#1c1c1c !important;
    --ink:#000000 !important;
    --deep:#000000 !important;
  }
  html, body { background:#fff !important; color:#1c1c1c !important; }

  /* Screenshots and rendered diagrams print as greys, not as colour. */
  img, .mermaid svg { filter:grayscale(1) contrast(1.06); }

  /* On paper a link is not clickable, so the underline is noise. */
  a { text-decoration:none !important; color:inherit !important; }

  /* Keep table headers legible when the printer drops background fills. */
  thead th { border-bottom:1.5px solid #000 !important; }

  .mermaid { border:1px solid #c8c8c8; page-break-inside:avoid; break-inside:avoid; }
  .mermaid svg { max-width:100% !important; height:auto !important; }
`;

export const MERMAID_THEME = {
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "loose",
  fontFamily: "IBM Plex Sans, Segoe UI, sans-serif",
  themeVariables: {
    background: "#ffffff",
    primaryColor: "#ffffff",
    primaryTextColor: "#000000",
    primaryBorderColor: "#000000",
    secondaryColor: "#efefef",
    tertiaryColor: "#f7f7f7",
    lineColor: "#3a3a3a",
    textColor: "#000000",
    mainBkg: "#ffffff",
    nodeBorder: "#000000",
    clusterBkg: "#f7f7f7",
    clusterBorder: "#8f8f8f",
    edgeLabelBackground: "#ffffff",
    fontSize: "13px",
    // sequence
    actorBkg: "#ffffff", actorBorder: "#000000", actorTextColor: "#000000",
    signalColor: "#3a3a3a", signalTextColor: "#000000",
    labelBoxBkgColor: "#efefef", labelBoxBorderColor: "#8f8f8f",
    labelTextColor: "#000000", loopTextColor: "#000000",
    activationBkgColor: "#efefef", activationBorderColor: "#3a3a3a",
    sequenceNumberColor: "#ffffff",
    // gantt
    sectionBkgColor: "#f7f7f7", altSectionBkgColor: "#ffffff",
    sectionBkgColor2: "#efefef",
    taskBkgColor: "#d4d4d4", taskBorderColor: "#3a3a3a",
    taskTextColor: "#000000", taskTextOutsideColor: "#000000",
    taskTextDarkColor: "#000000",
    activeTaskBkgColor: "#8f8f8f", activeTaskBorderColor: "#000000",
    doneTaskBkgColor: "#efefef", doneTaskBorderColor: "#8f8f8f",
    critBkgColor: "#5f5f5f", critBorderColor: "#000000",
    gridColor: "#c8c8c8", todayLineColor: "#000000",
    // state
    labelColor: "#000000",
  },
};

const JOBS = [
  { file: "technical-report.html",        pdf: "FYP-26-S3-10 Technical Report.pdf",       landscape: false },
  { file: "user-manual.html",             pdf: "FYP-26-S3-10 User Manual.pdf",            landscape: false },
  { file: "prototype-presentation.html",  pdf: "FYP-26-S3-10 Prototype Presentation.pdf", landscape: true  },
];

const browser = await chromium.launch();

for (const job of JOBS) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 1600 } });
  const problems = [];
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message.slice(0, 90)));

  await page.goto("file:///" + path.join(DOCS, job.file).replace(/\\/g, "/"), {
    waitUntil: "networkidle",
  });

  // Draw the diagrams.
  const blocks = await page.locator("pre.mermaid").count();
  if (blocks) {
    await page.addScriptTag({ url: MERMAID });
    const drawn = await page.evaluate(async (cfg) => {
      // eslint-disable-next-line no-undef
      mermaid.initialize(cfg);
      try {
        // eslint-disable-next-line no-undef
        await mermaid.run({ querySelector: "pre.mermaid" });
      } catch (e) {
        return { error: String(e).slice(0, 160) };
      }
      return { svgs: document.querySelectorAll("pre.mermaid svg, .mermaid svg").length };
    }, MERMAID_THEME);
    if (drawn.error) problems.push("mermaid: " + drawn.error);
    else if (drawn.svgs < blocks) problems.push(`mermaid drew ${drawn.svgs}/${blocks}`);
  }

  // Force greyscale, and let fonts settle before layout is measured.
  await page.addStyleTag({ content: BW });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(1200);

  const out = path.join(OUT, job.pdf);
  await page.pdf({
    path: out,
    format: "A4",
    landscape: job.landscape,
    printBackground: true,
    preferCSSPageSize: false,
    margin: job.landscape
      ? { top: "10mm", bottom: "10mm", left: "10mm", right: "10mm" }
      : { top: "16mm", bottom: "18mm", left: "16mm", right: "16mm" },
    displayHeaderFooter: !job.landscape,
    headerTemplate: `<div style="font:8pt 'Segoe UI',sans-serif;color:#777;width:100%;padding:0 16mm;">
      <span style="float:left">FYP-26-S3-10 &nbsp;·&nbsp; Wollongong News</span></div>`,
    footerTemplate: `<div style="font:8pt 'Segoe UI',sans-serif;color:#777;width:100%;padding:0 16mm;">
      <span style="float:right"><span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
  });

  const kb = fs.statSync(out).size / 1024;
  console.log(
    `${job.pdf.padEnd(44)} ${(kb / 1024).toFixed(2)} MB  diagrams:${blocks}  ` +
      (problems.length ? "ISSUES: " + problems.join("; ") : "ok"),
  );
  await page.close();
}

await browser.close();
