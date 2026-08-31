import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const vendorFiles = [
  ["node_modules/lucide/dist/umd/lucide.min.js", "vendor/lucide.min.js"],
  ["node_modules/marked/lib/marked.umd.js", "vendor/marked.umd.js"],
  ["node_modules/dompurify/dist/purify.min.js", "vendor/purify.min.js"]
];

await mkdir(path.join(root, "vendor"), { recursive: true });
for (const [source, destination] of vendorFiles) {
  await copyFile(path.join(root, source), path.join(root, destination));
}
