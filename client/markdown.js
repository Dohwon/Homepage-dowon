function browserDependency(name) {
  return globalThis[name] || globalThis.window?.[name];
}

function stripUnsafeHtmlUrls(html) {
  return String(html).replace(/\s(href|src)=(['"])(.*?)\2/gi, (match, attribute, quote, value) => (
    isSafeUrl(value) ? ` ${attribute}=${quote}${value}${quote}` : ""
  ));
}

function isPrivateIpv4(hostname) {
  if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(hostname)) return false;
  const [first, second] = hostname.split(".").map(Number);
  if (first === 10 || first === 127) return true;
  if (first === 169 && second === 254) return true;
  if (first === 192 && second === 168) return true;
  return first === 172 && second >= 16 && second <= 31;
}

function isSafeUrl(value) {
  const href = String(value || "").trim();
  if (!href) return false;
  if (href.startsWith("#")) return true;
  if (href.startsWith("/") && !href.startsWith("//")) return true;
  try {
    const url = new URL(href, "https://atlas.invalid");
    return /^https:$/i.test(url.protocol) && !isPrivateIpv4(url.hostname) && url.hostname !== "localhost";
  } catch {
    return false;
  }
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

  return stripUnsafeHtmlUrls(purifier.sanitize(raw, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["script", "style", "iframe", "object", "embed"],
    FORBID_ATTR: ["style", "onerror", "onclick"],
    ALLOWED_URI_REGEXP: /^(?:(?:https:)?\/\/|\/(?!\/)|#)/i
  }));
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
