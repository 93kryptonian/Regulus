from collections import Counter

from regulus.workflow import WorkflowStore

from .policy import ISO, PATTERNS


def scan_stores(store: WorkflowStore) -> Counter[str]:
    found: Counter[str] = Counter()

    def check(record_type: str, text: str | None) -> None:
        if not text:
            return
        plain = ISO.sub("", text)
        for kind, rx in PATTERNS.items():
            if rx.search(plain):
                found[f"{record_type}:{kind}"] += 1

    for oid in sorted(store.review._initial):
        for rec in store.review.get(oid)[1]:
            check("review_record.reason", rec.decision.reason)
            for r in rec.open_question_resolutions:
                check("review_record.note", r.note)
            if rec.reject_reason is not None:
                check("review_record.reject_text", rec.reject_reason.text)
    return found


def records_scanned(store: WorkflowStore) -> int:
    return sum(len(store.review.get(oid)[1]) for oid in store.review._initial)
