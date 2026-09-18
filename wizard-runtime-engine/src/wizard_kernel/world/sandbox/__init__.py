"""Sandbox factory — returns the right runtime based on config.

Two runtimes, and the default is the one that needs nothing installed:

    local_dev   LocalProcessRuntime — a real subprocess on this machine, with
                the real working directory. NOT isolation, and it never claims
                to be. This is the default because it works out of the box.
    docker      DockerSandboxRuntime — a container with no network, a read-only
                root and a read-only mount of the workspace. Real isolation,
                and the only mode that needs a Docker daemon running.

Docker is opt-in. Nothing in a default run touches it, which is why a machine
with the CLI installed but no daemon still runs every investigation fine — see
`docker_status` for how that is checked rather than assumed.
"""
import subprocess

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


def docker_status(timeout: float = 8.0) -> tuple[bool, str]:
    """Can the Docker runtime actually run here, and if not, exactly why not?

    Returns ``(usable, reason)``. `reason` is what the probe really saw, phrased
    for someone deciding what to do next — never a bare "unavailable", because
    "the CLI is missing", "the CLI is there but the daemon is not running" and
    "the daemon is running but slow" need three different actions.

    The distinction that matters most: a *client* being installed says nothing
    about a *server* being reachable. `docker version` asks the daemon, so its
    failure is the honest answer to "would a docker run work right now?".

    One probe, used by both the API (to refuse a docker request it cannot honour
    before starting) and the demo (to report the capability), so the two can
    never disagree about the same machine.
    """
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, "the docker CLI is not installed"
    except subprocess.TimeoutExpired:
        return False, f"the docker CLI did not answer within {timeout:.0f}s"
    except OSError as exc:
        return False, f"the docker CLI could not be run ({type(exc).__name__}: {exc})"

    if result.returncode == 0 and result.stdout.strip():
        return True, f"docker server {result.stdout.strip()}"

    # The daemon's own first clause is the diagnosis ("failed to connect to the
    # docker API at npipe://…"); what follows is docker's advice and the raw
    # Win32 error, which restate the same thing at three times the length. The
    # first clause is kept whole — it names the endpoint that was tried.
    text = (result.stderr or result.stdout or "").strip()
    if not text:
        return False, "the docker CLI is present but reported no server"
    first = text.splitlines()[0].split(";")[0].strip().rstrip(".")
    return False, first or text.splitlines()[0].strip()


__all__ = ["SandboxRuntime", "get_sandbox", "docker_status"]
