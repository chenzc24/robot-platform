import { cp, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = resolve(scriptDirectory, "..");
const projectDirectory = resolve(frontendDirectory, "..");
const sourceDirectory = resolve(frontendDirectory, "dist");
const backendDirectory = resolve(projectDirectory, "backend");
const targetDirectory = resolve(backendDirectory, "static");

// Docker's isolated frontend build stage and the desktop script's isolated
// source copy do not contain ../backend. Those workflows already copy dist in
// their own later stage, so synchronization is intentionally skipped there.
if (!existsSync(resolve(backendDirectory, "app"))) {
  console.log("Backend source is not present beside frontend; static sync skipped.");
  process.exit(0);
}

if (!existsSync(sourceDirectory)) {
  throw new Error(`Frontend build output does not exist: ${sourceDirectory}`);
}

// Both paths are resolved from this repository layout. Remove only the
// generated backend/static directory, never backend source or project data.
await rm(targetDirectory, { recursive: true, force: true });
await mkdir(targetDirectory, { recursive: true });
await cp(sourceDirectory, targetDirectory, { recursive: true });
console.log(`Synchronized frontend build to ${targetDirectory}`);
