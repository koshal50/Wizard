# Knowledge System

This document explains the Knowledge System — what it is, why it exists, how Knowledge Modules work, and how the Knowledge Registry manages them.

---

## Why the Knowledge System Exists

The Runtime Engine is designed to be completely technology-neutral. It knows how to investigate, verify evidence, compute trust, and generate reports. But it knows nothing about Python, Docker, Node.js, Kubernetes, or any other specific technology.

This is a deliberate design decision. If the Runtime Engine contained knowledge about every technology, it would become enormous and impossible to maintain. Every time a new framework came out, someone would have to modify the core engine. This would lead to bugs, regressions, and architectural complexity.

Instead, Wizard separates technology knowledge from investigation logic. The Runtime Engine knows how to investigate. The Knowledge System knows what to investigate.

Technology-specific knowledge lives in **Knowledge Modules**. The **Knowledge Registry** manages those modules and makes them available to the Runtime Engine during investigations.

---

## The Knowledge Registry

The Knowledge Registry is the central catalog of all available Knowledge Modules.

When Wizard starts up, every available Knowledge Module registers itself with the Knowledge Registry. The registry stores a catalog of what each module supports.

During the Knowledge Discovery phase of an investigation, the Runtime Engine scans the repository and then asks the Knowledge Registry: "Which modules are relevant for this repository?" The Registry looks through its catalog and returns the relevant modules. The Runtime Engine activates them.

Responsibilities of the Knowledge Registry:
- Maintaining the catalog of all registered modules
- Matching repository signals to relevant modules
- Activating modules for a specific investigation
- Deactivating modules when an investigation ends
- Providing modules to the Runtime Engine on demand

The Knowledge Registry does not perform any repository analysis itself. It only manages the catalog.

---

## What a Knowledge Module Is

A Knowledge Module is a self-contained package of knowledge about one technology or technology family. Examples:

- Python Knowledge Module
- Node.js Knowledge Module
- Docker Knowledge Module
- Docker Compose Knowledge Module
- GitHub Actions Knowledge Module
- FastAPI Knowledge Module
- Express Knowledge Module
- PostgreSQL Knowledge Module
- Redis Knowledge Module
- Kubernetes Knowledge Module

Each module is completely independent. It does not depend on other modules (though the Runtime Engine understands that technologies have relationships — an Express app depends on Node.js, for example).

Adding support for a new technology should only require creating a new Knowledge Module. Nothing in the Runtime Engine should need to change.

---

## What a Knowledge Module Contains

Every Knowledge Module provides the same set of components. These components are the only way a module contributes to the investigation.

### Identification Rules

Identification Rules define when this module should be activated. They are expressed as lightweight checks that can be performed during Knowledge Discovery.

Examples for the Docker module:
- Is there a file named `Dockerfile` in the repository?
- Is there a file named `.dockerignore`?
- Does `docker-compose.yml` exist?

Examples for the Node.js module:
- Is there a `package.json` file?
- Is there a `node_modules/` directory?
- Is there a `.nvmrc` file?

Identification Rules should be fast and cheap to evaluate. They are not doing deep analysis — they are just checking for well-known signals.

### Claim Types

The Claim Types section defines which kinds of claims this module is allowed to create.

The Docker module, for example, defines claim types like:
- Container Runtime (value: Docker)
- Base Image
- Exposed Port
- Container Service
- Volume Mount
- Docker Compose Version
- Service Dependency

By defining these explicitly, the module makes a clear contract with the Runtime Engine about what kind of knowledge it will contribute.

### Goal Templates

Goal Templates are reusable templates for the goals that should be generated when this technology is present.

When the Docker Knowledge Module is activated, the Runtime Engine instantiates goal templates from the module. These become actual Goals in the investigation.

Example goal templates from the Docker module:
- Verify Docker Build (can the Dockerfile be built successfully?)
- Verify Docker Runtime (can the container start and run?)
- Verify Multi-Container Deployment (does docker-compose work correctly?)
- Verify Port Mapping (are the right ports exposed?)

The user did not have to ask for these specifically. The Runtime Engine generated them automatically because Docker is present in the repository.

### Extractors

Extractors convert raw observations into structured claims.

Each Knowledge Module provides the extractors needed to understand its technology. The Docker module provides:
- A Dockerfile extractor (reads FROM, RUN, CMD, EXPOSE, etc.)
- A docker-compose.yml extractor (reads services, volumes, networks, etc.)
- A container log extractor (interprets container startup output)

Extractors can be deterministic (parsing structured files) or cognitive (using AI to understand ambiguous content). Both types are valid. When both are possible, always prefer deterministic.

### Relationship Templates

Relationship Templates define how claims from this module relate to claims from other parts of the system.

Examples:
- A Docker service DEPENDS_ON a Docker image
- A Docker image REQUIRES a base image
- A Docker Compose service PROVIDES a container
- Container deployment USES Docker runtime

These relationships are loaded into the Claim Graph when the module is active. They allow the Trust Engine to understand how claims influence each other.

### Verification Rules

Verification Rules define what evidence is needed to consider a goal from this module as "verified."

For example, the Docker module might specify:
- To verify that Docker Build works, you need: a successful `docker build` execution (exit code 0) AND the resulting image appearing in `docker images`
- To verify Docker Runtime, you need: a successful `docker run` AND the container being visible in `docker ps`

These rules tell the Goal Engine when to consider a Docker-related goal as satisfied. Without these rules, the Goal Engine would not know when to stop investigating.

### Report Contributions

Report Contributions are optional sections that the module contributes to the final Verification Report.

The Docker module might contribute:
- A "Container Configuration" section listing all container services and their configurations
- An "Image Analysis" section describing the base images and their versions
- A "Docker Compose Structure" section showing the service dependency graph

The Report Generator merges contributions from all active modules into the unified Verification Report.

---

## The Knowledge Module Lifecycle

Every module goes through the same lifecycle:

**Registration**: When Wizard starts, the module registers with the Knowledge Registry. It provides its metadata: what technology it handles, what files it recognizes, what claim types it supports.

**Discovery**: During Knowledge Discovery, the Runtime Engine evaluates each registered module's Identification Rules against the repository. If the rules match, the module is a candidate for activation.

**Activation**: The Runtime Engine activates the matching modules. Their extractors, goal templates, verification rules, and relationship templates become available for this investigation.

**Usage**: Throughout the investigation, the Runtime Engine uses the module's components. Extractors run. Goal templates become goals. Verification rules guide the Goal Engine.

**Deactivation**: When the investigation ends, the modules are deactivated. Their investigation-specific state is discarded. The modules themselves remain registered and ready for the next investigation.

---

## How Knowledge Modules Stay Independent from the Runtime

This distinction is important.

The Runtime Engine never calls technology-specific functions like `runDockerBuild()` or `checkPythonDependencies()`. It only uses the general-purpose components that modules provide:

- It runs extractors (without knowing which technology the extractor handles)
- It instantiates goal templates (without knowing they came from the Docker module)
- It uses verification rules (without knowing they relate to Docker)

The module provides the knowledge. The Runtime Engine applies it through generic mechanisms. This is why adding a new Knowledge Module requires no changes to the Runtime Engine.

---

## Example: What Happens When Docker Is Discovered

To make this concrete, here is the step-by-step sequence of what happens when the Docker Knowledge Module is used.

1. During Knowledge Discovery, the Runtime Engine scans the repository
2. It finds a file named `Dockerfile`
3. It asks the Knowledge Registry: "What module handles `Dockerfile`?"
4. The Registry responds: "The Docker Knowledge Module handles this"
5. The Runtime Engine activates the Docker Knowledge Module
6. The module's goal templates are instantiated as actual Goals: "Verify Docker Build," "Verify Container Runtime"
7. The agent starts investigating
8. The agent requests a tool: "Read the file at `Dockerfile`"
9. The Runtime Engine executes the tool in the sandbox
10. A raw observation is created containing the Dockerfile contents
11. The Extractor Framework receives the observation
12. The Docker Dockerfile Extractor processes it: "FROM node:18-alpine, EXPOSE 3000, CMD node index.js"
13. Claims are created: Base Image = node:18-alpine, Exposed Port = 3000, Startup Command = node index.js
14. The Evidence Engine links the observation to each claim
15. The Trust Engine calculates initial trust for each claim (medium, because this is just declarative evidence)
16. The Goal Engine checks: have Docker goals been satisfied? Not yet — no execution evidence
17. The Priority Engine recommends trying to build and run the container next
18. The agent requests: "Execute `docker build .`"
19. The sandbox runs the build
20. The execution result becomes an observation
21. The Docker Container Log Extractor processes it
22. New claims are created: Docker Build = Successful, Image = backend:latest
23. Trust for "Deployment = Docker" increases significantly (execution evidence)
24. The Goal Engine checks: "Verify Docker Build" is now satisfied
25. Investigation continues toward remaining goals

---

## What the Knowledge System Contributor (Yash) Owns

Yash is responsible for the entire Knowledge System.

This includes:
- Designing the Knowledge Module structure (the interface every module must implement)
- Implementing the Knowledge Registry
- Implementing the initial set of Knowledge Modules

The initial set of modules should cover the most common repository types. A reasonable starting set:
- Python
- Node.js
- Docker
- Docker Compose
- GitHub Actions

Additional modules can be added later without any changes to the Runtime Engine.

**Tech stack: Undefined.** Yash should propose a technology for implementing the Knowledge Registry and modules.

---

## Adding a New Knowledge Module

Any contributor can add support for a new technology by following these steps:

1. Create a new module directory
2. Implement the Identification Rules
3. Define the Claim Types the module will create
4. Write the Extractors (deterministic ones first)
5. Define the Goal Templates
6. Define the Relationship Templates
7. Write the Verification Rules
8. Optionally write Report Contribution templates
9. Register the module with the Knowledge Registry

No changes to the Runtime Engine are required. The new module is automatically discovered, activated when relevant, and used throughout the investigation.
