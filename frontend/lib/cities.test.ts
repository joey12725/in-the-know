import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isPilotCity, normalizeCity } from "./cities.ts";

type Case = { input: string; expected: string };

const cases = JSON.parse(
  readFileSync(new URL("../../shared/city-normalization-cases.json", import.meta.url), "utf8"),
) as Case[];

for (const { input, expected } of cases) {
  test(`normalizeCity(${JSON.stringify(input)})`, () => {
    assert.equal(normalizeCity(input), expected);
  });
}

test("pilot city gate", () => {
  assert.equal(isPilotCity("San Antonio, TX 78205"), true);
  assert.equal(isPilotCity("Portland, OR"), false);
});
