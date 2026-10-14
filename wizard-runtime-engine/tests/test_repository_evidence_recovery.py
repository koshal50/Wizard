"""Repository proof reuse, bounded recovery and persisted verdict integrity."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.verification import ARCHITECTURE_AREAS, CheckSpec, VerificationSpec
from wizard_kernel.control import checks, verification
from wizard_kernel.control.tool_validator import ToolRequestValidator
from wizard_kernel.ports.cerebras_gate import CerebrasRateGate
from wizard_kernel.ports.model import ModelPolicy, ModelFailure
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


def observation(content, *, goal=None, path='guide.md', oid='obs_guide'):
    return Observation(id=oid, investigation_id='inv_test', node_id='read', source_tool='read_file',
        obs_type='file_content', goal_id=goal, created_at=datetime.now(timezone.utc), success=True,
        payload={'ok': True, 'data': {'path': path, 'content': content}})


def check(target='guide.md', expected='workspace', **extra):
    return CheckSpec(id='architecture', description='Documented architecture', assertions=[{
        'source': 'repository', 'field': 'content', 'operator': 'contains',
        'expected': expected, 'target': target, **extra}])


@pytest.mark.parametrize('target', ['guide.md', 'obs_guide'])
def test_discovery_and_other_check_evidence_is_accessible_with_stable_id(target):
    proof = observation('workspace organization', goal='discovery')
    result = checks.evaluate(check(target), [proof])[0]
    assert result['verdict'] == 'passed'
    assert result['observation_id'] == proof.id
    assert result['actual'] == 'workspace organization'


def test_case_matching_is_explicit_and_exact_matching_is_preserved():
    proof = observation('Workspace organization')
    assert checks.verdict(checks.evaluate(check(), [proof])) == 'failed'
    assert checks.verdict(checks.evaluate(check(case_sensitive=False), [proof])) == 'passed'


def test_case_insensitive_witness_includes_match_beyond_preview_limit():
    proof = observation('x' * 3000 + 'Workspace')
    result = checks.evaluate(check(case_sensitive=False), [proof])[0]
    assert result['verdict'] == 'passed' and 'Workspace' in result['actual']


def test_unrelated_failed_read_does_not_erase_valid_repository_proof():
    failed = observation('', path='other.md', oid='obs_other').model_copy(update={'success': False})
    assert checks.verdict(checks.evaluate(check(), [observation('workspace'), failed])) == 'passed'


def test_missing_evidence_and_invalid_evidence_are_distinct():
    assert checks.verdict(checks.evaluate(check(), [])) == 'unverified'
    result = checks.evaluate(check(), [observation({'unexpected': 'workspace'})])[0]
    assert result['verdict'] == 'evaluation_error'
    assert result['observation_id'] == 'obs_guide'
    malformed = observation('workspace').model_copy(update={'payload': {'ok': True, 'data': ['invalid']}})
    assert checks.verdict(checks.evaluate(check(), [malformed])) == 'evaluation_error'


def test_all_requested_terms_are_evaluated_against_the_actual_file_contents():
    spec = CheckSpec(id='architecture', description='Documented component terms', assertions=[
        check('obs_guide', term, case_sensitive=False).assertions[0]
        for term in ('workspace', 'web', 'api')])
    result = checks.evaluate(spec, [observation('Workspace with a web client and API service')])
    assert checks.verdict(result) == 'passed'
    assert {r['observation_id'] for r in result} == {'obs_guide'}
    assert checks.verdict(checks.evaluate(spec, [observation('Workspace with a web client')])) == 'failed'


def test_observation_target_cannot_use_another_observation_as_proof():
    assert checks.verdict(checks.evaluate(check('obs_missing'), [observation('workspace')])) == 'unverified'
    assert checks.verdict(checks.evaluate(check(), [observation('workspace').model_copy(update={'success': False})])) == 'unverified'


def test_duplicate_read_returns_existing_proof_without_weakening_path_guards(tmp_path):
    validator = ToolRequestValidator(str(tmp_path))
    request = ToolRequest(tool='read_file', parameters={'path': 'guide.md', 'max_bytes': 3000})
    first = validator.validate(request, 5)
    assert first.valid and first.observation_id is None
    validator.record_execution('read_file', first.sanitised_params, {'ok': True, 'data': {}}, 'obs_original')
    duplicate = validator.validate(request, 5)
    assert duplicate.valid and duplicate.observation_id == 'obs_original'
    assert 'reuse' in duplicate.reason
    assert not validator.validate(ToolRequest(tool='read_file', parameters={'path': '../secret'}), 5).valid


def test_failed_read_cannot_be_reused(tmp_path):
    validator = ToolRequestValidator(str(tmp_path))
    request = ToolRequest(tool='read_file', parameters={'path': 'guide.md'})
    first = validator.validate(request, 5)
    validator.record_execution('read_file', first.sanitised_params, {'ok': False}, 'obs_failed')
    assert not validator.validate(request, 5).valid


def test_repository_refinement_advertises_only_supported_evidence_and_smaller_schema():
    from wizard_kernel.contracts.verification import decision_model, CheckRefinement
    from wizard_kernel.ports.model import strict_schema
    tools = ['read_file', 'list_tree', 'search_files', 'path_exists']
    model = decision_model(tools, repository_refinement=True)
    payload = {'kind': 'refine', 'reason': 'Actual repository evidence', 'refinement': {
        'observation_ids': ['obs_guide'], 'assertions': [check().assertions[0].model_dump()]}}
    assert CheckRefinement.model_validate(response(model, payload).refinement.model_dump()).assertions[0].source == 'repository'
    payload['refinement']['assertions'] = [{'source': 'process', 'field': 'is_running', 'expected': 'true'}]
    with pytest.raises(ValueError):
        response(model, payload)
    assert len(json.dumps(strict_schema(model))) < len(json.dumps(strict_schema(decision_model(tools))))


def test_synthesis_proof_cannot_double_escape_or_reformat_multiline_json():
    from wizard_kernel.contracts.verification import ArchitectureFinding
    base = {'area': 'structure', 'summary': 'Declared workspace organization'}
    for expected in ('"workspaces": [\\r\\n "web"]', '"workspaces": [\n "web"]'):
        with pytest.raises(ValueError):
            ArchitectureFinding.model_validate({**base, 'assertions': [check('guide.json', expected).assertions[0].model_dump()]})
    assert ArchitectureFinding.model_validate({**base, 'assertions': [
        check('guide.json', 'workspaces').assertions[0].model_dump()]}).assertions


def response(model, payload):
    return model.model_validate({'decision': payload} if 'decision' in model.model_fields else payload)


def test_satisfied_architecture_finishes_from_discovery_and_report_refs_resolve(tmp_path):
    descriptions = {'structure': 'Modules live in src/', 'entry_points': 'Entry point: app.py',
                    'startup': 'Run python app.py', 'boundaries': 'One application owns the CLI',
                    'packages': 'Modules use a workspace', 'configuration': 'Configuration: settings.json'}
    (tmp_path / 'README.md').write_text('\n'.join(descriptions.values()))
    class Policy:
        def request(self, role, context, model, **kwargs):
            if context.get('architecture_synthesis'):
                proof = context['repository_evidence'][0]
                return response(model, {'findings': [{'area': area, 'summary': descriptions[area],
                    'assertions': [check(proof['observation_id'], descriptions[area]).assertions[0].model_dump()]}
                    for area in ARCHITECTURE_AREAS]})
            assert role == 'planner', 'Satisfied evidence should require no explorer request'
            doc = context['discovery']['documents'][0]
            return response(model, {'checks': [check(doc['observation_id']).model_dump()]})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, Policy())
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state.value == 'completed'
    assert saved['model_calls'] == 2 and saved['executions'] == []
    proof_id = saved['results']['architecture']['assertions'][0]['observation_id']
    persisted = [Observation.model_validate(json.loads(p.read_text())) for p in (fs_store.inv_dir(inv.id) / 'observations').glob('*.json')]
    assert proof_id in {o.id for o in persisted}
    assert checks.verdict(checks.evaluate(CheckSpec.model_validate(saved['checks'][0]), persisted)) == 'passed'
    graph = fs_store.read(inv.id, 'investigation_graph.json')
    assert all('check_' + cid in json.dumps(graph) for cid in saved['architecture_coverage_ids'].values())
    report = fs_store.report_path(inv.id).read_text()
    assert '| PASS |' in report and proof_id in report and 'Not observed' not in report


def test_successful_read_proves_existence_with_original_provenance():
    existence = CheckSpec(id='presence', description='Read file exists', assertions=[{
        'source': 'repository', 'field': 'exists', 'expected': 'true', 'target': 'guide.md'}])
    result = checks.evaluate(existence, [observation('workspace')])[0]
    assert result['verdict'] == 'passed' and result['actual'] == 'true'
    assert result['observation_id'] == 'obs_guide'


def test_architecture_coverage_missing_area_prevents_false_completion(tmp_path):
    (tmp_path / 'README.md').write_text('workspace')
    class Policy:
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return response(model, {'checks': [check('README.md').model_dump()]})
            return response(model, {'findings': [{'area': area, 'summary': 'Documented ' + area,
                'assertions': [] if area == 'startup' else [check('README.md').assertions[0].model_dump()],
                'blocker': 'Startup implementation was not observed' if area == 'startup' else ''}
                for area in ARCHITECTURE_AREAS]})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, Policy())
    assert inv.state.value == 'incomplete'
    assert fs_store.read(inv.id, 'verification.json')['results']['architecture_startup']['status'] == 'unverified'
    assert 'Startup implementation was not observed' in fs_store.report_path(inv.id).read_text()


@pytest.mark.parametrize('corrected', [True, False])
def test_synthesis_correction_is_bounded_and_reports_remain_single_line_rows(tmp_path, corrected):
    (tmp_path / 'README.md').write_bytes(b'workspace\r\npackage content')
    class Policy:
        corrections = 0
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return response(model, {'checks': [check('README.md').model_dump()]})
            self.corrections += 1
            expected = 'workspace' if corrected and context.get('evaluation_feedback') else 'WORKSPACE'
            return response(model, {'findings': [{'area': area, 'summary': 'Documented ' + area,
                'assertions': [check('README.md', expected).assertions[0].model_dump()]}
                for area in ARCHITECTURE_AREAS]})
    policy = Policy()
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, policy)
    assert inv.state.value == ('completed' if corrected else 'failed') and policy.corrections == 2
    assert fs_store.read(inv.id, 'architecture_proposed_report.json')
    report = fs_store.report_path(inv.id).read_text()
    rows = [line for line in report.splitlines() if line.startswith('|')]
    assert len(rows) == 9 and all(line.endswith('|') for line in rows)


@pytest.mark.parametrize('vary_parameters', [False, True])
def test_unspecified_architecture_goal_recovers_from_repeated_missing_file(tmp_path, vary_parameters):
    (tmp_path / 'README.md').write_text('workspace')
    class Policy:
        reads = 0
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return response(model, {'checks': [{'id': 'discover', 'description': 'Explain architecture',
                    'capabilities': ['repository'], 'unresolved_reason': 'Discover architecture'}]})
            if context.get('architecture_synthesis'):
                return response(model, {'findings': [{'area': area, 'summary': 'Documented ' + area,
                    'assertions': [check('README.md').assertions[0].model_dump()]}
                    for area in ARCHITECTURE_AREAS]})
            self.reads += 1
            return response(model, {'kind': 'tool', 'reason': 'Read architecture', 'action': {
                'tool': 'read_file', 'parameters': {'path': 'missing.md', 'max_bytes': 3000 + (self.reads if vary_parameters else 0)}}})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, Policy())
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state.value == 'completed'
    assert saved['model_calls'] == 4 and len(saved['executions']) == (2 if vary_parameters else 1)
    assert len(saved['cycle_recovery']) == 1
    assert saved['results']['discover']['status'] == 'passed'


def test_cached_reads_are_bounded_and_do_not_abort_later_satisfiable_checks(tmp_path):
    (tmp_path / 'README.md').write_text('workspace organization')
    class Policy:
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return response(model, {'checks': [check('missing.md', 'missing-required-detail').model_dump(),
                    check('README.md').model_copy(update={'id': 'packages'}).model_dump()]})
            assert context['repository_evidence'][0]['observation_id']
            return response(model, {'kind': 'tool', 'reason': 'Read architecture', 'action': {
                'tool': 'read_file', 'parameters': {'path': 'README.md', 'max_bytes': 3000}}})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, Policy())
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state.value == 'incomplete'
    assert saved['model_calls'] == 3
    assert saved['executions'] == []
    assert len(saved['evidence_reuse']) == 1
    assert saved['results']['packages']['status'] == 'passed'
    assert saved['results']['architecture']['status'] == 'unverified'


def test_missing_proof_never_completes_and_report_uses_evaluator_blocker(tmp_path):
    (tmp_path / 'README.md').write_text('workspace')
    class Policy:
        def request(self, role, context, model, **kwargs):
            return response(model, {'checks': [check('missing.md').model_dump()]} if role == 'planner'
                else {'kind': 'evaluate', 'reason': 'Everything is satisfied'})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, Policy())
    assert inv.state.value == 'incomplete'
    report = fs_store.report_path(inv.id).read_text()
    assert 'No compatible observation' in report
    assert 'Everything is satisfied' not in report


def test_evaluation_error_survives_finalization_and_report(tmp_path):
    (tmp_path / 'README.md').write_text('workspace')
    def invalid(*args):
        return [{'assertion': check().assertions[0].model_dump(), 'verdict': 'evaluation_error',
                 'actual': None, 'observation_id': None, 'reason': 'Invalid evidence field content'}]
    class Policy:
        def request(self, role, context, model, **kwargs):
            assert role == 'planner'
            return response(model, {'checks': [check('README.md').model_dump()]})
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(checks, 'evaluate', invalid)
        manager = InvestigationManager()
        inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate'))
        verification.run(inv, manager, Policy())
    assert inv.state.value == 'failed'
    assert fs_store.read(inv.id, 'verification.json')['results']['architecture']['status'] == 'evaluation_error'
    assert 'EVALUATION ERROR' in fs_store.report_path(inv.id).read_text()


def test_gate_wait_is_deadline_bounded_and_cancellation_releases_database(tmp_path):
    gate = CerebrasRateGate(str(tmp_path / 'gate.sqlite'), interval_seconds=12)
    gate.acquire()
    with pytest.raises(InterruptedError, match='deadline'):
        gate.acquire(deadline=time.monotonic() + .02)
    def cancel():
        raise InterruptedError('Cancelled')
    with pytest.raises(InterruptedError, match='Cancelled'):
        gate.acquire(cancel_check=cancel)
    # Waiting reserves no future slot and leaves no lock/permit behind.
    with gate._connect() as db:
        db.execute("UPDATE provider_gate SET next_allowed=0")
    gate.acquire(deadline=time.monotonic() + 1)


def test_gate_database_connection_closes_after_failure(tmp_path):
    import sqlite3
    gate = CerebrasRateGate(str(tmp_path / 'gate.sqlite'), interval_seconds=0)
    connection = None
    with pytest.raises(RuntimeError):
        with gate._connect() as db:
            connection = db
            db.execute('BEGIN IMMEDIATE')
            raise RuntimeError('cancelled transaction')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')
    gate.acquire(deadline=time.monotonic() + 1)


def test_cancellation_during_capacity_wait_does_not_reserve_another_slot(tmp_path):
    gate = CerebrasRateGate(str(tmp_path / 'gate.sqlite'), interval_seconds=12)
    gate.acquire()
    with gate._connect() as db:
        reserved = db.execute('SELECT next_allowed FROM provider_gate').fetchone()[0]
    waiting = []
    def cancel():
        if waiting:
            raise InterruptedError('Cancelled while waiting')
    with pytest.raises(InterruptedError, match='Cancelled while waiting'):
        gate.acquire(cancel_check=cancel, on_wait=waiting.append)
    with gate._connect() as db:
        assert db.execute('SELECT next_allowed FROM provider_gate').fetchone()[0] == reserved


def test_provider_failure_preserves_rate_spacing_but_leaves_no_held_permit(tmp_path, monkeypatch):
    monkeypatch.setenv('CEREBRAS_KEY', 'test-key')
    monkeypatch.setenv('WIZARD_CEREBRAS_GATE_DB', str(tmp_path / 'gate.sqlite'))
    policy = ModelPolicy()
    def fail(*args, **kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx, 'post', fail)
    with pytest.raises(ModelFailure, match='ConnectError'):
        policy.request('planner', {}, VerificationSpec)
    assert policy.provider_requests == 1
    with policy.gate._connect() as db:
        assert db.execute('SELECT next_allowed FROM provider_gate').fetchone()[0] > time.time()
        db.execute('UPDATE provider_gate SET next_allowed=0')
    policy.gate.acquire(deadline=time.monotonic() + 1)


def test_repository_model_request_uses_only_relevant_instructions(monkeypatch):
    from wizard_kernel.contracts.verification import decision_model
    from wizard_kernel.ports.prompts import REPOSITORY_DECIDE
    monkeypatch.setenv('CEREBRAS_KEY', 'test-key')
    monkeypatch.setenv('WIZARD_LLM_BASE_URL', 'http://provider.test')
    model = decision_model(['read_file'], repository_refinement=True)
    answer = response(model, {'kind': 'evaluate', 'reason': 'Evidence is ready'})
    def reply(*args, **kwargs):
        assert kwargs['json']['messages'][0]['content'] == REPOSITORY_DECIDE
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': answer.model_dump_json()}}]})
    monkeypatch.setattr(httpx, 'post', reply)
    assert ModelPolicy().request('explorer', {'available_tools': ['read_file']}, model).kind == 'evaluate'
