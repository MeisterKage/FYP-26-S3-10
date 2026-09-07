import { chromium } from "playwright";
const { BW, MERMAID_THEME } = await import("./make-pdf-consts.mjs");
const M="https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js";
const b=await chromium.launch();
const p=await b.newPage({viewport:{width:1100,height:1500}});
await p.goto("file:///D:/Shawn/Claude%20Code/FYP/docs/technical-report.html",{waitUntil:"networkidle"});
await p.addScriptTag({url:M});
await p.evaluate(async cfg=>{mermaid.initialize(cfg);await mermaid.run({querySelector:"pre.mermaid"});},MERMAID_THEME);
await p.addStyleTag({content:BW});
await p.waitForTimeout(1500);
for (const [id,name] of [["#s5-3-5","arch"],["#s5-3-8","seq"]]) {
  await p.locator(id).scrollIntoViewIfNeeded(); await p.waitForTimeout(700);
  await p.screenshot({path:`vcheck-${name}.png`});
}
await b.close(); console.log("captured");
