# Command Line Interface

This document explains the Wizard Command Line Interface (CLI) — what commands are available, what each command does, how commands are parsed, and how the CLI communicates with the Runtime Engine.

---

## Overview

The CLI is the entry point into Wizard. Every interaction between a user and the system begins with a CLI command.

The CLI has one job: translate user intent into a structured Investigation Request and send it to the Runtime Engine. It then monitors the investigation and displays the results.

The CLI never analyzes repositories. It never talks to agents. It never computes trust. It is a thin translation layer between the user and the Runtime Engine.

---

## The Four Command Families

Wizard supports four command families. Every command the user runs belongs to one of these families.

### 1. investigate

```bash
wizard investigate <target> [options]
```

The `investigate` command tells Wizard to explore a specific aspect of the repository and explain what it finds. The focus is on understanding. This command does not aim for a definitive pass or fail verdict — it aims to produce the most useful description of the target area.

Available targets:

| Target | What It Investigates |
|---|---|
| `architecture` | The overall structure and design of the repository |
| `runtime` | How the application runs (language, framework, entry point) |
| `deployment` | How the application is deployed (Docker, Kubernetes, cloud) |
| `authentication` | How the application handles authentication and authorization |
| `api` | What API endpoints exist and how they work |
| `security` | Potential security concerns in the configuration or code |
| `build` | The build process and build tools |

Examples:
```bash
wizard investigate runtime
wizard investigate architecture
wizard investigate deployment
```

### 2. verify

```bash
wizard verify <target> [options]
```

The `verify` command tells Wizard to verify whether a specific aspect of the repository works correctly. This is more rigorous than `investigate` — it continues gathering evidence until it can produce a confident verdict (verified, failed, or uncertain with reasons).

Available targets:

| Target | What It Verifies |
|---|---|
| `runtime` | Whether the application starts and runs successfully |
| `dependencies` | Whether all required dependencies are available and installable |
| `containers` | Whether Docker containers build and run correctly |
| `ci` | Whether the CI/CD configuration is valid and functional |
| `security` | Whether known security requirements are satisfied |
| `deployment` | Whether the deployment configuration is complete and valid |
| `api` | Whether API endpoints respond as expected |

Examples:
```bash
wizard verify runtime
wizard verify dependencies
wizard verify containers
wizard verify ci
```

### 3. report

```bash
wizard report [options]
```

The `report` command generates the final Verification Report from the current investigation's verified knowledge. The report is saved as `verification_report.md`.

Options:
```bash
wizard report --format markdown    # Default output format
wizard report --format json        # Machine-readable format
wizard report --output report.md   # Specify custom output path
```

The `report` command can be run at any point during an investigation to see the current state of verified knowledge. It does not wait for convergence — it generates a report from whatever has been verified so far.

### 4. explain

```bash
wizard explain <target> [options]
```

The `explain` command generates a human-readable explanation of something the Runtime Engine already understands. Unlike `investigate`, it does not actively search for new evidence. It reads from the already-verified Claim Graph and produces a clear explanation.

Available targets:

| Target | What It Explains |
|---|---|
| `runtime` | How the application is expected to run |
| `architecture` | The design and structure of the project |
| `dependencies` | What dependencies the project requires |
| `deployment` | How the project is expected to be deployed |
| `security` | What security mechanisms are in place |

Examples:
```bash
wizard explain runtime
wizard explain architecture
wizard explain dependencies
```

---

## Command Syntax Reference

The general syntax for all commands is:

```bash
wizard <command> [target] [options]
```

Global options available on all commands:

```bash
--repo <path>          Path to the repository (default: current directory)
--verbose              Show detailed investigation progress
--quiet                Suppress all output except the final result
--budget <number>      Maximum number of tool executions allowed
--config <path>        Path to a custom configuration file
```

Examples with options:
```bash
wizard verify runtime --repo /path/to/my-project --verbose
wizard investigate architecture --repo ./some-project --budget 50
wizard report --format json --output ./reports/result.json
```

---

## How a Command Becomes an Investigation

This is the internal flow of what happens when the user runs a command.

### Step 1: Command Parsing

The CLI parses the raw command string into its components.

For `wizard verify runtime --repo ./my-project`:
- Command family: `verify`
- Target: `runtime`
- Options: `repo = ./my-project`

For `wizard investigate architecture --budget 30`:
- Command family: `investigate`
- Target: `architecture`
- Options: `budget = 30`

The CLI validates that:
- The command family is one of the four recognized families
- The target is valid for that command family
- The options are well-formed
- The repository path exists (if specified) or the current directory contains a repository

If validation fails, the CLI prints a clear error message explaining the problem and exits.

### Step 2: Intent Construction

The CLI converts the parsed command into a structured Intent object.

```
Command: wizard verify runtime
↓
Intent {
  action: "verify",
  targets: ["runtime"],
  confidence_threshold: "standard"
}
```

```
Command: wizard investigate architecture
↓
Intent {
  action: "investigate",
  targets: ["architecture"],
  confidence_threshold: "exploratory"
}
```

### Step 3: Investigation Request Assembly

The CLI assembles the Intent into a full Investigation Request.

```
Investigation Request {
  repository: {
    path: "/path/to/repository",
    type: "local"
  },
  intent: {
    action: "verify",
    targets: ["runtime"]
  },
  options: {
    budget: 100,
    output_format: "markdown"
  }
}
```

### Step 4: Runtime Engine Communication

The CLI sends the Investigation Request to the Runtime Engine through the Runtime Engine's API. The exact API format will be defined by the Runtime Engine contributor (Shivam).

The CLI then enters a monitoring mode, polling the Runtime Engine for progress updates and displaying them to the user.

### Step 5: Progress Display

While the investigation is running, the CLI displays progress to the user. This might look like:

```
Wizard — Verifying runtime
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Repository: /path/to/my-project

Knowledge Discovery...
  ✓ Found: Node.js (package.json)
  ✓ Found: Docker (Dockerfile)
  ✓ Found: GitHub Actions (.github/workflows/)

Goals:
  ● Verify Runtime (in progress)
  ● Verify Docker Runtime (waiting)
  ● Verify CI Configuration (waiting)

Collecting evidence... (12 observations so far)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Step 6: Result Display

When the investigation completes, the CLI displays the key findings and tells the user where the full report was saved.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wizard — Investigation Complete

Goals:
  ✓ Verify Runtime — Verified (Node.js 18.x, npm startup confirmed)
  ✓ Verify Docker Runtime — Verified (container builds and runs successfully)
  ⚠ Verify CI Configuration — Partially verified (workflow file valid, not executed)

Report saved: verification_report.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## What the CLI Does Not Do

The CLI never:

- Reads repository files or executes repository code
- Calls the AI agents directly
- Modifies claims, trust values, or goals
- Performs any verification logic
- Generates the verification report (the Runtime Engine does this)
- Makes decisions about what to investigate (the Runtime Engine does this)

Every analysis decision belongs to the Runtime Engine. The CLI only communicates the user's intent and displays results.

---

## Error Handling

The CLI should handle errors gracefully and provide helpful messages.

**Unknown command:**
```
Error: Unknown command "analyse". Did you mean "investigate"?
Run "wizard --help" for a list of available commands.
```

**Invalid target:**
```
Error: "networking" is not a valid target for "verify".
Valid targets for "verify": runtime, dependencies, containers, ci, security, deployment, api
```

**Repository not found:**
```
Error: Repository path does not exist: /path/to/missing-project
Specify a valid path with --repo or run Wizard from inside a repository.
```

**Runtime Engine unreachable:**
```
Error: Cannot connect to the Wizard Runtime Engine.
Make sure the runtime is running or try starting it with "wizard start".
```

---

## CLI Internal Structure

The CLI is organized as follows:

```
cli/
├── main.py (or main.ts, or main.go)       # Entry point
├── commands/
│   ├── investigate.py                      # Handler for "investigate"
│   ├── verify.py                           # Handler for "verify"
│   ├── report.py                           # Handler for "report"
│   └── explain.py                          # Handler for "explain"
├── parser/
│   ├── command_parser.py                   # Parses raw command strings
│   └── intent_builder.py                   # Builds Intent objects from parsed commands
├── runtime_client/
│   └── client.py                           # Communicates with the Runtime Engine API
├── display/
│   ├── progress.py                         # Progress display during investigation
│   └── results.py                          # Results display after investigation
└── models/
    ├── intent.py                            # Intent data model
    └── investigation_request.py            # Investigation Request data model
```

---

## What the CLI Contributor (Koshal) Owns

Koshal is responsible for the entire CLI.

This includes:
- Designing the exact command syntax and help text
- Implementing the command parser
- Building the four command handlers
- Implementing the Investigation Request assembly
- Implementing the Runtime Engine client (the code that sends requests and receives responses)
- Implementing progress display
- Implementing result display
- Writing error messages that are clear and helpful

**Tech stack: Undefined.** Koshal should propose a technology. Options include:
- Python with Typer or Click (excellent CLI frameworks, simple to use)
- Node.js with Commander
- Go with Cobra

The CLI should be lightweight. It does not need a complex framework. It needs to be reliable, easy to install, and easy to use.

---

## What the CLI Needs from Other Contributors

**From Shivam (Runtime Engine):**
- The Investigation Request format (exact JSON or data structure)
- The API endpoint where Investigation Requests are submitted
- The API endpoint for polling investigation progress
- The API endpoint for retrieving the Verification Report

**From Shivam (Runtime Engine):**
- Stable interface contracts before CLI implementation begins

The CLI cannot be completed until the Runtime Engine's API is defined. Koshal and Shivam should agree on this contract early in the project.
