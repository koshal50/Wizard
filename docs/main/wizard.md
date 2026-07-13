# Wizard Contributor Guide

This document is the primary reference for the four contributors building Wizard. It explains what Wizard is, how every part of the system works, how the parts connect to each other, and what your responsibilities are as a contributor.

Read this document end to end before writing any code. Every design decision explained here matters. If you disagree with something, bring it up with the team before changing it.

---

## What Wizard Actually Is

Wizard is an autonomous software repository verification system.

When a developer encounters an unknown repository — one that was AI-generated, inherited from another team, or simply unfamiliar — they have to spend a lot of time just understanding it before they can do anything productive. They need to figure out what language it uses, how to run it, which dependencies it needs, whether the documentation is accurate, and what the project actually does.

Wizard automates this process. It investigates the repository the same way a skilled developer would, but it does so autonomously, systematically, and in a way where every conclusion is backed by real evidence.

The key word here is **evidence**. Wizard does not trust the README. It does not trust documentation. It does not trust what the AI agent thinks. It only trusts observations collected from the repository itself, verified through actual execution where possible.

---

## The Central Idea: Evidence Driven Belief

Think about how a scientist works.

A scientist forms a hypothesis. They run an experiment. They observe the result. They update their belief based on what they observed. If a new experiment contradicts their previous belief, they revise it. They never publish a conclusion without showing the evidence that led to it.

Wizard works exactly the same way.

When Wizard investigates a repository, it forms hypotheses (called **Claims**), gathers evidence (called **Observations**), evaluates how trustworthy each claim is (called **Trust**), and only concludes an investigation when the evidence is sufficient.

The final output is a **Verification Report** — a document that explains everything Wizard found, what evidence supports each finding, and which areas remain uncertain.

---

## The Two Agent Framework

Wizard uses two AI agents working together. Both agents are built in **n8n**, which is the only technology that has been decided for the agent system.

### Explorer Agent

The Explorer Agent is responsible for navigating the repository and gathering information.

It receives a context from the Runtime Engine. That context tells it what the current investigation goals are, what is already known, and what still needs to be investigated. Using this information, the Explorer Agent decides which part of the repository to look at next.

It then issues a Tool Request, which tells the Runtime Engine to execute a specific operation, such as reading a file, running a command, or checking a dependency.

The Explorer Agent does not decide what is true. It only decides where to look next.

### Verification Agent

The Verification Agent is responsible for reviewing the conclusions formed during exploration.

After the Explorer Agent has gathered enough information about a particular topic, the Verification Agent reviews the claims and asks: does the evidence actually support this? Are there contradictions? Is the trust level appropriate?

If the Verification Agent finds contradictions or weak evidence, it can direct the Explorer Agent to investigate further before accepting a conclusion.

Together, these two agents form the intelligence layer of Wizard. But they are never the source of truth. The Runtime Engine is.

### How the Agents Are Built in n8n

n8n is a workflow automation platform that allows you to build complex AI workflows using a visual interface.

Each agent is built as an n8n workflow. The workflow receives input from the Runtime Engine through an API or webhook, processes that input using an LLM (such as OpenAI or Anthropic), and returns a structured response to the Runtime Engine.

The Explorer Agent workflow receives an Investigation Context and returns a Tool Request. The Verification Agent workflow receives a set of claims and returns a verification decision.

The exact n8n workflow structure — the specific nodes, connections, and prompts — needs to be designed by the Agent System contributor (Diksha). The key constraint is that both workflows must communicate with the Runtime Engine through the stable interfaces defined later in this document.

---

## The Four CLI Commands

The CLI is how users interact with Wizard. There are four command families.

### investigate

```bash
wizard investigate <target>
```

This command tells Wizard to explore a specific aspect of the repository and explain what it finds. The focus is on understanding rather than pass/fail verification.

Examples:
```bash
wizard investigate architecture
wizard investigate runtime
wizard investigate deployment
wizard investigate authentication
```

When this command runs, the CLI creates an Investigation Request with the intent set to "investigate" and the target set to whatever the user specified. The Runtime Engine then generates appropriate goals and begins the investigation.

### verify

```bash
wizard verify <target>
```

This command tells Wizard to verify whether a specific aspect of the repository works correctly. The focus is on producing a clear pass, fail, or uncertain verdict with evidence.

Examples:
```bash
wizard verify runtime
wizard verify dependencies
wizard verify containers
wizard verify security
wizard verify ci
```

Verify is more rigorous than investigate. It continues gathering evidence until it can make a confident determination.

### report

```bash
wizard report
```

This command generates the final Verification Report for the current investigation. It reads the verified knowledge from the Runtime Engine and assembles it into a structured document.

The report is saved as `verification_report.md`.

### explain

```bash
wizard explain <target>
```

This command generates a human-readable explanation of something the Runtime Engine already understands. Unlike investigate, it does not aggressively search for new evidence. It works with what has already been verified.

Examples:
```bash
wizard explain architecture
wizard explain runtime
wizard explain dependencies
```

---

## How Every Command Becomes an Investigation

This is one of the most important architectural ideas in Wizard.

There are no separate code paths for separate commands. Every command — whether it is `investigate`, `verify`, `explain`, or `report` — goes through exactly the same Runtime Engine using exactly the same investigation architecture.

The only thing that changes is the **Intent** and the **Goals** that get created.

When you run `wizard verify runtime`, the CLI creates an Investigation Request that says the intent is "verify" and the target is "runtime." The Runtime Engine takes that request, activates the relevant Knowledge Modules, generates appropriate goals, and begins the investigation loop.

When you run `wizard investigate architecture`, the same thing happens. A different intent is created. Different goals are generated. But the same Runtime Engine processes everything using the same pipeline.

This design decision means that once the Runtime Engine is built, every new command is easy to add. You just define a new intent type. You do not build a new pipeline.

---

## The Investigation Lifecycle

Every investigation goes through the same sequence of states. The Runtime Engine controls every state transition. The agents cannot skip states or force the investigation to end early.

### State 1: Created

The CLI submits an Investigation Request. The Runtime Engine creates a new Investigation object with a unique ID, an empty Observation Store, an empty Claim Graph, an empty Goal List, and an investigation budget.

### State 2: Knowledge Discovery

The Runtime Engine scans the repository using lightweight, inexpensive operations. It looks for things like:

- The presence of `package.json` (suggests Node.js)
- The presence of `Dockerfile` (suggests Docker)
- The presence of `requirements.txt` (suggests Python)
- The presence of `.github/workflows/` (suggests GitHub Actions)

Based on what it finds, it asks the Knowledge Registry which Knowledge Modules are relevant. Those modules are activated for this investigation.

This phase is fast. It is not doing deep analysis. It is just identifying which technologies are present.

### State 3: Goal Generation

After Knowledge Discovery, the Runtime Engine creates the initial set of Goals. Goals come from two places:

1. The user's intent (for example, the user asked to verify runtime, so there is a "Verify Runtime" goal)
2. The Knowledge Modules (for example, the Docker module says "if Docker is present, add a Verify Docker goal")

Goals can also be created dynamically during the investigation as new information is discovered.

### State 4: Agent Investigation

The Runtime Engine prepares an Investigation Context and sends it to the Explorer Agent. The context contains:

- The active goals
- The current state of the Claim Graph
- What evidence is missing
- The investigation history
- Which tools are available
- The remaining budget
- Previously failed actions

The Explorer Agent reasons about this context and returns a single Tool Request.

### State 5: Observation Collection

The Runtime Engine executes the Tool Request inside a Sandbox. Every interaction with the repository happens inside this isolated environment. The repository is treated as untrusted.

The result of the tool execution is converted into one or more Observations. An Observation is an immutable record of what happened. It contains:

- An Observation ID
- A timestamp
- The source (which tool produced it)
- The raw data
- The repository location it relates to
- The Investigation ID

Observations never change after they are created. They are permanent records.

### State 6: Evidence Processing

The Extractor Framework analyzes the Observations and converts them into structured Claims.

For example, if the Observation contains the contents of a Dockerfile with `FROM node:18`, the Node.js extractor creates a Claim: "Runtime = Node.js version 18."

There are two kinds of extractors:

- **Deterministic Extractors** work on structured data like JSON, YAML, and Dockerfiles. They always produce the same output for the same input. They do not use AI.
- **Cognitive Extractors** use an LLM to understand things that are not structured, like understanding what the overall architecture of the repository is from reading source code.

Even when a Cognitive Extractor is used, the resulting Claim must still pass Runtime validation before it enters the Claim Graph.

### State 7: Claim Graph Update

Validated Claims are added to the Claim Graph. The Claim Graph is the Runtime Engine's internal model of the repository. It stores everything the system has learned, along with the relationships between those pieces of knowledge.

For example:
- "Runtime = Node.js" and "Framework = Express" are connected by a "DEPENDS_ON" relationship.
- "Deployment = Docker" and "Container Orchestration = Docker Compose" are connected by a "USES" relationship.

The graph grows throughout the investigation. It starts empty and becomes richer with every iteration.

### State 8: Trust Evaluation

The Trust Engine recalculates how trustworthy each Claim is based on all available evidence.

Trust increases when independent sources support the same conclusion. Trust decreases when contradictory evidence appears. Trust is always calculated by the Runtime Engine — the agents are never allowed to set trust values themselves.

For example, if the README says "this project uses PostgreSQL" and the Docker Compose file also includes a PostgreSQL service and the environment variables reference PostgreSQL, the trust for the "Database = PostgreSQL" claim would be fairly high. But if the application fails to connect to PostgreSQL during execution, that trust would decrease and the contradiction would be recorded.

### State 9: Goal Evaluation

The Goal Engine checks whether any goals have been sufficiently satisfied by the current evidence. If a goal is satisfied, it is marked complete. If it needs more evidence, it remains active. If new information has revealed a new thing to investigate, a new goal is created.

### State 10: Convergence Check

The Priority Engine evaluates whether the investigation should continue or conclude. The investigation converges when:

- All primary goals have been satisfactorily verified
- No significant unresolved contradictions remain
- Additional investigation is unlikely to produce meaningful new evidence

If convergence has not been reached, the Runtime Engine prepares a new Investigation Context and the agent begins another iteration.

### State 11: Report Generation

When the investigation converges, the Report Generator assembles the Verification Report from all verified knowledge in the Claim Graph. Every statement in the report is backed by evidence. The report is saved as `verification_report.md`.

---

## The Runtime Engine in Detail

The Runtime Engine is the heart of Wizard. Everything that happens after an investigation begins is managed by the Runtime Engine. It is intentionally deterministic — given the same inputs and the same observations, it should always produce the same conclusions.

The Runtime Engine is composed of the following subsystems, each with a single responsibility:

### Runtime Kernel

The Runtime Kernel is the central coordinator. It behaves like an operating system kernel. It does not do the work itself — it coordinates the subsystems that do. It manages investigation creation, lifecycle, state transitions, and event dispatching.

### Investigation Manager

The Investigation Manager owns every active investigation. It creates new investigation objects, tracks their state, manages budgets, and coordinates completion. It is the single source of truth for what investigations exist and what state they are in.

### Repository Manager

The Repository Manager loads the repository and provides access to its contents. It tracks repository paths, manages temporary working directories, and provides repository metadata. It understands the repository as a file system, not as code. Understanding code is the job of the Knowledge Modules.

### Sandbox Manager

The Sandbox Manager creates isolated execution environments for every repository interaction. Repositories are untrusted. Every command executed against a repository runs inside a sandbox that limits what the command can access. After execution, the sandbox is destroyed.

### Tool Runtime

The Tool Runtime executes operations requested by the agent. Every tool follows the same interface: it accepts an input, executes a specific operation, and returns a standardized output. Examples of tools include Read File, Search Repository, Execute Command, and Check Network Port.

### Observation Engine

The Observation Engine stores every observation generated during an investigation. Observations are immutable. Nothing can modify an observation after it is created. The Observation Engine indexes observations and makes them searchable.

### Extractor Framework

The Extractor Framework converts raw observations into structured Claims. It selects the appropriate extractor for each observation, runs the extraction, validates the output, and forwards valid Claims to the Evidence Engine.

### Evidence Engine

The Evidence Engine links observations to claims. It creates Evidence objects that record which observations support which claims, and which observations contradict them. It prevents the same evidence from being counted multiple times (which would artificially inflate confidence).

### Claim Graph

The Claim Graph stores all verified claims and the relationships between them. It is the Runtime Engine's internal understanding of the repository. Every claim belongs to exactly one investigation.

### Trust Engine

The Trust Engine calculates and maintains the trust level for every claim. It considers the number of supporting observations, the independence of those observations, whether any contradictions exist, and whether execution has confirmed the claim.

### Goal Engine

The Goal Engine creates, updates, and evaluates investigation goals. It knows when a goal has been sufficiently satisfied and when a new goal needs to be created based on what has been discovered.

### Priority Engine

The Priority Engine decides what should be investigated next. It considers active goals, remaining uncertainty, the repository coverage, previously failed attempts, and the investigation budget. It provides the agent with a recommendation for where to focus attention.

### Knowledge Registry

The Knowledge Registry manages all available Knowledge Modules. It handles registration, discovery, and activation of modules during an investigation.

### Report Generator

The Report Generator assembles the final Verification Report from all verified knowledge. It reads from the Claim Graph, Evidence Engine, Goal Engine, and Observation Engine to produce a complete, evidence-backed document.

---

## The Knowledge System in Detail

The Knowledge System is what allows the Runtime Engine to remain technology-neutral.

The Runtime Engine knows nothing about Python, Docker, Node.js, Kubernetes, or any other specific technology. It only understands investigations, claims, observations, evidence, goals, and trust.

Technology-specific knowledge lives inside **Knowledge Modules**. Each Knowledge Module represents everything Wizard knows about one technology or technology family.

For example, the Docker Knowledge Module knows:
- That a `Dockerfile` means Docker is being used
- What Claims to create (Container Runtime, Image Configuration, etc.)
- What Goals to generate (Verify Docker Build, Verify Container Runtime)
- How to extract information from a Dockerfile
- What evidence is needed to verify Docker is working
- What relationships exist between Docker claims (a Compose service depends on an Image)

When the Runtime Engine discovers a `Dockerfile` during Knowledge Discovery, it activates the Docker Knowledge Module. From that point on, the Docker module's knowledge is available to the investigation.

Adding support for a new technology should only require creating a new Knowledge Module. The Runtime Engine should not need to change.

---

## The Agent System in Detail

The Agent System is built using **n8n**. This is the only decided technology for this subsystem.

### What the Agent Does

The agent's only job is to explore the repository and supply the Runtime Engine with useful tool requests. It does not determine truth. It does not modify claims. It does not calculate trust.

Think of the agent as a detective. A detective gathers evidence, forms hypotheses, and decides where to look next. The detective does not personally decide what is legally true — that is the court's job. In Wizard, the Runtime Engine is the court.

### The Agent Loop

The agent receives an Investigation Context and returns a Tool Request. That is the entire interaction from the agent's perspective.

```
Investigation Context comes in
      ↓
Agent reasons about what to investigate next
      ↓
Agent returns a single Tool Request
      ↓
Runtime Engine executes the request
      ↓
Runtime Engine sends updated context back to agent
      ↓
Repeat
```

### How the n8n Workflow Works

In n8n, each agent is a workflow made of connected nodes. Here is the logical structure:

**Explorer Agent Workflow:**

1. A webhook or HTTP node receives the Investigation Context from the Runtime Engine
2. A data preparation node formats the context into a prompt
3. An LLM node (connected to your AI provider) processes the prompt and returns a tool selection
4. A response formatting node structures the output as a valid Tool Request
5. An HTTP response node sends the Tool Request back to the Runtime Engine

**Verification Agent Workflow:**

1. A webhook receives a set of claims and their supporting evidence
2. A prompt preparation node formats this for review
3. An LLM node reviews the claims and identifies any contradictions or gaps
4. A response node returns a verification decision
5. An HTTP response node sends the decision back to the Runtime Engine

The exact prompts, node configurations, and workflow logic need to be designed by the Agent System contributor (Diksha). The key requirement is that the workflow must communicate through the Runtime Engine's stable API.

---

## How the Four Subsystems Connect

Here is the complete flow of a single investigation iteration showing how all four subsystems work together:

```
User runs a command
      ↓
CLI (Koshal) parses the command and creates an Investigation Request
      ↓
CLI sends the Investigation Request to the Runtime Engine
      ↓
Runtime Engine (Shivam) creates the Investigation
Runtime Engine performs Knowledge Discovery
Runtime Engine activates Knowledge Modules (Yash)
Runtime Engine generates Goals
Runtime Engine prepares Investigation Context
      ↓
Runtime Engine sends Investigation Context to Explorer Agent (Diksha)
      ↓
Explorer Agent (n8n) reasons about the context
Explorer Agent returns a Tool Request
      ↓
Runtime Engine validates the Tool Request
Runtime Engine executes the Tool in the Sandbox
Runtime Engine converts the output to Observations
Runtime Engine runs Extractors to create Claims
Runtime Engine builds Evidence linking Observations to Claims
Runtime Engine updates the Claim Graph
Runtime Engine recalculates Trust
Runtime Engine evaluates Goals
Runtime Engine checks for convergence
Runtime Engine prepares next Investigation Context
      ↓
Loop continues until convergence
      ↓
Report Generator assembles verification_report.md
      ↓
CLI displays the report to the user
```

---

## What Each Contributor Owns

### Koshal — Command Line Interface

Koshal owns everything between the user and the Runtime Engine.

Responsibilities:
- Design the four commands: investigate, verify, report, explain
- Parse user commands and validate their syntax
- Convert commands into structured Investigation Requests
- Send Investigation Requests to the Runtime Engine
- Display investigation progress to the user
- Display the final report

The CLI never does any analysis. It never calls the agent. It never modifies claims. It only translates user intent into a request that the Runtime Engine understands, and then communicates results back to the user.

**Tech stack: Undefined.** Koshal should propose one.

### Shivam — Runtime Engine

Shivam owns the complete investigation lifecycle and all verification logic.

Responsibilities:
- Implement the Runtime Kernel
- Implement the Investigation Manager
- Implement the Repository Manager
- Implement the Sandbox Manager
- Implement the Tool Runtime
- Implement the Observation Engine
- Implement the Event Bus
- Implement the Extractor Framework
- Implement the Evidence Engine
- Implement the Claim Graph
- Implement the Trust Engine
- Implement the Goal Engine
- Implement the Priority Engine
- Implement the Report Generator
- Define the APIs that the CLI and Agent System use to communicate with the Runtime

**Tech stack: Undefined.** Shivam should propose one. The Runtime must expose clear API endpoints so the CLI and agents can communicate with it.

### Diksha — Agent System

Diksha owns the two AI agents and the n8n workflows that implement them.

Responsibilities:
- Design the Explorer Agent workflow in n8n
- Design the Verification Agent workflow in n8n
- Write the prompts used by both agents
- Define how the agents receive the Investigation Context from the Runtime Engine
- Define how the agents return Tool Requests to the Runtime Engine
- Ensure the agents stay within their boundaries (they do not modify claims, they do not decide trust)

**Tech stack: n8n for orchestration. LLM provider: undefined.** Diksha should propose which LLM to use.

### Yash — Knowledge System

Yash owns everything related to technology-specific knowledge.

Responsibilities:
- Design the Knowledge Module structure
- Implement the Knowledge Registry
- Implement Knowledge Modules for the initial set of supported technologies
- Define the claim types each module supports
- Write the extractors for each module
- Define the goal templates for each module
- Define the verification rules for each module
- Define the relationship templates for each module

**Tech stack: Undefined.** Yash should propose one.

---

## Rules Every Contributor Must Follow

### The Runtime Engine owns truth

No other subsystem may decide whether a claim is verified. The agent may suggest. The extractors may produce. But only the Runtime Engine verifies.

### The agent never modifies knowledge directly

The agent can only return Tool Requests. It cannot insert claims into the Claim Graph. It cannot change trust values. It cannot mark goals as complete.

### Observations are immutable

Once an observation is created, it cannot be changed. New information always creates new observations.

### Technology knowledge belongs in Knowledge Modules

The Runtime Engine must never contain hardcoded logic about Python, Docker, or any other specific technology. All technology-specific knowledge belongs in Knowledge Modules.

### Reports are evidence-backed

Every statement in the verification report must be traceable to evidence. Reports are never generated directly from AI reasoning.

### Every repository is untrusted

All repository code executes inside a sandbox. The system never trusts repository code by default.

### Every investigation is independent

Investigations never share runtime state. Knowledge Modules are reusable across investigations, but all investigation-specific data (observations, claims, evidence, goals) belongs to a single investigation.

---

## Glossary

| Term | Definition |
|---|---|
| Investigation | One complete repository verification session |
| Investigation Request | The structured object the CLI sends to the Runtime Engine |
| Investigation Context | The information the Runtime Engine sends to the agent for each reasoning iteration |
| Intent | What the user wants (investigate, verify, explain, report) |
| Goal | A verification objective managed by the Runtime Engine |
| Observation | An immutable fact collected during the investigation |
| Claim | A structured piece of repository knowledge derived from observations |
| Evidence | The connection between observations and claims |
| Trust | The Runtime Engine's computed confidence in a claim |
| Claim Graph | The graph structure storing all claims and their relationships |
| Knowledge Module | A reusable package of technology-specific understanding |
| Knowledge Registry | The component that manages and activates Knowledge Modules |
| Extractor | A component that converts observations into claims |
| Sandbox | An isolated execution environment for running repository code safely |
| Tool | A controlled operation the agent can request (read file, execute command, etc.) |
| Tool Request | The structured object the agent sends to the Runtime Engine |
| Verification Report | The final document produced after an investigation completes |
| Runtime Kernel | The central coordinator of the Runtime Engine |
| Explorer Agent | The AI agent responsible for navigating the repository |
| Verification Agent | The AI agent responsible for reviewing conclusions |
