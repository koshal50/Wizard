# Refinement and repository-tool lifecycle fix

## Confirmed execution path and evidence

Branch: `fix/runtime-verification-integration`. The supported HTTP endpoint starts
`wizard_kernel.control.verification.run`, not the older `control.loop.run`.
The terminal command and TUI both consume this runtime through the investigation API.
The shared path serves explain, investigate and verify. Explain remains read-only.

Both reported failures exist in the saved `explain security` investigation
`inv_e57d95d15497`, against `sample-project`. Its events, decision results,
observations and verification state were inspected. The original broken branch
was not checked out over the user's working tree to repeat the live failure.
Deterministic tests reproduce the affected decision/execution sequences instead.

### Error A

The first rejected refinement targeted the real observation `obs_3ed2f1f7` but
listed the nonexistent `obs_3ed2f7` among its supporting observation IDs.
The provider schema allowed arbitrary strings for these references. Persistent
repository context mostly supplied read metadata, while full results disappeared
from the three-observation recent window. The rejection combined several possible
causes into one message, without identifying the invalid reference.

A subsequent proposal was accepted as grounded even though some proposed literal
predicates did not match the cited contents. Once admitted, those predicates
correctly could not be weakened, leaving the investigation pursuing unsupported
criteria. This was a separate grounding/admission problem, not proof that the
grounded-requirement guard should be relaxed.

Live verification also exposed malformed initial explanation plans: runtime
execution checks under explain, content attributed to another file, paraphrased
or Markdown-stripped expected strings, and existence-only alternatives. These
issues are addressed before plan admission or through explicit rejection, rather
than changing accepted requirements to obtain success.

### Error B

The saved run executed `list_tree` with `max_depth=2` (`obs_be2d042d`) and
`max_depth=3` (`obs_c58f11a5`), then requested the same listing again.
The validator recorded accepted fingerprints before executor completion and had
successful-result reuse only for `read_file`. Tree/search outcomes were absent
from persistent repository-result context and repository request history.
Successful tree requests therefore became duplicate errors instead of reusable
evidence. Failed/incomplete requests had no explicit bounded recovery eligibility.

Cycle detection itself was necessary. Disabling it would have permitted repeated
execution and concealed the missing history/reuse interface.

## Changes

| File | Purpose |
| --- | --- |
| `wizard-runtime-engine/src/wizard_kernel/contracts/verification.py` | Constrain refinement IDs to current eligible observations and repository targets to observed IDs/paths. Disable refinement without evidence. Add read-only explanation planning and a discovery-only correction schema. Optional keyword arguments preserve existing general schema callers. |
| `wizard-runtime-engine/src/wizard_kernel/control/verification.py` | Persistently expose source content, tree/search results, tool history and reuse feedback; prioritize requested older content within a bounded context; provide structured reference/content errors and actual supporting-source IDs. Validate explanation proposals before admission, with one discovery-only correction. Preserve accepted predicates and provenance. Integrate reuse and bounded recoverable retries without fabricated executions. |
| `wizard-runtime-engine/src/wizard_kernel/control/tool_validator.py` | Normalize tree defaults; reuse successful complete repository results by canonical parameters; keep different scopes distinct; permit one explicitly recoverable/incomplete tree retry; invalidate repository caches after successful mutating execution; return structured duplicate feedback. Existing authorization, traversal, egress and cycle checks remain enabled. |
| `wizard-runtime-engine/src/wizard_kernel/world/tools.py` | Capture `os.walk` enumeration failures and report partial listings as incomplete failures rather than complete successes. |
| `wizard-runtime-engine/src/wizard_kernel/ports/prompts.py` | Specify exact observation references, raw-source predicates, durable result reuse, scope-specific explanations and corrective feedback handling. |
| `wizard-runtime-engine/tests/test_refinement_and_tree_reuse.py` | 28 deterministic regressions covering references, grounding, histories, reuse, distinct scopes, retries, partial listings, cache invalidation, cycles, correction and three HTTP explanation intents. |
| `wizard-runtime-engine/tests/test_runtime_v2.py` | Update the explanation execution-safety test: an execution plan is now rejected before admission, with no execution or explorer call. |
| `docs/runtime-refinement-tree-fix.md` | Evidence, verification commands, results and remaining limitations. |

The pre-existing local browser setup change and the independently edited planner
`tsconfig.json` were preserved. They are not part of this bug fix. New test
dependencies and temporary artifacts were installed/written under the root venv.

## Behavior and invariants

- Refinement references are drawn from the current investigation's successful
  evidence. Authentication retains its check/browser scope. Cross-check process
  readiness references remain available where the existing workflow allows them.
- A nonexistent ID, uncited observation target, unsupported repository predicate,
  or attempted replacement of grounded assertions is rejected with field-level
  feedback. Actual alternative supporting records can be suggested by ID; the
  runtime does not substitute those references or accept the rejected proposal.
- Explanation plans cannot request process, HTTP or browser execution. Initial
  content targets come from observed discovery documents. Unsupported proposals
  are not admitted: one correction asks for unresolved repository discovery goals,
  then the explorer gathers/reuses evidence and proposes validated criteria.
- A successful duplicate listing returns its original observation ID. It does not
  execute again, append a fake success observation, consume an execution budget
  unit, or discard the original provenance. Reuse becomes visible in subsequent
  agent context, so context-cycle detection does not abort the first valid reuse.
- Different normalized parameters remain distinct. Permanent failures cannot be
  reused. Explicitly recoverable or incomplete listings get one retry. Repeated
  unchanged rejected decisions, repeated cached requests without progress, model
  call limits, elapsed-time limits and tool budgets still bound the investigation.
- Existence-only refinements cannot complete an explanation. Missing evidence,
  rejected proposals, provider failures and actual failed predicates remain visible.

## Verification commands and results

Run from the repository root in PowerShell:

```powershell
venv/Scripts/python.exe -m pytest wizard-runtime-engine/tests/test_refinement_and_tree_reuse.py wizard-runtime-engine/tests/test_repository_evidence_recovery.py wizard-runtime-engine/tests/test_runtime_v2.py::test_explain_cannot_execute_a_model_proposed_runtime_check -q --tb=short --basetemp=venv/tmp/pytest-final-target-schema -o cache_dir=venv/tmp/pytest-cache --junitxml=venv/tmp/focused-suite.xml
```

Result: **56 passed**, including **28 new regressions**. A Starlette/httpx
deprecation warning is present; tests still pass.

```powershell
venv/Scripts/python.exe -m pytest wizard-runtime-engine/tests -q --tb=short --basetemp=venv/tmp/pytest-release-verification -o cache_dir=venv/tmp/pytest-cache --junitxml=venv/tmp/release-suite.xml *> venv/tmp/release-suite.log
```

Result: **512 passed, 78 failed, 7 skipped**.

Baseline verification used a separate source copy under `venv/tmp/baseline-src`.
Changed implementation files were restored there from `git show HEAD:<path>`,
leaving the working tree intact. Its actual imported validator path was checked
before running the suite. The new regression file was excluded from that run.

```powershell
venv/Scripts/python.exe -c "import sys,pathlib; sys.path.insert(0,str(pathlib.Path('venv/tmp/baseline-src').resolve())); import wizard_kernel.control.tool_validator; import pytest; raise SystemExit(pytest.main(['wizard-runtime-engine/tests','--ignore=wizard-runtime-engine/tests/test_refinement_and_tree_reuse.py','-q','--tb=short','--basetemp=venv/tmp/pytest-baseline-all','-o','cache_dir=venv/tmp/pytest-baseline-cache','--junitxml=venv/tmp/baseline-suite.xml']))" *> venv/tmp/baseline-suite.log
```

Baseline result: **484 passed, 78 failed, 7 skipped**.
Final/baseline failure comparison: **identical failure sets; no additional failing cases**.

Also executed `venv/Scripts/python.exe -m pip check` (passed) and
`git diff --check -- wizard-runtime-engine` (passed).

## HTTP and live intent coverage

Deterministic integration tests exercise POST `/v1/investigations`, its actual
background worker, real repository executors, observation persistence, refinement,
evaluation and report finalization for explain security, architecture and runtime.
Only the model policy is scripted; tool execution and verification are real.
Additional multi-iteration tests execute and reuse a tree, read a source file,
refine with its real observation ID, and verify original provenance.

The supported CLI was also run against `D:\all projects\Wizard\sample-project`:

```powershell
& 'D:\all projects\Wizard\venv\Scripts\start-wizard.cmd' explain security
& 'D:\all projects\Wizard\venv\Scripts\start-wizard.cmd' explain architecture
& 'D:\all projects\Wizard\venv\Scripts\start-wizard.cmd' explain runtime
```

Representative successful live records:

| Intent | Investigation | Outcome |
| --- | --- | --- |
| security | `inv_03f5cb4eee64` | Completed after an unsupported plan became discovery work and a rejected refinement was corrected using actual supporting-source IDs. Four provider calls, 40,279 tokens. |
| architecture | `inv_95183a29af50` | Completed with repository content proof. One provider call, 9,266 tokens. |
| runtime | `inv_da25e64b7f55` | Completed with repository content proof, without starting the application. One provider call, 9,411 tokens. |

Saved reports and evidence are under
`wizard-runtime-engine/.wizard/investigations/<investigation_id>/`.
Other live attempts were incomplete: a provider HTTP 429, unsupported literal
proposals, a missing-file cycle, and an oversized context were observed during
development. These were not reclassified as successes. The grounding, discovery
fallback and context changes above were driven by that evidence.

## Remaining limitations

This does not guarantee that an arbitrary model will produce a correct or complete
explanation. Unsupported proposals, insufficient evidence and provider quotas can
still produce an explicit incomplete/failed outcome. Bounded correction is
intentional. Context remains bounded and may omit older content until it is reused.

The wider repository suite is not green. The baseline failures include legacy
context packaging (`process_observations` undefined), old verifier/finalization
contracts, HTTP retry expectations, browser/environment tests and timeout wording.
They were not fixed by broad unrelated changes. The full baseline failure list
appears below, and detailed tracebacks/JUnit results remain under `venv/tmp`.

The shared repository interfaces are covered by existing investigate/verify tests.
Live model runs were limited to the three explain intents listed above; no claim
is made that every intent or external application/browser workflow was retested.

## Full-suite remaining failures

- `test_api.py::test_cancel_investigation`
- `TestClaimsCount.py::test_claims_count_includes_extractor_claims`
- `TestPlannerDrivesGoals.py::test_kernel_does_not_inspect_goal_names`
- `test_browser.py::test_browser_control_selector_resolves_from_current_accessibility_schema`
- `test_browser.py::test_every_browser_event_carries_the_page`
- `test_browser.py::test_factory_backends`
- `test_browser.py::test_host_rule_fails_closed_on_empty_allowlist`
- `test_browser.py::test_host_rule_matches_the_validator`
- `test_browser.py::test_page_view_is_shaped_for_reading_not_for_scripting`
- `test_browser.py::test_page_view_returns_none_instead_of_raising`
- `test_builtin_planner_reads_the_command.py::test_a_describing_command_aimed_at_an_address_only_reads_it`
- `test_builtin_planner_reads_the_command.py::test_operating_the_page_is_the_goal_a_repository_goal_never_forces`
- `test_cancellation.py::test_a_cancelled_run_writes_a_report`
- `test_cancellation.py::test_an_uncancelled_run_still_completes`
- `test_cancellation.py::test_delete_reports_cancelled_when_the_cancel_wins`
- `test_context_engine.py::test_browser_snapshot_is_not_duplicated_in_previous_action_history`
- `test_context_engine.py::test_engine_builds_packet_and_kv_ordered_sections`
- `test_context_engine.py::test_engine_cache_hit_then_invalidate`
- `test_context_engine.py::test_engine_interceptor_reject`
- `test_context_engine.py::test_engine_interceptor_rewrite`
- `test_context_engine.py::test_latest_browser_interaction_page_schema_reaches_explorer_context`
- `test_context_engine.py::test_loop_emits_context_supplied_end_to_end`
- `test_context_engine.py::test_non_tool_failure_observations_are_not_serialized_as_previous_tools`
- `test_context_engine.py::test_packet_is_the_trust_stripped_contract`
- `test_context_engine.py::test_process_session_state_is_carried_into_next_explorer_packet`
- `test_context_engine.py::test_rejected_tool_request_and_reason_reach_next_explorer_decision`
- `test_explain_scope.py::test_local_architecture_does_not_inherit_unsolicited_browser_goals`
- `test_explain_scope.py::test_model_cannot_add_runtime_or_browser_goals_to_explain`
- `test_local_runtime_recovery.py::test_failed_command_then_planner_recovery_and_process_inspection`
- `test_local_runtime_recovery.py::test_foreground_service_timeout_schedules_one_distinct_owned_recovery`
- `test_local_runtime_recovery.py::test_no_valid_recovery_terminates_with_actual_error`
- `test_local_runtime_recovery.py::test_real_timeout_keeps_output_and_actionable_failure`
- `test_loop_with_mocks.py::test_a_goal_closing_does_not_abandon_the_rest_of_the_plan`
- `test_loop_with_mocks.py::test_blocked_terminal_state_is_set_when_app_cannot_start`
- `test_loop_with_mocks.py::test_consecutive_failures_halt_before_budget_drains`
- `test_loop_with_mocks.py::test_exception_path_still_finalizes_with_a_report`
- `test_loop_with_mocks.py::test_finalize_is_idempotent`
- `test_loop_with_mocks.py::test_loop_reaches_completed`
- `test_loop_with_mocks.py::test_loop_reports_incomplete_when_goals_stay_open`
- `test_loop_with_mocks.py::test_no_progress_halts_before_budget_drains`
- `test_loop_with_mocks.py::test_planner_repeating_scheduled_work_cannot_spin_forever`
- `test_loop_with_mocks.py::test_repeated_rejected_decisions_halt_before_budget_drains`
- `test_loop_with_mocks.py::test_validator_rejection_is_given_to_explorer_once_before_node_fails`
- `TestReportGeneration.py::test_report_preserves_planner_failure_before_any_work`
- `test_planner_seam.py::test_planner_http_error_preserves_rejection_without_retry`
- `test_progress_control.py::test_model_architecture_report_survives_runtime_finalization`
- `test_progress_control.py::test_provider_failure_produces_report_without_retry`
- `test_progress_control.py::test_rejected_action_receives_actual_parameters_then_terminates`
- `test_progress_control.py::test_stale_node_correction_is_bounded[False]`
- `test_progress_control.py::test_stale_node_correction_is_bounded[True]`
- `test_progress_control.py::test_suppressed_frontier_cannot_loop`
- `test_progress_control.py::test_terminal_never_calls_model[completed]`
- `test_progress_control.py::test_terminal_never_calls_model[failed]`
- `test_progress_control.py::test_terminal_never_calls_model[incomplete]`
- `test_progress_control.py::test_terminal_never_calls_model[timed_out]`
- `test_progress_control.py::test_timeout_kills_real_owned_process_and_closes_browser`
- `test_progress_control.py::test_windows_planned_read_matches_actual_normalized_path`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[False-False-200-completed]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[False-False-503-incomplete]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[False-True-200-completed]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[False-True-503-incomplete]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[True-False-200-completed]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[True-False-503-incomplete]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[True-True-200-completed]`
- `test_runtime_readiness.py::test_runtime_schedules_bounded_readiness_without_browser[True-True-503-incomplete]`
- `test_runtime_v2.py::test_actual_registration_then_login_through_agent_browser[False]`
- `test_runtime_v2.py::test_actual_registration_then_login_through_agent_browser[True]`
- `test_runtime_v2.py::test_observed_result_refinement_completes_without_another_model_call`
- `test_runtime_v2.py::test_one_verifier_review_preserves_actual_evidence_and_controls_failure[False]`
- `test_runtime_v2.py::test_one_verifier_review_preserves_actual_evidence_and_controls_failure[True]`
- `test_runtime_v2.py::test_real_browser_form_and_snapshot_through_runtime`
- `test_runtime_v2.py::test_real_run_guessed_port_refinement_boundary_replays_with_real_browser`
- `test_runtime_v2.py::test_service_dependency_to_real_browser_submission_completes`
- `test_runtime_v2.py::test_static_form_text_cannot_be_refined_into_auth_success`
- `test_verification_invariants.py::test_execution_observation_is_available_to_next_explorer_context`
- `test_verification_invariants.py::test_readiness_observations_can_be_repeated_after_world_state_changes`
- `test_verification_invariants.py::test_verifier_422_is_persisted_without_an_assessment`
- `test_world.py::test_local_sandbox_timeout`
