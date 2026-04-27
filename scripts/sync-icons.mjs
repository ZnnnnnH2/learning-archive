import { execFileSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceIcon = join(
  rootDir,
  "src",
  "assets",
  "branding",
  "sideshell-icon.svg"
);
const tauriIconsDir = join(rootDir, "src-tauri", "icons");
const tauriSourceIcon = join(tauriIconsDir, "icon-source.svg");
const publicDir = join(rootDir, "public");
const faviconTarget = join(publicDir, "favicon.svg");
const tauriCli = join(rootDir, "node_modules", "@tauri-apps", "cli", "tauri.js");
const tempOutputDir = mkdtempSync(join(tmpdir(), "sideshell-icons-"));
const generatedDesktopAssets = [
  "32x32.png",
  "128x128.png",
  "128x128@2x.png",
  "icon.png",
  "icon.ico",
  "icon.icns",
  "StoreLogo.png",
  "Square30x30Logo.png",
  "Square44x44Logo.png",
  "Square71x71Logo.png",
  "Square89x89Logo.png",
  "Square107x107Logo.png",
  "Square142x142Logo.png",
  "Square150x150Logo.png",
  "Square284x284Logo.png",
  "Square310x310Logo.png",
];
const legacyUnusedOutputs = ["64x64.png", "android", "ios"];

mkdirSync(tauriIconsDir, { recursive: true });
mkdirSync(publicDir, { recursive: true });

const iconSvg = readFileSync(sourceIcon);

writeFileSync(tauriSourceIcon, iconSvg);
writeFileSync(faviconTarget, iconSvg);

for (const relativePath of legacyUnusedOutputs) {
  const target = join(tauriIconsDir, relativePath);
  if (existsSync(target)) {
    rmSync(target, { recursive: true, force: true });
  }
}

execFileSync(process.execPath, [tauriCli, "icon", sourceIcon, "-o", tempOutputDir], {
  cwd: rootDir,
  stdio: "inherit",
});

for (const relativePath of generatedDesktopAssets) {
  const source = join(tempOutputDir, relativePath);
  const target = join(tauriIconsDir, relativePath);
  writeFileSync(target, readFileSync(source));
}

rmSync(tempOutputDir, { recursive: true, force: true });
