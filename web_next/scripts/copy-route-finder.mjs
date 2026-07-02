import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webNext = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = join(webNext, "..");
const dest = join(webNext, "route_finder");

const sources = [
  join(repoRoot, "route_finder"),
  join(webNext, "route_finder"),
];

const src = sources.find((path) => existsSync(path));
if (!src) {
  console.error("route_finder package not found. Checked:", sources.join(", "));
  process.exit(1);
}

if (src !== dest) {
  if (existsSync(dest)) {
    rmSync(dest, { recursive: true, force: true });
  }
  cpSync(src, dest, {
    recursive: true,
    filter: (path) => !path.includes("__pycache__") && !path.endsWith(".pyc"),
  });
  console.log("Copied route_finder into web_next for Vercel Python API");
} else {
  console.log("route_finder already present in web_next");
}
