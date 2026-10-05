from enum import StrEnum


class RegulationKind(StrEnum):
    UU = "UU"
    PERPU = "PERPU"
    PP = "PP"
    PERPRES = "PERPRES"
    PERMEN = "PERMEN"
    POJK = "POJK"
    OTHER = "OTHER"


class RegulationStatus(StrEnum):
    IN_FORCE = "IN_FORCE"
    AMENDED = "AMENDED"
    REPEALED = "REPEALED"
    UNKNOWN = "UNKNOWN"


class EventType(StrEnum):
    NEW = "NEW"
    AMEND = "AMEND"
    REPEAL = "REPEAL"
    PARTIAL_REPEAL = "PARTIAL_REPEAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ObligationStatus(StrEnum):
    GENERATED = "GENERATED"
    PENDING_REVIEW = "PENDING_REVIEW"
    EDITED = "EDITED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


class Origin(StrEnum):
    AI = "AI"
    RULE = "RULE"
    HUMAN = "HUMAN"
