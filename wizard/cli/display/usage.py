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
    line = (
        f"Tokens: {number(usage['total_tokens'])} "
        f"(in {number(usage.get('input_tokens', 0))} / out {number(usage.get('output_tokens', 0))})"
        f" | LLM calls: {usage.get('llm_calls', 0)}"
    )
    line += suffix
    if usage.get("transport_error"):
        line += " | reconnecting"
    if any(
        usage.get(k)
        for k in (
            "incomplete",
            "persistence_pending",
            "persistence_error",
            "accounting_incomplete",
        )
    ):
        line += " | incomplete"
    if usage.get("pending_requests") and not compact:
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
                "persistence_pending",
                "persistence_error",
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
    for command in ("investigate", "verify", "explain", "report"):
        totals = report.get("by_command", {}).get(command, {})
        lines.append(f"  {command + ':':<16}{totals.get('total_tokens', 0):,}")
    if report["totals"].get("incomplete") or any(
        report.get(k)
        for k in ("persistence_pending", "persistence_error", "accounting_incomplete")
    ):
        lines.append(
            "Usage is incomplete; some records are awaiting persistence or unavailable"
        )
    lines.append(f"Scope: local profile {report['profile_id']} (all sessions)")
    lines.append("----------------------------------------")
    return "\n".join(lines)
