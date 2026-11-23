// Reads a JSON array of {id, text} from stdin, prints a JSON array of {id, ok, error}.
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><body></body>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const mermaid = (await import("mermaid")).default;

const items = JSON.parse(readFileSync(0, "utf8"));
const results = [];
for (const { id, text } of items) {
  try {
    await mermaid.parse(text);
    results.push({ id, ok: true });
  } catch (e) {
    results.push({ id, ok: false, error: String(e?.message ?? e) });
  }
}
console.log(JSON.stringify(results));
