"""An architecture explanation must not fail on a planner's invented JSON layout."""
import pytest
from pydantic import ValidationError

from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.verification import ARCHITECTURE_AREAS
from wizard_kernel.control import verification
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


def test_architecture_synthesis_cannot_treat_content_as_an_evidence_location():
    from wizard_kernel.contracts.verification import architecture_report_model

    model = architecture_report_model([{'observation_id': 'obs_file', 'path': 'package.json'}])
    data = {'findings': [{'area': area, 'summary': area, 'assertions': [{
        'source': 'repository', 'field': 'content', 'operator': 'contains',
        'target': 'content', 'expected': 'workspaces'}]} for area in ARCHITECTURE_AREAS]}
    with pytest.raises(ValidationError):
        model.model_validate(data)
    for finding in data['findings']:
        finding['assertions'][0]['target'] = 'obs_file'
    assert model.model_validate(data).findings


def test_unobserved_json_format_is_rejected_before_architecture_goal_admission(tmp_path):
    (tmp_path / 'package.json').write_bytes(b'{\r\n  "workspaces": [\r\n    "server",\r\n    "client"\r\n  ]\r\n}\r\n')
    original_question = 'tell me the structure and which modules connect to whom'

    def predicate(target, expected):
        return {'source': 'repository', 'field': 'content', 'operator': 'contains',
                'target': target, 'expected': expected}

    class Policy:
        planner_calls = 0

        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                self.planner_calls += 1
                if not context.get('planning_feedback'):
                    return model.model_validate({'checks': [{'id': 'architecture', 'description': original_question,
                        'assertions': [predicate('package.json', '"workspaces": [\n    "server",\n    "client"\n]')]}]})
                assert context['original_request'] == original_question
                assert context['planning_feedback'][0]['verdict'] == 'failed'
                return model.model_validate({'checks': [{'id': 'architecture', 'description': original_question,
                    'assertions': [], 'unresolved_reason': 'Inspect the actual workspace and module boundaries',
                    'capabilities': ['repository']}]})
            proof = context['repository_evidence'][0]['observation_id']
            if context.get('architecture_synthesis'):
                return model.model_validate({'findings': [{'area': area, 'summary': 'Workspace declaration in package.json',
                    'assertions': [predicate(proof, 'workspaces')]} for area in ARCHITECTURE_AREAS]})
            return model.model_validate({'decision': {'kind': 'refine', 'reason': 'Use actual repository content',
                'refinement': {'assertions': [predicate(proof, 'workspaces')], 'observation_ids': [proof]}}})

    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate',
        targets=['architecture'], question=original_question))
    policy = Policy()
    verification.run(inv, manager, policy)
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state == 'completed', {k: v for k, v in saved.items() if k in {'failure_kind', 'stop_reason', 'results', 'architecture_findings'}}
    assert policy.planner_calls == 2
    assert len(saved['architecture_plan_attempts']) == 2
    assert saved['architecture_plan_attempts'][0]['feedback']
    assert not saved['architecture_plan_attempts'][1]['feedback']
    assert '\n' not in saved['checks'][0]['assertions'][0]['expected']


@pytest.mark.parametrize('correct_followup_quote', [True, False])
def test_missing_entry_point_gets_one_validated_followup_from_existing_reader(tmp_path, correct_followup_quote):
    (tmp_path / 'README.md').write_text('workspace')
    (tmp_path / 'app.py').write_text('def main(): pass')

    def predicate(target, expected):
        return {'source': 'repository', 'field': 'content', 'operator': 'contains',
                'target': target, 'expected': expected}

    class Policy:
        synthesis_calls = 0

        def request(self, role, context, model, **kwargs):
            if role == 'planner':
                return model.model_validate({'checks': [{'id': 'architecture', 'description': 'Explain architecture',
                    'assertions': [predicate('README.md', 'workspace')]}]})
            assert context['architecture_synthesis']
            self.synthesis_calls += 1
            if self.synthesis_calls == 1:
                assert 'app.py' in context['repository_paths']
                return model.model_validate({'findings': [{'area': area, 'summary': area,
                    'assertions': [] if area == 'entry_points' else [predicate('README.md', 'workspace')],
                    'blocker': 'Read the application entry point' if area == 'entry_points' else ''}
                    for area in ARCHITECTURE_AREAS], 'evidence_requests': ['app.py', '../outside.py']})
            entry = next(row for row in context['repository_evidence'] if row['path'] == 'app.py')
            assert entry['content'] == 'def main(): pass'
            quote = 'def main' if correct_followup_quote or self.synthesis_calls == 3 else 'def missing'
            return model.model_validate({'findings': [{'area': area, 'summary': area,
                'assertions': [predicate(entry['observation_id'], quote) if area == 'entry_points'
                               else predicate('README.md', 'workspace')]} for area in ARCHITECTURE_AREAS]})

    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    policy = Policy()
    verification.run(inv, manager, policy)
    saved = fs_store.read(inv.id, 'verification.json')
    assert inv.state == 'completed', {k: v for k, v in saved.items() if k in {'failure_kind', 'stop_reason', 'results', 'architecture_findings'}} and policy.synthesis_calls == (2 if correct_followup_quote else 3)
    assert len(saved['architecture_evidence_followup']) == 1
    assert saved['architecture_evidence_followup'][0]['path'] == 'app.py'
    assert any(e['purpose'] == 'architecture_evidence_followup' for e in saved['executions'])
