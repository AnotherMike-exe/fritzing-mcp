// Smoke test: drives fritzing-mcp over stdio with a raw MCP handshake + tool calls.
import { spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

const proc = spawn("uv", ["run", "--project", path.join(import.meta.dir), "fritzing-mcp"], {
  cwd: import.meta.dir,
});
let buf = "";
let id = 0;
const pending = new Map();

proc.stdout.on("data", (d) => {
  buf += d;
  for (;;) {
    const nl = buf.indexOf("\n");
    if (nl < 0) break;
    const line = buf.slice(0, nl).trim();
    buf = buf.slice(nl + 1);
    if (!line) continue;
    const msg = JSON.parse(line);
    if (msg.id !== undefined && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  }
});
proc.stderr.on("data", (d) => console.error("[srv]", String(d)));

function send(method, params) {
  return new Promise((res, rej) => {
    const mid = ++id;
    pending.set(mid, res);
    proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: mid, method, params }) + "\n");
    setTimeout(() => { if (pending.has(mid)) { pending.delete(mid); rej(new Error("timeout " + method)); } }, 120_000);
  });
}

const results = [];
async function call(name, args) {
  const r = await send("tools/call", { name, arguments: args });
  const text = r.result?.content?.[0]?.text ?? JSON.stringify(r);
  results.push({ tool: name, ok: !r.result?.isError, out: text.slice(0, 400) });
  console.log(`\n== ${name} ==\n`, text.slice(0, 400));
  if (r.result?.isError) process.exitCode = 1;
}

const init = await send("initialize", {
  protocolVersion: "2024-11-05",
  capabilities: {},
  clientInfo: { name: "smoke", version: "0.0.1" },
});
console.log("server:", init.result?.serverInfo);
proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");

const tools = await send("tools/list", {});
console.log("tools:", tools.result.tools.map((t) => t.name).join(", "));

const tmp = "/tmp/fritzing-smoke";
fs.rmSync(tmp, { recursive: true, force: true });
const sketch = `${tmp}/smoke.fzz`;
await call("fritzing_search_parts", { query: "resistor", limit: 3 });
await call("fritzing_part_connectors", { module_id: "ResistorModuleID" });
await call("fritzing_new_sketch", { path: sketch, force: true });
await call("fritzing_place_part", { file: sketch, module_id: "ResistorModuleID", x: 300, y: 250, ref: "r1", props: { resistance: "220" } });
await call("fritzing_place_part", { file: sketch, module_id: "3mmColorLEDModuleID", x: 500, y: 250, ref: "led1" });
await call("fritzing_wire", { file: sketch, ref_a: "r1.connector1", ref_b: "led1.connector1", color: "#ff0000" });
await call("fritzing_set_properties", { file: sketch, ref: "led1", props: { color: "Red (633nm)" } });
await call("fritzing_move_part", { file: sketch, ref: "led1", x: 520, y: 250 });
await call("fritzing_show_sketch", { file: sketch });
await call("fritzing_check", { file: sketch });
await call("fritzing_render", { target: tmp, png: true, view: "bb" });

console.log("\nSMOKE:", results.filter(r => r.ok).length + "/" + results.length, "passed");
proc.kill();
