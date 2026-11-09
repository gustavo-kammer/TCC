from ..models import ExtractionResult, Violation, Source, Severity
from .client import build_client, analyze
from .schemas import IsolatedAnalysis, NewViolation, SemanticAnalysis
from .prompt import build_prompt, build_prompt_llm


def _input_blocks(prompt: str, extraction: ExtractionResult) -> list[dict]:
    input_blocks = [{"type": "text", "text": prompt}]
    for shot in extraction.screenshots:
        input_blocks.append({
            "type": "image",
            "mime_type": "image/png",
            "data": shot,
        })
    return input_blocks


def _to_violations(new_violations: list[NewViolation]) -> list[Violation]:
    novas: list[Violation] = []
    for nv in new_violations:
        novas.append(Violation(
            heuristic=nv.heuristic,
            severity=nv.severity,
            location=nv.location,
            description=nv.description,
            justification=nv.justification,
            recommendation=nv.recommendation,
            source=Source.LLM,
            confidence=0.75,
            evidence=nv.evidence,
        ))
    return novas


def _format_page_text(extraction: ExtractionResult, max_items: int = 200) -> str:
    linhas: list[str] = []
    for el in extraction.computed_styles:
        txt = " ".join(((el.get("own_text") if "own_text" in el else el.get("text")) or "").split())
        attrs = " ".join((el.get("attrs") or "").split())
        if not txt and not attrs:
            continue
        linha = f'- [{el.get("tag")}] {txt}'.rstrip()
        if attrs:
            linha += f"  (atributos: {attrs})"
        linhas.append(linha)
        if len(linhas) >= max_items:
            break
    return "\n".join(linhas) if linhas else "(nenhum texto extraído)"


def _format_rule_violations(rule_violations: list[Violation]) -> str:
    if not rule_violations:
        return "(nenhuma — o motor de regras não encontrou inconformidades)"
    linhas = []
    for i, v in enumerate(rule_violations):
        linhas.append(
            f"[{i}] {v.heuristic.value} | severidade atual: {v.severity.value} "
            f"| local: {v.location} | {v.description}"
        )
    return "\n".join(linhas)


def build_semantic_prompt(
    extraction: ExtractionResult,
    rule_violations: list[Violation],
    context: str | None = None,
) -> str:
    return build_prompt(
        page_text=_format_page_text(extraction),
        rule_violations_block=_format_rule_violations(rule_violations),
        context_block=context,
    )


def analyze_semantics(
    extraction: ExtractionResult,
    rule_violations: list[Violation],
    client=None,
    context: str | None = None,
) -> tuple[list[Violation], list[Violation]]:

    client = client or build_client()

    prompt = build_semantic_prompt(extraction, rule_violations, context)
    raw = analyze(client, _input_blocks(prompt, extraction), SemanticAnalysis)
    result = SemanticAnalysis.model_validate_json(raw)

    novas = _to_violations(result.new_violations)

    reavaliadas: list[Violation] = []
    for rev in result.severity_revisions:
        if 0 <= rev.rule_index < len(rule_violations):
            original = rule_violations[rev.rule_index]
            revisada = original.model_copy()
            revisada.severity_revised = rev.revised_severity
            revisada.revision_rationale = rev.rationale
            reavaliadas.append(revisada)

    return novas, reavaliadas


def build_isolated_prompt(
    extraction: ExtractionResult,
    context: str | None = None,
) -> str:
    return build_prompt_llm(
        page_text=_format_page_text(extraction),
        context_block=context,
    )


def analyze_isolated(
    extraction: ExtractionResult,
    client=None,
    context: str | None = None,
) -> list[Violation]:

    client = client or build_client()

    prompt = build_isolated_prompt(extraction, context)
    raw = analyze(client, _input_blocks(prompt, extraction), IsolatedAnalysis)
    result = IsolatedAnalysis.model_validate_json(raw)
    return _to_violations(result.new_violations)
