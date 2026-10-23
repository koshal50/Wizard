"""Evidence selection and imports must broaden coverage without fabricating links."""
from pathlib import Path

from wizard_kernel.control.architecture_coverage import boundary, candidates, imports, source_path
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.control import verification
from wizard_kernel.session.architecture import export_architecture
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import fs_store


def test_bounded_selection_covers_layers_before_more_files_in_one_directory():
    files = [f'client/src/components/Widget{i}.tsx' for i in range(100)] + [
        'client/src/main.tsx', 'server/src/routes/auth.ts', 'server/src/services/login.ts',
        'server/src/repositories/pg.repository.js', 'server/src/db/index.js',
        'server/src/jobs/mail.ts', 'shared/types.ts']
    first = candidates(files)[:12]
    assert {boundary(p)[0] for p in first} == {boundary(p)[0] for p in files}
    for path in ['output/result.py', 'node_modules/lib/index.js', 'src/x.test.ts', 'src/x.d.ts',
                 'src/__tests__/x.ts', 'src/.cache/result.js', 'src/generated/client.ts', 'public/icon.svg']:
        assert not source_path(path)
    assert not set(first) & set(candidates(files, first))


def test_static_import_resolution_uses_real_paths_and_preserves_line_numbers():
    paths = {'app/main.tsx', 'app/view.tsx', 'app/data/index.ts', 'app/shared.ts', 'app/config.json'}
    content = '''// require('./view') is a comment
const misleading = "require('./view')";
/* import './view'; */
import {
  View
} from './view';
const db = require('./data');
export { shared } from './shared.js';
import './config.json';
import thing from '@unknown/alias';
import missing from './missing';
const dynamic = import(variable);
'''
    assert imports('app/main.tsx', content, paths) == [
        ('app/config.json', 9, './config.json'), ('app/data/index.ts', 7, './data'),
        ('app/shared.ts', 8, './shared.js'), ('app/view.tsx', 4, './view')]
    assert imports('app/main.tsx', '// only same-directory membership', paths) == []
    assert imports('pkg/main.py', 'from .data import save\nimport pkg.worker\n',
                   {'pkg/data.py', 'pkg/worker.py'}) == [
                       ('pkg/data.py', 1, 'pkg/data'), ('pkg/worker.py', 2, 'pkg.worker')]


def test_existing_investigation_collects_source_and_exports_grouped_evidence(tmp_path):
    (tmp_path / 'README.md').write_text('application')
    files = {'client/src/main.js': "import './pages/home.js';\n",
             'client/src/pages/home.js': "import '../api/client.js';\n",
             'client/src/api/client.js': "export const client = '/api/tasks';\n",
             'server/src/app.js': "const tasks = require('./routes/tasks');\n",
             'server/src/routes/tasks.js': "const service = require('../services/tasks');\n",
             'server/src/services/tasks.js': "const db = require('../db');\n",
             'server/src/db/index.js': "module.exports = {};\n"}
    for path, content in files.items():
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)

    class Policy:
        def request(self, role, context, model, **kwargs):
            predicate = {'source': 'repository', 'field': 'content', 'operator': 'contains',
                         'target': 'README.md', 'expected': 'application'}
            if role == 'planner':
                return model.model_validate({'checks': [{'id': 'architecture', 'description': 'Explain architecture',
                    'assertions': [predicate]}]})
            assert set(files) <= {r['path'] for r in context['repository_evidence']}
            from wizard_kernel.contracts.verification import ARCHITECTURE_AREAS
            refs = {r['path']:r['observation_id'] for r in context['repository_evidence']}
            subsystems = [{'id':name, 'label':name.title()+' application', 'type':'application',
                'description':'Observed application implementation', 'file_paths':[p for p in files if p.startswith(name+'/')],
                'observation_ids':[refs[p] for p in files if p.startswith(name+'/')]} for name in ['client','server']]
            return model.model_validate({'subsystems':subsystems, 'findings': [{'area': area, 'summary': 'Application',
                'assertions': [predicate]} for area in ARCHITECTURE_AREAS]})

    manager = InvestigationManager()
    inv = manager.create(InvestigationRequest(repository_path=str(tmp_path), intent='investigate', targets=['architecture']))
    verification.run(inv, manager, Policy())
    assert inv.state == 'completed'
    graph = export_architecture(inv)
    state = fs_store.read(inv.id, 'verification.json')
    assert state['architecture_coverage']['uninspected_files'] == []
    assert sum(n['level']=='subsystem' for n in graph['nodes']) == 2
    assert len(graph['relationships']) == 5
    assert all(e['classification'] == 'observed' for e in graph['relationships'])
    node_by_id = {n['id']: n for n in graph['nodes']}
    assert all(n['parent_id'] is not None for n in graph['nodes'] if n['level']=='file')
    proofs = {e['id']: e for e in graph['evidence']}
    for edge in graph['relationships']:
        for ref in edge['evidence_ids']:
            proof = proofs[ref]
            assert proof['line_start'] == 1 and proof['path'] in files
    assert export_architecture(inv) == graph  # deterministic IDs and ordering


def test_sampling_does_not_merge_routes_with_middleware_or_adapters_with_schema():
    files = [f'server/src/middleware/log{i}.js' for i in range(100)] + [
        'server/src/routes/auth.js', 'server/src/db/index.js', 'server/src/repositories/pg.repository.js']
    first = candidates(files)[:4]
    assert 'server/src/routes/auth.js' in first
    assert 'server/src/repositories/pg.repository.js' in first
    assert 'server/src/db/index.js' in first


def test_module_identity_does_not_depend_on_generated_display_names():
    from wizard_kernel.control.architecture_coverage import enrich_graph
    observations = [{'id': 'obs_module', 'payload': {'data': {'path': 'src/app.js', 'content': 'export const app = 1;'}}}]
    proof = {'id': 'obs_module', 'path': 'src/app.js', 'classification': 'observed', 'description': 'Read module'}
    def export(label):
        node = {'id': 'generated_' + label, 'label': label, 'type': 'module', 'path': 'src/app.js',
                'description': '', 'evidence_ids': ['obs_module']}
        return enrich_graph([node], [], [dict(proof)], observations, {}, ['src/app.js'])[0][0]['id']
    assert export('Application') == export('Entrypoint')


def test_balanced_excerpts_retain_startup_after_long_headers():
    from types import SimpleNamespace
    from wizard_kernel.control.architecture_coverage import balanced_evidence
    content = '// project header\n' * 200 + 'server.listen(config.port);\n'
    rows = balanced_evidence([SimpleNamespace(id='obs', success=True, source_tool='read_file',
         payload={'data': {'path': 'server.js', 'content': content}})])
    assert 'server.listen(config.port)' in rows[0]['content']
    assert rows[0]['excerpt_truncated']


def test_discovery_prefers_manifests_and_package_entries_over_example_readmes():
    from wizard_kernel.control.architecture_coverage import discovery_paths
    paths = [f'examples/{i}/README.md' for i in range(50)] + ['pyproject.toml','engine/pyproject.toml','planner/package.json','package-lock.json','README_backup.md']
    assert discovery_paths(paths)[:3] == ['pyproject.toml','engine/pyproject.toml','planner/package.json']
    assert 'README_backup.md' not in discovery_paths(paths)
    selected = candidates(['backend/__init__.py','backend/app.py'] + [f'example/src/part{i}/file.js' for i in range(100)])[:2]
    assert selected == ['backend/app.py','example/src/part0/file.js']
    assert imports('cli/main.py','from kernel.api import app',{'engine/src/kernel/api.py','engine/pyproject.toml'}) == [('engine/src/kernel/api.py',1,'kernel/api')]


def test_context_packing_retains_file_identity_and_exposes_excerpt_limits():
    import json
    from wizard_kernel.control.architecture_coverage import bounded_architecture_context
    original={'architecture_synthesis':True,'repository_evidence':[{'observation_id':str(i),'path':f'pkg{i}/app.py','content':'literal source line\n'*100} for i in range(40)],'repository_paths':[f'pkg{i}/app.py' for i in range(300)]}
    packed=bounded_architecture_context(original,{},'architecture',35000)
    assert len(packed['repository_evidence'])==40
    assert [r['path'] for r in packed['repository_evidence']]==[r['path'] for r in original['repository_evidence']]
    assert packed['context_limits']['shortened_excerpts']>0
    assert len(json.dumps([{'role':'system','content':'architecture'},{'role':'user','content':json.dumps(packed,ensure_ascii=False)}]))+2 <= 35000
    assert len(original['repository_evidence'][0]['content'])>len(packed['repository_evidence'][0]['content'])
