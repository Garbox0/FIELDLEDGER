import assert from "node:assert/strict";
import test from "node:test";
import { ACTIONS, ORGANIZATIONS } from "../fabric";

test("exposes only the three consortium organizations", () => {
  assert.deepEqual(Object.keys(ORGANIZATIONS), ["OperatorOrg", "ContractorOrg", "AuditorOrg"]);
});

test("whitelists the four ledger mutations", () => {
  assert.deepEqual(Object.keys(ACTIONS), ["REGISTER_ASSET", "PROPOSE_EVENT", "REVIEW_EVENT", "REGISTER_DOCUMENT"]);
});
