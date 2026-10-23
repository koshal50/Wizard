from copy import deepcopy

import pytest
from pydantic import ValidationError

from backend.architecture import ArchitectureGraph


def graph():
    return {"schema_version": 1, "title": "Local application", "repository_name": "sample-project", "status": "completed",
            "nodes": [{"id": "api", "label": "API", "type": "service", "path": "server/app.py", "evidence_ids": ["proof"]},
                      {"id": "db", "label": "Database", "type": "database", "evidence_ids": ["proof"]}],
            "relationships": [{"id": "uses", "source": "api", "target": "db", "type": "USES", "classification": "inferred", "evidence_ids": ["proof"]}],
            "evidence": [{"id": "proof", "description": "Database adapter referenced by the API.", "path": "server/app.py",
                          "line_start": 4, "line_end": 6, "classification": "observed"}]}


def test_valid_graph_round_trip():
    saved = ArchitectureGraph.model_validate(graph())
    assert ArchitectureGraph.model_validate_json(saved.model_dump_json()) == saved


@pytest.mark.parametrize("mutation", [
    lambda g: g["nodes"].append(deepcopy(g["nodes"][0])),
    lambda g: g["relationships"].append(deepcopy(g["relationships"][0])),
    lambda g: g["evidence"].append(deepcopy(g["evidence"][0])),
    lambda g: g["relationships"][0].update(target="missing"),
    lambda g: g["nodes"][0].update(evidence_ids=["missing"]),
    lambda g: g["evidence"][0].update(line_end=1),
    lambda g: g.update(schema_version=2),
    lambda g: g.update(owner_id="attacker"),
    lambda g: g["relationships"][0].update(classification="observed", evidence_ids=[]),
    lambda g: g["nodes"][0].update(description="x" * 2001),
    lambda g: g["nodes"][0].update(path="../secret"),
    lambda g: g["nodes"][0].update(path="C:/users/local/repo"),
    lambda g: g["evidence"][0].update(path="/home/user/repo"),
    lambda g: g["nodes"][0].update(path="a\\secret"),
])
def test_rejects_invalid_graph(mutation):
    data = graph()
    mutation(data)
    with pytest.raises(ValidationError):
        ArchitectureGraph.model_validate(data)


def grouped_graph():
    data = graph()
    data['groups'] = [dict(id='application', label='Application', evidence_ids=['proof'])]
    for node in data['nodes']:
        node['group_id'] = 'application'
    data['relationships'][0]['label'] = 'queries'
    data['limitations'] = ['Dynamic imports are unresolved.']
    return data


def test_groups_round_trip_and_old_documents_remain_valid():
    assert ArchitectureGraph.model_validate(grouped_graph()).groups[0].label == 'Application'
    assert ArchitectureGraph.model_validate(graph()).groups == []


@pytest.mark.parametrize('mutation', [
    lambda g: g['nodes'][0].update(group_id='missing'),
    lambda g: g['groups'].append(deepcopy(g['groups'][0])),
    lambda g: g['groups'][0].update(evidence_ids=['missing']),
    lambda g: g['groups'][0].update(id='api'),
    lambda g: g['relationships'].append(dict(g['relationships'][0], id='duplicate_semantic_edge')),
])
def test_invalid_grouped_documents_are_rejected(mutation):
    data = grouped_graph()
    mutation(data)
    with pytest.raises(ValidationError):
        ArchitectureGraph.model_validate(data)


def hierarchy_graph():
    data=graph()
    data['nodes'][0].update(level='subsystem')
    data['nodes'][1].update(level='module',parent_id='api')
    return data


def test_hierarchy_roundtrip_preserves_action_labels_and_old_documents():
    data=hierarchy_graph()
    data['relationships'][0]['label']='stores results'
    parsed=ArchitectureGraph.model_validate(data)
    assert parsed.nodes[1].parent_id=='api'
    assert parsed.relationships[0].label=='stores results'
    assert ArchitectureGraph.model_validate(graph()).nodes[0].parent_id is None


@pytest.mark.parametrize('mutation',[
    lambda g:g['nodes'][1].update(parent_id='unknown'),
    lambda g:g['nodes'][1].update(parent_id='db'),
    lambda g:g['nodes'][0].update(parent_id='db'),
    lambda g:g['nodes'][0].update(level='file'),
    lambda g:g.update(coverage={'candidate_files':1,'examined_files':['../secret'],'uninspected_file_count':0,'discovery_note':'Bounded'}),
    lambda g:g.update(coverage={'candidate_files':0,'examined_files':['src/app.js'],'uninspected_file_count':0,'discovery_note':'Bounded'}),
])
def test_invalid_hierarchy_and_coverage_rejected(mutation):
    data=hierarchy_graph();mutation(data)
    with pytest.raises(ValidationError):ArchitectureGraph.model_validate(data)
