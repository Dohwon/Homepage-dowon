function browserDependency(name) {
  return globalThis[name] || globalThis.window?.[name];
}

export function renderMarkdown(source) {
  const marked = browserDependency("marked");
  const purifier = browserDependency("DOMPurify");
  if (typeof marked?.parse !== "function" || typeof purifier?.sanitize !== "function") {
    throw new Error("markdown_renderer_unavailable");
  }

  const raw = marked.parse(String(source ?? ""), { gfm: true, breaks: false });
  if (raw && typeof raw.then === "function") {
    throw new Error("async_markdown_not_supported");
  }

  return purifier.sanitize(raw, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed"],
    FORBID_ATTR: ["style", "onerror", "onclick"]
  });
}
