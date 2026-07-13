# Agent System

This document explains the Agent System — what the two agents do, how they are built in n8n, how they communicate with the Runtime Engine, and what boundaries they must respect.

---

## Overview

The Agent System provides the intelligence for exploring repositories. Wizard uses two AI agents that work together: the Explorer Agent and the Verification Agent. Both agents are built using **n8n**, which is the only decided technology for the agent system.

The agents are deliberately limited in what they are allowed to do. They explore the repository. They reason about what to investigate next. They do not verify conclusions. They do not compute trust. They do not modify the Claim Graph. All of that belongs to the Runtime Engine.

Think of the agent as a detective. A detective forms hypotheses and decides where to search. The court — not the detective — evaluates the evidence and renders a verdict. In Wizard, the Runtime Engine is the court.

---

## Why There Are Two Agents

A single agent doing exploration and self-verification tends to reinforce its own beliefs. If the same system that reaches a conclusion also verifies it, there is a natural bias toward confirming rather than challenging.

By splitting these responsibilities:

- The **Explorer Agent** is free to explore freely and form hypotheses without worrying about being too critical
- The **Verification Agent** acts as an independent reviewer that specifically looks for weaknesses, gaps, and contradictions in the Explorer's conclusions

This creates a productive tension. The Explorer gathers information optimistically. The Verification Agent challenges it skeptically. Together, they produce more reliable conclusions than either would alone.

---

## The Explorer Agent

### What It Does

The Explorer Agent is responsible for navigating the repository and deciding what to investigate next.

It receives an Investigation Context from the Runtime Engine. The context tells it:
- What the current investigation goals are
- What is already known (the current Claim Graph state)
- What evidence is missing
- What has already been tried and failed
- Which tools are available
- How much budget remains

Based on this information, the Explorer Agent decides what to look at next. It returns a single Tool Request.

### What It Does Not Do

The Explorer Agent does not:
- Decide whether a claim is true
- Modify claims or trust values
- Mark goals as complete
- Generate the verification report
- Execute tools directly (it only requests execution)

### Example Explorer Agent Reasoning

Imagine the current context shows:
- Goal "Verify Runtime" is active but unsatisfied
- The Claim Graph shows `package.json` has been read and Node.js has been identified
- The missing evidence is: "No execution evidence for Node.js runtime"

The Explorer Agent might reason: "The runtime is identified as Node.js but I have no evidence that it actually runs. The most valuable next step is to attempt to execute the application. I'll request execution of `npm start`."

It returns: Tool Request → Execute Command → `npm start`

---

## The Verification Agent

### What It Does

The Verification Agent reviews the claims formed by the Explorer Agent before the investigation moves on from a particular topic.

It receives a set of claims and their supporting evidence. It reviews these claims critically, looking for:
- Weak evidence (claims supported by only one low-reliability observation)
- Contradictions (evidence pointing in different directions)
- Missing verification (claims that are declared but not confirmed through execution)
- Logical inconsistencies (claims that contradict each other in ways the Runtime Engine may have missed)

The Verification Agent returns a structured assessment. It might say: "The claim that the runtime is Node.js is well-supported. The claim that the application runs successfully is not — there is only documentation evidence but no execution evidence. The investigation should continue before these goals are marked complete."

### What It Does Not Do

The Verification Agent does not:
- Modify the Claim Graph directly
- Change trust values
- Complete goals
- Run tools

It only provides an assessment. The Runtime Engine reads this assessment and decides how to adjust goals and priorities accordingly.

---

## The n8n Workflow Architecture

n8n is a workflow automation platform that lets you build complex workflows using a visual node-based interface. It supports connecting to AI models (like OpenAI, Anthropic, or Groq) and building multi-step reasoning processes.

Each agent is a separate n8n workflow. The workflow receives input from the Runtime Engine, processes it using an LLM, and returns a structured response.

### Explorer Agent Workflow Structure

The Explorer Agent workflow receives requests from the Runtime Engine via an HTTP call or webhook. The workflow:

1. **Receive Input** (HTTP Trigger or Webhook node): Receives the Investigation Context from the Runtime Engine as a JSON payload
2. **Format Prompt** (Code or Set node): Converts the Investigation Context into a structured prompt for the LLM
3. **Call LLM** (OpenAI/Anthropic node): Sends the prompt to the AI model and receives a response
4. **Parse Response** (Code node): Extracts the Tool Request from the LLM's response and validates its structure
5. **Return Tool Request** (HTTP Response node): Sends the structured Tool Request back to the Runtime Engine

The LLM receives a prompt that includes:
- The active investigation goals
- The current state of the Claim Graph (summarized)
- What evidence is missing
- What has been tried before
- The available tools and what each does
- The remaining budget
- Instructions to return a valid Tool Request

The LLM returns a response indicating which tool to use and with what parameters. The workflow parses this response and validates it before sending it back to the Runtime Engine.

### Verification Agent Workflow Structure

The Verification Agent workflow is structured similarly:

1. **Receive Input**: Receives a set of claims, their evidence, and their trust levels from the Runtime Engine
2. **Format Review Prompt**: Prepares a prompt asking the LLM to critically evaluate the evidence
3. **Call LLM**: The LLM reviews the evidence and produces a structured assessment
4. **Parse Assessment**: The response is parsed into a structured format the Runtime Engine understands
5. **Return Assessment**: The assessment is sent back to the Runtime Engine

The LLM receives a prompt that describes:
- The claims being evaluated
- The observations that support each claim
- The trust level for each claim
- Instructions to identify weaknesses, contradictions, or gaps

---

## How the Agents Communicate with the Runtime Engine

All communication between the agents and the Runtime Engine goes through a stable API. The exact API design is the responsibility of the Runtime Engine contributor (Shivam), but the contract must be agreed upon by all contributors before implementation begins.

The basic communication pattern:

**Runtime Engine → Explorer Agent:**
```json
{
  "investigation_id": "inv_abc123",
  "active_goals": [...],
  "claim_graph_summary": {...},
  "missing_evidence": [...],
  "failed_actions": [...],
  "available_tools": [...],
  "remaining_budget": 45,
  "repository_metadata": {...}
}
```

**Explorer Agent → Runtime Engine:**
```json
{
  "investigation_id": "inv_abc123",
  "tool_request": {
    "tool": "execute_command",
    "parameters": {
      "command": "npm install",
      "working_directory": "/"
    },
    "reason": "Node.js dependencies need to be installed before attempting startup"
  }
}
```

**Runtime Engine → Verification Agent:**
```json
{
  "investigation_id": "inv_abc123",
  "claims_to_review": [
    {
      "claim_id": "claim_456",
      "type": "RUNTIME",
      "value": "Node.js 18",
      "trust": 0.72,
      "supporting_observations": [...],
      "contradictory_observations": [...]
    }
  ]
}
```

**Verification Agent → Runtime Engine:**
```json
{
  "investigation_id": "inv_abc123",
  "assessment": "overall_sufficient",
  "weak_claims": ["claim_789"],
  "recommended_additional_investigations": [
    "Execution confirmation needed for startup claim"
  ]
}
```

---

## Boundaries the Agents Must Respect

These rules are not optional. Violating them breaks the architectural integrity of Wizard.

### The agent never modifies the Claim Graph

The agent cannot insert, update, or delete claims. It can only request tool executions. The Extractor Framework and Runtime Engine create claims from observations.

### The agent never sets trust values

Trust is computed by the Trust Engine based on evidence. The agent cannot say "I am 90% confident this is correct." Even if the LLM produces a confidence score, the Runtime Engine ignores it.

### The agent never marks goals complete

Only the Goal Engine marks goals as complete, based on whether the verification rules have been satisfied by available evidence.

### The agent never executes tools directly

The agent returns a Tool Request. The Runtime Engine validates and executes it. The agent has no direct access to the repository, the sandbox, or the file system.

### The agent never generates the report

Report generation is the exclusive responsibility of the Report Generator subsystem of the Runtime Engine.

---

## What the Agent System Contributor (Diksha) Owns

Diksha is responsible for the entire Agent System.

This includes:
- Designing and building the Explorer Agent n8n workflow
- Designing and building the Verification Agent n8n workflow
- Writing the system prompts used by both agents
- Designing how the Investigation Context is formatted before being sent to the agents
- Coordinating with Shivam on the exact API format for agent communication
- Testing the agents against sample repositories to ensure they produce valid Tool Requests

**Tech stack: n8n for workflow orchestration. LLM provider: Undefined.** Diksha should propose which AI model to use. Options include OpenAI (GPT-4o), Anthropic (Claude), Google (Gemini), or an open-source alternative.

---

## Designing the Agent Prompts

The quality of agent behavior depends heavily on the prompts. Some guidelines:

**Be explicit about the agent's role.** The system prompt should clearly state that the agent is a repository investigator, not a verifier. It chooses where to look, not what is true.

**Be explicit about the output format.** The agent must return a structured Tool Request. The prompt should specify the exact JSON format required and explain that anything else will be rejected.

**Include the constraint on agent authority.** The prompt should remind the agent that it cannot decide what is true — it only recommends what to investigate next.

**Provide clear context about available tools.** The agent needs to know what tools exist and what each one does before it can make useful decisions.

**Handle failure gracefully.** The prompt should explain what to do when previous actions have failed — try a different approach rather than retrying the same thing.

---

## Handling Agent Failures

The Runtime Engine is designed to handle agent failures gracefully.

If the agent returns an invalid Tool Request (wrong format, invalid tool name, invalid parameters), the Runtime Engine rejects it and returns an error to the agent explaining why the request was invalid. The agent gets another chance to try.

If the agent repeatedly fails to produce valid requests, the Runtime Engine can pause the agent, log the failure as an observation, and either attempt a fallback or end the investigation gracefully.

If the LLM call in the n8n workflow fails (network error, rate limit, timeout), the workflow should handle this with retries before returning an error to the Runtime Engine.

The investigation never crashes because the agent failed. The failure becomes an observation, and the report explains what happened.
