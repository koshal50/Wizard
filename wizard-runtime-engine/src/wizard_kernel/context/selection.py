"""Deterministic selection of the exact payload sent to a model."""
from copy import deepcopy
import json


def request_size(context, system, schema):
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
    return len(json.dumps(messages)) + len(json.dumps(schema))


def select(context, system, schema, limit):
    """Remove optional history, never requirements, tool contracts or current refs.

    The last result and current resource state are protected. If those alone
    exceed the limit, the caller must report a context-budget failure.
    """
    selected = deepcopy(context)
    before = request_size(selected, system, schema)
    omitted = []
    candidates = [("knowledge", 0), ("recent_observations", 1), ("workflow", 0)]
    candidates += [("discovery.documents", 0), ("discovery.key_files", 0),
                   ("evidence", 1)]
    for path, keep in candidates:
        parent = selected
        parts = path.split(".")
        for part in parts[:-1]:
            parent = parent.get(part, {}) if isinstance(parent, dict) else {}
        items = parent.get(parts[-1]) if isinstance(parent, dict) else None
        while isinstance(items, list) and len(items) > keep and request_size(selected, system, schema) > limit:
            items.pop(0)
            omitted.append(path)
    return selected, {"before_chars": before, "after_chars": request_size(selected, system, schema),
                      "omitted_sections": {key: omitted.count(key) for key in sorted(set(omitted))}}
