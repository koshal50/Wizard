"""BackgroundProcess — handle for a long-running sandbox process."""
from pydantic import BaseModel


class BackgroundProcess(BaseModel):
    handle_id: str
    command: str
    cwd: str
    pid: int | None = None
    is_running: bool = True
    exit_code: int | None = None
    stdout_so_far: str = ""
    stderr_so_far: str = ""
