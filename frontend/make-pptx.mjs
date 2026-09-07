/**
 * Build the prototype presentation as an editable PowerPoint deck.
 *
 * Not a conversion of the HTML: every slide is authored natively as text
 * frames, tables and shapes, so the team can edit it in PowerPoint. The three
 * Mermaid diagrams have no PowerPoint equivalent, so those are rendered to PNG
 * first and placed as pictures.
 *
 * Black and white throughout, and the fonts are restricted to Georgia and
 * Calibri, which ship with Office on both Windows and macOS. A deck that
 * substitutes fonts on the assessor's machine reflows and looks broken.
 */
import PptxGenJS from "pptxgenjs";
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const OUT_DIR = "D:/Shawn/Claude Code/FYP/docs/pptx";
const TMP = path.join(OUT_DIR, "_diagrams");
fs.mkdirSync(TMP, { recursive: true });

/* -- palette ---------------------------------------------------------------
   The product's own committed world, from DESIGN.md: one hue (205deg) at ten
   lightnesses on #133955, so nothing on the slide is a true grey. No chromatic
   colour and no shadows, which is what keeps a monochromatic deck reading as
   chosen rather than drained.                                                */
const K = {
  ink: "133955",    // headings, primary text — the client's brand ink
  deep: "0A2233",   // filled elements only
  body: "294C65",   // running copy
  quiet: "446074",  // secondary text
  mute: "587184",   // captions, metadata
  rule: "9AB1C1",   // emphatic divider
  hair: "CCD8E0",   // hairline between related things
  sunken: "E5ECF0", // wells, table headers, meter troughs
  canvas: "F2F5F8", // the page itself — stock, not white
  paper: "FCFDFD",  // cards and panels
};
const DISPLAY = "Georgia";
const UI = "Calibri";

/* -- geometry -------------------------------------------------------------- */
const W = 13.333, H = 7.5;
const L = 0.62, R = W - 0.62, TOP = 0.5;
const COLW = R - L;

/* ==========================================================================
   1. Render the Mermaid diagrams to PNG
   ========================================================================== */

const DIAGRAMS = {
  gantt: `gantt
  title Project schedule
  dateFormat YYYY-MM-DD
  axisFormat %b
  section Planning
  Form team and topic          :done, a1, 2026-07-01, 14d
  Project website              :done, a2, 2026-07-08, 10d
  section Research
  Existing products            :done, b1, 2026-07-10, 21d
  Comparison and pick chart    :done, b2, 2026-07-24, 10d
  Requirements (PRD)           :milestone, done, m1, 2026-08-01, 0d
  section Design
  Use cases and DB design      :done, c1, 2026-08-01, 7d
  Design document (PDD)        :milestone, done, m2, 2026-08-07, 0d
  section Implementation
  Scoring engine and API       :done, d1, 2026-08-08, 18d
  Front end and design system  :done, d2, 2026-08-15, 20d
  Deployment and hardening     :done, d3, 2026-08-28, 8d
  Prototype demonstration      :milestone, active, m3, 2026-09-05, 0d
  section Remaining
  Final documentation          :e1, 2026-09-06, 21d
  User acceptance testing      :e2, 2026-09-15, 14d
  Final presentation           :milestone, m4, 2026-10-01, 0d`,

  arch: `flowchart LR
  subgraph client["Browser"]
    SPA["React SPA<br/>16 screens<br/>static site on Render"]
  end
  subgraph api["Application"]
    F["Flask REST API<br/>77 endpoints<br/>gunicorn on Render"]
    SEC["Permission middleware<br/>six roles"]
    SCORE["Scoring engine<br/>pure functions"]
  end
  subgraph data["Data"]
    DB[("PostgreSQL<br/>Supabase<br/>23 tables, RLS on")]
  end
  SPA -- "HTTPS + JWT" --> F
  F --> SEC
  SEC --> SCORE
  SEC --> DB
  SCORE --> DB
  DB -- "rows" --> F
  F -- "JSON incl. score ledger" --> SPA`,
};

const MERMAID_CFG = {
  startOnLoad: false,
  theme: "neutral",
  securityLevel: "loose",
  flowchart: { useMaxWidth: false },
  gantt: { useMaxWidth: true, barHeight: 22, barGap: 6, fontSize: 13, leftPadding: 210, gridLineStartPadding: 30 },
  fontFamily: "Calibri, Segoe UI, sans-serif",
  themeVariables: {
    background: "#FCFDFD", primaryColor: "#FCFDFD", primaryTextColor: "#133955",
    primaryBorderColor: "#133955", secondaryColor: "#E5ECF0", tertiaryColor: "#F2F5F8",
    lineColor: "#587184", textColor: "#133955", mainBkg: "#FCFDFD", nodeBorder: "#133955",
    clusterBkg: "#F2F5F8", clusterBorder: "#9AB1C1", edgeLabelBackground: "#FCFDFD",
    fontSize: "15px",
    sectionBkgColor: "#F2F5F8", altSectionBkgColor: "#FCFDFD", sectionBkgColor2: "#E5ECF0",
    taskBkgColor: "#CCD8E0", taskBorderColor: "#587184", taskTextColor: "#133955",
    taskTextOutsideColor: "#133955", taskTextDarkColor: "#133955",
    activeTaskBkgColor: "#9AB1C1", activeTaskBorderColor: "#133955",
    doneTaskBkgColor: "#E5ECF0", doneTaskBorderColor: "#9AB1C1",
    critBkgColor: "#587184", critBorderColor: "#133955",
    gridColor: "#CCD8E0", todayLineColor: "#133955", labelColor: "#133955",
  },
};

console.log("Rendering diagrams…");
const browser = await chromium.launch();
const dims = {};
for (const [name, code] of Object.entries(DIAGRAMS)) {
  const page = await browser.newPage({
    viewport: { width: 1800, height: 1200 },
    deviceScaleFactor: 2.5,
  });
  await page.setContent(
    `<style>html,body{margin:0;background:#FCFDFD;font-family:Calibri,sans-serif}
     #d{padding:14px;width:${name === "gantt" ? "1560px" : "max-content"}}</style><div id="d"><pre class="mermaid">${code}</pre></div>`,
  );
  await page.addScriptTag({
    url: "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js",
  });
  const res = await page.evaluate(async (cfg) => {
    mermaid.initialize(cfg);
    await mermaid.run({ querySelector: "pre.mermaid" });
    const svg = document.querySelector("svg");
    // Mermaid ships the SVG at width:100%, which an inline-block parent
    // shrink-to-fits to nothing. Pin it to its own viewBox instead.
    const vb = (svg.getAttribute("viewBox") || "").split(/[ ,]+/).map(Number);
    const w = vb.length === 4 && vb[2] ? vb[2] : svg.getBBox().width;
    const h = vb.length === 4 && vb[3] ? vb[3] : svg.getBBox().height;
    svg.style.maxWidth = "none";
    svg.style.width = w + "px";
    svg.style.height = h + "px";
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const b = svg.getBoundingClientRect();
    return { w: Math.ceil(b.width), h: Math.ceil(b.height) };
  }, MERMAID_CFG);
  await page.waitForTimeout(400);
  const file = path.join(TMP, name + ".png");
  await page.locator("#d").screenshot({ path: file });
  const png = fs.readFileSync(file);
  const pw = png.readUInt32BE(16), ph = png.readUInt32BE(20);
  dims[name] = { file, ratio: pw / ph };
  console.log(`  ${name.padEnd(6)} svg ${res.w}×${res.h}  png ${pw}×${ph}  ratio ${(pw / ph).toFixed(3)}`);
  await page.close();
}
await browser.close();

/* ==========================================================================
   2. Build the deck
   ========================================================================== */

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE"; // 13.333 x 7.5in — matches W/H below
pptx.author = "FYP-26-S3-10";
pptx.company = "University of Wollongong · SIM Global Education";
pptx.subject = "CSIT321 Final Year Project";
pptx.title = "Wollongong News — Prototype Presentation";

let n = 0;

/** A slide with the standing furniture: rule, footer, number. */
function slide({ eyebrow, title, plain = false } = {}) {
  n += 1;
  const s = pptx.addSlide();
  s.background = { color: K.paper };

  if (!plain) {
    s.addText("FYP-26-S3-10  ·  Wollongong News", {
      x: L, y: H - 0.44, w: 5, h: 0.25,
      fontFace: UI, fontSize: 9, color: K.mute,
    });
    s.addText(String(n).padStart(2, "0"), {
      x: R - 1, y: H - 0.44, w: 1, h: 0.25,
      fontFace: UI, fontSize: 9, color: K.rule, align: "right",
    });
  }

  let y = TOP;
  if (eyebrow) {
    s.addText(eyebrow.toUpperCase(), {
      x: L, y, w: COLW, h: 0.24,
      fontFace: UI, fontSize: 10, bold: true, color: K.mute, charSpacing: 1.4,
    });
    y += 0.3;
  }
  if (title) {
    s.addText(title, {
      x: L, y, w: COLW, h: 0.62,
      fontFace: DISPLAY, fontSize: 30, color: K.ink,
    });
    y += 0.72;
    s.addShape(pptx.ShapeType.line, {
      x: L, y, w: COLW, h: 0,
      line: { color: K.ink, width: 1.25 },
    });
    y += 0.28;
  }
  return { s, y };
}

/** Dash-led bullet list with optional sub-items. */
function bullets(s, items, { x, y, w, size = 14, gap = 0.1 }) {
  let cy = y;
  for (const it of items) {
    const text = typeof it === "string" ? it : it.t;
    const subs = typeof it === "string" ? [] : it.sub || [];
    const runs = Array.isArray(text) ? text : [{ text }];
    const lines = Math.max(
      1,
      Math.ceil(runs.reduce((a, r) => a + r.text.length, 0) / (w * 15.5)),
    );
    const h = lines * 0.235 + 0.06;
    s.addShape(pptx.ShapeType.line, {
      x, y: cy + 0.12, w: 0.13, h: 0, line: { color: K.rule, width: 1 },
    });
    s.addText(runs.map((r) => ({
      text: r.text,
      options: { bold: !!r.bold, color: r.bold ? K.ink : K.body },
    })), {
      x: x + 0.24, y: cy, w: w - 0.24, h,
      fontFace: UI, fontSize: size, color: K.body, lineSpacingMultiple: 1.12, valign: "top",
    });
    cy += h;
    for (const sub of subs) {
      const sh = Math.max(1, Math.ceil(sub.length / (w * 17))) * 0.21 + 0.02;
      s.addText("·  " + sub, {
        x: x + 0.46, y: cy, w: w - 0.46, h: sh,
        fontFace: UI, fontSize: size - 2, color: K.quiet, lineSpacingMultiple: 1.08, valign: "top",
      });
      cy += sh;
    }
    cy += gap;
  }
  return cy;
}

/** A titled block with a rule above it, used in multi-column slides. */
function block(s, { x, y, w, h, title, text, size = 12 }) {
  s.addShape(pptx.ShapeType.line, { x, y, w, h: 0, line: { color: K.hair, width: 1 } });
  s.addText(title, {
    x, y: y + 0.1, w, h: 0.26,
    fontFace: UI, fontSize: 13, bold: true, color: K.ink,
  });
  s.addText(text, {
    x, y: y + 0.4, w, h: h - 0.4,
    fontFace: UI, fontSize: size, color: K.quiet, lineSpacingMultiple: 1.14, valign: "top",
  });
}

const tableBase = {
  fontFace: UI, fontSize: 11, color: K.body,
  border: { type: "solid", pt: 0.5, color: K.hair },
  autoPage: false,
};
const th = (t) => ({
  text: t,
  options: { bold: true, color: K.ink, fill: { color: K.sunken }, fontSize: 9.5, valign: "middle" },
});

/* -- 01 title -------------------------------------------------------------- */
{
  const { s } = slide({ plain: true });
  s.addText("UNIVERSITY OF WOLLONGONG  ·  SIM GLOBAL EDUCATION", {
    x: L, y: 1.15, w: COLW, h: 0.26,
    fontFace: UI, fontSize: 10.5, bold: true, color: K.mute, charSpacing: 1.4,
  });
  s.addShape(pptx.ShapeType.line, {
    x: L, y: 1.55, w: COLW, h: 0, line: { color: K.ink, width: 2 },
  });
  s.addText("Who decides\nwhat you can trust?", {
    x: L, y: 1.8, w: 8.4, h: 1.9,
    fontFace: DISPLAY, fontSize: 46, color: K.ink, lineSpacingMultiple: 1.0,
  });
  s.addText(
    [
      { text: "Wollongong News", options: { bold: true } },
      { text: " — a news publishing platform where every article carries a Credibility Score you can trace, and every contributor an Accuracy Rate they earn." },
    ],
    { x: L, y: 3.85, w: 7.4, h: 1.0, fontFace: UI, fontSize: 15, color: K.body, lineSpacingMultiple: 1.2 },
  );
  s.addShape(pptx.ShapeType.line, {
    x: L, y: 5.35, w: COLW, h: 0, line: { color: K.hair, width: 1 },
  });
  const meta = [
    ["Project team", "FYP-26-S3-10"],
    ["Subject", "CSIT321 Final Year Project"],
    ["Supervisor", "[ to be filled in ]"],
    ["Assessor", "[ to be filled in ]"],
    ["Team members", "[ names and UOW IDs ]"],
  ];
  const cw = COLW / meta.length;
  meta.forEach(([k, v], i) => {
    s.addText(k.toUpperCase(), {
      x: L + i * cw, y: 5.55, w: cw - 0.15, h: 0.22,
      fontFace: UI, fontSize: 9, bold: true, color: K.mute, charSpacing: 1.2,
    });
    s.addText(v, {
      x: L + i * cw, y: 5.8, w: cw - 0.15, h: 0.5,
      fontFace: UI, fontSize: 11.5, color: K.ink, valign: "top",
    });
  });
}

/* -- 02 contents ----------------------------------------------------------- */
{
  const { s, y } = slide({ title: "Contents" });
  const items = [
    ["The project scope", "What we set out to build"],
    ["Learning objectives", "What we set out to learn"],
    ["Findings and research", "Six comparable products"],
    ["Comparison matrix", "Where we differ"],
    ["Pick chart", "What we chose to build, and to kill"],
    ["The six user roles", "Work breakdown"],
    ["Development tools", "Stack and why"],
    ["Scheduling", "Waterfall and Scrum"],
    ["Our prototype: architecture", "How it fits together"],
    ["Our prototype: the scoring engine", "A worked example"],
    ["Our prototype: what is running", "Screens and figures"],
    ["Future development", "What comes after v1"],
    ["Questions", ""],
  ];
  const rowH = 0.36;
  items.forEach(([t, note], i) => {
    const ry = y + i * rowH;
    s.addText(String(i + 1).padStart(2, "0"), {
      x: L, y: ry, w: 0.4, h: rowH, fontFace: UI, fontSize: 10, color: K.rule, valign: "middle",
    });
    s.addText(t, {
      x: L + 0.45, y: ry, w: 6.5, h: rowH, fontFace: UI, fontSize: 13.5, color: K.ink, valign: "middle",
    });
    s.addText(note, {
      x: R - 5, y: ry, w: 5, h: rowH,
      fontFace: UI, fontSize: 11, color: K.mute, align: "right", valign: "middle",
    });
    s.addShape(pptx.ShapeType.line, {
      x: L, y: ry + rowH, w: COLW, h: 0, line: { color: K.hair, width: 0.75 },
    });
  });
}

/* -- 03 scope -------------------------------------------------------------- */
{
  const { s, y } = slide({ title: "The project scope" });
  const end = bullets(s, [
    {
      t: [
        { text: "The goal ", bold: true },
        { text: "is a news publishing platform on which every published article carries a " },
        { text: "Credibility Score", bold: true },
        { text: ", and every contributor an " },
        { text: "Accuracy Rate", bold: true },
        { text: ", both produced by a fixed formula whose inputs are disclosed to the reader rather than by a hidden or predictive model." },
      ],
    },
    {
      t: [{ text: "The system covers ", bold: true }, { text: "the full editorial lifecycle:" }],
      sub: [
        "Drafting, submission, scheduling and publication of articles",
        "Editorial review scoped to an assigned content category",
        "Reader reporting of inaccuracies, and moderation of what is reported",
        "Corrections and retractions, logged permanently against the article",
        "Contributor appeals against a correction, resolved by an administrator",
        "Premium subscriptions and a tiered contributor revenue share",
      ],
    },
    {
      t: [
        { text: "Six user tiers ", bold: true },
        { text: "hold different permissions, from an unregistered visitor who can only read to a system administrator who governs the scoring thresholds themselves." },
      ],
    },
    {
      t: [
        { text: "Deliberately out of scope for v1: ", bold: true },
        { text: "machine-learned credibility prediction, semantic search, image and video analysis, multi-language publishing, and native mobile applications." },
      ],
    },
  ], { x: L, y, w: COLW, size: 13.5 });

  s.addShape(pptx.ShapeType.line, {
    x: L, y: end + 0.15, w: 0.02, h: 0.6, line: { color: K.rule, width: 2 },
  });
  s.addText(
    "The scope is bounded by a single design rule: if a reader cannot be shown why a score is what it is, the feature that produced it does not belong in v1.",
    { x: L + 0.18, y: end + 0.15, w: COLW - 0.3, h: 0.6, fontFace: UI, fontSize: 12, italic: true, color: K.quiet },
  );
}

/* -- 04 learning objectives ------------------------------------------------ */
{
  const { s, y } = slide({ title: "Learning objectives" });
  const cw = (COLW - 0.7) / 3;
  block(s, { x: L, y, w: cw, h: 2.0, title: "Explore industry tooling",
    text: "Work with the stack a graduate would actually meet: a React single-page application against a REST API, a relational database under versioned migrations, automated tests in continuous use, and a real cloud deployment rather than a localhost demonstration." });
  block(s, { x: L + cw + 0.35, y, w: cw, h: 2.0, title: "Improve technical skills",
    text: "REST API design, six-tier role-based access control, password hashing and token sessions, schema migration, input sanitisation, rate limiting, and writing tests that fail for the right reason." });
  block(s, { x: L + 2 * (cw + 0.35), y, w: cw, h: 2.0, title: "Practise team engineering",
    text: "Shared version control with reviewed commits, a documented design system so two people produce one interface, and SDLC documentation that stays in step with the code rather than describing an older version of it." });

  block(s, { x: L, y: y + 2.35, w: COLW, h: 1.5, size: 13,
    title: "The objective that shaped the project most — learning to say no",
    text: "A credibility platform invites feature after feature: sentiment analysis, bias detection, automated fact-checking. Each would have made the score unexplainable. Holding the line on a disclosed, arithmetic formula was the hardest engineering decision of the project, and the one the rest of the design depends on." });
}

/* -- 05 findings ----------------------------------------------------------- */
{
  const { s, y } = slide({ title: "Findings and research" });
  s.addText("We examined six products that assess or publish news, to establish what already exists and where a gap remains.", {
    x: L, y, w: COLW, h: 0.3, fontFace: UI, fontSize: 14, color: K.body,
  });
  const items = [
    ["NewsGuard", "Journalist-assigned trust ratings for whole publications, nine weighted criteria. Rates the outlet, never the article."],
    ["Ground News", "Aggregates one story across outlets and shows the political spread of coverage. Measures bias, not accuracy."],
    ["Media Bias / Fact Check", "Manually maintained directory of outlet bias and factual reporting. No publishing function, and updates lag."],
    ["Full Fact", "Charity fact-checking of individual claims, with automated claim detection. Checks claims after publication elsewhere."],
    ["Substack", "Independent publishing with paid subscriptions and a revenue share. No accuracy signal of any kind."],
    ["Medium", "Open publishing with editorial curation and a partner programme. Curation is discretionary and undisclosed."],
  ];
  const cw = (COLW - 0.7) / 3;
  items.forEach(([t, d], i) => {
    const col = i % 3, row = Math.floor(i / 3);
    block(s, {
      x: L + col * (cw + 0.35), y: y + 0.5 + row * 1.35, w: cw, h: 1.15,
      title: t, text: d, size: 11.5,
    });
  });
  block(s, { x: L, y: y + 3.3, w: COLW, h: 1.0, size: 13, title: "The gap",
    text: "Every product we examined does one of two things: it rates outlets without publishing them, or it publishes writers without rating them. None scores the individual article, ties that score to the writer's own track record, and shows the reader the arithmetic. That intersection is the product." });
}

/* -- 06 comparison matrix -------------------------------------------------- */
{
  const { s, y } = slide({ title: "Product comparison matrix" });
  const cols = ["NewsGuard", "Ground News", "MBFC", "Full Fact", "Substack", "Medium", "Wollongong News"];
  const rows = [
    ["Publish original articles", 0, 0, 0, 1, 1, 1, 1],
    ["Credibility rating of an outlet", 1, 1, 1, 0, 0, 0, 0],
    ["Credibility score per article", 0, 0, 0, 0, 0, 0, 1],
    ["Per-author accuracy record", 0, 0, 0, 0, 0, 0, 1],
    ["Published scoring inputs", 1, 0, 1, 0, 0, 0, 1],
    ["Score breakdown shown to reader", 0, 0, 0, 0, 0, 0, 1],
    ["Verifiable source links counted", 0, 0, 0, 1, 0, 0, 1],
    ["Reader reporting of inaccuracy", 0, 0, 0, 1, 0, 1, 1],
    ["Permanent public correction log", 0, 0, 0, 1, 0, 0, 1],
    ["Author appeal against a correction", 0, 0, 0, 0, 0, 0, 1],
    ["Editorial review before publication", 0, 0, 0, 0, 0, 1, 1],
    ["Paid subscriptions", 1, 1, 0, 0, 1, 1, 1],
    ["Contributor revenue share", 0, 0, 0, 0, 1, 1, 1],
    ["Bias / political spread analysis", 1, 1, 1, 0, 0, 0, 0],
    ["Machine-learned prediction", 0, 1, 0, 1, 0, 1, 0],
  ];
  const data = [
    [th("Function"), ...cols.map((c) => ({ ...th(c), options: { ...th(c).options, align: "center" } }))],
    ...rows.map((r) => [
      { text: r[0], options: { color: K.ink } },
      ...r.slice(1).map((v) => ({
        text: v ? "✓" : "—",
        options: { align: "center", bold: !!v, color: v ? K.ink : K.rule },
      })),
    ]),
  ];
  s.addTable(data, {
    ...tableBase, x: L, y, w: COLW,
    colW: [3.9, ...Array(7).fill((COLW - 3.9) / 7)],
    rowH: 0.223, fontSize: 10,
  });
  s.addText("The last row is a deliberate absence, not a shortfall. A predicted score cannot be shown its own arithmetic, which is the one thing this product promises.", {
    x: L, y: H - 0.95, w: COLW, h: 0.3, fontFace: UI, fontSize: 11, italic: true, color: K.quiet,
  });
}

/* -- 07 pick chart --------------------------------------------------------- */
{
  const { s, y } = slide({ title: "Pick chart" });
  s.addText("Candidate features by payoff against difficulty. Everything in the upper-left quadrant is built and running.", {
    x: L, y, w: COLW, h: 0.3, fontFace: UI, fontSize: 13, color: K.body,
  });

  const cx = L + 0.62, cy = y + 0.45, cwid = COLW - 1.0, chgt = 4.05;

  s.addShape(pptx.ShapeType.rect, {
    x: cx, y: cy, w: cwid, h: chgt,
    fill: { color: K.canvas }, line: { color: K.hair, width: 1 },
  });
  s.addShape(pptx.ShapeType.line, {
    x: cx + cwid / 2, y: cy, w: 0, h: chgt, line: { color: K.hair, width: 1 },
  });
  s.addShape(pptx.ShapeType.line, {
    x: cx, y: cy + chgt / 2, w: cwid, h: 0, line: { color: K.hair, width: 1 },
  });

  const quad = (t, qx, qy) => s.addText(t.toUpperCase(), {
    x: qx - 0.8, y: qy, w: 1.6, h: 0.22,
    fontFace: UI, fontSize: 9.5, bold: true, color: K.mute, align: "center", charSpacing: 1.2,
  });
  quad("Implement", cx + cwid * 0.25, cy + 0.07);
  quad("Challenging", cx + cwid * 0.75, cy + 0.07);
  quad("Possible", cx + cwid * 0.25, cy + chgt - 0.28);
  quad("Kill", cx + cwid * 0.75, cy + chgt - 0.28);

  // px, py are fractions of the plot area.
  const bub = (t, px, py, kind) => {
    const bw = 1.5, bh = 0.34;
    s.addText(t, {
      x: cx + cwid * px - bw / 2, y: cy + chgt * py - bh / 2, w: bw, h: bh,
      fontFace: UI, fontSize: 9, align: "center", valign: "middle",
      color: kind === "kill" ? K.mute : K.ink,
      bold: kind === "built",
      fill: { color: K.paper },
      line: {
        color: kind === "built" ? K.ink : K.rule,
        width: kind === "built" ? 1.25 : 0.75,
        dashType: kind === "kill" ? "dash" : "solid",
      },
      rectRadius: 0.16,
      shape: pptx.ShapeType.roundRect,
    });
  };

  bub("Credibility score", 0.12, 0.16, "built");
  bub("Accuracy rate", 0.34, 0.13, "built");
  bub("Corrections log", 0.23, 0.29, "built");
  bub("Review queue", 0.11, 0.36, "built");
  bub("Reader reporting", 0.35, 0.35, "built");
  bub("Registration", 0.10, 0.45, "built");
  bub("Category-scoped editors", 0.36, 0.45, "built");

  bub("Dispute resolution", 0.63, 0.17, "built");
  bub("Tiered revenue share", 0.85, 0.30, "built");
  bub("Real payment gateway", 0.64, 0.42, "planned");

  bub("Reading lists", 0.13, 0.62, "built");
  bub("Follows", 0.33, 0.60, "built");
  bub("Notification settings", 0.19, 0.79, "built");
  bub("Share links", 0.40, 0.77, "built");

  bub("Semantic search", 0.62, 0.61, "kill");
  bub("ML score prediction", 0.85, 0.59, "kill");
  bub("Image & video analysis", 0.63, 0.80, "kill");
  bub("Automated fact-checking", 0.85, 0.79, "kill");

  s.addText("PAYOFF", {
    x: cx - 1.05, y: cy + chgt / 2 - 0.15, w: 0.9, h: 0.3,
    fontFace: UI, fontSize: 9.5, bold: true, color: K.mute, align: "right", charSpacing: 1.2,
  });
  s.addText("High", { x: cx - 1.05, y: cy, w: 0.9, h: 0.22, fontFace: UI, fontSize: 9, color: K.mute, align: "right" });
  s.addText("Low", { x: cx - 1.05, y: cy + chgt - 0.22, w: 0.9, h: 0.22, fontFace: UI, fontSize: 9, color: K.mute, align: "right" });
  s.addText("Easy", { x: cx, y: cy + chgt + 0.06, w: 1, h: 0.22, fontFace: UI, fontSize: 9, color: K.mute });
  s.addText("DIFFICULTY", { x: cx + cwid / 2 - 1, y: cy + chgt + 0.06, w: 2, h: 0.22, fontFace: UI, fontSize: 9.5, bold: true, color: K.mute, align: "center", charSpacing: 1.2 });
  s.addText("Hard", { x: cx + cwid - 1, y: cy + chgt + 0.06, w: 1, h: 0.22, fontFace: UI, fontSize: 9, color: K.mute, align: "right" });

  const keyY = cy + chgt + 0.34;
  const keys = [["Built in the prototype", "built"], ["Planned, not yet built", "planned"], ["Rejected for v1", "kill"]];
  keys.forEach(([label, kind], i) => {
    const kx = cx + i * 2.6;
    s.addShape(pptx.ShapeType.line, {
      x: kx, y: keyY + 0.11, w: 0.28, h: 0,
      line: {
        color: kind === "built" ? K.ink : K.rule,
        width: kind === "built" ? 1.5 : 1,
        dashType: kind === "kill" ? "dash" : "solid",
      },
    });
    s.addText(label, { x: kx + 0.36, y: keyY, w: 2.2, h: 0.24, fontFace: UI, fontSize: 10, color: K.quiet });
  });
}

/* -- 08 roles ------------------------------------------------------------- */
{
  const { s, y } = slide({ title: "The six user roles" });
  s.addText(
    "Work breakdown by role. Each tier inherits everything the tiers above it can do, so only what each one adds is listed.",
    { x: L, y, w: COLW, h: 0.3, fontFace: UI, fontSize: 13.5, color: K.body },
  );

  const roles = [
    ["Unregistered\nvisitor",
      ["Read published articles", "Browse categories", "See credibility scores",
       "Search"]],
    ["Free registered\nreader",
      ["Register and sign in", "Comment, like, follow", "Save a reading list",
       "Report an inaccuracy", "Apply to contribute"]],
    ["Premium\nreader",
      ["Subscriber-only articles", "Manage subscription"]],
    ["Verified\ncontributor",
      ["Draft and edit articles", "Tag verifiable sources", "Submit for review",
       "Schedule publication", "Track accuracy rate", "View earnings",
       "Dispute a correction"]],
    ["Editor",
      ["Review assigned sections", "Approve or reject", "Moderate flagged content",
       "Log corrections"]],
    ["System\nadministrator",
      ["Govern accounts", "Decide applications", "Assign editor sections",
       "Manage categories", "Set scoring thresholds", "Resolve disputes",
       "Read the audit log"]],
  ];

  const cw = (COLW - 5 * 0.22) / 6;
  const cy = y + 0.5;
  roles.forEach(([role, adds], i) => {
    const x = L + i * (cw + 0.22);
    s.addShape(pptx.ShapeType.line, { x, y: cy, w: cw, h: 0, line: { color: K.ink, width: 1.5 } });
    s.addText(String(i + 1).padStart(2, "0"), {
      x, y: cy + 0.1, w: cw, h: 0.22,
      fontFace: UI, fontSize: 9, color: K.rule,
    });
    s.addText(role, {
      x, y: cy + 0.32, w: cw, h: 0.62,
      fontFace: DISPLAY, fontSize: 14, color: K.ink, valign: "top",
    });
    s.addText(adds.join("\n"), {
      x, y: cy + 1.0, w: cw, h: 2.6,
      fontFace: UI, fontSize: 11, color: K.quiet, valign: "top", lineSpacingMultiple: 1.32,
    });
  });

  s.addShape(pptx.ShapeType.line, {
    x: L, y: cy + 3.75, w: COLW, h: 0, line: { color: K.hair, width: 1 },
  });
  s.addText(
    "The sixth role needs no account. Permission is enforced once, in one middleware, so the interface hides what a role cannot do only as a courtesy — the server refuses it regardless.",
    { x: L, y: cy + 3.85, w: COLW, h: 0.4, fontFace: UI, fontSize: 11, italic: true, color: K.quiet },
  );
}

/* -- 09 development tools -------------------------------------------------- */
{
  const { s, y } = slide({ title: "Development tools" });
  const cw = (COLW - 0.5) / 2;
  const left = [
    ["Back end — Python 3.12 and Flask", "Flask is the single entry point; no client queries the database directly. SQLAlchemy for the ORM, Alembic for versioned migrations, Argon2 for password hashing, PyJWT for sessions, bleach for HTML sanitisation on write, Flask-Limiter for rate limiting."],
    ["Database — PostgreSQL via Supabase", "The PDD specifies MySQL. The team moved to Supabase for a managed instance the whole team shares. Row Level Security is enabled on all 23 tables and default privileges revoked, so a leaked key alone reads nothing."],
    ["Front end — React 18 with Vite", "A single-page application in plain JSX with hand-written CSS against a documented token file. No component framework, so every rule in the design system is one we can account for."],
  ];
  const right = [
    ["Hosting — Render", "Two services from one blueprint: the built front end as a static site, and Flask under gunicorn as a web service. Supabase holds the database only — it cannot serve a website, so the two are complements, not alternatives."],
    ["Testing — pytest and Playwright", "139 automated test cases covering the scoring engine, permission middleware, editorial workflow, error handling and rate limiting. A batched Playwright pass captures every screen at desktop and mobile width."],
    ["Version control and environment", "GitHub for source control, with the environment file held out of the repository. Visual Studio Code as the editor across the team."],
  ];
  left.forEach(([t, d], i) => block(s, { x: L, y: y + i * 1.42, w: cw, h: 1.28, title: t, text: d, size: 11 }));
  right.forEach(([t, d], i) => block(s, { x: L + cw + 0.5, y: y + i * 1.42, w: cw, h: 1.28, title: t, text: d, size: 11 }));

  s.addText("One deployment constraint worth recording: the API runs a single gunicorn worker, because the rate limiter holds its counters in process memory. Two workers meant two independent counters and a limit twice as loose as configured.", {
    x: L, y: H - 0.95, w: COLW, h: 0.4, fontFace: UI, fontSize: 11, italic: true, color: K.quiet,
  });
}

/* -- 10 scheduling --------------------------------------------------------- */
{
  const { s, y } = slide({ title: "Scheduling" });
  const cw = (COLW - 0.5) / 2;
  block(s, { x: L, y, w: cw, h: 1.0, title: "Waterfall — for the deliverables", size: 11.5,
    text: "The subject's milestones are fixed and sequential: requirements, design, prototype, final product. The waterfall model matches those dates and is how we plan against the assessment calendar." });
  block(s, { x: L + cw + 0.5, y, w: cw, h: 1.0, title: "Scrum — for the development itself", size: 11.5,
    text: "Inside each phase the work runs as short sprints against a backlog of user stories, because requirements did change: the database moved to Supabase, and the accuracy formula was rewritten after testing." });

  const availH = H - (y + 1.25) - 0.6;
  const r = dims.gantt.ratio;
  let iw = COLW, ih = iw / r;
  if (ih > availH) { ih = availH; iw = ih * r; }
  s.addImage({ path: dims.gantt.file, x: L + (COLW - iw) / 2, y: y + 1.2, w: iw, h: ih });
  s.addText("Figure 2 — Milestones to date and work remaining. Dates are indicative, to be confirmed against the subject calendar.", {
    x: L, y: H - 0.72, w: COLW, h: 0.25, fontFace: UI, fontSize: 10, color: K.mute,
  });
}

/* -- 11 architecture ------------------------------------------------------- */
{
  const { s, y } = slide({ title: "Our prototype — architecture" });
  const availH = H - (y + 0.1) - 0.95;
  const r = dims.arch.ratio;
  let iw = COLW, ih = iw / r;
  if (ih > availH) { ih = availH; iw = ih * r; }
  s.addImage({ path: dims.arch.file, x: L + (COLW - iw) / 2, y: y + 0.05, w: iw, h: ih });
  s.addText("Figure 3 — No client reaches the database directly. Every request passes the permission middleware first, and the scoring engine is a set of pure functions with no database access, no clock and no randomness, so a score can be recomputed and verified from its inputs alone.", {
    x: L, y: H - 0.95, w: COLW, h: 0.45, fontFace: UI, fontSize: 10.5, color: K.mute,
  });
}

/* -- 12 scoring engine ----------------------------------------------------- */
{
  const { s, y } = slide({ title: "Our prototype — the scoring engine" });
  const cw = (COLW - 0.6) / 2;

  s.addText("A reader is never shown a bare number. Every article carries the ledger that produced it: what the writer's record contributed, what the sources added, and what each correction took away.", {
    x: L, y, w: cw, h: 0.75, fontFace: UI, fontSize: 13, color: K.body, lineSpacingMultiple: 1.15,
  });
  s.addText("The score is a fixed arithmetic expression. The inputs are named in public; the tuning weights are internal and administrator-configurable, so no constant may be hard-coded into the interface.", {
    x: L, y: y + 0.85, w: cw, h: 0.75, fontFace: UI, fontSize: 13, color: K.body, lineSpacingMultiple: 1.15,
  });
  block(s, { x: L, y: y + 1.75, w: cw, h: 1.6, size: 11.5, title: "Accuracy is smoothed, not a raw ratio",
    text: "A plain ratio of clean articles to published ones cost a five-article writer 15.0 points for one correction, against 1.9 for a forty-article writer — a 7.9× penalty for the same mistake. Blending toward a platform baseline reduces that gap to 4.4× and removes the cliff where a single article moved a whole back catalogue." });

  const x2 = L + cw + 0.6;
  s.addText("WORKED EXAMPLE — A PUBLISHED ARTICLE", {
    x: x2, y, w: cw, h: 0.24, fontFace: UI, fontSize: 9.5, bold: true, color: K.mute, charSpacing: 1.2,
  });
  const ledger = [
    ["Contributor accuracy record", "+ 63.75"],
    ["Verifiable sources (5 × 5, capped at 25)", "+ 25.00"],
    ["Logged corrections (1)", "− 15.00"],
    ["Retraction", "− 0.00"],
    ["Upheld reader reports (below threshold)", "− 0.00"],
  ];
  let ly = y + 0.32;
  s.addShape(pptx.ShapeType.line, { x: x2, y: ly, w: cw, h: 0, line: { color: K.hair, width: 1 } });
  ledger.forEach(([k, v]) => {
    ly += 0.05;
    s.addText(k, { x: x2, y: ly, w: cw - 1.2, h: 0.28, fontFace: UI, fontSize: 12, color: K.body, valign: "middle" });
    s.addText(v, { x: x2 + cw - 1.2, y: ly, w: 1.2, h: 0.28, fontFace: UI, fontSize: 12, color: K.ink, align: "right", valign: "middle" });
    ly += 0.28;
    s.addShape(pptx.ShapeType.line, { x: x2, y: ly, w: cw, h: 0, line: { color: K.hair, width: 0.75 } });
  });
  ly += 0.06;
  s.addShape(pptx.ShapeType.line, { x: x2, y: ly, w: cw, h: 0, line: { color: K.ink, width: 1.5 } });
  ly += 0.06;
  s.addText("Credibility score", { x: x2, y: ly, w: cw - 1.2, h: 0.3, fontFace: UI, fontSize: 13, bold: true, color: K.ink, valign: "middle" });
  s.addText("73.75", { x: x2 + cw - 1.2, y: ly, w: 1.2, h: 0.3, fontFace: UI, fontSize: 13, bold: true, color: K.ink, align: "right", valign: "middle" });

  ly += 0.45;
  s.addShape(pptx.ShapeType.rect, { x: x2, y: ly, w: cw, h: 0.09, fill: { color: K.sunken }, line: { color: K.sunken, width: 0 } });
  s.addShape(pptx.ShapeType.rect, { x: x2, y: ly, w: cw * 0.7375, h: 0.09, fill: { color: K.ink }, line: { color: K.ink, width: 0 } });
  s.addText([{ text: "Band: " }, { text: "Moderate", options: { bold: true, color: K.ink } }, { text: " — 60 and above" }], {
    x: x2, y: ly + 0.16, w: cw, h: 0.24, fontFace: UI, fontSize: 11, color: K.mute,
  });

  s.addText("Bands are High, Moderate, Low and Disputed. None is signalled by colour: the band word is always rendered and is always the authority, so the reading survives greyscale printing and colour-blind vision.", {
    x: x2, y: ly + 0.55, w: cw, h: 0.7, fontFace: UI, fontSize: 11, italic: true, color: K.quiet, lineSpacingMultiple: 1.1,
  });
}

/* -- 13 what is running ---------------------------------------------------- */
{
  const { s, y } = slide({ title: "Our prototype — what is running" });
  s.addText("The prototype is deployed and reachable, not a local demonstration. Every figure below is counted from the running system.", {
    x: L, y, w: COLW, h: 0.3, fontFace: UI, fontSize: 13.5, color: K.body,
  });

  const stats = [["77", "API endpoints"], ["16", "Screens"], ["23", "Database tables"], ["6", "User roles"], ["139", "Automated tests"], ["50", "Seeded articles"]];
  const sw = COLW / stats.length;
  const sy = y + 0.45;
  s.addShape(pptx.ShapeType.line, { x: L, y: sy, w: COLW, h: 0, line: { color: K.hair, width: 1 } });
  stats.forEach(([num, label], i) => {
    s.addText(num, {
      x: L + i * sw, y: sy + 0.12, w: sw - 0.12, h: 0.6,
      fontFace: DISPLAY, fontSize: 34, color: K.ink,
    });
    s.addText(label, {
      x: L + i * sw, y: sy + 0.76, w: sw - 0.12, h: 0.24,
      fontFace: UI, fontSize: 11, color: K.mute,
    });
    if (i) s.addShape(pptx.ShapeType.line, { x: L + i * sw - 0.06, y: sy, w: 0, h: 1.05, line: { color: K.hair, width: 0.75 } });
  });
  s.addShape(pptx.ShapeType.line, { x: L, y: sy + 1.05, w: COLW, h: 0, line: { color: K.hair, width: 1 } });

  const cw = (COLW - 0.5) / 2;
  const by = sy + 1.35;
  block(s, { x: L, y: by, w: cw, h: 0.95, size: 11.5, title: "Reading",
    text: "Front page, article with its score ledger and correction history, section pages, writer profiles, keyword search, and a page that explains the scoring in words." });
  block(s, { x: L, y: by + 1.05, w: cw, h: 0.95, size: 11.5, title: "Writing",
    text: "Rich-text editor with source tagging, draft and submission workflow, scheduling, per-article status, and an accuracy rate that updates as the record changes." });
  block(s, { x: L + cw + 0.5, y: by, w: cw, h: 0.95, size: 11.5, title: "Editing and moderation",
    text: "Review queue scoped to assigned sections, flagged-content queue with every reader report shown in full, correction logging, and a dispute queue for appeals." });
  block(s, { x: L + cw + 0.5, y: by + 1.05, w: cw, h: 0.95, size: 11.5, title: "Administration",
    text: "Nine tabs: accounts, applications, editor assignments, platform-wide article moderation, disputes, categories, scoring thresholds and the audit log." });
}

/* -- 14 future development ------------------------------------------------- */
{
  const { s, y } = slide({ title: "Future development" });
  const cw = (COLW - 0.5) / 2;
  const left = [
    ["Security", "Two-factor authentication for editor and administrator accounts; email verification at registration; moving rate-limit counters to shared storage so the API can run more than one worker."],
    ["Account management", "Real transactional email for password resets and notifications, which the prototype currently logs rather than sends."],
    ["Payments", "A real payment gateway in place of the stubbed integration, and scheduled payout runs against the tiered revenue share."],
    ["Country-based news", "Country-scoped feeds so readers see coverage from their own region first, with editors assigned by country as they are by category today."],
  ];
  const right = [
    ["Scoring", "Per-category weights, since a science article and a sports report do not carry the same sourcing expectation; and a public history of threshold changes, so a score movement can be attributed to a policy change rather than to the writer."],
    ["Editorial", "Cover images, comment moderation, and a duplicate-content check surfaced to editors during review."],
    ["Expansion", "A native mobile client, and multi-language publishing with per-language editorial assignment."],
    ["Monthly digest", "A month-end compilation for a chosen topic, collecting the highest-scoring articles in that category into one issue readers can subscribe to."],
  ];
  left.forEach(([t, d], i) => block(s, { x: L, y: y + i * 1.28, w: cw, h: 1.14, title: t, text: d, size: 11 }));
  right.forEach(([t, d], i) => block(s, { x: L + cw + 0.5, y: y + i * 1.28, w: cw, h: 1.14, title: t, text: d, size: 11 }));

  s.addText("Three documentation amendments are also outstanding: the PDD still specifies MySQL, Figure 5.96 states that threshold changes do not affect existing scores when in fact they recalculate, and Figure 5.87's \u201cremove articles\u201d is implemented as unpublish rather than delete, because a corrected article is the record of that correction.", {
    x: L, y: H - 1.05, w: COLW, h: 0.55, fontFace: UI, fontSize: 10.5, italic: true, color: K.quiet, lineSpacingMultiple: 1.1,
  });
}

/* -- 15 questions ---------------------------------------------------------- */
{
  const { s } = slide({ plain: true });
  s.addText("FYP-26-S3-10", {
    x: 0, y: 2.7, w: W, h: 0.26,
    fontFace: UI, fontSize: 10.5, bold: true, color: K.mute, align: "center", charSpacing: 1.4,
  });
  s.addText("Questions", {
    x: 0, y: 3.05, w: W, h: 1.1,
    fontFace: DISPLAY, fontSize: 54, color: K.ink, align: "center",
  });
  s.addText("Live prototype, demonstration accounts and the full test suite are available to run during the session.", {
    x: W / 2 - 3.2, y: 4.3, w: 6.4, h: 0.6,
    fontFace: UI, fontSize: 14, color: K.body, align: "center", lineSpacingMultiple: 1.15,
  });
}

const outFile = path.join(OUT_DIR, "FYP-26-S3-10 Prototype Presentation.pptx");
await pptx.writeFile({ fileName: outFile });
const mb = fs.statSync(outFile).size / 1024 / 1024;
console.log(`\n${path.basename(outFile)} — ${n} slides, ${mb.toFixed(2)} MB`);
