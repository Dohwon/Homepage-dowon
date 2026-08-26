export class AtlasApiError extends Error {
  constructor(code, status = 0) {
    super(code);
    this.name = "AtlasApiError";
    this.code = code;
    this.status = status;
  }
}

function normalizeBaseUrl(value) {
  const normalized = String(value || "/api/atlas").replace(/\/+$/, "");
  return normalized || "/api/atlas";
}

async function readPayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function createAtlasApi({ baseUrl = "/api/atlas", fetchImpl = globalThis.fetch } = {}) {
  if (typeof fetchImpl !== "function") throw new TypeError("fetch_required");
  const root = normalizeBaseUrl(baseUrl);

  async function get(path, { signal } = {}) {
    const response = await fetchImpl(`${root}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal
    });
    const payload = await readPayload(response);
    if (!response.ok) {
      const code = typeof payload?.error === "string" ? payload.error : "atlas_request_failed";
      throw new AtlasApiError(code, response.status);
    }
    if (payload === null) throw new AtlasApiError("invalid_atlas_response", response.status);
    return payload;
  }

  return Object.freeze({
    bootstrap: options => get("/bootstrap", options),
    project(projectId, options) {
      const id = String(projectId || "").trim();
      if (!id) return Promise.reject(new TypeError("project_id_required"));
      return get(`/projects/${encodeURIComponent(id)}`, options);
    },
    graph: options => get("/graph", options),
    search(query, options) {
      const params = new URLSearchParams({ q: String(query || "") });
      return get(`/search?${params}`, options);
    }
  });
}
