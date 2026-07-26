"""Command handler: wizard verify <target> [options]

Orchestrates the complete 6-step CLI pipeline for the "verify"
command family, as defined in cli.md:

    Step 1 -- Command Parsing:      Validate target against known targets
    Step 2 -- Intent Construction:   Build a typed Intent from parsed components
    Step 3 -- Request Assembly:      Package Intent + repo + options into InvestigationRequest
    Step 4 -- Runtime Communication: Send the request to the Runtime Engine
    Step 5 -- Progress Display:      Show investigation progress to the user
    Step 6 -- Result Display:        Render the Runtime Engine's response

The verify command tells Wizard to verify whether a specific aspect of
the repository works correctly. This is more rigorous than investigate --
it continues gathering evidence until it can produce a confident verdict
(verified, failed, or uncertain with reasons).

This handler contains ZERO domain logic. It does not know what
"runtime" or "dependencies" means in a verification context. It only
knows how to translate the user's command into a structured request
and display the response.

Note: Targets like "security" and "deployment" under verify are distinct
from their investigate counterparts. The investigate versions explore and
describe; the verify versions produce confident pass/fail verdicts. The
CLI does not encode this difference -- it is the Runtime Engine's
responsibility to interpret the intent's action + target combination.
"""

from __future__ import annotations

from pathlib import Path

import typer

from wizard.cli.parser.command_parser import (
    CommandValidationError,
    get_valid_targets,
    validate_target,
)
from wizard.cli.parser.intent_builder import build_intent
from wizard.cli.models.investigation_request import (
    InvestigationRequest,
    RepositoryInfo,
    RequestOptions,
)
from wizard.cli.runtime_client.client import send_request
from wizard.cli.display.progress import show_progress
from wizard.cli.display.results import show_results


# Build a formatted help string listing all valid targets
_valid_targets = get_valid_targets("verify")
_target_help = (
    "What to verify. "
    f"Valid targets: {', '.join(_valid_targets)}"
)


def verify(
    target: str = typer.Argument(
        ...,
        help=_target_help,
        show_default=False,
    ),
    repo: str = typer.Option(
        ".",
        "--repo",
        "-r",
        help="Path to the repository.",
        show_default="current directory",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed verification progress.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress all output except the final result.",
    ),
    budget: int = typer.Option(
        100,
        "--budget",
        "-b",
        help="Maximum number of tool executions allowed.",
        min=1,
    ),
    output_format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: markdown or json.",
    ),
) -> None:
    """Verify whether a specific aspect of a repository works correctly.

    More rigorous than investigate -- continues gathering evidence until
    it can produce a confident verdict (verified, failed, or uncertain
    with reasons).

    \b
    Examples:
        wizard verify runtime
        wizard verify dependencies
        wizard verify containers
        wizard verify ci
        wizard verify security
        wizard verify deployment
        wizard verify api
        wizard verify runtime --repo /path/to/project --verbose
        wizard verify dependencies --budget 50
    """

    # -----------------------------------------------------------------------
    # Step 1: Command Parsing -- Validate the target
    # -----------------------------------------------------------------------
    try:
        validate_target("verify", target)
    except CommandValidationError as e:
        typer.echo(f"Error: {e.message}", err=True)
        raise typer.Exit(code=1)

    # Validate that the repository path exists
    repo_path = Path(repo).resolve()
    if not repo_path.exists():
        typer.echo(
            f'Error: Repository path does not exist: {repo}\n'
            f'Specify a valid path with --repo or run Wizard from inside a repository.',
            err=True,
        )
        raise typer.Exit(code=1)

    if not repo_path.is_dir():
        typer.echo(
            f'Error: Not a directory: {repo}',
            err=True,
        )
        raise typer.Exit(code=1)

    # -----------------------------------------------------------------------
    # Step 2: Intent Construction -- Build the Intent
    # -----------------------------------------------------------------------
    intent = build_intent(action="verify", target=target)

    # -----------------------------------------------------------------------
    # Step 3: Investigation Request Assembly -- Package everything
    # -----------------------------------------------------------------------
    request = InvestigationRequest(
        repository=RepositoryInfo(
            path=str(repo_path),
            type="local",
        ),
        intent=intent,
        options=RequestOptions(
            budget=budget,
            output_format=output_format,
            verbose=verbose,
            quiet=quiet,
        ),
    )

    # -----------------------------------------------------------------------
    # Step 5: Progress Display -- Show what we're about to do
    # -----------------------------------------------------------------------
    show_progress(request)

    # -----------------------------------------------------------------------
    # Step 4: Runtime Engine Communication -- Send the request
    # -----------------------------------------------------------------------
    response = send_request(request)

    # -----------------------------------------------------------------------
    # Step 6: Result Display -- Show the response
    # -----------------------------------------------------------------------
    show_results(response, verbose=verbose)
