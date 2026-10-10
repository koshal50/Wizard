"""Command/target report contract shared by deterministic rendering and model review."""

from __future__ import annotations

COMMAND_TARGETS = {
    "investigate": (
        "architecture",
        "runtime",
        "deployment",
        "authentication",
        "api",
        "security",
        "build",
    ),
    "verify": ("runtime", "dependencies", "containers", "ci", "security", "deployment", "api"),
    "explain": ("runtime", "architecture", "dependencies", "deployment", "security"),
    "report": (),
}

# Explicit subject sections, never an architecture fallback for unknown subjects.
TARGET_SECTIONS = {
    "architecture": (
        "Application stack",
        "Major components and responsibilities",
        "Established relationships",
        "Relevant repository structure",
        "External dependencies and services",
        "Architecture gaps",
    ),
    "api": (
        "API overview",
        "Routes and handlers",
        "Request and response contracts",
        "Authentication and validation",
        "API gaps",
    ),
    "runtime": (
        "Runtime verification levels",
        "Entry points and startup commands",
        "Configuration and initialization",
        "Runtime dependencies",
    ),
    "deployment": (
        "Deployment manifests",
        "Service and environment configuration",
        "Deployment execution",
        "Deployment gaps",
    ),
    "authentication": (
        "Identity and session handling",
        "Authentication middleware",
        "Protected routes and authorization",
        "Authentication gaps",
    ),
    "security": (
        "Evidence-backed security findings",
        "Checks performed",
        "Unresolved security risks",
    ),
    "build": ("Declared build commands", "Build configuration and artifacts", "Build execution"),
    "dependencies": (
        "Declared dependencies",
        "Availability and resolution checks",
        "Dependency gaps",
    ),
    "containers": (
        "Container configuration",
        "Image build and container execution",
        "Container gaps",
    ),
    "ci": ("CI workflows", "Workflow checks and execution", "CI gaps"),
}

CLAIM_TYPES = {
    "architecture": {"RUNTIME", "FRAMEWORK", "FILESYSTEM", "ARCHITECTURE", "DATABASE"},
    "api": {"WEB", "API", "ENDPOINT", "HTTP", "VALIDATION"},
    "runtime": {"RUNTIME", "PROCESS", "CONFIGURATION"},
    "deployment": {"DEPLOYMENT", "CONFIGURATION"},
    "authentication": {"AUTHENTICATION", "AUTHORIZATION", "SECURITY"},
    "security": {"SECURITY", "AUTHENTICATION", "AUTHORIZATION"},
    "build": {"BUILD", "TESTING"},
    "dependencies": {"PACKAGE", "DEPENDENCY", "DEPENDENCIES"},
    "containers": {"DEPLOYMENT", "CONTAINER", "DOCKER"},
    "ci": {"CI", "TESTING"},
}


def report_contract(inv):
    targets = list(dict.fromkeys(t.lower() for t in inv.targets if t.lower() in TARGET_SECTIONS))
    return {
        "schema_version": "2",
        "template": "wizard_dynamic_intent_report_template.md",
        "command": inv.intent,
        "targets": targets,
        "question": inv.question,
        "investigation_id": inv.id,
        "sections": {t: list(TARGET_SECTIONS[t]) for t in targets},
        "operation": {
            "investigate": "Explain source/configuration and separately label executed results",
            "verify": "Assess only requested checks against authoritative goal requirements",
            "explain": "Explain inspected knowledge; do not demand execution",
            "report": "Render only supplied existing state; never initiate new work",
        }.get(inv.intent, "Render supplied state"),
        "integrity": [
            "Cite observation IDs in every narrative paragraph",
            "Use only supplied source paths, claims, observations and established relationships",
            "Do not override Runtime state or imply unperformed checks succeeded",
            "Discuss only selected targets and the user question; do not add unrelated sections",
        ],
    }
