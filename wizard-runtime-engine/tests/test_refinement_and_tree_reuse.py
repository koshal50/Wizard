"""Shared refinement/evidence lifecycle regressions, through the normal Runtime."""
import time
from datetime import datetime, timezone

import pytest

from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.verification import CheckRefinement, CheckSpec, decision_model, planning_model
from wizard_kernel.control import verification
from wizard_kernel.control.tool_validator import ToolRequestValidator
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


def predicate(target='obs_one', expected='requireAuth'):
    return dict(source='repository', field='content', operator='contains', target=target, expected=expected)


def proof(oid='obs_one', content='requireAuth', inv='inv_one'):
    return Observation(id=oid, investigation_id=inv, node_id='read', goal_id='discover',
        source_tool='read_file', obs_type='file_content', success=True, created_at=datetime.now(timezone.utc),
        payload={'ok': True, 'data': {'path': 'app.py', 'content': content}})


def refinement(ids=None, target='obs_one', expected='requireAuth'):
    return CheckRefinement(assertions=[predicate(target, expected)], observation_ids=ids or ['obs_one'])


def wire(model, data):
    return model.model_validate({'decision': data} if 'decision' in model.model_fields else data)


def test_refinement_actual_ids_and_cited_content_are_required():
    check = CheckSpec(id='discover', description='Discover security', unresolved_reason='Read implementation')
    assert not verification.refinement_errors(check, refinement(), [proof()], {'obs_one'})
    errors = verification.refinement_errors(check, refinement(['obs_typo']), [proof()], {'obs_one'})
    assert errors['invalid_observation_ids'] == ['obs_typo']
    assert errors['uncited_observation_targets'] == ['obs_one']
    assert verification.refinement_errors(check, refinement(expected='invented'), [proof()], {'obs_one'})['unsupported_assertions']
    assert verification.refinement_errors(check, refinement(), [], set())['invalid_observation_ids']


def test_grounded_requirements_cannot_be_replaced():
    check = CheckSpec(id='discover', description='Keep authentication', assertions=[predicate(expected='requireAuth AND token')])
    errors = verification.refinement_errors(check, refinement(), [proof()], {'obs_one'})
    assert errors['grounded_requirements'] == [a.model_dump() for a in check.assertions]
    assert check.assertions[0].expected == 'requireAuth AND token'


def test_explanation_cannot_replace_content_with_file_existence():
    check = CheckSpec(id='discover', description='Explain architecture', unresolved_reason='Read source')
    exists = CheckRefinement(observation_ids=['obs_one'], assertions=[
        dict(source='repository', field='exists', expected='true', target='app.py')])
    assert verification.refinement_errors(check, exists, [proof()], {'obs_one'}, require_content=True)['missing_content_proof']


def test_explanation_planning_schema_disallows_execution_and_presence_only_proof():
    model = planning_model(['python app.py'], read_only=True)
    base = dict(id='explain', description='Explain runtime', capabilities=['repository'])
    assert wire(model, {'checks': [{**base, 'assertions': [predicate()]}]})
    for assertions, capabilities in [
        ([dict(source='process', field='is_running', expected='true')], ['process']),
        ([dict(source='repository', field='exists', expected='true', target='app.py')], ['repository']),
    ]:
        with pytest.raises(ValueError):
            wire(model, {'checks': [{**base, 'assertions': assertions, 'capabilities': capabilities}]})


def test_explanation_planner_cannot_attribute_observed_text_to_invented_file():
    model = planning_model([], read_only=True, repository_targets=['README.md', 'obs_readme'])
    for target in ['README.md', 'obs_readme']:
        wire(model, {'checks': [{'id': 'explain', 'description': 'Explain architecture', 'assertions': [predicate(target)]}]})
    with pytest.raises(ValueError):
        wire(model, {'checks': [{'id': 'explain', 'description': 'Explain architecture', 'assertions': [predicate('missing.md')]}]})
    empty = planning_model([], read_only=True, repository_targets=[])
    with pytest.raises(ValueError):
        wire(empty, {'checks': [{'id': 'explain', 'description': 'Explain architecture', 'assertions': [predicate()]}]})


@pytest.mark.parametrize('correct', [True, False])
def test_unsupported_explanation_plan_gets_one_correction_before_admission(tmp_path, correct):
    (tmp_path / 'README.md').write_text('requireAuth')
    class Policy:
        calls = 0
        def request(self, role, context, model, **kwargs):
            if role == 'explorer':
                oid = context['repository_evidence'][0]['observation_id']
                return wire(model, {'kind': 'refine', 'reason': 'Observed content', 'refinement': refinement([oid], oid).model_dump()})
            self.calls += 1
            if self.calls == 2:
                assert context['planning_feedback'][0]['assertion']['expected'] == 'invented'
                if correct:
                    return wire(model, {'checks': [{'id': 'explain', 'description': 'Explain security',
                        'assertions': [], 'unresolved_reason': 'Discover content criteria from real sources'}]})
            return wire(model, {'checks': [{'id': 'explain', 'description': 'Explain security',
                'assertions': [predicate('README.md', 'requireAuth' if correct and self.calls == 2 else 'invented')]}]})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='explain', targets=['security']))
    policy = Policy()
    verification.run(inv, manager, policy)
    assert policy.calls == 2
    assert inv.state.value == ('completed' if correct else 'failed')
    state = fs_store.read(inv.id, 'verification.json')
    assert state['explanation_plan_attempts'][0]['feedback']
    if not correct:
        assert state['checks'] == [] and state['executions'] == []


def test_schema_only_advertises_current_investigation_evidence():
    model = decision_model(['read_file'], repository_refinement=True, observation_ids=['obs_one', 'obs_two'],
        repository_targets=['obs_one', 'obs_two', 'app.py'])
    payload = {'kind': 'refine', 'reason': 'Observed implementation', 'refinement': refinement().model_dump()}
    assert wire(model, payload).refinement.observation_ids == ['obs_one']
    for invalid in ['obs_typo', 'obs_another_investigation']:
        payload['refinement']['observation_ids'] = [invalid]
        with pytest.raises(ValueError):
            wire(model, payload)
    empty = decision_model(['read_file'], observation_ids=[])
    with pytest.raises(ValueError):
        wire(empty, payload)
    payload['refinement']['observation_ids'] = ['obs_one']
    payload['refinement']['assertions'][0]['target'] = 'invented/file.py'
    with pytest.raises(ValueError):
        wire(model, payload)


def test_multiple_observation_targets_must_be_cited():
    check = CheckSpec(id='discover', description='Discover implementation', unresolved_reason='Read sources')
    refs = CheckRefinement(assertions=[predicate(), predicate('obs_two', 'token')], observation_ids=['obs_one', 'obs_two'])
    assert not verification.refinement_errors(check, refs, [proof(), proof('obs_two', 'token')], {'obs_one', 'obs_two'})
    assert verification.refinement_errors(check, refs, [proof()], {'obs_one'})['invalid_observation_ids'] == ['obs_two']


def test_rejection_feedback_locates_real_support_without_retargeting_requirement():
    check = CheckSpec(id='discover', description='Explain security', unresolved_reason='Read source')
    unrelated = proof(content='unrelated content')
    support = proof('obs_actual_support').model_copy(update={
        'payload': {'ok': True, 'data': {'path': 'security.py', 'content': 'requireAuth'}}})
    proposed = refinement()
    errors = verification.refinement_errors(check, proposed, [unrelated, support], {'obs_one', 'obs_actual_support'})
    assert errors['unsupported_assertions'][0]['supporting_sources'] == [
        {'observation_id': 'obs_actual_support', 'path': 'security.py'}]
    assert proposed.assertions[0].target == 'obs_one' and not check.assertions


def test_reused_older_content_is_prioritized_within_context_budget():
    from types import SimpleNamespace
    observations = [proof('obs_older', 'requireAuth' + 'x' * 8000)] + [
        proof('obs_' + str(n), 'y' * 8000) for n in range(4)]
    inv = SimpleNamespace(intent='explain', targets=['security'], question='security', active_goals=[], budget_remaining=5)
    check = CheckSpec(id='discover', description='Read security', unresolved_reason='Gather proof')
    context = verification._context(inv, check, [], observations, ['read_file'], {}, {}, preferred_ids=['obs_older'])
    older = next(e for e in context['repository_evidence'] if e['observation_id'] == 'obs_older')
    assert older['excerpt'].startswith('requireAuth') and not older['content_complete']
    assert sum(len(e['excerpt']) for e in context['repository_evidence']) <= 12100


def test_tree_defaults_are_normalized_and_success_is_reused_without_execution(tmp_path):
    validator = ToolRequestValidator(str(tmp_path))
    first = validator.validate(ToolRequest(tool='list_tree', parameters={}), 5)
    validator.record_execution('list_tree', first.sanitised_params, {'ok': True, 'data': {'tree': ['app.py']}}, 'obs_tree')
    repeated = validator.validate(ToolRequest(tool='list_tree', parameters={'max_depth': 3}), 5)
    assert repeated.valid and repeated.observation_id == 'obs_tree'
    assert validator.validate(ToolRequest(tool='list_tree', parameters={'max_depth': 4}), 5).observation_id is None
    other = ToolRequestValidator(str(tmp_path))
    assert other.validate(ToolRequest(tool='list_tree', parameters={}), 5).observation_id is None


@pytest.mark.parametrize('payload', [
    {'ok': False, 'error': 'Transient IO failure', 'meta': {'retryable': True}},
    {'ok': True, 'data': {'tree': [], 'incomplete': True}},
])
def test_recoverable_tree_results_get_one_retry_and_are_not_reused(tmp_path, payload):
    validator = ToolRequestValidator(str(tmp_path))
    request = ToolRequest(tool='list_tree', parameters={'max_depth': 3})
    first = validator.validate(request, 5)
    validator.record_execution('list_tree', first.sanitised_params, payload, 'obs_failed')
    retry = validator.validate(request, 5)
    assert retry.valid and retry.observation_id is None
    validator.record_execution('list_tree', retry.sanitised_params, payload, 'obs_failed_again')
    assert not validator.validate(request, 5).valid


def test_permanent_tree_failure_and_invalid_parameters_stay_rejected(tmp_path):
    validator = ToolRequestValidator(str(tmp_path))
    request = ToolRequest(tool='list_tree', parameters={'max_depth': 3})
    params = validator.validate(request, 5).sanitised_params
    validator.record_execution('list_tree', params, {'ok': False, 'error': 'Access denied'}, 'obs_denied')
    assert not validator.validate(request, 5).valid
    assert not validator.validate(ToolRequest(tool='list_tree', parameters={'max_depth': -1}), 5).valid


@pytest.mark.parametrize('intent', ['security', 'architecture', 'runtime'])
def test_explain_shared_runtime_reuses_tree_and_refines_from_actual_content(tmp_path, intent):
    (tmp_path / 'app.py').write_text('requireAuth token startup')
    class Policy:
        step = 0
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return wire(model, {'checks': [{'id': 'discover', 'description': 'Explain ' + intent,
                    'unresolved_reason': 'Read the implementation', 'capabilities': ['repository']}]})
            self.step += 1
            if self.step <= 2:
                if self.step == 2:
                    assert context['repository_results'][0]['result']['tree'] == ['app.py']
                    assert context['repository_requests'][0]['tool'] == 'list_tree'
                return wire(model, {'kind': 'tool', 'reason': 'Inspect structure',
                    'action': {'tool': 'list_tree', 'parameters': {'max_depth': 3}}})
            if self.step == 3:
                return wire(model, {'kind': 'tool', 'reason': 'Read implementation',
                    'action': {'tool': 'read_file', 'parameters': {'path': 'app.py'}}})
            evidence = next(e for e in context['repository_evidence'] if e['path'] == 'app.py')
            assert 'requireAuth' in evidence['excerpt']
            return wire(model, {'kind': 'refine', 'reason': 'Cited implementation',
                'refinement': refinement([evidence['observation_id']], evidence['observation_id']).model_dump()})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='explain', targets=[intent]))
    verification.run(inv, manager, Policy())
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state.value == 'completed'
    assert [e['tool'] for e in saved['executions']] == ['list_tree', 'read_file']
    assert saved['evidence_reuse'][0]['tool'] == 'list_tree'
    witness = saved['results']['discover']['assertions'][0]['observation_id']
    assert witness == next(e['observation_id'] for e in saved['executions'] if e['tool'] == 'read_file')


@pytest.mark.parametrize('correct', [True, False])
def test_invalid_refinement_feedback_can_recover_but_unchanged_retries_stop(tmp_path, correct):
    (tmp_path / 'README.md').write_text('requireAuth')
    class Policy:
        requests = 0
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return wire(model, {'checks': [{'id': 'discover', 'description': 'Explain security',
                    'unresolved_reason': 'Discover criteria', 'capabilities': ['repository']}]})
            self.requests += 1
            oid = context['repository_evidence'][0]['observation_id']
            if self.requests > 1:
                assert context['refinement_feedback'][0]['details']['unsupported_assertions']
            return wire(model, {'kind': 'refine', 'reason': 'Resolve criteria',
                'refinement': refinement([oid], oid, 'requireAuth' if correct and self.requests > 1 else 'invented').model_dump()})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='explain', targets=['security']))
    policy = Policy()
    verification.run(inv, manager, policy)
    assert policy.requests == 2
    assert inv.state.value == ('completed' if correct else 'incomplete')
    if not correct:
        assert not fs_store.read(inv.id, 'verification.json')['checks'][0]['assertions']


def test_repeated_tree_reuse_stops_without_fabricating_success(tmp_path):
    class Policy:
        def request(self, role, context, model, **kwargs):
            return wire(model, {'checks': [{'id': 'discover', 'description': 'Explain security',
                'unresolved_reason': 'No implementation', 'capabilities': ['repository']}]} if role == 'planner'
                else {'kind': 'tool', 'reason': 'Inspect tree', 'action': {'tool': 'list_tree', 'parameters': {}}})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='explain', targets=['security']))
    verification.run(inv, manager, Policy())
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state.value == 'incomplete' and len(saved['executions']) == 1
    assert saved['model_calls'] == 4


@pytest.mark.parametrize('intent', ['security', 'architecture', 'runtime'])
def test_explain_http_entry_point_preserves_real_proof(tmp_path, monkeypatch, intent):
    from fastapi.testclient import TestClient
    from wizard_kernel.api.app import app
    from wizard_kernel.api.deps import get_manager
    (tmp_path / 'README.md').write_text('requireAuth startup architecture')
    class Policy:
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return wire(model, {'checks': [{'id': 'discover', 'description': 'Explain ' + intent,
                    'unresolved_reason': 'Discover implementation', 'capabilities': ['repository']}]})
            oid = context['repository_evidence'][0]['observation_id']
            return wire(model, {'kind': 'refine', 'reason': 'Retrieved documentation',
                'refinement': refinement([oid], oid).model_dump()})
    monkeypatch.setattr(verification, 'ModelPolicy', Policy)
    with TestClient(app) as client:
        response = client.post('/v1/investigations', json={'repository_path': str(tmp_path),
            'intent': 'explain', 'targets': [intent], 'question': intent})
        assert response.status_code == 201
        iid = response.json()['investigation_id']
        deadline = time.monotonic() + 10
        while not get_manager().get(iid).report_ready and time.monotonic() < deadline:
            time.sleep(.01)
        assert get_manager().get(iid).state.value == 'completed'
        saved = fs_store.read(iid, 'verification.json')
        assert saved['results']['discover']['assertions'][0]['observation_id'].startswith('obs_')


def test_tree_result_remains_available_after_recent_window(tmp_path):
    from types import SimpleNamespace
    tree = proof('obs_tree').model_copy(update={'source_tool': 'list_tree',
        'payload': {'ok': True, 'data': {'tree': ['app.py'], 'count': 1}}})
    observations = [tree] + [proof('obs_' + str(n)) for n in range(4)]
    inv = SimpleNamespace(intent='explain', targets=['security'], question='security', active_goals=[],
        budget_remaining=5)
    context = verification._context(inv, CheckSpec(id='discover', description='Discover security',
        unresolved_reason='Read implementation'), [], observations, ['read_file', 'list_tree'], {}, {})
    assert 'obs_tree' not in {o['id'] for o in context['recent_observations']}
    assert context['repository_results'][0]['observation_id'] == 'obs_tree'
    assert context['repository_results'][0]['result']['tree'] == ['app.py']


def test_listing_io_errors_are_incomplete_not_success(tmp_path, monkeypatch):
    import os
    from wizard_kernel.world.tools import ToolExecutor
    from wizard_kernel.world.sandbox import get_sandbox
    def partial_walk(root, onerror):
        onerror(PermissionError('Cannot enumerate subtree'))
        yield str(tmp_path), [], ['app.py']
    monkeypatch.setattr(os, 'walk', partial_walk)
    result = ToolExecutor(get_sandbox('local_dev'), str(tmp_path)).execute({'tool': 'list_tree', 'params': {}})
    assert not result['ok'] and result['data']['incomplete']
    assert result['data']['tree'] == ['app.py']


def test_repository_cache_invalidates_after_mutating_execution(tmp_path):
    validator = ToolRequestValidator(str(tmp_path))
    request = ToolRequest(tool='list_tree', parameters={'max_depth': 3})
    params = validator.validate(request, 5).sanitised_params
    validator.record_execution('list_tree', params, {'ok': True, 'data': {'tree': []}}, 'obs_before')
    validator.record_execution('execute_command', {'command': 'npm install'}, {'ok': True})
    assert validator.validate(request, 5).observation_id is None


def test_transient_tree_failure_retries_through_runtime(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('requireAuth')
    original = verification.ToolExecutor.execute
    attempts = []
    def execute(self, action):
        if action['tool'] == 'list_tree':
            attempts.append(action)
            if len(attempts) == 1:
                return {'ok': False, 'error': 'Temporary listing failure', 'meta': {'retryable': True}}
        return original(self, action)
    monkeypatch.setattr(verification.ToolExecutor, 'execute', execute)
    class Policy:
        step = 0
        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return wire(model, {'checks': [{'id': 'discover', 'description': 'Explain security',
                    'unresolved_reason': 'Read sources', 'capabilities': ['repository']}]})
            self.step += 1
            if self.step <= 2:
                return wire(model, {'kind': 'tool', 'reason': 'Inspect structure',
                    'action': {'tool': 'list_tree', 'parameters': {}}})
            if self.step == 3:
                return wire(model, {'kind': 'tool', 'reason': 'Read source',
                    'action': {'tool': 'read_file', 'parameters': {'path': 'app.py'}}})
            oid = next(e['observation_id'] for e in context['repository_evidence'] if e['path'] == 'app.py')
            return wire(model, {'kind': 'refine', 'reason': 'Observed source', 'refinement': refinement([oid], oid).model_dump()})
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='explain', targets=['security']))
    verification.run(inv, manager, Policy())
    assert inv.state.value == 'completed' and len(attempts) == 2
