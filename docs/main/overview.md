# System Overview

This document describes the high level architecture of Wizard and explains how the four major subsystems connect to each other.

---

## What Wizard Is

Wizard is an autonomous software repository verification system. It investigates unknown software repositories, collects evidence about how they work, verifies that evidence through actual execution, and produces a structured verification report.

The key characteristic that separates Wizard from other tools is its separation of intelligence from verification. An AI agent explores the repository and forms hypotheses. The Runtime Engine independently verifies every hypothesis before accepting it as true.

---

## The Four Subsystems

Wizard is composed of four subsystems. Each subsystem has a single, well-defined responsibility. No subsystem performs another subsystem's job.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User                                        │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Command Line Interface                           │
│                                                                     │
│  Accepts commands. Creates Investigation Requests.                  │
│  Displays progress and results.                                     │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │  Investigation Request
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Runtime Engine                                 │
│                                                                     │
│  Manages the complete investigation lifecycle.                      │
│  Owns all verification logic. Owns all state.                       │
│  Computes trust. Evaluates goals. Generates reports.                │
│                                                                     │
│           ┌─────────────────┬──────────────────┐                   │
│           │                 │                  │                   │
│           ▼                 ▼                  ▼                   │
│    Knowledge System   Agent System       Sandbox                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       verification_report.md
```

### Command Line Interface

The CLI is the entry point. It receives commands from the user, parses them, validates them, and converts them into Investigation Requests that the Runtime Engine can understand.

The CLI does not perform any analysis. It does not communicate with the agent. It does not touch the repository. It only translates user commands into structured requests and displays results.

### Runtime Engine

The Runtime Engine is the core of Wizard. It owns everything.

It creates and manages investigations. It executes tools in the sandbox. It stores observations. It runs extractors to create claims. It builds the claim graph. It calculates trust. It evaluates goals. It decides when the investigation is complete. It generates the verification report.

Everything passes through the Runtime Engine. The CLI talks to it. The agents talk to it. The Knowledge System provides data to it. Nothing bypasses it.

### Knowledge System

The Knowledge System teaches the Runtime Engine how to understand different technologies.

The Runtime Engine itself knows nothing about Python, Docker, Kubernetes, Node.js, or any other technology. That knowledge is packaged into **Knowledge Modules**. The Knowledge Registry manages these modules and activates the right ones for each investigation.

When the Runtime Engine discovers a `Dockerfile` in a repository, it asks the Knowledge Registry which module handles Docker. The Docker Knowledge Module is activated. The Runtime Engine now has access to Docker-specific extractors, goal templates, verification rules, and claim types.

### Agent System

The Agent System provides the intelligence for exploring the repository.

There are two agents, both built in n8n. The Explorer Agent decides what to investigate next. The Verification Agent reviews conclusions before they are finalized.

The agents communicate with the Runtime Engine through a stable API. The Runtime Engine gives them an Investigation Context. They return a Tool Request. The Runtime Engine executes the tool, creates observations, processes evidence, and then provides an updated context to the agent.

The agents never directly modify claims, trust, or goals. All modifications go through the Runtime Engine.

---

## How Information Flows

Every piece of information follows the same path regardless of the repository, the technology, or the user's command.

```
Repository File or Execution Output
           ↓
       Observation
    (immutable fact)
           ↓
        Extractor
    (structured parsing)
           ↓
         Claim
  (repository knowledge)
           ↓
        Evidence
  (observation linked to claim)
           ↓
         Trust
  (how strongly to believe the claim)
           ↓
      Goal Update
  (is the goal satisfied?)
           ↓
   Next Investigation
  (what to look at next?)
```

This pipeline never changes. Whether the repository is a Python web app, a Java microservice, or a Kubernetes deployment, the information always flows through the same steps.

---

## The Investigation Loop

The investigation is a repeating loop. The Runtime Engine controls when the loop starts and when it ends.

```
Runtime Engine prepares Investigation Context
           ↓
Agent receives context and returns Tool Request
           ↓
Runtime Engine validates Tool Request
           ↓
Sandbox executes the tool
           ↓
Observations are created
           ↓
Extractors create Claims
           ↓
Evidence Engine links Observations to Claims
           ↓
Claim Graph is updated
           ↓
Trust Engine recalculates trust
           ↓
Goal Engine evaluates active goals
           ↓
Priority Engine selects next focus
           ↓
Back to the top
```

The loop ends when the investigation converges, the budget is exhausted, or the user cancels.

---

## Why There Is Only One Architecture

This is an important design decision that affects every contributor.

Wizard does not have separate code paths for `wizard verify` and `wizard investigate`. Both commands use the same investigation loop. The only difference is the **Intent** they carry and the **Goals** that get generated.

This design means that once the Runtime Engine is built, adding new commands requires very little new code. You define a new intent type and the goals it should generate. Everything else — the agent loop, the evidence pipeline, the trust computation — works automatically.

This also means that Knowledge Modules can be added to support new technologies without changing any existing code. The Runtime Engine simply activates the new module and the investigation adapts.

---

## Communication Between Subsystems

All communication between subsystems goes through defined interfaces. Subsystems do not directly touch each other's internal state.

The primary communication mechanism is the **Event Bus**. When something important happens inside the Runtime Engine, it publishes an event. Other subsystems subscribe to the events they care about and react accordingly.

For example, when an Observation is created:
- The Extractor Framework subscribes to "Observation Created" and begins extraction
- The Observation Engine stores it

When a Claim is created:
- The Evidence Engine subscribes to "Claim Created" and links it to observations
- The Trust Engine subscribes to "Evidence Added" and recalculates trust

This event-driven approach prevents subsystems from becoming tightly coupled. A new subsystem can be added simply by subscribing to existing events. No existing code needs to change.

---

## What Each Contributor Is Responsible For

| Contributor | Subsystem | Primary Output |
|---|---|---|
| Koshal | Command Line Interface | Working CLI with 4 commands |
| Shivam | Runtime Engine | Complete investigation engine with all 13 subsystems |
| Diksha | Agent System | Two n8n workflows (Explorer and Verification agents) |
| Yash | Knowledge System | Knowledge Registry and initial set of Knowledge Modules |

Each contributor works independently on their subsystem. The contracts between subsystems — the Investigation Request format, the Investigation Context format, the Tool Request format, the Knowledge Module interface — must be agreed upon by all contributors before implementation begins.
