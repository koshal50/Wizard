"""Architecture consent for the existing one-shot investigate command."""
from rich.prompt import Confirm

from wizard.cli.parser.intent_parser import parse_intent
from wizard.cli.tui.session import sanitize_terminal


def offer_upload(session, console, *, confirm=None):
    if session.family != 'investigate' or session.status not in {'completed', 'incomplete', 'failed'}:
        return None
    targets = parse_intent(session.intent_text, 'investigate', menu_target=session.target or None).targets
    if 'architecture' not in targets or not session.investigation_id:
        return None
    from wizard.cli.account_login import account_origin
    from wizard.cli.runtime_client.architecture import prepare, upload

    try:
        graph = prepare(session.investigation_id)
        destination = account_origin()
        console.print(sanitize_terminal(
            f"Architecture graph: {graph['status']}\nRepository: {graph['repository_name']}\n"
            f"Groups: {len(graph.get('groups', []))} | Nodes: {len(graph['nodes'])} | Relationships: {len(graph['relationships'])} | Evidence: {len(graph['evidence'])}\n"
            f"Upload destination: {destination}\n"
            "Uploads labels, descriptions, relative paths, evidence references, and short verified predicates. "
            "No full source files are uploaded. Solid connections are observed module references; reasoned connections are marked inferred."
        ), markup=False)
        if confirm is None:
            if not console.is_terminal:
                console.print('No interactive upload consent; architecture results remain local.', markup=False)
                return None
            confirm = lambda: Confirm.ask('Upload this architecture graph?', default=False, console=console)
        try:
            consent = confirm()
        except (EOFError, KeyboardInterrupt):
            consent = False
        if consent is not True:
            console.print('Architecture results remain local.', markup=False)
            return None
        if account_origin() != destination:
            raise ValueError('Upload destination changed. Review it again before consenting.')
        console.print(sanitize_terminal(upload(graph, consent=True)), markup=False)
        return True
    except Exception as exc:  # noqa: BLE001 -- retain the local result on any upload failure
        console.print('Architecture upload failed. ' + sanitize_terminal(str(exc)) + ' Local results are preserved.', markup=False)
        return False
