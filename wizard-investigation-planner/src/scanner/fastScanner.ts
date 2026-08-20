/**
 * Fast Scanner — Tier 1 of progressive context.
 *
 * Adapted from the existing Wizard scanner (packages/investigation/src/scanner).
 * Performs a LIGHTWEIGHT, metadata-only walk of the repository. It reads NO file
 * contents — only names, paths, sizes, and structure. This is the raw material
 * the Manifest builder turns into the compact Repository Manifest the Planner
 * receives for its initial call.
 */
import fs from "node:fs/promises";
import path from "node:path";

export interface ScannedFile {
  /** repo-relative POSIX-style path. */
  relativePath: string;
  extension: string; // includes leading dot, or "" if none
  sizeBytes: number;
}

export interface ScanResult {
  repositoryName: string;
  rootPath: string;
  files: ScannedFile[];
  directories: string[]; // repo-relative dir paths
  totalFiles: number;
  totalDirectories: number;
}

const IGNORED_DIRS = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".next",
  "coverage",
  "__pycache__",
  ".venv",
  "venv",
  ".mypy_cache",
  ".pytest_cache",
  ".idea",
  ".vscode",
]);

function toPosix(p: string): string {
  return p.split(path.sep).join("/");
}

async function walk(
  dir: string,
  root: string,
  files: ScannedFile[],
  directories: string[],
): Promise<void> {
  let entries: import("node:fs").Dirent[];
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return; // unreadable dir — skip rather than crash the scan
  }

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (IGNORED_DIRS.has(entry.name)) continue;
      directories.push(toPosix(path.relative(root, fullPath)));
      await walk(fullPath, root, files, directories);
    } else if (entry.isFile()) {
      let sizeBytes = 0;
      try {
        const st = await fs.stat(fullPath);
        sizeBytes = st.size;
      } catch {
        sizeBytes = 0;
      }
      const ext = path.extname(entry.name).toLowerCase();
      files.push({
        relativePath: toPosix(path.relative(root, fullPath)),
        extension: ext,
        sizeBytes,
      });
    }
  }
}

export async function scanRepository(repositoryPath: string): Promise<ScanResult> {
  const absolutePath = path.resolve(repositoryPath);
  const stat = await fs.stat(absolutePath).catch(() => null);
  if (!stat || !stat.isDirectory()) {
    throw new Error(`Repository path does not exist or is not a directory: ${absolutePath}`);
  }

  const files: ScannedFile[] = [];
  const directories: string[] = [];
  await walk(absolutePath, absolutePath, files, directories);

  // Stable ordering for deterministic manifests.
  files.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  directories.sort((a, b) => a.localeCompare(b));

  return {
    repositoryName: path.basename(absolutePath),
    rootPath: absolutePath,
    files,
    directories,
    totalFiles: files.length,
    totalDirectories: directories.length,
  };
}
