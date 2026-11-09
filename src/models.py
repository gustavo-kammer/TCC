from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class Heuristic(str, Enum):
    H01_VISIBILIDADE = "H01_visibilidade_do_estado_do_sistema"
    H02_CORRESPONDENCIA = "H02_correspondencia_sistema_mundo_real"
    H03_CONTROLE = "H03_controle_e_liberdade_do_usuario"
    H04_CONSISTENCIA = "H04_consistencia_e_padronizacao"
    H05_RECONHECIMENTO = "H05_reconhecimento_em_vez_de_memorizacao"
    H06_FLEXIBILIDADE = "H06_flexibilidade_e_eficiencia_de_uso"
    H07_ESTETICA = "H07_design_estetico_e_minimalista"
    H08_PREVENCAO_ERROS = "H08_prevencao_de_erros"
    H09_RECUPERACAO_ERROS = "H09_diagnostico_e_recuperacao_de_erros"
    H10_AJUDA = "H10_ajuda_e_documentacao"


class Severity(int, Enum):
    NAO_E_PROBLEMA = 0
    COSMETICO = 1
    MENOR = 2
    MAIOR = 3
    CATASTROFE = 4


class Source(str, Enum):
    REGRAS = "motor_de_regras"
    LLM = "llm"


class Evidence(BaseModel):
    kind: Literal["texto", "visual"] = Field(
        description="'texto' se o problema se apoia em texto, rótulo ou atributo do TEXTO EXTRAÍDO; "
                    "'visual' se só aparece na captura de tela.")
    quote: str = Field(
        description="Para kind 'texto': trecho literal copiado do TEXTO EXTRAÍDO (até 120 caracteres). "
                    "Para kind 'visual': string vazia.")
    region: str = Field(
        description="Para kind 'visual': região da captura onde o problema aparece. "
                    "Para kind 'texto': string vazia.")


class Violation(BaseModel):
    heuristic: Heuristic
    severity: Severity
    location: str
    description: str
    justification: str
    recommendation: str
    source: Source
    confidence: float | None = None
    severity_revised: Severity | None = None
    revision_rationale: str | None = None
    evidence: Evidence | None = None


class ExtractionResult(BaseModel):
    url: str
    html: str
    screenshots: list[str] = Field(default_factory=list)
    computed_styles: list[dict] = Field(default_factory=list)
    render_facts: list[dict] = Field(default_factory=list)
    render_facts_status: str = "ausente"
    warnings: list[str] = Field(default_factory=list)


class InspectionReport(BaseModel):
    url: str
    violations: list[Violation]


class CellResult(BaseModel):
    heuristic: Heuristic
    nota: int
    nota_por_origem: dict[str, int]
    violacoes: list[dict] = Field(default_factory=list)


class FlowReport(BaseModel):
    metadata: dict
    flow_id: str
    site: str
    tarefa: str | None
    pasta: str | None
    estados: list[dict]
    celulas: dict[str, CellResult]
