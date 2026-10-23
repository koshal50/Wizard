"""Semantic boundaries must collapse detail without losing file or edge proof."""
from copy import deepcopy

from backend.architecture import ArchitectureGraph
from wizard_kernel.control.architecture_hierarchy import abstract_graph


def evidence_graph():
    paths = ['client/main.js', 'client/view.js', 'server/app.js', 'server/tasks.js', 'schema.sql', 'client/unrelated.js']
    observations = [{'id': 'obs_' + str(i), 'payload': {'data': {'path': path, 'content': ''}}} for i, path in enumerate(paths)]
    proof = [{'id': o['id'], 'path': o['payload']['data']['path'], 'description': 'Observed file', 'classification': 'observed'} for o in observations]
    nodes = [{'id': 'n' + str(i), 'path': path, 'label': path.rsplit('/', 1)[-1], 'type': 'module',
              'description': '', 'evidence_ids': [proof[i]['id']]} for i, path in enumerate(paths)]
    edges = [{'id': 'e' + str(i), 'source': a, 'target': b, 'type': 'imports', 'classification': 'observed',
              'description': 'Resolved import', 'evidence_ids': ['obs_0']} for i, (a, b) in enumerate([('n0','n1'),('n2','n3')])]
    edges += [{'id': 'request', 'source': 'n0', 'target': 'n2', 'type': 'requests', 'label': 'loads tasks',
               'description': 'API request correspondence', 'classification': 'inferred', 'evidence_ids': ['obs_0','obs_2']}]
    def subsystem(id, label, type, path, ref):
        return {'id': id, 'label': label, 'type': type, 'description': 'Responsibility backed by inspected source.',
                'file_paths': [path], 'observation_ids': [ref]}
    diagram = {'subsystems': [subsystem('client','Task client','application',paths[0],'obs_0'),
                              subsystem('server','Task API','service',paths[2],'obs_2'),
                              subsystem('store','PostgreSQL','database',paths[4],'obs_4')],
               'components': [{'id':'main','path':paths[0],'subsystem_id':'client'}, {'id':'api','path':paths[2],'subsystem_id':'server'}]}
    return nodes, edges, proof, diagram, observations, paths


def test_semantic_hierarchy_keeps_every_file_and_relationship_with_evidence():
    args = evidence_graph()
    nodes, edges, coverage, warnings = abstract_graph(*deepcopy(args), lambda x:x)
    graph = ArchitectureGraph.model_validate({'title':'Architecture','repository_name':'local', 'status':'completed',
        'nodes':nodes,'relationships':edges,'evidence':args[2],'coverage':coverage})
    assert len([n for n in graph.nodes if n.level == 'subsystem']) == 3
    assert len([n for n in graph.nodes if n.level == 'file']) == len(args[-1])
    assert len(graph.relationships) == len(args[1])
    assert next(e for e in graph.relationships if e.type == 'requests').label == 'loads tasks'
    by_path = {n.path:n for n in graph.nodes if n.level == 'file'}
    assert by_path['client/view.js'].parent_id is not None  # actual import propagation
    assert by_path['client/unrelated.js'].parent_id is None  # folder membership is insufficient
    assert coverage['unassigned_files'] == ['client/unrelated.js']
    assert any('architectural inference' in w for w in warnings)
    assert abstract_graph(*deepcopy(args), lambda x:x) == (nodes, edges, coverage, warnings)


def test_shared_import_is_not_silently_owned_by_one_application():
    args=list(evidence_graph())
    args[1].append({'id':'shared','source':'n2','target':'n1','type':'imports','classification':'observed',
                   'description':'Shared import','evidence_ids':['obs_2']})
    nodes, _, coverage, _ = abstract_graph(*args, lambda x:x)
    assert next(n for n in nodes if n['level']=='file' and n['path']=='client/view.js')['parent_id'] is None
    assert 'client/view.js' in coverage['unassigned_files']


def test_unobserved_subsystem_paths_never_appear_as_components():
    args=list(evidence_graph())
    args[3]['subsystems'][0]['file_paths']=['invented/app.js','../secret']
    nodes, _, coverage, warnings=abstract_graph(*args,lambda x:x)
    assert not any(n['level']=='subsystem' and n['label']=='Task client' for n in nodes)
    assert 'client/main.js' in coverage['unassigned_files'] and warnings


def test_existing_reader_reports_partial_reads_without_exceeding_content_limit(tmp_path):
    from wizard_kernel.world.tools import ToolExecutor
    class Sandbox:
        def __init__(self,data):self.data=data
        def read_file(self,path,max_bytes):return self.data[:max_bytes]
    for raw,partial in [(b'1234',False),(b'12345',True)]:
        result=ToolExecutor(Sandbox(raw),str(tmp_path))._tool_read_file('source.py',max_bytes=4)
        assert result['data']['content']=='1234'
        assert result['data']['bytes_read']==4
        assert result['data']['truncated'] is partial
