import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import ts from "typescript";

async function importTranspiledTs(path) {
  const sourcePath = resolve(path);
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
  return import(moduleUrl);
}

const ordering = await importTranspiledTs("src/activityOrdering.ts");
const hydration = await importTranspiledTs("src/projectHydration.ts");

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

{
  const projects = Object.fromEntries(
    Array.from({ length: 8 }, (_, index) => {
      const id = `project${index + 1}`;
      return [
        id,
        {
          id,
          name: id,
          path: `D:\\${id}`,
          expanded: true,
          shellIds: [],
        },
      ];
    })
  );
  const expanded = hydration.applyDefaultProjectExpansion(
    projects,
    Object.keys(projects)
  );
  assert.deepEqual(
    Object.values(expanded).map((project) => project.expanded),
    [true, true, true, true, true, true, false, false]
  );
}

{
  const projects = Object.fromEntries(
    Array.from({ length: 6 }, (_, index) => {
      const id = `project${index + 1}`;
      return [
        id,
        {
          id,
          name: id,
          path: `D:\\${id}`,
          expanded: false,
          shellIds: [],
        },
      ];
    })
  );
  const expanded = hydration.applyDefaultProjectExpansion(
    projects,
    Object.keys(projects)
  );
  assert.equal(
    Object.values(expanded).every((project) => project.expanded),
    true
  );
}

{
  const shells = {};
  const projects = Object.fromEntries(
    Array.from({ length: 8 }, (_, index) => {
      const id = `project${index + 1}`;
      return [
        id,
        {
          id,
          name: id,
          path: `D:\\${id}`,
          expanded: true,
          shellIds: [],
          updatedAt: index === 7 ? undefined : localNoon(-index),
        },
      ];
    })
  );
  const sortedProjectOrder = ordering.sortProjectsByActivityDay(
    Object.keys(projects),
    projects,
    shells
  );
  const expanded = hydration.applyDefaultProjectExpansion(
    projects,
    sortedProjectOrder
  );
  assert.equal(sortedProjectOrder.at(-1), "project8");
  assert.equal(expanded.project8.expanded, false);
}

console.log("activity ordering tests passed");
