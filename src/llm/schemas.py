from pydantic import BaseModel, Field
from ..models import Evidence, Heuristic, Severity


class NewViolation(BaseModel):
    heuristic: Heuristic
    severity: Severity
    location: str = Field(description="Região da tela ou elemento afetado.")
    description: str = Field(description="O problema observado, em uma frase.")
    justification: str = Field(
        description="Por que fere a heurística, com base no que se vê.")
    recommendation: str = Field(description="Correção sugerida, objetiva.")
    evidence: Evidence = Field(
        description="Evidência que sustenta o achado: trecho literal do texto extraído ou região da captura.")


class SeverityRevision(BaseModel):
    rule_index: int = Field(
        description="Índice da violação das regras que está sendo reavaliada.")
    revised_severity: Severity = Field(
        description="Severidade reavaliada considerando o contexto visual.")
    rationale: str = Field(
        description="Justificativa da mudança (ou da manutenção) da severidade.")


class IsolatedAnalysis(BaseModel):
    reasoning: str = Field(
        description="Resumo da análise geral da interface, antes das conclusões.")
    new_violations: list[NewViolation] = Field(default_factory=list)


class SemanticAnalysis(BaseModel):
    reasoning: str = Field(
        description="Resumo da análise geral da interface, antes das conclusões.")
    new_violations: list[NewViolation] = Field(default_factory=list)
    severity_revisions: list[SeverityRevision] = Field(default_factory=list)
