const test = require("node:test");
const assert = require("node:assert/strict");
const { validatePublicEvidenceUrlLiteral } = require("../../lib/public-evidence-url");

test("Node public evidence URL helper rejects local hostname suffixes", () => {
  for (const value of [
    "https://foo.localhost/private",
    "https://foo.local/private",
    "https://foo.internal/private"
  ]) {
    assert.throws(() => validatePublicEvidenceUrlLiteral(value), /invalid_public_evidence_url/, value);
  }

  assert.equal(validatePublicEvidenceUrlLiteral("https://example.com/report"), "https://example.com/report");
});

test("Node public evidence URL helper never throws a RangeError for numeric HTML entities", () => {
  const invalidEntities = [
    "https://example.com/&#x110000;",
    "https://example.com/&#xD800;",
    "https://example.com/&#55296;",
    "https://example.com/&#9999999999999999999999;",
    "https://example.com/&#x;"
  ];

  for (const value of invalidEntities) {
    assert.throws(
      () => validatePublicEvidenceUrlLiteral(value),
      (error) => error?.message === "invalid_public_evidence_url",
      value
    );
  }
  assert.equal(
    validatePublicEvidenceUrlLiteral("https://example.com/&#x10FFFF;"),
    "https://example.com/&#x10FFFF;"
  );
});
