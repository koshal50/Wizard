"""Bounded architecture coverage over the existing manifest and file observations.

This module never scans or reads a repository. All reads remain runtime tools.
Only literal local module dependencies are classified as observed imports.
"""
import ast
import hashlib
import posixpath
import re
from collections import defaultdict
from pathlib import PurePosixPath

SOURCE = {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.py', '.go', '.rs', '.java', '.cs', '.rb', '.php', '.sql'}
SKIP = {'node_modules', 'vendor', 'dist', 'build', 'target', 'output', 'coverage', 'generated',
        '__pycache__', '__tests__', 'tests', 'test', 'fixtures', 'assets', 'public'}


def stable(prefix, value):
    return prefix + '_' + hashlib.sha256(value.encode()).hexdigest()[:16]


def source_path(path):
    p = PurePosixPath(path.replace('\\', '/'))
    return (p.suffix.lower() in SOURCE and not any(s.startswith('.') or s.lower() in SKIP for s in p.parts)
            and not re.search(r'(\.test\.|\.spec\.|\.min\.|\.d\.ts$|\.generated\.)', p.name))


def boundary(path):
    """Name real package/layer boundaries; create no absent categories."""
    parts = PurePosixPath(path).parts
    if re.search(r'(?:\.config\.[^.]+$|^(?:Dockerfile|docker-compose|compose)(?:[.-]|$))', parts[-1], re.I):
        return 'infrastructure', 'Build and configuration'
    lower = [p.lower() for p in parts[:-1]]
    root = parts[0] if len(parts) > 1 and parts[0] not in {'src', 'lib', 'app'} else ''
    layers = {'pages': 'Interface', 'components': 'Interface', 'context': 'Client logic', 'api': 'Client logic',
              'routes': 'HTTP', 'controllers': 'HTTP', 'services': 'Services',
              'middleware': 'HTTP', 'db': 'Data', 'repositories': 'Data', 'models': 'Data',
              'schemas': 'Contracts', 'types': 'Contracts', 'shared': 'Shared', 'utils': 'Utilities',
              'jobs': 'Background jobs', 'workers': 'Background jobs', 'integrations': 'Integrations',
              'config': 'Configuration'}
    for index, segment in enumerate(lower):
        if segment in layers:
            prefix = '/'.join(parts[:index])
            label = (root.replace('-', ' ').title() + ' / ' if root and index else '') + layers[segment]
            # Data adapters and schema live in one actual package boundary.
            key = prefix + '/' + layers[segment]
            return key, label
    if source_path(path):
        prefix = '/'.join(parts[:-1]) or 'root'
        return prefix, (root.replace('-', ' ').title() + ' / ' if root else '') + 'Application'
    return 'infrastructure', 'Build and configuration'


def candidates(paths, read_paths=()):
    buckets = defaultdict(list)
    read = set(read_paths)
    for path in sorted({p.replace('\\', '/') for p in paths}):
        if source_path(path) and path not in read:
            parts = PurePosixPath(path).parts[:-1]
            # Sampling keeps routes/middleware and pages/components separate
            # even when presentation combines them into one logical boundary.
            depth = parts.index('src') + 3 if 'src' in parts else 3
            bucket = '/'.join(parts[:depth]) or 'root'
            buckets[bucket].append(path)
    def priority(path):
        name = PurePosixPath(path).stem.lower()
        return (3 if name in {'migrate', 'migration', 'memory.repository'} else 2 if name == '__init__' else 0 if name in {'main', 'index', 'app', 'server', 'mod'} else 1,
                len(PurePosixPath(path).parts), path)
    for rows in buckets.values():
        rows.sort(key=priority)
    # Fairness across packages first, then their modules. A nested example or
    # a large UI folder must not consume all source reads before another app.
    packages = defaultdict(list)
    for key in sorted(buckets):
        packages[key.split('/')[0]].append(key)
    result = []
    while packages:
        for package in sorted(list(packages)):
            key = packages[package].pop(0)
            result.append(buckets[key].pop(0))
            if buckets[key]:
                packages[package].append(key)
            if not packages[package]:
                del packages[package]
    return result


def discovery_paths(paths, limit=8):
    metadata = {'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'pom.xml',
                'setup.py', 'composer.json', 'Gemfile'}
    useful = [p for p in paths if not re.search(r'(?:lock|backup|\.env)', p, re.I)]
    manifests = [p for p in useful if PurePosixPath(p.replace('\\', '/')).name in metadata]
    manifests.sort(key=lambda p: (len(PurePosixPath(p.replace('\\', '/')).parts), p))
    others = sorted((p for p in useful if p not in manifests),
                    key=lambda p: (len(PurePosixPath(p.replace('\\', '/')).parts), p))
    return (manifests + others)[:limit]


def imports(path, content, known_paths):
    """Resolve literal JS/TS relative imports and Python imports against manifest only.

    No alias guessing, dynamic expression evaluation, or package execution.
    Return target, source line, reference. Comments/strings must not become edges.
    """
    known = set(known_paths)
    refs = []
    if PurePosixPath(path).suffix in {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'}:
        # Preserve line offsets while excluding comments. Match only import/export
        # declarations or literal require()/import() calls, never arbitrary paths.
        pattern = r'''(?://[^\n]*|/\*[\s\S]*?\*/|(?:\b(?:import|export)\s+(?:[\w*$\s{},]+?\s+from\s*)?["'](?P<decl>[^"']+)["']|\b(?:require|import)\s*\(\s*["'](?P<call>[^"']+)["']\s*\))|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)'''
        for match in re.finditer(pattern, content):
            ref = match.group('decl') or match.group('call')
            if not ref:
                continue
            if not ref.startswith('.'):
                continue
            base = posixpath.normpath(posixpath.join(posixpath.dirname(path), ref))
            options = [base] + [base + ext for ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs', '.json')]
            if base.endswith('.js'):
                options += [base[:-3] + ext for ext in ('.ts', '.tsx')]
            options += [base + '/index' + ext for ext in ('.js', '.jsx', '.ts', '.tsx')]
            target = next((p for p in options if p in known), None)
            if target and target != path:
                refs.append((target, content[:match.start()].count('\n') + 1, ref))
    elif path.endswith('.py'):
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            return []
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parents = path.split('/')[:-node.level]
                    base = '/'.join(parents + ([node.module.replace('.', '/')] if node.module else []))
                else:
                    base = (node.module or '').replace('.', '/')
                modules = [base] + [base + '/' + a.name for a in node.names]
            for module in modules:
                base = module.replace('.', '/') if isinstance(node, ast.Import) else module
                roots = {'', 'src'}
                roots.update(p.rsplit('/src/', 1)[0] + '/src' for p in known if '/src/' in p)
                roots.update(posixpath.dirname(p) for p in known if PurePosixPath(p).name in {'pyproject.toml', 'setup.py'})
                matches = {posixpath.join(root, item) for root in roots
                           for item in (base + '.py', base + '/__init__.py')
                           if posixpath.join(root, item) in known}
                target = next(iter(matches)) if len(matches) == 1 else None
                if target and target != path:
                    refs.append((target, node.lineno, module))
    return sorted(set(refs))


def balanced_evidence(observations):
    latest = {}
    for o in observations:
        if o.success and o.source_tool == 'read_file':
            latest[(o.payload.get('data') or {}).get('path', '').replace('\\', '/')] = o
    rows = []
    for path, o in sorted(latest.items()):
        if PurePosixPath(path).name.endswith('lock.json') or path.endswith(('.lock', '.env.example')):
            continue
        content = str((o.payload.get('data') or {}).get('content', ''))
        # Equal per-file allowance preserves all discovered layers. Source lines
        # remain literal (no reconstructed snippets used as predicate evidence).
        if len(content) <= 900:
            excerpt = content
        else:
            # Preserve literal, numbered lines across the file: imports alone
            # omit route registrations and calls that occur after long headers.
            lines = content.splitlines()
            selected = list(range(min(5, len(lines))))
            important = re.compile(r'(?:import |require\(|from |fetch\(|axios|/api/|\.(?:use|get|post|put|delete|patch|query|connect|listen|start|serve|register)\(|export |module\.exports|baseURL|BASE_URL|API_URL|DATABASE|postgres|Router\(|"(?:scripts|start|build|workspaces|main)")')
            selected += [i for i, line in enumerate(lines) if re.search(r'\.(?:listen|start|serve|use|get|post|put|patch|delete|query|connect)\(|["\'](?:scripts|start|build|workspaces)["\']', line)]
            selected += [i for i, line in enumerate(lines) if important.search(line)]
            selected += list(range(max(0, len(lines) - 3), len(lines)))
            chunks, used = [], 0
            for i in dict.fromkeys(selected):
                line = lines[i][:180]
                if used + len(line) > 800:
                    continue
                chunks.append(str(i + 1) + ': ' + line)
                used += len(line)
            excerpt = '[Selected literal lines; numeric prefixes are not source content]\n' + '\n'.join(chunks)
        rows.append({'observation_id': o.id, 'path': path, 'content': excerpt,
                     'excerpt_truncated': excerpt != content})
    return rows[:40]

def enrich_graph(nodes, edges, evidence, observations, coverage, manifest_paths):
    """Adapt existing measured results to a grouped map without additional IO."""
    by_path = {}
    by_id = {e['id']: e for e in evidence}
    for obs in observations:
        data = obs.get('payload', {}).get('data') or {}
        path = str(data.get('path', '')).replace('\\', '/')
        if obs['id'] in by_id:
            path = by_id[obs['id']]['path']
            by_path[path] = (obs, data)
    known = {p.replace('\\', '/') for p in manifest_paths} or set(by_path)
    # Every exported file is a real, successful observation in this manifest.
    eligible = {p for p in by_path if p in known and source_path(p)}
    represented = {}
    for n in nodes:
        represented.setdefault(n.get('path'), n)
    for path in sorted(eligible):
        if path in represented:
            continue
        obs, _ = by_path[path]
        layer = boundary(path)[1]
        n = {'id': stable('module', path), 'label': PurePosixPath(path).name,
             'type': 'module', 'path': path, 'description': 'Repository module in ' + layer + '.',
             'evidence_ids': [obs['id']]}
        nodes.append(n)
        represented[path] = n
    # File identities remain stable when the model changes a display label.
    # Distinct external resources supported by one config keep semantic keys.
    mapping, seen = {}, set()
    unique_nodes = []
    for n in nodes:
        key = (n['path'],) if n.get('path') in eligible else (n.get('path', ''), n['type'].casefold(), n['label'].casefold())
        nid = stable('component', '|'.join(key))
        mapping[n['id']] = nid
        if nid in seen:
            continue
        n['id'] = nid
        seen.add(nid)
        unique_nodes.append(n)
    nodes = unique_nodes
    # The path map points to the node objects whose IDs were normalized above.
    for edge in edges:
        edge['source'] = mapping.get(edge['source'], edge['source'])
        edge['target'] = mapping.get(edge['target'], edge['target'])
    for path in sorted(eligible):
        obs, data = by_path[path]
        for target, line, reference in imports(path, str(data.get('content', '')), known):
            if target not in represented or represented[path]['id'] == represented[target]['id']:
                continue
            eid = stable('proof', path + ':' + str(line) + ':' + target)
            evidence.append({'id': eid, 'description': 'Literal module reference to ' + target + '.',
                             'classification': 'observed', 'path': path,
                             'line_start': line + int(data.get('start_line') or 1) - 1,
                             'line_end': line + int(data.get('start_line') or 1) - 1})
            edges.append({'id': stable('import', path + ':' + target),
                          'source': represented[path]['id'], 'target': represented[target]['id'],
                          'type': 'imports', 'label': 'imports', 'classification': 'observed',
                          'description': 'Static local module dependency; runtime execution is not asserted.',
                          'evidence_ids': [eid]})
    # Keep different supported relation kinds; remove semantic duplicates and self loops.
    unique_edges = {}
    for edge in sorted(edges, key=lambda e: e['classification'] != 'observed'):
        key = (edge['source'], edge['target'], edge['type'].casefold())
        if key[0] == key[1] or key[0] not in seen or key[1] not in seen:
            continue
        if key in unique_edges:
            continue
        edge['id'] = stable('relationship', '|'.join(key))
        unique_edges[key] = edge
    groups = {}
    for n in nodes:
        key, label = boundary(n['path'])
        gid = stable('group', key)
        n['group_id'] = gid
        group = groups.setdefault(gid, {'id': gid, 'label': label, 'description': 'Observed repository boundary: ' + label + '.',
                                       'evidence_ids': []})
        group['evidence_ids'] = sorted(set(group['evidence_ids'] + n['evidence_ids']))[:100]
    edges = list(unique_edges.values())
    linked = {e['source'] for e in edges} | {e['target'] for e in edges}
    coverage['graph_quality'] = {'nodes': len(nodes), 'relationships': len(edges), 'groups': len(groups),
        'cross_group_relationships': sum(next(n for n in nodes if n['id'] == e['source'])['group_id'] !=
                                          next(n for n in nodes if n['id'] == e['target'])['group_id'] for e in edges),
        'isolated_nodes': len(seen - linked)}
    limitations = ['Static import resolution covers literal relative JavaScript/TypeScript and Python module references. '
                  'Dynamic imports, aliases, runtime calls and other languages may require inferred evidence.']
    if coverage.get('uninspected_files'):
        limitations.append(str(len(coverage['uninspected_files'])) + ' source files were not read within the investigation budget; this map is bounded.')
    for label in coverage.get('unrepresented_boundaries', []):
        limitations.append('No source file inspected in discovered boundary: ' + label + '.')
    return nodes, edges, list(groups.values()), limitations

def bounded_architecture_context(context, schema, instruction, limit):
    """Fit excerpts to the existing transport limit without dropping file identities."""
    import copy
    import json
    packet = copy.deepcopy(context)
    limits = {'shortened_excerpts': 0, 'unlisted_discovery_paths': 0}
    def size():
        return len(json.dumps([{'role':'system','content':instruction},
                               {'role':'user','content':json.dumps(packet,ensure_ascii=False)}])) + len(json.dumps(schema))
    shortened = set()
    while size() > limit - 500:
        changed = False
        for row in packet.get('repository_evidence', []):
            content = row.get('content', '')
            if len(content) <= 300:
                continue
            cut = max(300, int(len(content) * .8))
            excerpt = content[:cut]
            if '\n' in excerpt:
                excerpt = excerpt.rsplit('\n', 1)[0] or excerpt
            row['content'], row['excerpt_truncated'] = excerpt, True
            shortened.add(row['observation_id'])
            changed = True
        if not changed and len(packet.get('repository_paths', [])) > 8:
            paths = packet['repository_paths']
            cut = max(8, len(paths) // 2)
            limits['unlisted_discovery_paths'] += len(paths) - cut
            packet['repository_paths'] = paths[:cut]
            changed = True
        limits['shortened_excerpts'] = len(shortened)
        packet['context_limits'] = limits
        if not changed:
            break  # The established transport rejects any still-oversized request.
    return packet
