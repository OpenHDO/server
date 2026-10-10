import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/notifications-state.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext },
}).outputText;
const { addNotice } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);

test("repeated errors do not duplicate active notifications", () => {
  const current = Object.freeze([
    { id: 1, tone: "error", message: "Unavailable" },
  ]);
  assert.equal(
    addNotice(current, { id: 2, tone: "error", message: "Unavailable" }),
    current,
  );
  assert.equal(
    addNotice(current, { id: 3, tone: "success", message: "Unavailable" })
      .length,
    2,
  );
});

test("notification stack keeps only the newest three without changing prior state", () => {
  const current = Object.freeze(
    [1, 2, 3].map((id) => ({ id, tone: "success", message: `Saved ${id}` })),
  );
  const next = addNotice(current, { id: 4, tone: "error", message: "Failed" });
  assert.deepEqual(
    next.map((item) => item.id),
    [2, 3, 4],
  );
  assert.deepEqual(
    current.map((item) => item.id),
    [1, 2, 3],
  );
});
