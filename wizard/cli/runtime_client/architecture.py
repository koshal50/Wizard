"""Consent-gated upload through the existing account service and credential."""
from uuid import UUID

import httpx

from backend.architecture import ArchitectureGraph
from wizard.cli.account_login import account_origin
from wizard.cli.runtime_client.account import account_headers
from wizard.cli.runtime_client.client import base_url


def prepare(inv_id):
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get(f"{base_url()}/{inv_id}/architecture")
        response.raise_for_status()
        graph = ArchitectureGraph.model_validate(response.json())
    if not graph.nodes:
        raise ValueError("No architecture nodes were supported by local evidence.")
    return graph.model_dump()


def upload(graph, *, consent=False):
    if consent is not True:
        raise ValueError("Explicit upload consent is required.")
    graph = ArchitectureGraph.model_validate(graph)
    if len(graph.model_dump_json().encode("utf-8")) > 2_000_000:
        raise ValueError("Architecture payload exceeds the 2 MB upload limit. Local results are preserved.")
    origin = account_origin()
    headers = account_headers()
    if not headers:
        raise ValueError("Sign in using the existing /login flow before uploading.")
    # Redirects stay disabled so credentials cannot be forwarded to another origin.
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.post(origin + "/api/investigations", json=graph.model_dump(), headers=headers)
        if response.status_code != 201:
            if response.status_code == 401:
                raise ValueError("Authentication expired. Use /login; local results are preserved.")
            raise ValueError(f"Architecture was not saved (HTTP {response.status_code}). Local results are preserved.")
        public_id = str(UUID(response.json()["investigation_id"]))
    return ("Architecture investigation saved successfully.\n\n"
            f"Nodes: {len(graph.nodes)}\nRelationships: {len(graph.relationships)}\n\n"
            f"[Open interactive architecture diagram]({origin}/investigations/{public_id})")
