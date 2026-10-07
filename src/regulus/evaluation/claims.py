import re

FORBIDDEN = (
    (
        re.compile(r"\bregulus\b[^.]{0,40}\baccuracy\b", re.IGNORECASE),
        "an overall Regulus accuracy",
    ),
    (
        re.compile(r"\b(overall|pipeline|system)\s+(accuracy|score|f1)\b", re.IGNORECASE),
        "an overall score",
    ),
    (
        re.compile(r"\bproduction[- ]?(ready|grade)\b", re.IGNORECASE),
        "a production-readiness claim",
    ),
    (
        re.compile(r"\bwill\s+generali[sz]e\b|\bgeneali[sz]es\s+to\b", re.IGNORECASE),
        "a generalization claim",
    ),
    (
        re.compile(
            r"\b(real|local)\s+corpus\b[^.]{0,80}\b(accuracy|precision|recall|error[- ]free|zero errors)\b",
            re.IGNORECASE,
        ),
        "a correctness claim from corpus coverage",
    ),
    (
        re.compile(
            r"\b(better|worse|higher|lower)\s+than\s+(the\s+)?(relevance|lineage|extraction|generation|similarity)\b",
            re.IGNORECASE,
        ),
        "a cross-layer comparison",
    ),
)
BARE = re.compile(
    r"\b(precision|recall|accuracy|f1)\b[^.]{0,30}\b\d{1,3}(\.\d+)?\s?%", re.IGNORECASE
)
POPULATION = re.compile(
    r"\b(on the|in the|over the)\b[^.]{0,80}\b(set|cases|pairs|queries|operations|snippets|items|runs)\b",
    re.IGNORECASE,
)


def violations(text: str) -> list[str]:
    out = [why for rx, why in FORBIDDEN if rx.search(text)]
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if BARE.search(sentence) and not POPULATION.search(sentence):
            out.append("a rate stated without its population")
            break
    return out
