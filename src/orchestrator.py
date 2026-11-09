import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from .extractor import extract
from .frozen import Flow, extract_frozen_state
from .models import CellResult, ExtractionResult, FlowReport, Heuristic, Source, Violation
from .rules.engine import run_rules, ruleset_version
from .llm.analyzer import (
    analyze_isolated, analyze_semantics, build_isolated_prompt, build_semantic_prompt)
from .llm.prompt import PROMPT_VARIANT_HIBRIDO, PROMPT_VARIANT_LLM, build_context_block
from .prioritization import prioritize
from .report import build_report, save_json
from .llm.client import build_client, MODEL, SEED, TEMPERATURE
from .llm.prompt import PROMPT_VERSION
from .evaluation.stats import median_severe

Config = Literal["hibrido", "regras", "llm"]
CONFIGS: tuple[Config, ...] = ("hibrido", "regras", "llm")
PROMPT_VARIANTS: dict[str, str | None] = {
    "hibrido": PROMPT_VARIANT_HIBRIDO, "regras": None, "llm": PROMPT_VARIANT_LLM}
OUTPUT_DIR = Path("output")


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def extract_flow(flow: Flow, verbose: bool = True) -> list[ExtractionResult]:
    extracoes = []
    for est in flow.estados:
        if verbose:
            print(f"  [extração] {flow.id} estado {est.ordem} ({est.nome})")
        if est.html is not None:
            extracoes.append(extract_frozen_state(est))
        else:
            extracoes.append(extract(est.url_no_momento))
    return extracoes


def _state_context(flow: Flow, idx: int, n_fatias: int) -> str:
    est = flow.estados[idx]
    return build_context_block(
        estado_ordem=est.ordem,
        total_estados=len(flow.estados),
        estado_nome=est.nome,
        estados_vistos=[e.nome for e in flow.estados[:idx]],
        n_fatias=n_fatias,
        tarefa=flow.tarefa,
    )


def _inspect_state(
    extraction: ExtractionResult,
    config: Config,
    client,
    context: str,
) -> tuple[list[Violation], str | None]:
    if config == "regras":
        return prioritize(run_rules(extraction), [], []), None

    if config == "llm":
        prompt = build_isolated_prompt(extraction, context)
        llm_new = analyze_isolated(extraction, client=client, context=context)
        return prioritize([], llm_new, []), _sha256(prompt)

    rule_violations = run_rules(extraction)
    prompt = build_semantic_prompt(extraction, rule_violations, context)
    llm_new, llm_revised = analyze_semantics(
        extraction, rule_violations, client=client, context=context)
    return prioritize(rule_violations, llm_new, llm_revised), _sha256(prompt)


def aggregate_cells(estados: list[tuple[int, str, list[Violation]]]) -> dict[str, CellResult]:
    celulas: dict[str, CellResult] = {}
    for h in Heuristic:
        violacoes: list[dict] = []
        for ordem, nome, vs in estados:
            relatorio = build_report(nome, [v for v in vs if v.heuristic == h])
            for item in relatorio["violations"]:
                item.pop("rank")
                violacoes.append(
                    {"estado_ordem": ordem, "estado_nome": nome, **item})

        def _max(fonte: str | None = None) -> int:
            return max((v["severity_effective"] for v in violacoes
                        if fonte is None or v["source"] == fonte), default=0)

        celulas[h.value] = CellResult(
            heuristic=h,
            nota=_max(),
            nota_por_origem={s.value: _max(s.value) for s in Source},
            violacoes=violacoes,
        )
    return celulas


def inspect_flow(
    flow: Flow,
    config: Config,
    run_id: int = 0,
    client=None,
    extractions: list[ExtractionResult] | None = None,
    verbose: bool = True,
) -> FlowReport:
    if config not in CONFIGS:
        raise ValueError(f"Configuração inválida: {config}")
    if config != "regras":
        client = client or build_client()
    extractions = extractions or extract_flow(flow, verbose=verbose)

    estados_out: list[dict] = []
    por_estado: list[tuple[int, str, list[Violation]]] = []
    for idx, (est, extraction) in enumerate(zip(flow.estados, extractions)):
        if verbose:
            print(f"  [{config} run {run_id}] {flow.id} estado {est.ordem} ({est.nome})")
        context = _state_context(flow, idx, len(extraction.screenshots))
        prioritized, prompt_hash = _inspect_state(
            extraction, config, client, context)
        por_estado.append((est.ordem, est.nome, prioritized))
        estados_out.append({
            "ordem": est.ordem,
            "nome": est.nome,
            "url_no_momento": est.url_no_momento,
            "n_fatias": len(extraction.screenshots),
            "prompt_sha256": prompt_hash,
            "avisos_extracao": extraction.warnings,
            "relatorio": build_report(est.url_no_momento, prioritized),
        })

    hashes = [e["prompt_sha256"] for e in estados_out if e["prompt_sha256"]]
    metadata = {
        "modelo": MODEL if config != "regras" else None,
        "temperatura": TEMPERATURE if config != "regras" else None,
        "seed": SEED if config != "regras" else None,
        "prompt_variante": PROMPT_VARIANTS[config],
        "prompt_versao": PROMPT_VERSION if config != "regras" else None,
        "prompt_sha256": _sha256("\n".join(hashes)) if hashes else None,
        "regras_versao": ruleset_version() if config != "llm" else None,
        "data_hora": datetime.now().astimezone().isoformat(timespec="seconds"),
        "configuracao": config,
        "run_id": run_id,
    }

    return FlowReport(
        metadata=metadata,
        flow_id=flow.id,
        site=flow.site,
        tarefa=flow.tarefa,
        pasta=str(flow.pasta) if flow.pasta else None,
        estados=estados_out,
        celulas=aggregate_cells(por_estado),
    )


def aggregate_runs(reports: list[FlowReport]) -> dict:
    if not reports:
        raise ValueError("aggregate_runs: nenhuma execução")
    base = reports[0]
    celulas: dict[str, dict] = {}
    for h in Heuristic:
        cel = [r.celulas[h.value] for r in reports]
        notas = [c.nota for c in cel]
        por_origem = {s.value: [c.nota_por_origem[s.value] for c in cel]
                      for s in Source}
        origens = sorted({v["source"] for c in cel for v in c.violacoes
                          if c.nota > 0 and v["severity_effective"] == c.nota})
        celulas[h.value] = {
            "nota": median_severe(notas),
            "notas_execucoes": notas,
            "nota_por_origem": {s: median_severe(v) for s, v in por_origem.items()},
            "notas_por_origem_execucoes": por_origem,
            "origens": origens,
            "violacoes": [{"run_id": r.metadata["run_id"], **v}
                          for r, c in zip(reports, cel) for v in c.violacoes],
        }

    meta = base.metadata
    return {
        "metadata": {
            "modelo": meta["modelo"],
            "temperatura": meta["temperatura"],
            "seed": meta["seed"],
            "prompt_variante": meta.get("prompt_variante"),
            "prompt_sha256_execucoes": [r.metadata["prompt_sha256"] for r in reports],
            "regras_versao": meta["regras_versao"],
            "data_hora": datetime.now().astimezone().isoformat(timespec="seconds"),
            "configuracao": meta["configuracao"],
            "run_ids": [r.metadata["run_id"] for r in reports],
            "n_execucoes": len(reports),
            "agregacao": "mediana por célula; empate (n par) = nível mais severo",
        },
        "flow_id": base.flow_id,
        "site": base.site,
        "tarefa": base.tarefa,
        "pasta": base.pasta,
        "celulas": celulas,
    }


def _carregar_run_valida(caminho: Path, flow: Flow, config: Config) -> FlowReport | None:
    if not caminho.exists():
        return None
    try:
        rep = FlowReport.model_validate(json.loads(caminho.read_text(encoding="utf-8")))
    except Exception:
        return None
    atuais = [(e.nome, e.url_no_momento) for e in flow.estados]
    gravados = [(e.get("nome"), e.get("url_no_momento")) for e in rep.estados]
    if atuais != gravados:
        return None
    if config != "regras" and rep.metadata.get("modelo") != MODEL:
        return None
    if config != "regras" and rep.metadata.get("prompt_versao") != PROMPT_VERSION:
        return None
    return rep


def run_flow(
    flow: Flow,
    config: Config,
    runs: int = 3,
    client=None,
    out_dir: str | Path = OUTPUT_DIR,
    extractions: list[ExtractionResult] | None = None,
    verbose: bool = True,
) -> dict:
    out_dir = Path(out_dir)
    extractions = extractions or extract_flow(flow, verbose=verbose)
    if config != "regras":
        client = client or build_client()

    reports: list[FlowReport] = []
    for k in range(runs):
        caminho = out_dir / "runs" / config / flow.id / f"run_{k}.json"
        rep = _carregar_run_valida(caminho, flow, config)
        if rep is not None:
            if verbose:
                print(f"  [{config} run {k}] {flow.id}: já gravada, reaproveitada")
        else:
            rep = inspect_flow(flow, config, run_id=k, client=client,
                               extractions=extractions, verbose=verbose)
            save_json(rep.model_dump(mode="json"), caminho)
        reports.append(rep)

    agregado = aggregate_runs(reports)
    save_json(agregado, out_dir / "agregado" / config / f"{flow.id}.json")
    return agregado
