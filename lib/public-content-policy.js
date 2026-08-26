class UnsafePublicContentError extends Error {
  constructor(category) {
    super(`unsafe_public_content: ${category}`);
    this.name = "UnsafePublicContentError";
    this.code = "unsafe_public_content";
    this.category = category;
  }
}

const DETECTORS = [
  ["secret", /(?:\bsk-[A-Za-z0-9_-]{12,}\b|\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{12,}\b|\bAKIA[A-Z0-9]{16}\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*["']?[^\s"']{8,})/i],
  ["absolute_path", /(?:^|[\s"'(`])(?:\/home\/[^\s<>"']+|\/Users\/[^\s<>"']+|[A-Za-z]:[\\/]Users[\\/][^\s<>"']+|\\\\[^\\/\s]+[\\/][^\\/\s]+)/],
  ["email", /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i],
  ["phone", /(?<![A-Za-z0-9])(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?![A-Za-z0-9])/],
  ["private_ip", /\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b/],
  ["html_comment", /<!--[\s\S]*?-->/],
  ["source_map", /(?:\bsourceMappingURL\s*=\s*\S+|\b[A-Za-z0-9_.\/-]+\.map\b)/i],
  ["internal_url", /https?:\/\/(?:localhost|127\.0\.0\.1|\[::1\]|[^\s/:]+\.(?:internal|local))(?:[:/]|$)/i]
];

function assertSafePublicValue(value) {
  visit(value);
  return value;
}

function visit(value) {
  if (typeof value === "string") {
    inspectString(value);
    return;
  }
  if (value === null || value === undefined || typeof value === "boolean" || typeof value === "number") {
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) visit(item);
    return;
  }
  if (typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      inspectString(key);
      visit(item);
    }
    return;
  }
  throw new UnsafePublicContentError("unsupported_value");
}

function inspectString(value) {
  for (const [category, pattern] of DETECTORS) {
    if (pattern.test(value)) throw new UnsafePublicContentError(category);
  }
}

module.exports = {
  UnsafePublicContentError,
  assertSafePublicValue
};
