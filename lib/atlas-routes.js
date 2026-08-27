function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

async function handleAtlasApi(req, res, url, store) {
  if (req.method === "GET" && url.pathname === "/api/atlas/bootstrap") {
    sendJson(res, 200, await store.bootstrap());
    return true;
  }

  if (req.method === "GET" && url.pathname.startsWith("/api/atlas/projects/")) {
    const id = decodeURIComponent(url.pathname.slice("/api/atlas/projects/".length));
    const project = await store.project(id);
    if (!project) sendJson(res, 404, { error: "project_not_found" });
    else sendJson(res, 200, project);
    return true;
  }

  if (req.method === "GET" && url.pathname === "/api/atlas/graph") {
    sendJson(res, 200, await store.graph());
    return true;
  }

  if (req.method === "GET" && url.pathname === "/api/atlas/search") {
    sendJson(res, 200, { items: await store.search(url.searchParams.get("q") || "") });
    return true;
  }

  return false;
}

module.exports = {
  handleAtlasApi
};
