# 🧙 Wizard

**Open-source repository intelligence CLI** — analyze codebases with zero execution.

Wizard reads your project files to generate comprehensive insights about structure, technologies, dependencies, and repository health. It never executes code, installs packages, or modifies files.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/your-org/wizard.git
cd wizard

# Install dependencies
pip install -e .

# Analyze a project
wizard analyze /path/to/project

# Get dependency insights
wizard dependency-insights /path/to/project
```

## Commands

### `wizard analyze`

Generate a comprehensive overview of a project's structure, technologies, and health.

```bash
wizard analyze .                    # Analyze current directory
wizard analyze ./backend            # Analyze a subdirectory
wizard analyze /path/to/project     # Analyze any project

# Options
wizard analyze . --summary          # Brief summary mode
wizard analyze . --verbose          # Detailed output
wizard analyze . --json             # JSON output
```

### `wizard dependency-insights`

Analyze dependency manifests and provide usage insights.

```bash
wizard dependency-insights .
wizard dependency-insights ./backend

# Options
wizard dependency-insights . --summary    # Brief summary
wizard dependency-insights . --json       # JSON output
wizard dependency-insights . --graph      # Dependency relationship view
```

## Configuration

Create a `.wizardrc` file in your project root or home directory:

```yaml
# .wizardrc
show_banner: true
default_format: rich        # rich | json
summary_mode: false
verbose: false
ignore_dirs:
  - node_modules
  - .git
  - __pycache__
```

## Design Principles

- **Read-only**: Never executes code, installs packages, or modifies files
- **Static analysis only**: All insights derived from reading project files
- **Zero network**: No remote API calls or package downloads
- **Cross-platform**: Works on Windows, Linux, and macOS

## License

MIT
