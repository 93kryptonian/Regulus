FIXED = {
    "ROLE": "Your role does not permit this action.",
    "FOUR_EYES": "The same person may not both edit and approve, or approve and publish.",
    "NO_CLAIM": "You must hold a valid claim on this task.",
    "TASK_MISMATCH": "The request names a different task.",
    "SOURCE_WITHDRAWN": "The source was withdrawn; approval and publication are not possible.",
    "no verified evidence": "No evidence span could be verified against the source text.",
    "EVIDENCE": "Evidence verified against the source text",
    "CLAIM": "You hold the claim",
    "AUTHORIZATION": "Your role and the four-eyes rule permit this action",
    "REJECT_REASON": "A rejection reason is required.",
    "EDIT_CHANGES_AND_REASON": "An edit needs at least one change and a reason.",
    "DUPLICATE_OF_NOT_IN_SNAPSHOT": "The named match is not in this review snapshot.",
}
PREFIX = {
    "OPEN_QUESTION:": "Open question needs a resolution: ",
    "DISPOSITION:": "Disposition needed for match ",
    "ACKNOWLEDGE:": "Acknowledgement needed: ",
}
STATUS = {
    "APPLIED": "Applied. The decision was recorded.",
    "DENIED": "Refused. Nothing was recorded.",
    "STALE": "Stale. The obligation or review context changed since this page was shown. Nothing was recorded.",
    "INCOMPLETE_REVIEW": "Incomplete review. Nothing was recorded.",
    "INVALID_TRANSITION": "Not allowed in the current state. Nothing was recorded.",
    "EVIDENCE_INVALID": "Evidence could not be verified. Nothing was recorded.",
    "NOT_RECORDED": "The store failed. Nothing was recorded; the action may be retried.",
}
BANNER = {
    "VERIFIED": "SOURCE VERIFIED: the source was processed completely.",
    "INCOMPLETE": "SOURCE INCOMPLETE: the source was not completely processed. Approval requires acknowledgement.",
    "CHANGED": "SOURCE CHANGED: the source changed after extraction. Review the updated source; approval requires acknowledgement.",
    "WITHDRAWN": "SOURCE WITHDRAWN: approval and publication are unavailable. The only available review action is rejection, subject to normal authorization and transition rules; the engine may still refuse it.",
}
FIELD_STATE = {
    "NOT_STATED": "not stated in the source",
    "UNDETERMINED": "undetermined",
    "PRESENT": "present",
}


def explain(code: str) -> str:
    if code in FIXED:
        return FIXED[code]
    for p, text in PREFIX.items():
        if code.startswith(p):
            return text + code[len(p) :]
    return code
