import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.control.goals import Goal, GoalEngine, evidence_categories_for_tool
from wizard_kernel.control.runtime_checks import runtime_levels, readiness_target
from wizard_kernel.control import loop, report
from wizard_kernel.contracts.node import InvestigationNode, Hypothesis, HypothesisKind
from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry, GoalDefinition
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.ports.agents import MockExplorer, MockVerifier
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.world.tools import ToolExecutor


def test_readiness_discovers_existing_relative_imports_only(tmp_path):
    from wizard_kernel.control.runtime_checks import readiness_source_files
    (tmp_path / 'server.js').write_text('')
    (tmp_path / 'routes.js').write_text("app.get('/healthz', handler)")
    obs = observation('read_file', {'ok': True, 'data': {'path': 'server.js',
        'content': "const routes = require('./routes'); require('./missing'); require('../outside');"}})
    assert readiness_source_files([obs], tmp_path) == ['routes.js']


def observation(tool, payload, goal='g'):
    return Observation(id=tool, investigation_id='inv', node_id=tool, goal_id=goal,
        source_tool=tool, obs_type='command_result', payload=payload, created_at=datetime.now(timezone.utc),
        success=bool(payload.get('ok')), evidence_categories=evidence_categories_for_tool(tool, payload))


def test_listening_is_startup_not_http_readiness():
    obs = observation('read_process', {'ok': True, 'data': {'is_running': True},
        'stdout': 'server listening on http://localhost:8123'})
    assert obs.evidence_categories == ['process_execution', 'runtime_startup']
    assert runtime_levels([obs])['Server startup (listening message)']
    assert not runtime_levels([obs])['HTTP readiness']


def test_running_process_without_response_is_not_ready():
    obs = observation('read_process', {'ok': True, 'data': {'is_running': True}})
    goals = GoalEngine('inv')
    goals.add(Goal('g', 'Verify Runtime', ['RUNTIME'], required_evidence=['process_execution', 'http_readiness']))
    assert goals.evidence_status('g', [obs])['missing'] == ['http_readiness']


def test_successful_targeted_response_proves_readiness():
    obs = observation('http_request', {'ok': True, 'data': {'status_code': 204}, 'readiness_check': {'purpose': 'readiness'}})
    assert 'http_readiness' in obs.evidence_categories
    assert runtime_levels([obs])['HTTP readiness']
    assert 'http_readiness' not in observation('http_request', {'ok': True, 'data': {'status_code': 200}}).evidence_categories


def test_unhealthy_health_body_does_not_pass_on_http_200():
    from wizard_kernel.control.runtime_checks import readiness_failure
    payload = {'ok': True, 'readiness_check': True,
               'data': {'url': 'http://localhost:8123/health', 'status_code': 200, 'body_preview': '{"ready":false}'}}
    assert 'unhealthy' in readiness_failure(payload)
    assert 'http_readiness' not in evidence_categories_for_tool('http_request', payload)


def test_readiness_requires_observed_route_not_invented_health():
    source = observation('read_file', {'ok': True, 'data': {'content': "app.get('/status', handler)"}})
    assert readiness_target([source], 'http://localhost:8123') == 'http://localhost:8123/status'
    assert readiness_target([], 'http://localhost:8123') is None


def test_existing_planner_http_result_is_reused_as_readiness_proof():
    source = observation('read_file', {'ok': True, 'data': {'content': "app.get('/status', handler)"}})
    live = observation('read_process', {'ok': True, 'data': {'is_running': True}, 'stdout': 'listening on http://localhost:8123'})
    response = observation('http_request', {'ok': True, 'data': {'status_code': 200, 'url': 'http://localhost:8123/status'}})
    observations = [source, live, response]
    goals = GoalEngine('inv')
    goals.add(Goal('g', 'Verify Runtime', [], required_evidence=['http_readiness']))
    assert goals.evidence_status('g', observations)['missing'] == []
    assert runtime_levels(observations)['HTTP readiness'] == ['http_request']


@pytest.mark.parametrize('required', [False, True])
def test_timeout_is_scoped_and_required_check_cannot_be_ignored(required):
    failed = observation('execute_command', {'ok': False, 'error': 'timeout after 30s', 'required_check': required})
    live = observation('read_process', {'ok': True, 'data': {'is_running': True}})
    goals = GoalEngine('inv')
    goals.add(Goal('g', 'Verify Runtime', [], required_evidence=['process_execution']))
    kg = SimpleNamespace(all_claims=lambda: [])
    assert goals.evaluate_checkpoint('g', kg, [failed, live]) is (not required)
    assert runtime_levels([failed, live])['Process liveness'] == ['read_process']


@pytest.mark.parametrize('status, expected_state', [(200, 'completed'), (503, 'incomplete')])
@pytest.mark.parametrize('late_route', [False, True])
@pytest.mark.parametrize('import_discovery', [False, True])
def test_runtime_schedules_bounded_readiness_without_browser(tmp_path, monkeypatch, status, expected_state, late_route, import_discovery):
    (tmp_path / 'app.js').write_text("app.get('/healthz', (req,res) => res.json({status:'ok'}))")
    (tmp_path / 'server.js').write_text("const {createApp} = require('./app');")
    def node(id, tool, params, type='execute'):
        return InvestigationNode(id=id, type=type, action={'tool': tool, 'params': params},
            hypothesis=Hypothesis(kind=HypothesisKind.always_success))
    class Planner:
        def initial(self, *args, **kwargs):
            seeds = [node('source', 'read_file', {'path': 'server.js' if import_discovery else 'app.js'}, 'read'),
                     node('start', 'start_process', {'command': 'node app.js'})]
            return TechnologyPlan(technologies=[TechnologyEntry(name='Node.js', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Verify Runtime')])], seed_nodes=[
                    seeds[1]] if late_route else seeds)
        def next_nodes(self, context):
            if late_route and not any(r['tool'] == 'read_file' for r in context['successful_results']):
                return [node('source', 'read_file', {'path': 'server.js' if import_discovery else 'app.js'}, 'read')]
            return []
        def interpret(self, *args):
            return []
    monkeypatch.setattr(ToolExecutor, '_tool_start_process', lambda self, command, cwd='.' :
        {'ok': True, 'data': {'handle_id': 'proc_test', 'is_running': True, 'pid': 123}})
    monkeypatch.setattr(ToolExecutor, '_tool_read_process', lambda self, handle_id:
        {'ok': True, 'data': {'handle_id': 'proc_test', 'is_running': True}, 'stdout': 'listening on http://localhost:8123'})
    monkeypatch.setattr(ToolExecutor, '_tool_check_port', lambda self, port, host='localhost':
        {'ok': True, 'data': {'active': True, 'host': host, 'port': port}})
    monkeypatch.setattr(ToolExecutor, '_tool_http_request', lambda self, url, method='GET', body=None:
        {'ok': True, 'data': {'status_code': status, 'body_preview': 'ok' if status == 200 else 'unavailable', 'url': url, 'method': method}})
    class Explorer(MockExplorer):
        def request(self, context):
            if context['current_node']['action'].get('readiness_check'):
                assert context['available_tools'] == ['http_request']
                assert context['http']['runtime_authorized_readiness_target'] == 'http://localhost:8123/healthz'
            return super().request(context)
    class Verifier(MockVerifier):
        def assess(self, claims, investigation_id=''):
            assert claims and all(c['type'] == 'RUNTIME' for c in claims)
            return super().assess(claims, investigation_id)
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (Explorer(), Verifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='verify', targets=['runtime']))
    loop.run(inv, manager, Planner())
    assert inv.state.value == expected_state and inv.report_ready
    records = [json.loads(p.read_text(encoding='utf-8')) for p in (fs_store.inv_dir(inv.id)/'observations').glob('o_*.json')]
    http = [o for o in records if o['source_tool'] == 'http_request']
    assert len(http) == 1
    assert http[0]['payload']['action']['params']['url'] == 'http://localhost:8123/healthz'
    assert http[0]['success'] is (status == 200)
    assert not any(o['source_tool'].startswith('browser_') for o in records)
    markdown = fs_store.read_text(inv.id, 'verification_report.md')
    assert 'Process liveness: verified' in markdown
    assert ('HTTP readiness: verified' if status == 200 else 'HTTP readiness: failed') in markdown
    if status == 503:
        assert 'HTTP 503' in markdown and 'PARTIALLY VERIFIED' in markdown
