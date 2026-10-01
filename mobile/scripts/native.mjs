import { access, readFile } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { buildMobile, root } from "./build.mjs";
import { buildSettings } from "./config.mjs";

const [platform, ...args] = process.argv.slice(2);
if (!["android", "ios"].includes(platform)) throw new Error("Choose android or ios.");
const settings = buildSettings(args);
process.chdir(root);
const cli = path.join(root, "node_modules/@capacitor/cli/bin/capacitor");
function run(...command) {
  const result = spawnSync(process.execPath, [cli, ...command], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status || 1);
}
let exists = true;
try {
  await access(path.join(root, platform));
} catch {
  exists = false;
}
if (exists) {
  const identityFile =
    platform === "android" ? "android/app/build.gradle" : "ios/App/App.xcodeproj/project.pbxproj";
  const identity = await readFile(path.join(root, identityFile), "utf8");
  if (!identity.includes(settings.appId))
    throw new Error(
      "The native project has a different app ID. Update its bundle/application ID before syncing.",
    );
}
await buildMobile(settings);
if (!exists) run("add", platform);
run("sync", platform);
console.log(
  `${platform} project prepared. ${settings.development ? "DEVELOPMENT build: do not submit to a store." : "Release backend configured; signing and store review are separate steps."}`,
);
if (args.includes("--open")) run("open", platform);
