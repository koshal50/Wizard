"""Runtime proof levels and bounded readiness discovery from observed sources."""
import re
import json
from urllib.parse import urlsplit
from pathlib import Path


def readiness_source_files(observations, root):
    """One bounded import-discovery batch; never invent source filenames."""
    root = Path(root).resolve()
    read_paths = {(o.payload.get('data') or {}).get('path', '').replace('\\', '/')
                  for o in observations if o.success and o.source_tool == 'read_file'}
    candidates = []
    for obs in observations:
        if not obs.success or obs.source_tool != 'read_file':
            continue
        data = obs.payload.get('data') or {}
        path = data.get('path') or ((obs.payload.get('action') or {}).get('params') or {}).get('path')
        if not path:
            continue
        content = data.get('content') or obs.payload.get('content') or ''
        imports = re.findall(r'(?:require\(\s*|\bfrom\s+)[\"\'](\.[^\"\']+)[\"\']', content)
        for imported in imports:
            base = (root / str(path).replace('\\', '/')).parent / imported
            for candidate in (base, Path(str(base) + '.js'), Path(str(base) + '.ts'), base / 'index.js'):
                candidate = candidate.resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    continue
                relative = candidate.relative_to(root).as_posix()
                if relative not in read_paths and relative not in candidates:
                    candidates.append(relative)
                break
    return candidates[:4]


def observed_get_routes(observations):
    candidates = []
    for obs in observations:
        if not obs.success or obs.source_tool != 'read_file':
            continue
        content = (obs.payload.get('data') or {}).get('content') or obs.payload.get('content') or ''
        candidates.extend(re.findall(r'\bapp\.get\(\s*[\"\'](/[^\"\']*)[\"\']', content))
    return [p for p in candidates if not re.search(r'[:*{}?]', p)]


def listening_url(payload):
    data = payload.get('data') or {}
    text = str(payload.get('stdout') or data.get('stdout_so_far') or '')
    match = re.search(r'\b(?:listening|serving|running|ready)\b[^\n]{0,100}?(https?://[^\s)]+)', text, re.I)
    return match.group(1).rstrip('.,;') if match else None


def readiness_target(observations, url):
    """Only literal GET routes actually read from the repository are eligible.

    Mounted routers and dynamic routes require a Planner decision; do not guess.
    """
    candidates = observed_get_routes(observations)
    if not candidates:
        return None
    path = next((p for p in candidates if re.search(r'(?:healthz?|healthcheck|readyz?|readiness)(?:/|$)', p, re.I)), candidates[0])
    parsed = urlsplit(url)
    if parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        return None
    return f'{parsed.scheme}://{parsed.netloc}{path}'


def runtime_levels(observations, goal_id=None):
    selected = [o for o in observations if goal_id is None or o.goal_id == goal_id]
    ready_ids = {o.id for id in {o.goal_id for o in selected if o.goal_id}
                 for o in readiness_observations(observations, id)}
    return {
        'Process started': [o.id for o in selected if o.success and o.source_tool == 'start_process'],
        'Process liveness': [o.id for o in selected if o.success and o.source_tool == 'read_process'
                             and (o.payload.get('data') or {}).get('is_running')],
        'Server startup (listening message)': [o.id for o in selected if o.success and o.source_tool == 'read_process'
                                               and listening_url(o.payload)],
        'HTTP readiness': [o.id for o in selected if o.success and ('http_readiness' in o.evidence_categories or o.id in ready_ids)],
    }


def readiness_failure(payload):
    data = payload.get('data') or {}
    status = data.get('status_code')
    if not isinstance(status, int) or not 200 <= status < 300:
        return f'Readiness GET returned HTTP {status}; expected 2xx for the observed route'
    # A health response explicitly reporting unhealthy must not pass merely
    # because its transport status is 200. Unknown response schemas stay opaque.
    if re.search(r'health|ready|readiness', urlsplit(data.get('url', '')).path, re.I):
        try:
            body = json.loads(data.get('body_preview', ''))
        except (ValueError, TypeError):
            body = None
        if isinstance(body, dict) and (body.get('ready') is False or body.get('healthy') is False
                or str(body.get('status', '')).lower() in {'unhealthy', 'not_ready', 'error', 'failed', 'down'}):
            return 'Readiness endpoint explicitly reported an unhealthy/not-ready state'
    return None


def readiness_observations(observations, goal_id):
    """A Planner-issued GET can prove the same criterion without re-execution."""
    targets = {readiness_target(observations, url) for o in observations
               if o.goal_id == goal_id and o.success and o.source_tool == 'read_process'
               and (o.payload.get('data') or {}).get('is_running')
               and (url := listening_url(o.payload))}
    results = []
    for obs in observations:
        if obs.goal_id != goal_id or not obs.success or obs.source_tool != 'http_request':
            continue
        data = obs.payload.get('data') or {}
        params = (obs.payload.get('action') or {}).get('params') or {}
        status = data.get('status_code')
        if (data.get('url', params.get('url')) in targets and params.get('method', data.get('method', 'GET')) == 'GET'
                and isinstance(status, int) and 200 <= status < 300 and not readiness_failure(obs.payload)):
            results.append(obs)
    return results
