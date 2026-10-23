"""Semantic hierarchy adapter over the existing synthesis and observed file graph.

No repository IO or new investigation. Detailed edges survive; the viewer projects
these saved edges at the requested hierarchy level without fabricating connections.
"""
from collections import Counter, defaultdict

from backend.architecture import Located
from wizard_kernel.control.architecture_coverage import source_path, stable


def measured_coverage(manifest_paths, observations, evidence, assigned=()):
    known = {p.replace('\\', '/') for p in manifest_paths}
    sources = {p for p in known if source_path(p)}
    proof_paths = {e['id']: e['path'] for e in evidence if e.get('path')}
    read, partial, unmeasured = set(), set(), set()
    for obs in observations:
        path = proof_paths.get(obs['id'])
        if not path:
            continue
        read.add(path)
        data = obs.get('payload', {}).get('data') or {}
        if 'truncated' not in data:
            unmeasured.add(path)
        if data.get('truncated'):
            partial.add(path)
    def area(path):
        return (path.rsplit('/', 1)[0] if '/' in path else '[root]')[:240]
    missed = sources - read
    missed_areas = sorted({area(p) for p in missed})
    return {'candidate_files': len(sources), 'examined_files': sorted(read & sources),
        'context_files': sorted(read - sources), 'examined_areas': sorted({area(p) for p in read})[:500],
        'uninspected_file_count': len(missed), 'uninspected_areas': missed_areas[:500],
        'unlisted_area_count': max(0, len(missed_areas) - 500),
        'unassigned_files': sorted((read & sources) - set(assigned)), 'partial_files': sorted(partial),
        'unmeasured_read_count': len(unmeasured),
        'discovery_note': 'The existing manifest excludes dependency/build/cache directories and stops at depth 8. '
                          'Read and model budgets bound inspection; unread files are not proof of absent architecture.'}


def abstract_graph(nodes, edges, evidence, diagram, observations, manifest_paths, sanitize):
    by_proof = {e['id']: e for e in evidence}
    observed = defaultdict(list)
    for obs in observations:
        if obs['id'] in by_proof:
            observed[by_proof[obs['id']]['path']].append(obs['id'])
    known = {p.replace('\\', '/') for p in manifest_paths} or set(observed)
    raw = diagram.get('subsystems', [])
    counts = Counter(s['id'] for s in raw)
    roots, raw_root, owners, warnings = [], {}, defaultdict(list), []
    for subsystem in raw:
        if counts[subsystem['id']] != 1:
            warnings.append('Ambiguous subsystem identifiers were excluded from semantic hierarchy.')
            continue
        paths = []
        for path in subsystem['file_paths']:
            try:
                path = path.replace('\\', '/')
                Located(path=path)
            except ValueError:
                continue
            if path in observed and path in known:
                paths.append(path)
        refs = [i for i in subsystem['observation_ids'] if i in by_proof]
        if not paths or not refs or not any(by_proof[i].get('path') in paths for i in refs):
            warnings.append('An unsupported subsystem was excluded; its file evidence remains inspectable.')
            continue
        paths = sorted(set(paths))
        nid = stable('subsystem', paths[0] + ':' + subsystem['type'])
        if any(n['id'] == nid for n in roots):
            warnings.append('Duplicate subsystem anchors were excluded.')
            continue
        refs = sorted({i for path in paths for i in observed[path]})
        node = {'id': nid, 'label': sanitize(subsystem['label'])[:240], 'type': subsystem['type'],
                'description': sanitize(subsystem['description']), 'evidence_ids': refs,
                'level': 'subsystem', 'parent_id': None}
        roots.append(node)
        raw_root[subsystem['id']] = nid
        for path in paths:
            owners[path].append(nid)
    owner = {p: ids[0] for p, ids in owners.items() if len(ids) == 1}
    if any(len(ids) > 1 for ids in owners.values()):
        warnings.append('Files assigned to conflicting subsystems remain unassigned evidence rather than invented ownership.')
    # Complete membership from actual imports, never folder similarity. A file
    # reachable from multiple explicit boundaries stays unassigned/shared evidence.
    paths_by_node = {n['id']: n.get('path') for n in nodes}
    imports = defaultdict(set)
    for edge in edges:
        if edge['classification'] == 'observed' and edge['type'] == 'imports':
            imports[paths_by_node.get(edge['source'])].add(paths_by_node.get(edge['target']))
    reachable = defaultdict(set)
    for root in sorted(set(owner.values())):
        pending = [p for p in owner if owner[p] == root]
        visited = set(pending)
        for path in pending:
            for target in imports[path]:
                if target not in observed or target in visited or target in owners:
                    continue
                visited.add(target)
                reachable[target].add(root)
                pending.append(target)
    inherited = {p: next(iter(ids)) for p, ids in reachable.items() if len(ids) == 1}
    owner.update(inherited)
    if inherited:
        warnings.append(f'{len(inherited)} file memberships follow unique observed imports from a synthesized boundary; '
                        'membership is an architectural inference, not proof of runtime isolation.')
    # Keep semantic components as expandable modules. The measured file graph
    # supplies Level 3, not dozens of additional overview boxes.
    semantic_paths = {c['path'].replace('\\', '/').rstrip('/'): c for c in diagram.get('components', [])}
    modules, module_path, node_map = [], {}, {}
    for node in nodes:
        path = node.get('path')
        component = semantic_paths.get(path)
        if not component or path not in owner:
            continue
        proposed = raw_root.get(component.get('subsystem_id'))
        parent = proposed if proposed == owner[path] else owner[path]
        mid = stable('module', path)
        if mid in {n['id'] for n in modules}:
            continue
        module = {k: v for k, v in node.items() if k != 'group_id'}
        module.update(id=mid, level='module', parent_id=parent)
        modules.append(module)
        module_path[path] = mid
    files = []
    for path, refs in sorted(observed.items()):
        if path not in known or not (source_path(path) or path in owner):
            continue
        parent = module_path.get(path)
        if parent is None and path in owner:
            supporting = [m for m in modules if m['parent_id'] == owner[path] and set(m['evidence_ids']) & set(refs)]
            parent = sorted(supporting, key=lambda m: m['id'])[0]['id'] if supporting else owner[path]
        files.append({'id': stable('file', path), 'label': path.rsplit('/', 1)[-1], 'type': 'file',
                      'path': path, 'description': 'Source evidence implementing the selected architecture; inspect its supported relationships.',
                      'evidence_ids': refs, 'parent_id': parent, 'level': 'file'})
    file_path = {n['path']: n['id'] for n in files}
    for node in nodes:
        path = node.get('path')
        node_map[node['id']] = (module_path.get(path), file_path.get(path))
    mapped = {}
    for edge in edges:
        a = node_map.get(edge['source'], (None, None))
        b = node_map.get(edge['target'], (None, None))
        index = 1 if edge['classification'] == 'observed' and edge['type'] == 'imports' else 0
        source, target = a[index] or a[1], b[index] or b[1]
        if not source or not target or source == target:
            continue
        key = source, target, edge['type'].casefold()
        if key in mapped:
            mapped[key]['evidence_ids'] = sorted(set(mapped[key]['evidence_ids'] + edge['evidence_ids']))
            continue
        mapped[key] = {**edge, 'id': stable('relation', '|'.join(key)), 'source': source, 'target': target}
    coverage = measured_coverage(manifest_paths, observations, evidence, owner)
    return roots + modules + files, list(mapped.values()), coverage, list(dict.fromkeys(warnings))
