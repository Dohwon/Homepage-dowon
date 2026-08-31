function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(payload));
}

function sendImage(res, image) {
  res.writeHead(200, {
    "Content-Type": image.contentType,
    "Content-Length": image.bytes.length,
    "Cache-Control": "public, max-age=3600"
  });
  res.end(image.bytes);
}

async function handleAtlasApi(req, res, url, store) {
  if (req.method === "GET" && url.pathname === "/api/atlas/bootstrap") {
    sendJson(res, 200, await store.bootstrap());
    return true;
  }

  const coverMatch = /^\/api\/atlas\/projects\/([^/]+)\/cover$/.exec(url.pathname);
  if (req.method === "GET" && coverMatch) {
    const id = decodeURIComponent(coverMatch[1]);
    const cover = await store.cover(id);
    if (!cover) sendJson(res, 404, { error: "cover_not_found" });
    else sendImage(res, cover);
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
