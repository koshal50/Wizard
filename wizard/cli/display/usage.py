"""Terminal formatting only. Values and aggregation come from the runtime."""


def compact_tokens(value):
    """Format only; integer accounting is untouched (round half up at 10 tokens)."""
    if value < 1000:
        return str(value)
    hundredths = (value + 5) // 10
    return f"{hundredths // 100}.{hundredths % 100:02}k"


def counter(usage, elapsed=None, *, compact=False):
    suffix = ""
    if elapsed is not None:
        seconds = max(0, int(elapsed))
        suffix = f" | Elapsed: {seconds // 60:02}:{seconds % 60:02}"
    if not usage or "total_tokens" not in usage:
        if usage and any(
            usage.get(k)
            for k in ("incomplete", "persistence_error", "accounting_incomplete")
        ):
            return "Tokens: unavailable | usage incomplete" + suffix
        return (
            "Tokens: pending | LLM calls: pending"
            + suffix
            + (" | reconnecting" if usage and usage.get("transport_error") else "")
        )
    number = compact_tokens if compact else lambda value: f"{value:,}"
    if compact:
        line = (f"Tokens: {number(usage['total_tokens'])} "
                f"(\u2191 {number(usage.get('input_tokens', 0))} / \u2193 {number(usage.get('output_tokens', 0))})"
                f" | LLM calls: {usage.get('llm_calls', 0)}")
    else:
        line = (f"Tokens: {number(usage['total_tokens'])} "
                f"(in {number(usage.get('input_tokens', 0))} / out {number(usage.get('output_tokens', 0))})"
                f" | LLM calls: {usage.get('llm_calls', 0)}")
    line += suffix
    if usage.get("transport_error"):
        line += " | reconnecting"
    if any(
        usage.get(k)
        for k in (
            "incomplete",
            "accounting_incomplete",
        )
    ):
        line += " | incomplete"
    if usage.get("pending_requests"):
        line += " | in progress"
    return line


def format_status(report):
    lines = [
        "Wizard Usage Monitor",
        "----------------------------------------",
        "Current run",
    ]
    run = report.get("current_run")
    if run:
        lines += [
            f"  {'Command:':<16}{run['command']}",
            f"  {'Intent:':<16}{run.get('intent') or '-'}",
            f"  {'Status:':<16}{run['status']}",
            f"  {'Run tokens:':<16}{run.get('total_tokens', 0):,}",
            f"  {'Input tokens:':<16}{run.get('input_tokens', 0):,}",
            f"  {'Output tokens:':<16}{run.get('output_tokens', 0):,}",
            f"  {'LLM calls:':<16}{run.get('llm_calls', 0)}",
        ]
        if any(
            run.get(key)
            for key in (
                "incomplete",
                "accounting_incomplete",
            )
        ):
            lines.append("  Usage is incomplete")
        if not run.get("finished_at") or run.get("pending_requests"):
            lines.append("  Usage is in progress")
    else:
        lines.append(
            "  Usage pending; the runtime is accepting the current run"
            if report.get("current_run_pending")
            else "  No recorded runs"
        )
    if report.get("history_scope") == "local_recorded_runs":
        lines.append("  History: runs recorded on this machine")
    totals = report["totals"]
    lines += [
        "",
        "Overall usage",
        f"  {'Total tokens:':<16}{totals.get('total_tokens', 0):,}",
        f"  {'Input tokens:':<16}{totals.get('input_tokens', 0):,}",
        f"  {'Output tokens:':<16}{totals.get('output_tokens', 0):,}",
        f"  Total LLM calls: {totals.get('llm_calls', 0)}",
        "",
        "Usage by command",
    ]
    for command in ("investigate", "verify", "explain", "report", "btw"):
        totals = report.get("by_command", {}).get(command, {})
        lines.append(f"  {command + ':':<16}{totals.get('total_tokens', 0):,}")
    if report["totals"].get("incomplete") or any(
        report.get(k)
        for k in ("accounting_incomplete",)
    ):
        lines.append(
            "Usage is incomplete; some requests lack confirmed provider counts"
        )
    if report.get("persistence_pending") or report.get("persistence_error"):
        lines.append("History sync is pending or unavailable; confirmed local totals remain available")
    if report.get("scope") == "account":
        lines.append(f"Scope: Wizard account {report.get('account_id') or report['profile_id']} (all sessions)")
    else:
        lines.append(f"Scope: local profile {report['profile_id']} (all sessions)")
    lines.append("----------------------------------------")
    return "\n".join(lines)
