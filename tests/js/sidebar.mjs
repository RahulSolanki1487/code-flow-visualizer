// Loads a rendered flow page in jsdom (real Bootstrap, stubbed Mermaid) and exercises the sidebar.
// Usage: node sidebar.mjs <page.html> <bootstrap.bundle.min.js> <jsdom-dir>
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const [, , pagePath, bootstrapPath, jsdomDir] = process.argv;
const require = createRequire(pathToFileURL(jsdomDir + "/"));
const { JSDOM } = require("jsdom");

const renders = [];
const dom = new JSDOM(readFileSync(pagePath, "utf8"), {
  url: "http://localhost/page.html", // history.replaceState needs a real URL
  runScripts: "dangerously",
  pretendToBeVisual: true,
  beforeParse(window) {
    window.scrollTo = () => {}; // not implemented in jsdom
    window.mermaid = {
      initialize() {},
      // slow, out-of-order renders: the first flow finishes AFTER the second
      async render(id, text) {
        renders.push(text);
        await new Promise((r) => setTimeout(r, text.includes("FIRST") ? 60 : 5));
        return { svg: `<svg data-src="${text.includes("FIRST") ? "first" : "second"}" width="10" height="10"></svg>` };
      },
    };
  },
});
dom.window.eval(readFileSync(bootstrapPath, "utf8")); // real Bootstrap tabs (after parse: it needs document)
const { document } = dom.window;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const active = (sel) => document.querySelector(sel).classList.contains("active");

await sleep(100);
const out = {};
const items = document.querySelectorAll("#cfv-flow-list .list-group-item");
out.flowCount = items.length;
const plainBox = () => ({ text: document.getElementById("cfv-plain-text").textContent, hidden: document.getElementById("cfv-plain").classList.contains("d-none") });
out.plainFirst = plainBox();            // flow 1 has a plain summary

// 1. go to the Steps tab, then click the second flow in the sidebar
document.getElementById("cfv-steps-tab").click();
await sleep(50);
out.stepsActiveBefore = active("#tab-steps");
items[1].click();
await sleep(150);
out.diagramActiveAfter = active("#tab-diagram");
out.stepsActiveAfter = active("#tab-steps");
out.title = document.getElementById("cfv-title").textContent;
out.plainSecond = plainBox();           // flow 2 has none: the box must hide, not keep flow 1's text
out.diagramSource = document.querySelector("#cfv-diagram svg")?.getAttribute("data-src") ?? null;

// 2. click flow 0 then flow 1 quickly: the slow first render must not overwrite the second
items[0].click();
items[1].click();
await sleep(200);
out.diagramAfterRace = document.querySelector("#cfv-diagram svg")?.getAttribute("data-src") ?? null;

// 3. the Notes tab then the "Open sub-flow" path / sidebar from Files tab
document.querySelector('[data-bs-target="#tab-files"]').click();
await sleep(50);
items[0].click();
await sleep(150);
out.diagramActiveFromFiles = active("#tab-diagram");
console.log(JSON.stringify(out));
