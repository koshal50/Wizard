from pydantic import BaseModel


class RepositoryManifest(BaseModel):
    investigation_id: str
    root_path: str
    total_files: int
    total_dirs: int
    key_files: list[str]
    extensions: dict[str, int]
    directory_tree: list[str]
    size_bytes_approx: int
