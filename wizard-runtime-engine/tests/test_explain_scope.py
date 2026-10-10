import json
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.control.tool_validator import ToolRequestValidator
from wizard_kernel.control import loop
from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry, GoalDefinition
from wizard_kernel.contracts.node import InvestigationNode, Hypothesis, HypothesisKind
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store
from wizard_kernel.ports.agents import MockExplorer, MockVerifier


def test_explain_disables_browser_and_rejects_execution(tmp_path):
    request = InvestigationRequest(repository_path=str(tmp_path), intent='explain', options={'browser_enabled': True})
    assert not request.options.browser_enabled
    validator = ToolRequestValidator(str(tmp_path), browser_enabled=True, read_only=True)
    for tool, params in [('start_process', {'command': 'node app.js'}),
                         ('browser_navigate', {'url': 'http://localhost:4000'}),
                         ('http_request', {'url': 'http://localhost:4000'})]:
        assert not validator.validate(ToolRequest(tool=tool, parameters=params), 20).valid


def test_model_cannot_add_runtime_or_browser_goals_to_explain(tmp_path, monkeypatch):
    (tmp_path / 'package.json').write_text('{"dependencies":{"express":"4"}}')
    class Planner:
        def initial(self, *args, **kwargs):
            return TechnologyPlan(technologies=[TechnologyEntry(name='Node.js', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Verify Runtime'), GoalDefinition(name='Operate Web Surface')])],
                seed_nodes=[InvestigationNode(id='read', type='read', action={'tool':'read_file','params':{'path':'package.json'}},
                    hypothesis=Hypothesis(kind=HypothesisKind.always_success))])
        def next_nodes(self, context): raise AssertionError('No execution needed')
        def interpret(self, *args): return []
    class Explorer(MockExplorer):
        def request(self, context):
            assert set(context['available_tools']) <= {'read_file','list_tree','search_files','path_exists'}
            return super().request(context)
    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (Explorer(), MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='explain', targets=['dependencies']))
    loop.run(inv, manager, Planner())
    assert inv.state.value == 'completed' and inv.report_ready
    assert fs_store.read(inv.id, 'goals.json')[0]['name'] == 'Inspect dependencies'
    records = [json.loads(p.read_text(encoding='utf-8')) for p in (fs_store.inv_dir(inv.id)/'observations').glob('o_*.json')]
    assert [o['source_tool'] for o in records] == ['read_file']


def test_local_architecture_does_not_inherit_unsolicited_browser_goals(tmp_path, monkeypatch):
    from wizard_kernel.contracts.node import ClaimTemplate

    (tmp_path / 'app.py').write_text('print("hello")')

    class Planner:
        def initial(self, *args, **kwargs):
            return TechnologyPlan(technologies=[TechnologyEntry(name='Python', confidence='high', signals=[],
                initial_goals=[GoalDefinition(name='Inspect Architecture'),
                    GoalDefinition(name='Verify Web Surface'), GoalDefinition(name='Operate Web Surface')])],
                seed_nodes=[InvestigationNode(id='read', type='read',
                    action={'tool': 'read_file', 'params': {'path': 'app.py'}},
                    hypothesis=Hypothesis(kind=HypothesisKind.always_success),
                    on_success=ClaimTemplate(claim_type='FILE_READ', key='app.py', value=True))])

        def next_nodes(self, context):
            raise AssertionError('An unsolicited browser goal must not trigger replanning')

        def interpret(self, *args):
            return []

    monkeypatch.setattr('wizard_kernel.ports.agents.get_agents', lambda _: (MockExplorer(), MockVerifier()))
    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    loop.run(inv, manager, Planner())
    assert inv.state.value == 'completed' and inv.report_ready
    assert [g['name'] for g in fs_store.read(inv.id, 'goals.json')] == ['Inspect Architecture']
