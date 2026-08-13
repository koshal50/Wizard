# Example End-to-End Workflow

`examples/end_to_end_example.py` walks through the entire documented
integration flow using `MockLLMProvider` and `MockRuntimeExecutor`, so it
runs with no configuration and no API key:

```bash
python examples/end_to_end_example.py
```

## What it does

1. **Builds an `ExplorerInput`** simulating what the Investigation
   Planner would hand off: a node (`identify_application_entrypoint`), a
   two-node route, and Python repository metadata.
2. **Calls `ExplorerAgent.investigate()`**, printing the resulting
   `ExplorerOutput` — a validated Tool Request / Execution Plan
   (selected tool, parameters, expected observation, next node).
3. **Converts the output to a `ToolRequest`** via
   `explorer_output.to_tool_request()` and executes it against
   `MockRuntimeExecutor` (standing in for the real Runtime Engine),
   printing the resulting `Observation`.
4. **Builds a `ClaimInput`** from that observation — this step
   simulates what Runtime would do when updating the Claims Graph;
   the Agent System itself never creates claims.
5. **Calls `VerificationAgent.verify()`** with a `VerificationInput`
   built from that claim, printing the resulting `VerificationOutput`.
6. **Writes `report_markdown`** to `examples/verification_report.md`,
   simulating Runtime's final report-generation step.

## Sample output shape

```
=== 1. Explorer Input ===
{ "investigation_id": "inv-example-001", ... }

=== 2. Explorer Output (Tool Request / Plan) ===
{ "selected_tool": "read_file", "parameters": {"path": "/repo"}, "next_node": "inspect_dependencies", ... }

=== 3. Observation (from Runtime, mocked) ===
{'tool': 'read_file', 'success': True, 'data': {'content': '# mock file contents'}}

=== 4. Verification Output ===
{ "overall_assessment": "1/1 claim(s) well-supported, 0 weak, 0 contradicted, 0 unresolved.", ... }

=== 5. Wrote report to examples/verification_report.md ===
```

To see the same flow driven through the real HTTP API instead of calling
the agents directly, start the server (`uvicorn app.api.main:app
--reload`) and `curl` the two POST endpoints documented in `docs/api.md`
with the `ExplorerInput` / `VerificationInput` JSON shown there.
