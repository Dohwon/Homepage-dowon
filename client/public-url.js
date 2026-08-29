const CONTROL_OR_SPACE = /[\u0000-\u0020\u007F]/;
const IPV4_LITERAL = /^(?:\d{1,3}\.){3}\d{1,3}$/;
const HTML_ENTITY = /&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]+);/gi;
const NUMERIC_ENTITY_CANDIDATE = /&#(?:x[^;]*|[^;]*);/gi;
const TAG_WITH_ATTRIBUTES = /<([a-z][a-z0-9:-]*)(\s[^<>]*?)?>/gi;
const ATTRIBUTE_WITH_URL = /\s(href|src|xlink:href|action|formaction)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/gi;
const URL_ATTRIBUTES = Object.freeze(["href", "src", "xlink:href", "action", "formaction"]);
const NAMED_ENTITIES = Object.freeze({
  amp: "&",
  apos: "'",
  colon: ":",
  gt: ">",
  lt: "<",
  newline: "\n",
  quot: '"',
  tab: "\t"
});

function decodeHtmlEntities(value) {
  return String(value).replace(HTML_ENTITY, (match, token) => {
    const normalized = String(token).toLowerCase();
    if (normalized.startsWith("#x")) {
      const codePoint = Number.parseInt(normalized.slice(2), 16);
      return isUnicodeScalar(codePoint) ? String.fromCodePoint(codePoint) : match;
    }
    if (normalized.startsWith("#")) {
      const codePoint = Number.parseInt(normalized.slice(1), 10);
      return isUnicodeScalar(codePoint) ? String.fromCodePoint(codePoint) : match;
    }
    return Object.hasOwn(NAMED_ENTITIES, normalized) ? NAMED_ENTITIES[normalized] : match;
  });
}

function isUnicodeScalar(codePoint) {
  return Number.isInteger(codePoint)
    && codePoint >= 0
    && codePoint <= 0x10FFFF
    && (codePoint < 0xD800 || codePoint > 0xDFFF);
}

function hasInvalidNumericEntity(value) {
  return String(value).match(NUMERIC_ENTITY_CANDIDATE)?.some((entity) => {
    const token = entity.slice(2, -1).toLowerCase();
    const hexadecimal = token.startsWith("x");
    const digits = hexadecimal ? token.slice(1) : token;
    if (!(hexadecimal ? /^[0-9a-f]+$/ : /^\d+$/).test(digits)) return true;
    return !isUnicodeScalar(Number.parseInt(digits, hexadecimal ? 16 : 10));
  }) ?? false;
}

function decodePercent(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalizeLeadingSegment(value) {
  const trimmed = String(value ?? "").trim();
  const stop = trimmed.search(/[/?#]/);
  const segment = stop === -1 ? trimmed : trimmed.slice(0, stop);
  return segment.replace(CONTROL_OR_SPACE, "");
}

function schemeOf(value) {
  const match = normalizeLeadingSegment(value).match(/^([a-z][a-z0-9+.-]*):/i);
  return match ? match[1].toLowerCase() : "";
}

function revealsObfuscatedScheme(rawValue) {
  let current = String(rawValue ?? "").trim();
  for (let index = 0; index < 4; index += 1) {
    const nextEntity = decodeHtmlEntities(current);
    if (nextEntity !== current) {
      const currentScheme = schemeOf(current);
      const nextScheme = schemeOf(nextEntity);
      if (nextScheme && (nextScheme !== currentScheme || normalizeLeadingSegment(nextEntity) !== normalizeLeadingSegment(current))) {
        return true;
      }
      current = nextEntity;
      continue;
    }
    const nextPercent = decodePercent(current);
    if (nextPercent !== current) {
      const currentScheme = schemeOf(current);
      const nextScheme = schemeOf(nextPercent);
      if (nextScheme && (nextScheme !== currentScheme || normalizeLeadingSegment(nextPercent) !== normalizeLeadingSegment(current))) {
        return true;
      }
      current = nextPercent;
      continue;
    }
    break;
  }
  return false;
}

function normalizeHost(hostname) {
  return String(hostname || "").toLowerCase().replace(/^\[|\]$/g, "").replace(/\.+$/g, "");
}

function isLocalHostname(hostname) {
  return ["localhost", "local", "internal"].some((suffix) => (
    hostname === suffix || hostname.endsWith(`.${suffix}`)
  ));
}

function isIpLiteral(hostname) {
  return IPV4_LITERAL.test(hostname) || hostname.includes(":");
}

export function toSafePublicHref(value, { allowRelative = false, allowFragment = false } = {}) {
  const href = String(value ?? "").trim();
  if (!href || href.includes("\\") || CONTROL_OR_SPACE.test(href)) return "";
  if (hasInvalidNumericEntity(href)) return "";
  if (revealsObfuscatedScheme(href)) return "";
  if (allowFragment && href.startsWith("#")) return href;
  if (allowRelative && href.startsWith("/") && !href.startsWith("//")) return href;
  const explicitScheme = schemeOf(href);
  if (explicitScheme && explicitScheme !== "https") return "";

  let parsed;
  try {
    parsed = new URL(href);
  } catch {
    return "";
  }
  if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password) return "";
  const hostname = normalizeHost(parsed.hostname);
  if (!hostname || isLocalHostname(hostname) || isIpLiteral(hostname)) return "";
  return parsed.toString();
}

function attributePolicy(tagName, attributeName, options) {
  const anchorHref = tagName === "a" && attributeName === "href";
  const sourceAttribute = attributeName === "src";
  return {
    allowRelative: options.allowRelative && (anchorHref || sourceAttribute),
    allowFragment: options.allowFragment && anchorHref
  };
}

function sanitizeWithDom(html, options) {
  const parser = new DOMParser();
  const document = parser.parseFromString(`<body>${html}</body>`, "text/html");
  const elements = document.body.querySelectorAll("[href], [src], [xlink\\:href], [action], [formaction]");
  for (const element of elements) {
    const tagName = element.tagName.toLowerCase();
    for (const attributeName of URL_ATTRIBUTES) {
      if (!element.hasAttribute(attributeName)) continue;
      const safeHref = toSafePublicHref(element.getAttribute(attributeName), attributePolicy(tagName, attributeName, options));
      if (safeHref) element.setAttribute(attributeName, safeHref);
      else element.removeAttribute(attributeName);
    }
  }
  return document.body.innerHTML;
}

function sanitizeWithRegex(html, options) {
  return String(html).replace(TAG_WITH_ATTRIBUTES, (match, tagName, attributeSource = "") => {
    const sanitizedAttributes = attributeSource.replace(ATTRIBUTE_WITH_URL, (attributeMatch, attributeName, wholeValue, doubleQuoted, singleQuoted, bareValue) => {
      const rawValue = doubleQuoted ?? singleQuoted ?? bareValue ?? "";
      const quote = doubleQuoted !== undefined ? '"' : singleQuoted !== undefined ? "'" : "";
      const safeHref = toSafePublicHref(rawValue, attributePolicy(String(tagName).toLowerCase(), attributeName.toLowerCase(), options));
      return safeHref ? ` ${attributeName}=${quote}${safeHref}${quote}` : "";
    });
    return `<${tagName}${sanitizedAttributes}>`;
  });
}

export function sanitizeHtmlUrls(html, options = {}) {
  if (!html) return "";
  if (typeof DOMParser === "function") return sanitizeWithDom(html, options);
  return sanitizeWithRegex(html, options);
}
