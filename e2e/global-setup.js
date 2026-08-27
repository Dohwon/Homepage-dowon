const fsp = require("node:fs/promises");
const path = require("node:path");

module.exports = async function globalSetup() {
  const root = path.join(__dirname, "..");
  const target = path.join(root, ".atlas-test-data");
  await fsp.rm(target, { recursive: true, force: true });
  await fsp.cp(path.join(root, "seed-data"), target, { recursive: true });
};
