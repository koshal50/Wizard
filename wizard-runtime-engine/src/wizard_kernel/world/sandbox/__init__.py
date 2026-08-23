"""Sandbox factory — returns the right runtime based on config."""
from wizard_kernel.world.sandbox.base import SandboxRuntime


def get_sandbox(sandbox_mode: str) -> SandboxRuntime:
    match sandbox_mode:
        case "docker":
            from wizard_kernel.world.sandbox.docker import DockerSandboxRuntime
            return DockerSandboxRuntime()
        case _:
            # local_dev — dev/tests only, never claim isolation
            from wizard_kernel.world.sandbox.local import LocalProcessRuntime
            return LocalProcessRuntime()
