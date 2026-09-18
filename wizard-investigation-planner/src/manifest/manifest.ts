/**
 * Manifest builder — turns a raw ScanResult into the compact Repository
 * Manifest. Also renders the human/LLM-facing compact text form used in the
 * initial Planner prompt (the "200–500 token" summary from the design doc).
 */
import type { ScanResult, ScannedFile } from "../scanner/fastScanner.ts";
import type { ManifestFile, RepositoryManifest } from "./types.ts";
import {
  detectDatabases,
  detectDependencies,
  detectEntryFiles,
  detectFrameworks,
  detectLanguages,
  detectPackageManagers,
  detectProjectType,
  detectStructure,
} from "./detectors.ts";

/**
 * How many repo files ride along in the manifest. A target the user names has
 * to be resolvable to a real path, and that check is only as good as the list
 * it runs against — but the manifest is Tier-1 context, so it is bounded
 * rather than exhaustive. 2000 covers every repo this has been run on while
 * keeping the payload well under a megabyte.
 */
const _TREE_FILE_CAP = 2000;

/** Well-known signal files the Planner cares about. */
export const KEY_FILE_NAMES: readonly string[] = [
  "package.json",
  "package-lock.json",
  "pnpm-lock.yaml",
  "yarn.lock",
  "tsconfig.json",
  "Dockerfile",
  "docker-compose.yml",
  "docker-compose.yaml",
  "requirements.txt",
  "pyproject.toml",
  "poetry.lock",
  "Pipfile",
  "manage.py",
  "pom.xml",
  "build.gradle",
  "go.mod",
  "go.sum",
  "Cargo.toml",
  "Cargo.lock",
  "README.md",
  ".env.example",
  "Makefile",
  "runtime.txt",
  "Procfile",
];

function baseName(p: string): string {
  const idx = p.lastIndexOf("/");
  return idx >= 0 ? p.slice(idx + 1) : p;
}

function collectKeyFiles(files: ScannedFile[]): ManifestFile[] {
  const wanted = new Set(KEY_FILE_NAMES);
  const out: ManifestFile[] = [];
  for (const f of files) {
    const bn = baseName(f.relativePath);
    if (wanted.has(bn)) {
      out.push({ path: f.relativePath, sizeBytes: f.sizeBytes, extension: f.extension });
    }
    // GitHub Actions workflows are a signal even though the filename varies.
    if (f.relativePath.startsWith(".github/workflows/")) {
      out.push({ path: f.relativePath, sizeBytes: f.sizeBytes, extension: f.extension });
    }
  }
  return out;
}

function extensionHistogram(files: ScannedFile[]): Record<string, number> {
  const hist: Record<string, number> = {};
  for (const f of files) {
    const key = f.extension || "<none>";
    hist[key] = (hist[key] ?? 0) + 1;
  }
  return hist;
}

function importantPaths(keyFiles: ManifestFile[], entryFiles: string[]): string[] {
  const set = new Set<string>();
  for (const k of keyFiles) set.add(k.path);
  for (const e of entryFiles) set.add(e);
  return Array.from(set);
}

export function buildManifest(scan: ScanResult): RepositoryManifest {  const keyFiles = collectKeyFiles(scan.files);
  const entryFiles = detectEntryFiles(scan.files);
  const structure = detectStructure(scan.files, scan.directories);

  return {
    repositoryName: scan.repositoryName,
    rootPath: scan.rootPath,
    fileCount: scan.totalFiles,
    directoryCount: scan.totalDirectories,
    languages: detectLanguages(scan.files),
    frameworks: detectFrameworks(scan.files),
    packageManagers: detectPackageManagers(scan.files),
    dependencies: detectDependencies(scan.files),
    databases: detectDatabases(scan.files),
    keyFiles,
    entryFiles,
    extensions: extensionHistogram(scan.files),
    projectType: detectProjectType(scan.files),
    treeFiles: scan.files.slice(0, _TREE_FILE_CAP).map((f) => f.relativePath),
    structure: {
      directories: scan.directories.slice(0, 60),
      importantPaths: importantPaths(keyFiles, entryFiles),
      folders: structure.folders,
      applications: structure.applications,
    },
  };
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  return `${(bytes / 1024).toFixed(1)}KB`;
}

/**
 * Compact text rendering of the manifest for the initial Planner prompt.
 * Deliberately small — this is the "Tier 1" context.
 */
export function renderManifestForPrompt(manifest: RepositoryManifest): string {
  const topExtensions = Object.entries(manifest.extensions)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([ext, n]) => `${ext} (${n})`)
    .join(", ");

  const keyFileLines = manifest.keyFiles
    .slice(0, 20)
    .map((k) => `  ${k.path} (${formatBytes(k.sizeBytes)})`)
    .join("\n");

  const topDirs = manifest.structure.directories.slice(0, 15).join(", ");

  // The file sample is what lets the Planner honour a named target. Key files
  // alone are not enough: they are the same handful of manifests in every repo,
  // so a plan built from them alone is identical whatever was asked.
  const fileSample = manifest.treeFiles
    .filter((f) => !manifest.keyFiles.some((k) => k.path === f))
    .slice(0, 40)
    .join(", ");

  return [
    `Repository: ${manifest.repositoryName}`,
    `Files: ${manifest.fileCount} files across ${manifest.directoryCount} directories`,
    `Project type: ${manifest.projectType}`,
    `Languages: ${manifest.languages.join(", ") || "unknown"}`,
    `Framework signals: ${manifest.frameworks.join(", ") || "none"}`,
    `Package managers: ${manifest.packageManagers.join(", ") || "none"}`,
    ``,
    `Key files detected:`,
    keyFileLines || "  (none)",
    ``,
    `Entry file candidates: ${manifest.entryFiles.join(", ") || "none"}`,
    `Top directories: ${topDirs || "(flat)"}`,
    `Other files (sample of ${manifest.treeFiles.length}): ${fileSample || "(none)"}`,
    `Dominant extensions: ${topExtensions || "none"}`,
  ].join("\n");
}
