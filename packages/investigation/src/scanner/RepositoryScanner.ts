import fg from "fast-glob";
import path from "path";

import { RepositoryScanResult } from "./types";

export class RepositoryScanner {
  public async scan(
    repositoryPath: string
  ): Promise<RepositoryScanResult> {

    const entries = await fg(["**/*"], {
      cwd: repositoryPath,
      dot: false,
      onlyFiles: false,
    });

    const files: string[] = [];
    const folders: string[] = [];

    for (const entry of entries) {
      const ext = path.extname(entry);

      if (ext) {
        files.push(entry);
      } else {
        folders.push(entry);
      }
    }

    return {
      repositoryName: path.basename(repositoryPath),
      rootPath: repositoryPath,
      files,
      folders,
      configFiles: [],
      languages: [],
    };
  }
}