const { isIP } = require("node:net");

const CONTROL_OR_SPACE = /[\u0000-\u0020\u007F]/;
const HTML_ENTITY = /&(#x[0-9a-f]+|#\d+|[a-z][a-z0-9]+);/gi;
const NUMERIC_ENTITY_CANDIDATE = /&#(?:x[^;]*|[^;]*);/gi;
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

function validatePublicEvidenceUrlLiteral(value) {
  if (typeof value !== "string") throw new Error("invalid_public_evidence_url");
  const href = value.trim();
  if (!href || href.includes("\\") || CONTROL_OR_SPACE.test(href) || hasInvalidNumericEntity(href) || revealsObfuscatedScheme(href)) {
    throw new Error("invalid_public_evidence_url");
  }
  if (schemeOf(href) !== "https") throw new Error("invalid_public_evidence_url");

  let parsed;
  try {
    parsed = new URL(href);
  } catch {
    throw new Error("invalid_public_evidence_url");
  }
  if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password) {
    throw new Error("invalid_public_evidence_url");
  }
  const hostname = normalizeHost(parsed.hostname);
  if (!hostname || isLocalHostname(hostname) || isIP(hostname) !== 0) {
    throw new Error("invalid_public_evidence_url");
  }
  return parsed.toString();
}

module.exports = {
  validatePublicEvidenceUrlLiteral
};
