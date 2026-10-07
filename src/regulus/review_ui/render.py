from html import escape as _e

from regulus.review import Action, Disposition, RejectCode, Resolution

from .text import BANNER, FIELD_STATE, STATUS, explain
from .view import QueueView, ReviewView

CSS_PATH = "/static/review.css"
CSS = """body{font:16px/1.5 system-ui,sans-serif;margin:0;color:#111;background:#fff}
main{padding:1rem;max-width:80rem;margin:auto}h1,h2{margin:.6em 0 .3em}
section{border:1px solid #888;border-radius:6px;padding:.6rem 1rem;margin:.8rem 0}
.banner{border:2px solid #000;padding:.5rem;font-weight:bold}.ai{border:2px dashed #000;padding:.3rem;font-weight:bold}
mark{background:#ffe08a;color:#000;outline:1px solid #000}table{border-collapse:collapse}
td,th{border:1px solid #888;padding:.2rem .5rem;text-align:left;vertical-align:top}
:focus-visible{outline:3px solid #0050d0;outline-offset:2px}
.blocked{font-weight:bold}.diff{background:#eef}pre{white-space:pre-wrap}"""


def e(value: object) -> str:
    return _e("" if value is None else str(value), quote=True)


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="id"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{e(title)}</title><link rel="stylesheet" href="{CSS_PATH}"></head>'
        f"<body><main>{body}</main></body></html>"
    )


def render_outcome(status: str, reasons: tuple[str, ...] = ()) -> str:
    items = "".join(f"<li>{e(explain(r))} <code>{e(r)}</code></li>" for r in reasons)
    return (
        '<section aria-labelledby="outcome-h"><h2 id="outcome-h">Outcome</h2>'
        f'<div role="status" aria-live="polite"><p><strong>{e(status)}</strong>: '
        f"{e(STATUS.get(status, status))}</p>{'<ul>' + items + '</ul>' if items else ''}</div></section>"
    )


def render_queue(q: QueueView) -> str:
    rows = "".join(
        f'<tr><td><a href="/tasks/{e(i.task_id)}">{e(i.task_id)}</a></td><td>{e(i.article_id)}</td>'
        f"<td>{e(i.status)}</td><td>{e(', '.join(i.markers) or 'no blockers')}</td>"
        f"<td>{i.open_questions}</td><td>{i.age_seconds}s</td></tr>"
        for i in q.items
    )
    body = (
        '<nav aria-label="Review queue"><h1>Review queue</h1>'
        '<table><caption>Ordered by review risk, then age</caption><thead><tr><th scope="col">Task</th>'
        '<th scope="col">Article</th><th scope="col">Status</th><th scope="col">Markers</th>'
        '<th scope="col">Open questions</th><th scope="col">Age</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></nav>"
    )
    return _page("Review queue", body)


def _source(v: ReviewView) -> str:
    s = v.source
    if not s.available:
        text = "<p><strong>SOURCE TEXT UNAVAILABLE</strong>: evidence cannot be verified.</p>"
    else:
        parts = [
            f"<mark>{e(seg.text)}<sup> [{e(', '.join(seg.evidence))}]</sup></mark>"
            if seg.evidence
            else e(seg.text)
            for seg in s.segments
        ]
        text = f"<pre>{''.join(parts)}</pre>"
    ev = "".join(
        f"<li>{e(x.id)}: {e(x.owner_id)}, chars {x.span[0]}-{x.span[1]}: &ldquo;{e(x.quote)}&rdquo; "
        f"{'<strong>exact quote verified</strong>' if x.verified else '<strong>EVIDENCE INVALID</strong>'}</li>"
        for x in s.evidence
    )
    return (
        f'<section aria-labelledby="src-h"><h2 id="src-h">Source: {e(s.owner_id)}</h2>{text}'
        f"<h3>Evidence</h3><ul>{ev or '<li>No evidence recorded.</li>'}</ul></section>"
    )


def _provenance(v: ReviewView) -> str:
    if not v.provenance_recorded:
        return '<section aria-labelledby="prov-h"><h2 id="prov-h">Provenance</h2><p>No field provenance recorded.</p></section>'
    rows = []
    for p in v.provenance:
        cite = (
            f"{e(p.owner_id)}, chars {p.span[0]}-{p.span[1]}: "
            f"{'exact quote verified' if p.verified else 'NOT VERIFIED' if p.verified is False else 'not verifiable (source text unavailable)'}"
            if p.span and p.owner_id
            else "no citation"
        )
        extra = f" Reason: {e(p.reason)}." if p.reason else ""
        qs = "".join(f"<br>Open question: {e(q)}" for q in p.questions)
        rows.append(
            f'<tr><th scope="row">{e(p.field)}</th><td>{e(p.state)} ({e(FIELD_STATE.get(p.state, p.state))})'
            f"{extra}</td><td>{e(p.value) if p.value else ''}</td><td>{cite}{qs}</td></tr>"
        )
    return (
        '<section aria-labelledby="prov-h"><h2 id="prov-h">Provenance</h2><table>'
        '<thead><tr><th scope="col">Field</th><th scope="col">State</th><th scope="col">Value</th>'
        f'<th scope="col">Source citation</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>'
    )


def _diff(v: ReviewView) -> str:
    rows = "".join(
        f'<tr{' class="diff"' if d.changed else ""}><th scope="row">{e(d.field)}</th>'
        f"<td>{e(d.generated) if d.generated is not None else 'not stated'}</td>"
        f"<td>{e(d.current) if d.current is not None else 'not stated'}</td>"
        f"<td>{'EDITED' if d.changed else 'unchanged'}</td></tr>"
        for d in v.diff
    )
    edits = "".join(
        f"<li>{e(x.actor_id)} edited {e(', '.join(x.fields))}: {e(x.reason)}"
        + (
            f" <strong>Source divergence</strong>: {e(', '.join(x.divergence))} not in the source."
            if x.divergence
            else ""
        )
        + "</li>"
        for x in v.edits
    )
    ai = (
        '<p class="ai">AI-GENERATED. Review before relying on it.</p>'
        if v.header.ai_generated
        else ""
    )
    return (
        f'<section aria-labelledby="diff-h"><h2 id="diff-h">Obligation</h2>{ai}'
        '<table><thead><tr><th scope="col">Field</th><th scope="col">Generated (AI, read-only)</th>'
        f'<th scope="col">Current (human review)</th><th scope="col">Change</th></tr></thead><tbody>{rows}</tbody></table>'
        f"<h3>Edits</h3><ul>{edits or '<li>No edits.</li>'}</ul></section>"
    )


def _questions(v: ReviewView) -> str:
    items = "".join(
        f"<li>{e(q.question)}{' (carried from an earlier snapshot)' if q.carried else ''}: "
        f"{'RESOLVED' if q.resolved else 'OPEN'}</li>"
        for q in v.questions
    )
    return f'<section aria-labelledby="q-h"><h2 id="q-h">Open questions</h2><ul>{items or "<li>None.</li>"}</ul></section>'


def _matches(v: ReviewView) -> str:
    out = []
    for m in v.matches:
        cmp = "".join(
            f'<tr><th scope="row">{e(c.field)}</th><td>{e(c.query)}</td><td>{e(c.match)}</td><td>{e(c.relation)}</td></tr>'
            for c in m.comparisons
        )
        flag = " <strong>NEEDS DISPOSITION</strong>" if m.needs_disposition else ""
        weak = " (weak: text similarity only)" if m.weak else ""
        rec = (
            f"<p>Recorded human disposition: {e(m.recorded_disposition)}</p>"
            if m.recorded_disposition
            else ""
        )
        out.append(
            f"<article><h3>Match {e(m.match_id)}</h3>"
            f"<p>Retrieval score: {m.retrieval_score:.2f} ({e(m.score_kind)}, uncalibrated).</p>"
            f"<p>Relationship: {e(m.relationship)}{weak}{flag}</p><p>Lineage: {e(m.lineage)}</p>{rec}"
            '<table><thead><tr><th scope="col">Field</th><th scope="col">This</th><th scope="col">Match</th>'
            f'<th scope="col">Relation</th></tr></thead><tbody>{cmp}</tbody></table></article>'
        )
    return f'<section aria-labelledby="m-h"><h2 id="m-h">Similarity and lineage</h2>{"".join(out) or "<p>No matches.</p>"}</section>'


def _gates(v: ReviewView) -> str:
    items = "".join(
        f"<li>{'PASS' if g.ok else 'BLOCKED'}: {e(explain(g.id))}</li>" for g in v.gates
    )
    blockers = [g for g in v.gates if not g.ok]
    why = (
        f'<p class="blocked">{len(blockers)} gate(s) are not satisfied; approval is not available.</p>'
        if blockers and not v.actions[Action.APPROVE].available
        else ""
    )
    acts = "".join(
        f"<li>{a.value}: {'available' if x.available else 'unavailable'}"
        + (f" ({e('; '.join(explain(r) for r in x.reasons))})" if x.reasons else "")
        + "</li>"
        for a, x in v.actions.items()
    )
    return (
        f'<section aria-labelledby="g-h"><h2 id="g-h">Review gates</h2>{why}<ul>{items}</ul>'
        f"<h3>Actions</h3><ul>{acts}</ul>"
        "<p>The engine decides when you submit; an available action may still be refused.</p></section>"
    )


def _history(v: ReviewView) -> str:
    items = "".join(
        f"<li>{h.index + 1}. {e(h.from_status)} to {e(h.to_status)} by {e(h.actor_id)} "
        f"({e(', '.join(h.roles))}) at {e(h.at.isoformat())}{': ' + e(h.reason) if h.reason else ''}"
        f"<br>hash {e(h.hash[:12])} previous {e(h.prev_hash[:12])}</li>"
        for h in v.history
    )
    chain = "AUDIT CHAIN VERIFIED" if v.chain_valid else "AUDIT CHAIN INVALID"
    return f'<section aria-labelledby="h-h"><h2 id="h-h">History</h2><ol>{items or "<li>No decisions yet.</li>"}</ol><p><strong>{chain}</strong></p></section>'


def _form(v: ReviewView, csrf: str) -> str:
    h = v.header
    hidden = (
        f'<input type="hidden" name="csrf" value="{e(csrf)}">'
        f'<input type="hidden" name="base_version" value="{e(h.base_version)}">'
        f'<input type="hidden" name="snapshot_hash" value="{e(h.snapshot_hash)}">'
    )
    res = "".join(
        f"<fieldset><legend>Open question: {e(q.question)}</legend>"
        f'<label for="res-{i}">Resolution</label><select id="res-{i}" name="res:{e(q.question)}">'
        '<option value="">(none)</option>'
        + "".join(f'<option value="{r.value}">{r.value}</option>' for r in Resolution)
        + f'</select> <label for="note-{i}">Note</label><input id="note-{i}" name="note:{e(q.question)}"></fieldset>'
        for i, q in enumerate(v.questions)
        if not q.resolved
    )
    disp = "".join(
        f"<fieldset><legend>Disposition for match {e(m.match_id)} ({e(m.relationship)})</legend>"
        + "".join(
            f'<label><input type="radio" name="disp:{e(m.match_id)}" value="{d.value}"> {d.value}</label> '
            for d in Disposition
        )
        + "</fieldset>"
        for m in v.matches
        if m.needs_disposition
    )
    ack = "".join(
        f'<label><input type="checkbox" name="ack" value="{flag}"> I acknowledge: {text}</label> '
        for flag, text in (
            ("SOURCE_INCOMPLETE", "the source is incomplete"),
            ("SOURCE_CHANGED", "the source changed after extraction"),
        )
        if any(g.id == f"ACKNOWLEDGE:{flag}" for g in v.gates)
    )
    edit = "".join(
        f'<div><label for="edit-{d.field}">{e(d.field)}</label> '
        f'<input id="edit-{d.field}" name="edit:{d.field}" value="{e(d.current)}">'
        f'<input type="hidden" name="before:{d.field}" value="{e(d.current)}"></div>'
        for d in v.diff
        if d.field != "text"
    )
    rej = "".join(f'<option value="{c.value}">{c.value}</option>' for c in RejectCode)

    def btn(a: Action, label: str) -> str:
        ok = v.actions[a].available
        return f'<button type="submit" name="action" value="{a.value}">{label}{"" if ok else " (unavailable)"}</button>'

    return (
        f'<section aria-labelledby="d-h"><h2 id="d-h">Decision</h2>'
        f'<form method="post" action="/tasks/{e(h.task_id)}/action">{hidden}'
        f'<label for="reason">Reason</label><textarea id="reason" name="reason"></textarea>'
        f"{res}{disp}{ack}"
        f'<fieldset><legend>Reject</legend><label for="rc">Reason code</label><select id="rc" name="reject_code">'
        f'<option value="">(none)</option>{rej}</select> <label for="rt">Text</label>'
        f'<input id="rt" name="reject_text"> <label for="rm">Duplicate of match</label><input id="rm" name="reject_match"></fieldset>'
        f"<fieldset><legend>Edit fields</legend>{edit}</fieldset>"
        f"<p>{btn(Action.APPROVE, 'Approve')} {btn(Action.EDIT, 'Submit edit')} "
        f"{btn(Action.REJECT, 'Reject')} {btn(Action.PUBLISH, 'Publish')}</p></form>"
        f'<form method="post" action="/tasks/{e(h.task_id)}/claim">'
        f'<input type="hidden" name="csrf" value="{e(csrf)}"><button type="submit">Claim task</button></form></section>'
    )


def render_task(v: ReviewView, csrf: str = "", outcome: str = "") -> str:
    h = v.header
    head = (
        f"<header><h1>Review {e(h.obligation_id)}</h1><p>Task {e(h.task_id)} · status {e(h.status)} · "
        f"task {e(h.task_status)}"
        f"{' · claimed by ' + e(h.claimed_by) if h.claimed_by else ''} · article {e(h.article_id)}</p>"
        f'<p><a href="/tasks">Back to queue</a></p></header>'
    )
    banner = f'<p class="banner" role="note">{e(BANNER[v.banner.value])}</p>'
    return _page(
        f"Review {h.obligation_id}",
        head
        + outcome
        + banner
        + _source(v)
        + _provenance(v)
        + _diff(v)
        + _questions(v)
        + _matches(v)
        + _gates(v)
        + _form(v, csrf)
        + _history(v),
    )
