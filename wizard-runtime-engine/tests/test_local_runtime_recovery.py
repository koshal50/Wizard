"""Local execution recovery and evidence regressions using real subprocesses."""
import json
import sys
import pytest
from wizard_kernel.control import loop
from wizard_kernel.contracts.agent import VerifierAssessment
from wizard_kernel.contracts.node import InvestigationNode, Hypothesis, HypothesisKind
from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry, GoalDefinition
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.context.packager import _result_record
from wizard_kernel.control.goals import evidence_categories_for_tool
from wizard_kernel.belief.extractors import extract
from wizard_kernel.ports.agents import MockExplorer
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.world.sandbox.local import LocalProcessRuntime
from wizard_kernel.world.tools import ToolExecutor


def make_node(identifier, tool, params):
    return InvestigationNode(id=identifier, type='execute', action={'tool': tool, 'params': params},
                             hypothesis=Hypothesis(kind=HypothesisKind.always_success))


def observations(inv):
    return [json.loads(p.read_text(encoding='utf-8'))
            for p in sorted((fs_store.inv_dir(inv.id) / 'observations').glob('o_*.json'))]


def test_failed_command_then_planner_recovery_and_process_inspection(tmp_path, monkeypatch):
    (tmp_path / 'fail.py').write_text("import sys\nprint('missing startup configuration', file=sys.stderr)\nsys.exit(7)\n")
    (tmp_path / 'worker.py').write_text("import time\nprint('worker started', flush=True)\ntime.sleep(30)\n")
    (tmp_path / 'package.json').write_text('{"name":"incidental-configuration","version":"1.0.0"}')
    config = make_node('configuration', 'read_file', {'path': 'package.json'}).model_copy(update={'type': 'read'})
    failed = make_node('failed', 'execute_command', {'command': f'"{sys.executable}" fail.py', 'cwd': '.'})
    recovered = make_node('recovered', 'start_process', {'command': f'"{sys.executable}" worker.py', 'cwd': '.'})
    class Planner:
        contexts = []
        def initial(self, *args, **kwargs):
            return TechnologyPlan(technologies=[TechnologyEntry(name='Python', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Verify Runtime', required_claim_types=['RUNTIME'],
                    required_evidence=['command_execution', 'process_execution'], requires_execution_evidence=True)])],
                seed_nodes=[config, failed])
        def next_nodes(self, context):
            self.contexts.append(context)
            assert 'missing startup configuration' in context['recent_failures'][-1]['reason']
            assert context['recent_failures'][-1]['exit_code'] == 7
            assert context['plan'][-1]['state'] == 'failed'
            assert [r['tool'] for r in context['successful_results']] == ['read_file']
            return [recovered]
        def interpret(self, *args): return []
    class Explorer(MockExplorer):
        contexts = []
        def request(self, context):
            self.contexts.append(context)
            return super().request(context)
    class Verifier:
        calls = 0
        def assess(self, claims, investigation_id=''):
            self.calls += 1
            requirements = json.loads(self.context['context'])['goal_requirements'][0]
            assert requirements['required'] == ['command_execution', 'process_execution']
            assert requirements['missing'] == []
            assert all(c['type'] == 'RUNTIME' for c in claims)
            assert any(c['type'] == 'RUNTIME' and any(e['source_tier'] == 'execution' for e in c['evidence']) for c in claims)
            return VerifierAssessment(investigation_id=investigation_id, assessment='overall_sufficient',
                report_markdown='# Verification Findings\n\nThe owned process was observed alive. '
                    + json.loads(self.context['context'])['successful_results'][-1]['observation_id'])
    explorer, verifier, planner = Explorer(), Verifier(), Planner()
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (explorer, verifier))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['runtime']))
    loop.run(inv, manager, planner)
    assert inv.state == LifecycleState.completed and inv.report_ready
    assert len(planner.contexts) == 1 and verifier.calls == 1
    records = observations(inv)
    assert [o['source_tool'] for o in records] == ['read_file', 'execute_command', 'start_process', 'read_process']
    assert records[1]['evidence_categories'] == [] and not records[1]['success']
    assert records[2]['evidence_categories'] == ['command_execution']
    assert records[3]['success'] and records[3]['evidence_categories'] == ['process_execution']
    assert 'missing startup configuration' in explorer.contexts[2]['recent_failures'][-1]['reason']
    assert explorer.contexts[3]['node_selection']['valid_node_ids'] == [records[3]['node_id']]
    assert explorer.contexts[3]['plan']['current_node']['state'] == 'running'
    assert inv.cleanup['processes_terminated'] is True
    report = fs_store.read_text(inv.id, 'verification_report.md')
    assert 'missing startup configuration' in report and 'The owned process was observed alive.' in report


def test_real_timeout_keeps_output_and_actionable_failure(tmp_path):
    (tmp_path / 'server.py').write_text("import time\nprint('actual startup output', flush=True)\ntime.sleep(30)\n")
    sandbox = LocalProcessRuntime()
    sandbox.start(str(tmp_path))
    try:
        result = ToolExecutor(sandbox, str(tmp_path)).execute({'tool': 'execute_command',
            'params': {'command': f'"{sys.executable}" server.py', 'timeout_sec': .4}})
        assert not result['ok'] and result['exit_code'] == -1
        assert 'timeout after' in result['error']
        assert 'actual startup output' in result['stdout']
        assert evidence_categories_for_tool('execute_command', result) == []
    finally:
        sandbox.stop()


def test_missing_file_is_failed_but_empty_existing_file_is_success(tmp_path):
    (tmp_path / 'empty.py').write_text('')
    sandbox = LocalProcessRuntime()
    sandbox.start(str(tmp_path))
    tools = ToolExecutor(sandbox, str(tmp_path))
    assert not tools.execute({'tool': 'read_file', 'params': {'path': 'missing.py'}})['ok']
    assert tools.execute({'tool': 'read_file', 'params': {'path': 'empty.py'}})['ok']
    sandbox.stop()


def test_no_valid_recovery_terminates_with_actual_error(tmp_path, monkeypatch):
    (tmp_path / 'fail.py').write_text("import sys\nprint('real configuration error', file=sys.stderr)\nsys.exit(7)\n")
    failed = make_node('failed', 'execute_command', {'command': f'"{sys.executable}" fail.py'})
    class Planner:
        calls = 0
        def initial(self, *args, **kwargs):
            return TechnologyPlan(technologies=[TechnologyEntry(name='Python', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Verify Runtime', required_claim_types=['RUNTIME'],
                    required_evidence=['command_execution', 'process_execution'], requires_execution_evidence=True)])],
                seed_nodes=[failed])
        def next_nodes(self, context):
            self.calls += 1
            assert 'real configuration error' in context['recent_failures'][0]['reason']
            return [failed.model_copy(update={'id': 'duplicate'})]
        def interpret(self, *args): return []
    class Verifier:
        def assess(self, *args, **kwargs):
            pytest.fail('No usable execution evidence: Verifier must not run')
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (MockExplorer(), Verifier()))
    manager, planner = InvestigationManager(), Planner()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['runtime']))
    loop.run(inv, manager, planner)
    assert inv.state == LifecycleState.incomplete and inv.report_ready and planner.calls == 1
    assert 'No forward progress' in inv.error and 'real configuration error' in inv.error
    records = observations(inv)
    assert len(records) == 1 and not records[0]['success'] and not records[0]['evidence_categories']
    assert 'real configuration error' in fs_store.read_text(inv.id, 'verification_report.md')


def test_process_creation_is_not_runtime_verification():
    from wizard_kernel.contracts.observation import Observation
    from datetime import datetime, timezone
    payload = {'ok': True, 'data': {'handle_id': 'owned', 'pid': 123, 'is_running': True}}
    obs = Observation(id='started', investigation_id='inv', node_id='node', source_tool='start_process',
                      obs_type='command_result', success=True, payload=payload, created_at=datetime.now(timezone.utc))
    assert evidence_categories_for_tool('start_process', payload) == ['command_execution']
    assert not any(c.claim_type == 'RUNTIME' for c in extract(obs))


def test_foreground_service_timeout_schedules_one_distinct_owned_recovery(tmp_path, monkeypatch):
    (tmp_path / 'service.py').write_text(
        "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
        "server = HTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)\n"
        "print(f'listening on http://127.0.0.1:{server.server_port}', flush=True)\n"
        "server.serve_forever()\n")
    initial = make_node('foreground', 'execute_command',
        {'command': f'"{sys.executable}" service.py', 'timeout_sec': .5, 'cwd': '.'})
    class Planner:
        def initial(self, *args, **kwargs):
            return TechnologyPlan(technologies=[TechnologyEntry(name='Python', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Verify Runtime', required_claim_types=['RUNTIME'],
                    required_evidence=['command_execution', 'process_execution'], requires_execution_evidence=True)])],
                seed_nodes=[initial])
        def next_nodes(self, context):
            pytest.fail('A distinct owned service recovery is already runnable')
        def interpret(self, *args): return []
    from wizard_kernel.ports.agents import MockVerifier
    class Explorer(MockExplorer):
        contexts = []
        def request(self, context):
            self.contexts.append(context)
            return super().request(context)
    explorer = Explorer()
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (explorer, MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['runtime']))
    loop.run(inv, manager, Planner())
    assert inv.state == LifecycleState.completed and inv.cleanup['processes_terminated'] is True
    records = observations(inv)
    assert [o['source_tool'] for o in records] == ['execute_command', 'start_process', 'read_process']
    assert not records[0]['success'] and records[0]['evidence_categories'] == []
    assert 'listening on http://' in explorer.contexts[1]['recent_failures'][-1]['failure_output']['stdout']
    assert explorer.contexts[1]['node_selection']['valid_node_ids'] == [records[1]['node_id']]
