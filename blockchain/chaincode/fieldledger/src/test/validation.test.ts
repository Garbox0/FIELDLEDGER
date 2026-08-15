import assert from "node:assert/strict";
import test from "node:test";
import { parsePayload, requireSha256 } from "../validation";

test("accepts a valid object and SHA-256", () => {
  assert.deepEqual(parsePayload('{"assetId":"A-1"}'), { assetId: "A-1" });
  assert.equal(requireSha256("a".repeat(64)), "a".repeat(64));
});

test("rejects arrays and malformed hashes", () => {
  assert.throws(() => parsePayload("[]"), /JSON object/);
  assert.throws(() => requireSha256("abc"), /SHA-256/);
});
