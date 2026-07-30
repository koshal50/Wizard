export interface RepositoryScanResult {
  repositoryName: string;
  rootPath: string;

  files: string[];
  folders: string[];

  configFiles: string[];
  languages: string[];
}