import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import ts from "typescript";

const sourcePath = resolve("src/activityOrdering.ts");
const source = await readFile(sourcePath, "utf8");
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
    verbatimModuleSyntax: false,
  },
  fileName: sourcePath,
}).outputText;

const moduleUrl =
  "data:text/javascript;base64," + Buffer.from(transpiled).toString("base64");
const ordering = await import(moduleUrl);

function localNoon(dayOffset) {
  const now = new Date();
  return new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() + dayOffset,
    12,
    0,
    0,
    0
  ).getTime();
}

{
  const updatedAt = {
    older: localNoon(-7),
    today: localNoon(0),
    yesterday: localNoon(-1),
  };
  assert.deepEqual(
    ordering.sortIdsByActivityDay(
      ["older", "today", "yesterday"],
      (id) => updatedAt[id]
    ),
    ["today", "yesterday", "older"]
  );
}

{
  const sameDayMorning = new Date(localNoon(0)).setHours(8);
  const sameDayEvening = new Date(localNoon(0)).setHours(20);
  assert.deepEqual(
    ordering.sortIdsByActivityDay(["evening", "morning"], (id) =>
      id === "evening" ? sameDayEvening : sameDayMorning
    ),
    ["evening", "morning"]
  );
}

{
  assert.deepEqual(
    ordering.sortIdsByActivityDay(["a", "b", "c"], () => undefined),
    ["a", "b", "c"]
  );
}

{
  const shells = {
    shellOld: { updatedAt: localNoon(-5) },
    shellToday: { updatedAt: localNoon(0) },
    shellMissing: {},
  };
  assert.deepEqual(
    ordering.sortShellIdsByActivityDay(
      ["shellOld", "shellToday", "shellMissing"],
      shells
    ),
    ["shellToday", "shellOld", "shellMissing"]
  );
}

{
  const shells = {
    childToday: { updatedAt: localNoon(0) },
    childOld: { updatedAt: localNoon(-10) },
  };
  const projects = {
    projectByChild: {
      updatedAt: localNoon(-30),
      shellIds: ["childToday"],
    },
    projectYesterday: {
      updatedAt: localNoon(-1),
      shellIds: ["childOld"],
    },
    projectMissing: {
      shellIds: [],
    },
  };
  assert.deepEqual(
    ordering.sortProjectsByActivityDay(
      ["projectYesterday", "projectMissing", "projectByChild"],
      projects,
      shells
    ),
    ["projectByChild", "projectYesterday", "projectMissing"]
  );
}

console.log("activity ordering tests passed");
