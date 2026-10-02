import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = resolve(SCRIPT_DIR, "..");
const PACKAGE_JSON_PATH = resolve(ROOT_DIR, "package.json");
const TAURI_CONFIG_PATH = resolve(ROOT_DIR, "src-tauri", "tauri.conf.json");
const CARGO_TOML_PATH = resolve(ROOT_DIR, "src-tauri", "Cargo.toml");
const TAURI_CLI_PATH = resolve(
  ROOT_DIR,
  "node_modules",
  "@tauri-apps",
  "cli",
  "tauri.js"
);

const args = process.argv.slice(2);
const dryRun = args.includes("--dry-run");
const versionArg = getPositionalArgs(args)[0] ?? "patch";
const bundleArg = getOptionValue(args, "--bundles") ?? "nsis";
const originals = new Map();

try {
  const packageJsonText = rememberOriginal(PACKAGE_JSON_PATH);
  const tauriConfigText = rememberOriginal(TAURI_CONFIG_PATH);
  const cargoTomlText = rememberOriginal(CARGO_TOML_PATH);

  const packageJson = JSON.parse(packageJsonText);
  const tauriConfig = JSON.parse(tauriConfigText);
  const currentVersion = packageJson.version;
  const nextVersion = resolveNextVersion(currentVersion, versionArg);

  if (nextVersion === currentVersion) {
    throw new Error(`target version is unchanged: ${currentVersion}`);
  }

  packageJson.version = nextVersion;
  tauriConfig.version = nextVersion;

  const nextCargoToml = replaceCargoPackageVersion(cargoTomlText, nextVersion);

  if (!dryRun) {
    writeText(PACKAGE_JSON_PATH, `${JSON.stringify(packageJson, null, 2)}\n`);
    writeText(TAURI_CONFIG_PATH, `${JSON.stringify(tauriConfig, null, 2)}\n`);
    writeText(CARGO_TOML_PATH, nextCargoToml);
  }

  console.log(`Version: ${currentVersion} -> ${nextVersion}`);

  if (dryRun) {
    console.log("Dry run only. No files were changed and no build was started.");
    process.exit(0);
  }

  runTauriBuild(["build", "--bundles", resolveBundles(bundleArg)]);
} catch (error) {
  restoreOriginals();
  console.error(
    error instanceof Error ? error.message : String(error)
  );
  process.exit(1);
}

function rememberOriginal(path) {
  const text = readFileSync(path, "utf8");
  originals.set(path, text);
  return text;
}

function restoreOriginals() {
  for (const [path, text] of originals) {
    try {
      writeText(path, text);
    } catch {}
  }
}

function writeText(path, text) {
  writeFileSync(path, text, "utf8");
}

function getPositionalArgs(inputArgs) {
  const positionals = [];

  for (let index = 0; index < inputArgs.length; index += 1) {
    const arg = inputArgs[index];
    if (arg === "--bundles") {
      index += 1;
      continue;
    }
    if (arg.startsWith("--bundles=") || arg.startsWith("-")) {
      continue;
    }
    positionals.push(arg);
  }

  return positionals;
}

function getOptionValue(inputArgs, optionName) {
  for (let index = 0; index < inputArgs.length; index += 1) {
    const arg = inputArgs[index];
    if (arg === optionName) {
      return inputArgs[index + 1] ?? null;
    }
    if (arg.startsWith(`${optionName}=`)) {
      return arg.slice(optionName.length + 1);
    }
  }
  return null;
}

function resolveNextVersion(currentVersion, requested) {
  const current = parseVersion(currentVersion);
  const normalized = requested.trim().toLowerCase();

  if (normalized === "patch") {
    return `${current.major}.${current.minor}.${current.patch + 1}`;
  }
  if (normalized === "minor") {
    return `${current.major}.${current.minor + 1}.0`;
  }
  if (normalized === "major") {
    return `${current.major + 1}.0.0`;
  }

  return formatVersion(parseVersion(requested));
}

function parseVersion(value) {
  const match = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(value.trim());
  if (!match) {
    throw new Error(
      `invalid version "${value}". Use patch, minor, major, or x.y.z`
    );
  }

  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
  };
}

function formatVersion(version) {
  return `${version.major}.${version.minor}.${version.patch}`;
}

function replaceCargoPackageVersion(cargoTomlText, nextVersion) {
  const lines = cargoTomlText.split(/\r?\n/);
  let inPackageSection = false;
  let replaced = false;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (/^\s*\[package\]\s*$/.test(line)) {
      inPackageSection = true;
      continue;
    }
    if (/^\s*\[.+\]\s*$/.test(line)) {
      inPackageSection = false;
    }
    if (inPackageSection && /^\s*version\s*=/.test(line)) {
      lines[index] = `version = "${nextVersion}"`;
      replaced = true;
      break;
    }
  }

  if (!replaced) {
    throw new Error("failed to update version in src-tauri/Cargo.toml");
  }

  return `${lines.join("\n")}\n`;
}

function resolveBundles(value) {
  const normalized = value.trim().toLowerCase();
  if (!normalized || normalized === "default") {
    return "nsis";
  }
  if (normalized === "all") {
    return "nsis,msi";
  }

  const bundles = normalized
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  if (bundles.length === 0) {
    throw new Error("invalid --bundles value");
  }

  for (const bundle of bundles) {
    if (bundle !== "nsis" && bundle !== "msi") {
      throw new Error(
        `unsupported bundle "${bundle}". Use nsis, msi, or all`
      );
    }
  }

  return bundles.join(",");
}

function runTauriBuild(commandArgs) {
  const result = spawnSync(process.execPath, [TAURI_CLI_PATH, ...commandArgs], {
    cwd: ROOT_DIR,
    stdio: "inherit",
    env: process.env,
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(
      `tauri ${commandArgs.join(" ")} failed with exit code ${result.status}`
    );
  }
}
