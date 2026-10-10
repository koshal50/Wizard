# Verification Report — Runtime

> **Command:** `verify` · **Intent:** `Whether the application starts and runs successfully` · **Status:** `PARTIALLY VERIFIED (INCOMPLETE)` · **Investigation:** `inv_17a9b849de49`

## Executive Summary

Assess only requested checks against authoritative goal requirements. Requested subject: Whether the application starts and runs successfully. The final investigation state is **incomplete**; report outcome: **PARTIALLY VERIFIED (INCOMPLETE)**.

### Main conclusions

- **Observed:** process started supported at observation time (`obs_4e70f8c9`).
- **Observed:** process liveness supported at observation time (`obs_4bf986e8`).
- **Observed:** server startup (listening message) supported at observation time (`obs_4bf986e8`).
- Verify Runtime: Verified according to Runtime criteria.

### Important gaps or failures

- timeout after 30s;  (`obs_4e26df60`).

### Recommended next step

Review the missing evidence and failed actions below before choosing the next check.

## Investigation Overview

| Field | Value |
| --- | --- |
| Command | verify |
| Intent | Whether the application starts and runs successfully |
| Repository | D:\all projects\Wizard\sample-project |
| Investigation ID | inv_17a9b849de49 |
| Started / generated | 2026-10-10 13:41:31.847019+00:00 / 2026-10-10 15:35:01.904253+00:00 |
| Duration | 2m 36s |
| Final state / reason | incomplete — Verifier did not confirm sufficient evidence for final verification |
| Goals verified | 1 / 1 |
| Observations collected | 8 |
| Claims supported | 14 |
| Budget used | 8 / 100 |

## Runtime — Verification

### Runtime verification levels

- Process started: verified at observation time — `obs_4e70f8c9`
- Process liveness: verified at observation time — `obs_4bf986e8`
- Server startup (listening message): verified at observation time — `obs_4bf986e8`
- HTTP readiness: not verified

### Entry points and startup commands

| Manifest | Entry point | State | Evidence |
| --- | --- | --- | --- |
| package.json | Not declared | Declared entry point | obs_78073cfe |

| Manifest | Script | Command | State | Evidence |
| --- | --- | --- | --- | --- |
| package.json | dev | concurrently -n server,client -c blue,magenta "npm:dev:server" "npm:dev:client" | Declared; execution must be established separately | obs_78073cfe |
| package.json | dev:server | npm run dev --workspace server | Declared; execution must be established separately | obs_78073cfe |
| package.json | dev:client | npm run dev --workspace client | Declared; execution must be established separately | obs_78073cfe |
| package.json | start | npm run start --workspace server | Declared; execution must be established separately | obs_78073cfe |

### Configuration and initialization

| Source | Observed declaration | State | Evidence |
| --- | --- | --- | --- |
| server/src/server.js:13 | const app = createApp(); | Inferred from source | obs_6bf6ea25 |
| server/src/server.js:14 | const server = app.listen(config.port, () =&gt; { | Inferred from source | obs_6bf6ea25 |
| server/src/server.js:15 | console.log(`[server] listening on http://localhost:${config.port} (${config.env})`); | Inferred from source | obs_6bf6ea25 |
| server/src/server.js:16 | console.log(`[server] database driver: ${config.dbDriver}`); | Inferred from source | obs_6bf6ea25 |
| server/src/server.js:26 | console.error(`[server] port ${config.port} is already in use. Set PORT to something else.`); | Inferred from source | obs_6bf6ea25 |

### Runtime dependencies

| Manifest | Declared engine requirements | Evidence |
| --- | --- | --- |
| package.json | {'node': '&gt;=18'} | obs_78073cfe |

### Checks executed

| Tool | Target | Outcome | Evidence |
| --- | --- | --- | --- |
| execute_command | {'cwd': './', 'timeout_sec': 30, 'command': 'npm run start --workspace server'} | Failed: timeout after 30s;  | obs_4e26df60 |
| start_process | {'command': 'npm run start --workspace server', 'cwd': './'} | Executed; exit None | obs_4e70f8c9 |
| read_process | {'handle_id': 'proc_575b62ed'} | Executed; exit None | obs_4bf986e8 |


## Goal Verification

| Goal | Required claims / evidence | Result | Reason |
| --- | --- | --- | --- |
| Verify Runtime | RUNTIME, command_execution, process_execution | Verified | Runtime goal state: satisfied |

### Verified

- Verify Runtime (`goal_c4dfc2`).

### Failed

- None recorded.

### Not verified

- None recorded.

## Findings

| Finding / claim | Value | Trust | Evidence | Source | Assessment |
| --- | --- | --- | --- | --- | --- |
| RUNTIME: has_start_script (`cl_21858124`) | npm run start --workspace server | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: has_test_script (`cl_2f9b4c6d`) | npm run test --workspaces --if-present | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: node_version_required (`cl_416064d6`) | &gt;=18 | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: process:proc_575b62ed:running (`cl_3ca7e904`) | True | 0.9091 | `obs_4bf986e8` | execution | support |

## Evidence and Provenance

References retain their original investigation ownership. Repeated references are not independent evidence.

| Source / method | Observation ID | Outcome |
| --- | --- | --- |
| read_file | obs_6bf6ea25 | Observed source result |
| read_file | obs_fee12e06 | Observed source result |
| read_file | obs_2c9ed7e8 | Observed source result |
| read_file | obs_000c8f4b | Observed source result |
| read_file | obs_78073cfe | Observed source result |
| execute_command | obs_4e26df60 | Failed; not successful evidence |
| start_process | obs_4e70f8c9 | Observed execution result |
| read_process | obs_4bf986e8 | Observed execution result |

<details>
<summary>Show complete evidence index</summary>

| Observation ID | Tool | Source path | Outcome |
| --- | --- | --- | --- |
| obs_6bf6ea25 | read_file | server\src\server.js | Observed |
| obs_fee12e06 | read_file | client\src\main.jsx | Observed |
| obs_2c9ed7e8 | read_file | docker-compose.yml | Observed |
| obs_000c8f4b | read_file | client\vite.config.js | Observed |
| obs_78073cfe | read_file | package.json | Observed |
| obs_4e26df60 | execute_command |  | Failed |
| obs_4e70f8c9 | start_process |  | Observed |
| obs_4bf986e8 | read_process |  | Observed |

| Claim / finding | Value | Trust | Observation ID | Source tier | Assessment |
| --- | --- | --- | --- | --- | --- |
| FILE_READ: server/src/server.js (`cl_5928fc08`) | True | 0.8571 | `obs_6bf6ea25` | config_parse | support |
| FILE_READ: client/src/main.jsx (`cl_3475249e`) | True | 0.8571 | `obs_fee12e06` | config_parse | support |
| FILE_READ: docker-compose.yml (`cl_59988d73`) | True | 0.8571 | `obs_2c9ed7e8` | config_parse | support |
| DEPLOYMENT: has_compose_file (`cl_ef26ac9a`) | True | 0.8571 | `obs_2c9ed7e8` | config_parse | support |
| DEPLOYMENT: compose_image (`cl_a7b9c495`) | postgres:16-alpine | 0.8571 | `obs_2c9ed7e8` | config_parse | support |
| DEPLOYMENT: published_port (`cl_cf8b5246`) | 5432 | 0.8571 | `obs_2c9ed7e8` | config_parse | support |
| FILE_READ: client/vite.config.js (`cl_2786a37d`) | True | 0.8571 | `obs_000c8f4b` | config_parse | support |
| PACKAGE: name (`cl_3487148b`) | taskboard | 0.8571 | `obs_78073cfe` | config_parse | support |
| PACKAGE: version (`cl_d64f4c2c`) | 1.0.0 | 0.8571 | `obs_78073cfe` | config_parse | support |
| PACKAGE: has_scripts (`cl_b72bbe3c`) | True | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: has_start_script (`cl_21858124`) | npm run start --workspace server | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: has_test_script (`cl_2f9b4c6d`) | npm run test --workspaces --if-present | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: node_version_required (`cl_416064d6`) | &gt;=18 | 0.8571 | `obs_78073cfe` | config_parse | support |
| RUNTIME: process:proc_575b62ed:running (`cl_3ca7e904`) | True | 0.9091 | `obs_4bf986e8` | execution | support |

</details>

### Evidence quality

- Directly observed: 8 collected observations; successful and failed outcomes are distinguished.
- Inferred: source and configuration declarations are not successful execution.
- Missing evidence: None recorded by the supplied goal engine.

## Contradictions and Uncertainty

No contradiction relationships recorded within this investigation.

## Runtime Activity

<details>
<summary>Show executed actions, failures and cleanup</summary>

| Tool | Target / parameters | Outcome | Observation ID |
| --- | --- | --- | --- |
| execute_command | {'cwd': './', 'timeout_sec': 30, 'command': 'npm run start --workspace server'} | Failed: timeout after 30s;  | obs_4e26df60 |
| start_process | {'command': 'npm run start --workspace server', 'cwd': './'} | Executed; exit None | obs_4e70f8c9 |
| read_process | {'handle_id': 'proc_575b62ed'} | Executed; exit None | obs_4bf986e8 |

### Failed actions

| Action | Goal | Error / exit code | Observation |
| --- | --- | --- | --- |
| execute_command | goal_c4dfc2 | timeout after 30s;  | obs_4e26df60 |

### Cleanup

Cleanup below is Runtime-reported, not an independent external check.
- processes terminated: confirmed by Runtime
- browser closed: not used

</details>

## Limitations and Next Steps

Scope is limited to observations collected for this investigation. Uninspected information and unperformed requested checks remain unverified.

Review the missing evidence and failed actions below before choosing the next check.

## Investigation Graph

<details>
<summary>Show investigation graph</summary>

| Node ID | Action type | State | Observation IDs |
| --- | --- | --- | --- |
| node_fa2cc0 | read | complete | obs_6bf6ea25 |
| node_b2c84f | read | complete | obs_fee12e06 |
| node_879d6f | read | complete | obs_2c9ed7e8 |
| node_9930f2 | read | complete | obs_000c8f4b |
| node_dc8d1b | read | complete | obs_78073cfe |
| node_435999 | execute | failed | obs_4e26df60 |
| node_a6a8bb | execute | complete | obs_4e70f8c9 |
| node_6d10fd | execute | complete | obs_4bf986e8 |

</details>

<sub>Generated by Wizard Investigation Kernel · Report schema 2</sub>
