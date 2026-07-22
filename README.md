# 🧙 Wizard

**Intent Translation Layer** — translate user commands into structured runtime requests.

Wizard CLI is one module of a larger architecture (CLI → Runtime Engine → Investigation Planner → Agent System). The CLI's only job is to translate human commands into clean, standardized `InvestigationRequest` objects and send them to the Runtime Engine.

The CLI never inspects repositories, analyzes code, or performs investigations. Those responsibilities belong to the Runtime Engine and Agent System.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/wizard.git
cd wizard

# Install
pip install -e .

# Investigate a repository
wizard investigate architecture
wizard investigate runtime
wizard investigate security
```

## Commands

### `wizard investigate <target>`

Explore a specific aspect of a repository and explain what it finds. The focus is on understanding — not a pass/fail verdict.

```bash
wizard investigate architecture        # Structure and design
wizard investigate runtime             # Language, framework, entry point
wizard investigate deployment          # Docker, Kubernetes, cloud
wizard investigate authentication      # Auth and authorization
wizard investigate api                 # API endpoints
wizard investigate security            # Security concerns
wizard investigate build               # Build process and tools
```

**Options:**
```bash
--repo <path>       Path to the repository (default: current directory)
--verbose           Show detailed progress and full request payload
--quiet             Suppress all output except final result
--budget <number>   Maximum tool executions allowed (default: 100)
--format <type>     Output format: markdown or json (default: markdown)
```

**Examples:**
```bash
wizard investigate architecture --repo /path/to/project --verbose
wizard investigate security --budget 50
wizard investigate runtime --format json
```

### `wizard verify <target>`

The verify command tells Wizard to verify whether a specific aspect of the repository works correctly. This is more rigorous than investigate — it continues gathering evidence until it can produce a confident verdict (verified, failed, or uncertain with reasons).

```bash
wizard verify runtime	      #Whether the application starts and runs successfully
wizard verify dependencies	#Whether all required dependencies are available and installable
wizard verify containers	#Whether Docker containers build and run correctly
wizard verify ci	            #Whether the CI/CD configuration is valid and functional
wizard verify security	       #Whether known security requirements are satisfied
wizard verify deployment	#Whether the deployment configuration is complete and valid
wizard verify api	            #Whether API endpoints respond as expected


```

**Examples:**
```bash
wizard verify runtime --repo /path/to/project --verbose
wizard verify security --budget 50
wizard verify runtime --format json
```

### `wizard report` *(coming soon)*

Generate a verification report from verified knowledge.

### `wizard explain <target>` *(coming soon)*

Explain something the Runtime Engine already understands.

---

## Architecture

The CLI follows a strict 6-step pipeline:

```
User Command
      ↓
Step 1: Parse Command        → Validate command family + target
      ↓
Step 2: Build Intent         → Create structured Intent object
      ↓
Step 3: Assemble Request     → Package Intent + repo + options
      ↓
Step 4: Send to Runtime      → Transmit InvestigationRequest
      ↓
Step 5: Show Progress        → Display investigation progress
      ↓
Step 6: Display Results      → Render the Runtime Engine's response
```

### What the CLI knows:
- Command families and their valid targets
- Syntax validation rules
- How to build an Intent
- How to communicate with the Runtime Engine

### What the CLI does NOT know:
- Repository contents or structure
- Dependency graphs or ASTs
- Planning strategies or execution graphs
- Agent coordination or investigation techniques

---

## Project Structure

```
wizard/
├── __init__.py                          # Package metadata
├── __main__.py                          # python -m wizard
└── cli/
    ├── main.py                          # Entry point — Typer app
    ├── commands/
    │   └── investigate.py               # "wizard investigate" handler
    ├── parser/
    │   ├── command_parser.py            # Target validation + registry
    │   └── intent_builder.py            # Intent construction
    ├── runtime_client/
    │   └── client.py                    # Runtime Engine communication (stub)
    ├── display/
    │   ├── progress.py                  # Progress display
    │   └── results.py                   # Results display
    └── models/
        ├── intent.py                    # Intent dataclass
        └── investigation_request.py     # InvestigationRequest dataclass
```

## Design Principles

- **Intentionally dumb**: The CLI's success is measured by how little domain knowledge it contains
- **Stable boundary**: The CLI is the permanent communication interface between users and the Runtime Engine
- **Single integration point**: Only `runtime_client/client.py` changes when the Runtime Engine is built
- **Clean contracts**: Every command produces the same `Intent` → `InvestigationRequest` shape

## License

MIT
