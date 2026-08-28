const fsp = require("node:fs/promises");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { once } = require("node:events");

const fixtureDir = path.join(__dirname, "../fixtures/public-bundle");

async function request(target, pathname, { method = "GET", headers = {}, body } = {}) {
  const payload = body === undefined ? null : Buffer.from(typeof body === "string" ? body : JSON.stringify(body));
  const requestHeaders = { ...headers };
  const baseUrl = typeof target === "string" ? target : target.url;
  const socketPath = typeof target === "string" ? undefined : target.socketPath;
  if (socketPath && !requestHeaders.Host && !requestHeaders.host) {
    requestHeaders.Host = "localhost";
  }
  if (payload) {
    requestHeaders["Content-Length"] = payload.length;
    if (!requestHeaders["Content-Type"]) requestHeaders["Content-Type"] = "application/json";
  }
  return new Promise((resolve, reject) => {
    const resolved = new URL(pathname, baseUrl);
    const requestOptions = socketPath ? {
      method,
      headers: requestHeaders,
      socketPath,
      path: `${resolved.pathname}${resolved.search}`,
    } : {
      method,
      headers: requestHeaders,
      hostname: resolved.hostname,
      port: resolved.port,
      path: `${resolved.pathname}${resolved.search}`,
    };
    const outgoing = http.request(
      requestOptions,
      (incoming) => {
      const chunks = [];
      incoming.on("data", (chunk) => chunks.push(chunk));
      incoming.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolve({
          status: incoming.statusCode,
          headers: incoming.headers,
          text,
          json: () => JSON.parse(text)
        });
      });
    });
    outgoing.on("error", reject);
    if (payload) outgoing.write(payload);
    outgoing.end();
  });
}

async function startTestServer({ atlasBundleDir = fixtureDir, prepareDataDir } = {}) {
  const dataDir = await fsp.mkdtemp(path.join(os.tmpdir(), "atlas-server-test-"));
  const socketPath = path.join(dataDir, "atlas-test.sock");
  await fsp.cp(path.join(__dirname, "../../seed-data"), dataDir, { recursive: true });
  if (prepareDataDir) await prepareDataDir(dataDir);

  process.env.DEV_ALLOW_LOCAL_LOGIN = "true";
  process.env.DEV_ADMIN_EMAIL = "admin@example.com";
  process.env.ADMIN_EMAILS = "admin@example.com";
  process.env.PORTFOLIO_DATA_DIR = dataDir;

  const { createApplicationServer } = require("../../server");
  const server = await createApplicationServer({
    socketPath,
    atlasBundleDir,
    dataDir
  });
  if (!server.listening) await once(server, "listening");

  let closed = false;
  return {
    dataDir,
    socketPath,
    url: "http://localhost",
    async close() {
      if (closed) return;
      closed = true;
      if (server.listening) {
        server.closeIdleConnections?.();
        server.closeAllConnections?.();
        await new Promise((resolve, reject) => {
          server.close((error) => error ? reject(error) : resolve());
        });
      }
      await fsp.rm(socketPath, { force: true });
      await fsp.rm(dataDir, { recursive: true, force: true });
    }
  };
}

module.exports = {
  fixtureDir,
  request,
  startTestServer
};
