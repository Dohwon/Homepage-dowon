import { sanitizeHtmlUrls } from "./public-url.js";

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

  return sanitizeHtmlUrls(purifier.sanitize(raw, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed"],
    FORBID_ATTR: ["style", "onerror", "onclick"],
    ALLOWED_URI_REGEXP: /^(?:(?:https:)?\/\/|\/(?!\/)|#)/i
  }), {
    allowRelative: true,
    allowFragment: true
  });
}

export function sanitizeSvg(source) {
  const purifier = browserDependency("DOMPurify");
  if (typeof purifier?.sanitize !== "function" || !source) return "";
  const sanitized = purifier.sanitize(String(source), {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ["script", "foreignObject", "iframe", "object", "embed"],
    FORBID_ATTR: ["style", "onload", "onclick", "onerror", "href", "xlink:href"]
  });
  return /<svg[\s>]/i.test(sanitized) ? sanitized : "";
}
