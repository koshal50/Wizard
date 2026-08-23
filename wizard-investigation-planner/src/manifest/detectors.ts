/**
 * Manifest detectors. Ported and expanded from the existing Wizard detectors
 * (languageDetector, frameworkDetector, dependencyDetector, structureDetector).
 * All detectors operate on file metadata only — never file contents.
 */
import type { ScannedFile } from "../scanner/fastScanner.ts";

const EXTENSION_LANGUAGE: Record<string, string> = {
  ".py": "Python",
  ".js": "JavaScript",
  ".jsx": "JavaScript",
  ".mjs": "JavaScript",
  ".cjs": "JavaScript",
  ".ts": "TypeScript",
  ".tsx": "TypeScript",
  ".html": "HTML",
  ".css": "CSS",
  ".scss": "CSS",
  ".java": "Java",
  ".go": "Go",
  ".rs": "Rust",
  ".rb": "Ruby",
  ".php": "PHP",
  ".cs": "C#",
  ".kt": "Kotlin",
  ".swift": "Swift",
  ".c": "C",
  ".cpp": "C++",
  ".sh": "Shell",
};

function baseName(p: string): string {
  const idx = p.lastIndexOf("/");
  return idx >= 0 ? p.slice(idx + 1) : p;
}

export function detectLanguages(files: ScannedFile[]): string[] {
  const langs = new Set<string>();
  for (const f of files) {
    const lang = EXTENSION_LANGUAGE[f.extension];
    if (lang) langs.add(lang);
  }
  return Array.from(langs);
}

export function detectFrameworks(files: ScannedFile[]): string[] {
  const names = files.map((f) => f.relativePath);
  const bases = new Set(names.map(baseName));
  const frameworks = new Set<string>();

  if (names.some((n) => n.endsWith("manage.py"))) frameworks.add("Django");
  if (bases.has("package.json")) frameworks.add("Node.js");
  if (names.some((n) => baseName(n).startsWith("next.config"))) frameworks.add("Next.js");
  if (names.some((n) => baseName(n).startsWith("vite.config"))) frameworks.add("Vite");
  if (bases.has("nest-cli.json")) frameworks.add("NestJS");
  if (bases.has("angular.json")) frameworks.add("Angular");
  if (bases.has("pom.xml") || bases.has("build.gradle")) frameworks.add("Java/JVM");
  if (bases.has("go.mod")) frameworks.add("Go modules");
  if (bases.has("Cargo.toml")) frameworks.add("Cargo/Rust");
  if (bases.has("pyproject.toml") || bases.has("requirements.txt")) frameworks.add("Python");
  if (bases.has("Gemfile")) frameworks.add("Ruby/Rails");
  return Array.from(frameworks);
}

export function detectPackageManagers(files: ScannedFile[]): string[] {
  const bases = new Set(files.map((f) => baseName(f.relativePath)));
  const managers = new Set<string>();
  if (bases.has("package-lock.json")) managers.add("npm");
  if (bases.has("pnpm-lock.yaml")) managers.add("pnpm");
  if (bases.has("yarn.lock")) managers.add("yarn");
  if (bases.has("package.json") && managers.size === 0) managers.add("npm");
  if (bases.has("requirements.txt")) managers.add("pip");
  if (bases.has("poetry.lock") || bases.has("pyproject.toml")) managers.add("poetry/pip");
  if (bases.has("Pipfile")) managers.add("pipenv");
  if (bases.has("go.sum") || bases.has("go.mod")) managers.add("go");
  if (bases.has("Cargo.lock") || bases.has("Cargo.toml")) managers.add("cargo");
  return Array.from(managers);
}

export function detectDependencies(files: ScannedFile[]): string[] {
  const bases = new Set(files.map((f) => baseName(f.relativePath)));
  const deps: string[] = [];
  if (bases.has("requirements.txt") || bases.has("pyproject.toml")) deps.push("Python Packages");
  if (bases.has("package.json")) deps.push("Node Packages");
  if (bases.has("go.mod")) deps.push("Go Modules");
  if (bases.has("Cargo.toml")) deps.push("Rust Crates");
  return deps;
}

export function detectDatabases(files: ScannedFile[]): string[] {
  const names = files.map((f) => f.relativePath);
  const dbs = new Set<string>();
  if (names.some((n) => n.endsWith(".sqlite3") || n.endsWith(".sqlite") || n.endsWith("db.sqlite3"))) {
    dbs.add("SQLite");
  }
  return Array.from(dbs);
}

export function detectEntryFiles(files: ScannedFile[]): string[] {
  const CANDIDATES = ["manage.py", "main.py", "app.py", "server.js", "server.ts", "index.js", "index.ts", "main.go", "main.rs"];
  return files
    .map((f) => f.relativePath)
    .filter((p) => CANDIDATES.includes(baseName(p)))
    .slice(0, 20);
}

export function detectStructure(files: ScannedFile[], directories: string[]): {
  folders: string[];
  applications: string[];
} {
  const folders = new Set<string>();
  const applications = new Set<string>();
  for (const dir of directories) {
    const top = dir.split("/")[0];
    if (top) folders.add(top);
  }
  for (const f of files) {
    if (baseName(f.relativePath) === "apps.py") {
      const top = f.relativePath.split("/")[0];
      if (top) applications.add(top);
    }
  }
  return { folders: Array.from(folders), applications: Array.from(applications) };
}

export function detectProjectType(files: ScannedFile[]): string {
  const bases = new Set(files.map((f) => baseName(f.relativePath)));
  if (bases.has("manage.py")) return "Django Project";
  if (bases.has("package.json")) return "Node.js Project";
  if (bases.has("go.mod")) return "Go Project";
  if (bases.has("Cargo.toml")) return "Rust Project";
  if (bases.has("pyproject.toml") || bases.has("requirements.txt")) return "Python Project";
  return "Unknown";
}
