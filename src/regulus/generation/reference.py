from regulus.domain import Origin

from .models import GenerationRequest, RawGenerated
from .trace import expected


class ExtractiveGenerator:
    id = "extractive"
    version = "1"
    origin = Origin.RULE
    model: str | None = None
    prompt_version: str | None = None

    def generate(self, request: GenerationRequest) -> RawGenerated:
        src = request.source
        content, trace = expected(request.candidate)
        parts = [*([src.lead_in] if src.lead_in else []), src.clause, *src.items]
        return RawGenerated(
            text=" ".join(" ".join(p.split()) for p in parts), content=content, trace=trace
        )
