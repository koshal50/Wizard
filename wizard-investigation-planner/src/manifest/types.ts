/**
 * Repository Manifest — the compact (200–500 token) structural summary that is
 * the ONLY thing the Planner receives for its initial call.
 *
 * This is a superset of the existing Wizard manifest shape (repositoryName,
 * languages, frameworks, ...) plus the structural fields the Planner needs
 * (keyFiles with sizes, extension histogram, directory list). Existing callers
 * that read `languages` / `frameworks` / `structure` keep working.
 */

export interface ManifestFile {
  path: string;
  sizeBytes: number;
  extension: string;
}

export interface RepositoryManifest {
  repositoryName: string;
  rootPath: string;

  fileCount: number;
  directoryCount: number;

  /** dominant languages inferred from extensions. */
  languages: string[];
  /** coarse framework signals (Django, Node.js, Next.js, ...). */
  frameworks: string[];
  /** detected package managers (npm, pnpm, pip, poetry, ...). */
  packageManagers: string[];
  /** coarse dependency signal categories. */
  dependencies: string[];
  databases: string[];

  /** well-known signal files that were found (with size). */
  keyFiles: ManifestFile[];
  /** likely entry files. */
  entryFiles: string[];

  /** extension -> count histogram. */
  extensions: Record<string, number>;

  projectType: string;

  /**
   * Every file the scan saw, relative to the root (bounded — this is Tier-1
   * context, not a filesystem dump).
   *
   * This is what lets a *named target* resolve to something readable. The user
   * may say "investigate auth" and the plan has to turn that into concrete
   * paths; without a file list the only targets that could ever be honoured
   * were the handful of signal files the scan flags as `keyFiles`, so every
   * run read the same three manifests and nothing the user actually asked
   * about.
   */
  treeFiles: string[];

  structure: {
    directories: string[];
    importantPaths: string[];
    /** legacy fields kept for compatibility with existing detectors. */
    folders: string[];
    applications: string[];
  };
}
