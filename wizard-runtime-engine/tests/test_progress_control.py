"""Regression tests for the real Runtime's progress and lifecycle authority."""
from datetime import datetime, timedelta, timezone
import sys
import threading
import time

import pytest

from wizard_kernel.contracts.agent import ExplorerResponse, ToolRequest
from wizard_kernel.contracts.actions import fingerprint
from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry, GoalDefinition
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.control import loop
from wizard_kernel.session.control import RunControl, DeadlineExceeded
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.world.sandbox.local import LocalProcessRuntime
from wizard_kernel.ports.agents import MockVerifier


def create(tmp_path):
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='verify',
                                             options={'sandbox_mode': 'local_dev', 'budget': 30}))
    return manager, inv


def node(identifier='n1', tool='read_file', params=None):
    return InvestigationNode(id=identifier, type='read', action={'tool': tool, 'params': params or {'path': 'README.md'}},
                             hypothesis=Hypothesis(kind=HypothesisKind.always_success))


class Planner:
    def __init__(self, seeds=()):
        self.seeds = list(seeds)
        self.calls = 0

    def initial(self, *args, **kwargs):
        return TechnologyPlan(technologies=[TechnologyEntry(name='Test', confidence='high', signals=[],
            initial_goals=[GoalDefinition(name='Unreachable goal', required_claim_types=['UNREACHABLE'])])], seed_nodes=self.seeds)

    def next_nodes(self, context):
        self.calls += 1
        return [node('again')]

    def interpret(self, *args):
        return []


def test_suppressed_frontier_cannot_loop(tmp_path):
    (tmp_path / 'README.md').write_text('actual file')
    manager, inv = create(tmp_path)
    planner = Planner([node()])
    loop.run(inv, manager, planner)
    assert inv.state == LifecycleState.incomplete
    assert planner.calls == 1
    assert inv.model_calls < 5
    assert inv.report_ready and 'No forward progress' in fs_store.read_text(inv.id, 'verification_report.md')


def test_rejected_action_receives_actual_parameters_then_terminates(tmp_path, monkeypatch):
    class Explorer:
        contexts = []
        def request(self, packet):
            self.contexts.append(packet)
            return ExplorerResponse(investigation_id=packet['investigation_id'],
                                    tool_request=ToolRequest(tool='read_file', parameters={'path': '../outside.txt'}))
    explorer = Explorer()
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (explorer, MockVerifier()))
    manager, inv = create(tmp_path)
    loop.run(inv, manager, Planner([node()]))
    assert inv.state == LifecycleState.incomplete
    assert len(explorer.contexts) == 2
    packet = explorer.contexts[1]
    assert packet['previous_actions'] == [] and packet['successful_results'] == []
    failure = packet['recent_failures'][-1]
    assert failure['params'] == {'path': '../outside.txt'}
    assert failure['status'] == 'REJECTED' and failure['prohibited_from_repeating']
    assert failure['required_next_behavior']
    assert inv.report_ready


def test_single_flight_and_completed_step_is_not_queued(tmp_path):
    manager, inv = create(tmp_path)
    assert manager.acquire_run(inv.id)
    assert not manager.acquire_run(inv.id)
    first = manager.begin_step(inv.id, LifecycleState.planning, True)
    duplicate = manager.begin_step(inv.id, LifecycleState.planning, True)
    assert duplicate['id'] == first['id'] and duplicate['existing']
    assert inv.model_calls == 1
    manager.end_step(inv.id, first['id'], 'completed')
    manager.end_step(inv.id, first['id'], 'failed')
    assert inv.active_step['status'] == 'completed'
    second = manager.begin_step(inv.id, LifecycleState.replanning, True)
    assert second['id'] != first['id']


@pytest.mark.parametrize('state', ['completed', 'failed', 'incomplete', 'cancelled', 'timed_out'])
def test_terminal_never_calls_model(tmp_path, state):
    manager, inv = create(tmp_path)
    manager.update(inv.id, state=LifecycleState(state))
    planner = Planner()
    loop.run(inv, manager, planner)
    assert inv.model_calls == 0 and planner.calls == 0
    with pytest.raises(RuntimeError, match='terminal'):
        manager.begin_step(inv.id, LifecycleState.planning, True)


def test_hard_deadline_discards_late_provider_result(tmp_path):
    manager, inv = create(tmp_path)
    assert (inv.deadline_at - inv.started_at).total_seconds() <= 300.01
    inv.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=.12)
    control = RunControl(inv, manager)
    finished = threading.Event()
    def late():
        finished.wait(.6)
        return 'late provider output'
    started = time.monotonic()
    with pytest.raises(DeadlineExceeded):
        control.call(LifecycleState.exploring, late, model=True)
    assert time.monotonic() - started < .4
    assert inv.active_step['status'] == 'cancelled'
    finished.set()


def test_timeout_kills_real_owned_process_and_closes_browser(tmp_path, monkeypatch):
    sandbox = LocalProcessRuntime()
    captured = {}
    class Browser:
        closed = False
        def start(self): pass
        def stop(self): self.closed = True
    browser = Browser()
    monkeypatch.setattr(loop, 'get_sandbox', lambda _: sandbox)
    monkeypatch.setattr('wizard_kernel.world.browser.get_browser', lambda _: browser)
    class BlockingPlanner(Planner):
        def initial(self, *args, **kwargs):
            process = sandbox.exec_background(f'"{sys.executable}" -c "import time; time.sleep(30)"', '.')
            captured['process'] = process
            threading.Event().wait(1)
            return super().initial(*args, **kwargs)
    manager, inv = create(tmp_path)
    inv.options['browser_enabled'] = True
    inv.deadline_at = datetime.now(timezone.utc) + timedelta(seconds=.3)
    loop.run(inv, manager, BlockingPlanner())
    assert inv.state == LifecycleState.timed_out and inv.report_ready
    assert captured['process'].pid > 0 and browser.closed
    assert sandbox._closed and not sandbox._bg
    assert inv.cleanup == {'processes_terminated': True, 'browser_closed': True}
    assert 'TIMED OUT' in fs_store.read_text(inv.id, 'verification_report.md')


def test_fingerprints_normalize_paths_and_ignore_read_size():
    assert fingerprint('read_file', {'path': './src\\app.py', 'max_bytes': 10}) == fingerprint('read_file', {'path': 'src/app.py'})
    assert fingerprint('read_file', {'path': 'a'}) != fingerprint('read_file', {'path': 'b'})


def test_provider_failure_produces_report_without_retry(tmp_path, monkeypatch):
    class Explorer:
        calls = 0
        def request(self, packet):
            self.calls += 1
            raise TimeoutError('provider request expired')
    explorer = Explorer()
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (explorer, MockVerifier()))
    manager, inv = create(tmp_path)
    loop.run(inv, manager, Planner([node()]))
    assert explorer.calls == 1 and inv.state == LifecycleState.incomplete and inv.report_ready


@pytest.mark.parametrize('corrects', [True, False])
def test_stale_node_correction_is_bounded(tmp_path, monkeypatch, corrects):
    class Explorer:
        contexts = []
        def request(self, packet):
            self.contexts.append(packet)
            selected = packet['current_node']['id'] if corrects and len(self.contexts) == 2 else 'completed-old-node'
            return ExplorerResponse(investigation_id=packet['investigation_id'], node_id=selected,
                                    tool_request=ToolRequest(tool='read_file', parameters={'path': 'README.md'}))
    explorer = Explorer()
    (tmp_path / 'README.md').write_text('actual repository evidence')
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (explorer, MockVerifier()))
    manager, inv = create(tmp_path)
    loop.run(inv, manager, Planner([node()]))
    assert len(explorer.contexts) == 2
    assert explorer.contexts[1]['node_selection']['valid_node_ids'] == ['n1']
    assert explorer.contexts[1]['recent_failures'][-1]['status'] == 'REJECTED'
    import json
    observations = [json.loads(p.read_text(encoding='utf-8'))
                    for p in (fs_store.inv_dir(inv.id) / 'observations').glob('o_*.json')]
    assert any(o['source_tool'] == 'read_file' for o in observations) == corrects
    assert inv.report_ready and inv.state == LifecycleState.incomplete
    if not corrects:
        assert 'completed-old-node' in fs_store.read_text(inv.id, 'verification_report.md')


def test_windows_planned_read_matches_actual_normalized_path():
    assert loop._planned_action_matches({'tool': 'read_file', 'params': {'path': 'src/entry.py', 'max_bytes': 65536}},
                                        'read_file', {'path': r'src\entry.py', 'max_bytes': 10000})
    assert not loop._planned_action_matches({'tool': 'read_file', 'params': {'path': 'src/entry.py'}},
                                            'read_file', {'path': 'src/other.py'})


def test_agent_transport_allows_rate_gate_wait_within_deadline():
    from wizard_kernel.ports.agents import _remaining_timeout
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=55)).isoformat()
    assert 54 < _remaining_timeout(deadline) <= 55
    with pytest.raises(DeadlineExceeded):
        _remaining_timeout((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())


def test_model_architecture_report_survives_runtime_finalization(tmp_path, monkeypatch):
    from wizard_kernel.contracts.node import ClaimTemplate
    from wizard_kernel.contracts.agent import VerifierAssessment
    from wizard_kernel.ports.agents import MockExplorer
    class LocalPlanner(Planner):
        def initial(self, *args, **kwargs):
            return TechnologyPlan(technologies=[TechnologyEntry(name='Source', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Inspect Architecture', required_claim_types=['FILE_READ'],
                                             required_evidence=['repository_read'])])], seed_nodes=self.seeds)
    class Verifier:
        calls = 0
        def assess(self, claims, investigation_id=''):
            self.calls += 1
            assert claims and claims[0]['evidence']
            return VerifierAssessment(investigation_id=investigation_id, assessment='overall_sufficient',
                                      report_markdown='# Verification Findings\n\nREADME.md was inspected. '
                                      + claims[0]['evidence'][0]['observation_ids'][0])
    (tmp_path / 'README.md').write_text('actual local source')
    manager, inv = create(tmp_path)
    inv.intent = 'investigate'
    inv.targets = ['architecture']
    seed = node().model_copy(update={'on_success': ClaimTemplate(claim_type='FILE_READ', key='README.md', value=True)})
    verifier = Verifier()
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (MockExplorer(), verifier))
    loop.run(inv, manager, LocalPlanner([seed]))
    assert inv.state == LifecycleState.completed and inv.report_ready
    assert verifier.calls == 1
    assert 'README.md was inspected.' in fs_store.read_text(inv.id, 'verification_report.md')
    assert fs_store.read_text(inv.id, 'model_report.md').startswith('# Verification Findings')
