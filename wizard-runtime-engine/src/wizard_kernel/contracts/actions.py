"""One canonical action identity shared by scheduling and execution validation."""
import hashlib
import json
import posixpath
from urllib.parse import urlsplit, urlunsplit


def normalize(tool, parameters):
    params = dict(parameters)
    for key in ('path', 'cwd', 'glob'):
        if isinstance(params.get(key), str):
            params[key] = posixpath.normpath(params[key].replace('\\', '/'))
    if tool == 'read_file':
        params.pop('max_bytes', None)
    if tool in {'read_process', 'execute_command'}:
        params.pop('timeout_sec', None)
    if tool == 'http_request':
        params['method'] = str(params.get('method', 'GET')).upper()
    if isinstance(params.get('url'), str):
        url = urlsplit(params['url'])
        params['url'] = urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path or '/', url.query, ''))
    return params


def fingerprint(tool, params):
    canonical = json.dumps([tool, normalize(tool, params)], sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def safe_parameters(params):
    return {key: ('[REDACTED]' if any(s in key.lower() for s in ('password', 'secret', 'token', 'credential')) else value)
            for key, value in params.items()}


def failure_reason(payload):
    """Preserve the executor's actionable error, including command stderr."""
    data = payload.get('data') or {}
    return (payload.get('detail') or payload.get('error') or payload.get('stderr')
            or data.get('stderr_so_far') or payload.get('stdout')
            or (f"Command exited with code {payload['exit_code']}" if payload.get('exit_code') is not None else 'Action failed'))
