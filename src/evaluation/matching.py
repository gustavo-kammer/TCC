from __future__ import annotations

import csv
import hashlib
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field

from .stats import quadratic_weighted_kappa

CONFIGS = ("hibrido", "regras", "llm")
PASTA_GABARITO = {"p12": "observatorio", "p13": "siout"}


@dataclass
class Problema:
    code: str
    description: str
    severity: int


@dataclass
class Achado:
    id: int
    estado: str
    heuristica: str
    severidade: int
    local: str
    descricao: str


def carregar_problemas(raiz: Path, fluxo: str) -> list[Problema]:
    arq = raiz / "gabarito" / PASTA_GABARITO[fluxo] / "problemas.csv"
    with open(arq, encoding="utf-8") as f:
        return [Problema(r["code"], r["description"].strip(), int(r["severity"]))
                for r in csv.DictReader(f)]


def carregar_achados(arq_run: Path) -> list[Achado]:
    d = json.loads(arq_run.read_text(encoding="utf-8"))
    achados: list[Achado] = []
    for est in d["estados"]:
        for v in est["relatorio"]["violations"]:
            achados.append(Achado(
                id=len(achados) + 1, estado=est["nome"],
                heuristica=v["heuristic"][:3], severidade=int(v["severity_effective"]),
                local=v.get("location") or "", descricao=v["description"]))
    return achados


class Par(BaseModel):
    problem_code: str
    match: Literal["full", "partial", "none"]
    finding_id: int = Field(description="Número do achado correspondente; 0 se não houver.")
    rationale: str = Field(description="Uma frase justificando.")


class ResultadoCasamento(BaseModel):
    matches: list[Par]


CRITERIOS = """\
Você é um avaliador imparcial. Recebe (A) problemas de usabilidade registrados \
por especialistas em uma interface e (B) achados produzidos por um sistema de \
inspeção automática sobre a MESMA interface. Para CADA problema de A, decida se \
algum achado de B descreve o mesmo problema.

Critérios:
- "full": o achado trata do mesmo elemento ou região da interface E do mesmo \
tipo de problema (mesma causa de usabilidade), ainda que com outras palavras.
- "partial": trata do mesmo elemento ou do mesmo tipo de problema, mas de forma \
incompleta ou mais genérica (cobre só parte do que o especialista descreveu).
- "none": nenhum achado corresponde. Não case por semelhança superficial de \
palavras, nem apenas por usarem a mesma heurística de Nielsen.
- Um achado pode corresponder a mais de um problema. Escolha, para cada \
problema, o melhor achado (finding_id = 0 quando "none").
- Os problemas estão em inglês e os achados em português; ignore a diferença \
de idioma e de formulação.
Devolva exatamente uma entrada por problema, na ordem recebida."""


def montar_prompt(problemas: list[Problema], achados: list[Achado]) -> str:
    a = "\n".join(f"[{p.code}] {p.description}" for p in problemas)
    b = "\n".join(f"[{x.id}] ({x.estado}; {x.heuristica}) {x.local} — {x.descricao}"
                  for x in achados) or "(nenhum achado)"
    return f"{CRITERIOS}\n\n(A) PROBLEMAS DOS ESPECIALISTAS\n{a}\n\n(B) ACHADOS DO SISTEMA\n{b}"


_CLIENTE = None


def modelo_juiz_padrao() -> str:
    from ..llm.client import JUIZ_MODEL
    return JUIZ_MODEL


def juiz_com_modelo(modelo: str | None = None):
    def juiz(problemas: list[Problema], achados: list[Achado]) -> ResultadoCasamento:
        from ..llm.client import analyze, build_client
        global _CLIENTE
        if _CLIENTE is None:
            _CLIENTE = build_client()
        prompt = montar_prompt(problemas, achados)
        raw = analyze(_CLIENTE, [{"type": "text", "text": prompt}], ResultadoCasamento,
                      model=modelo or modelo_juiz_padrao())
        return ResultadoCasamento.model_validate_json(raw)
    juiz.modelo = modelo or modelo_juiz_padrao()
    return juiz


def juiz_llm(problemas: list[Problema], achados: list[Achado]) -> ResultadoCasamento:
    return juiz_com_modelo()(problemas, achados)


Juiz = Callable[[list[Problema], list[Achado]], ResultadoCasamento]


def casar(raiz: Path, out_dir: Path, cfg: str, fluxo: str, run: int,
          juiz: Juiz = juiz_llm, pasta: str = "matching") -> dict:
    problemas = carregar_problemas(raiz, fluxo)
    achados = carregar_achados(out_dir / "runs" / cfg / fluxo / f"run_{run}.json")
    modelo = getattr(juiz, "modelo", None) or (modelo_juiz_padrao() if juiz is juiz_llm else "externo")
    chave = hashlib.sha256((montar_prompt(problemas, achados) + "|juiz=" + modelo).encode()).hexdigest()
    cache = out_dir / pasta / cfg / fluxo / f"run_{run}.json"
    if cache.exists():
        c = json.loads(cache.read_text(encoding="utf-8"))
        if c.get("chave") == chave:
            return c
    res = juiz(problemas, achados) if achados else ResultadoCasamento(matches=[
        Par(problem_code=p.code, match="none", finding_id=0, rationale="sem achados")
        for p in problemas])
    por_codigo = {m.problem_code: m for m in res.matches}
    matches = []
    for p in problemas:
        m = por_codigo.get(p.code)
        ok = m is not None and (m.match == "none" or 1 <= m.finding_id <= len(achados))
        matches.append({"problem_code": p.code,
                        "match": m.match if ok else "none",
                        "finding_id": m.finding_id if ok and m.match != "none" else 0,
                        "rationale": m.rationale if m else "sem resposta do juiz"})
    c = {"chave": chave, "juiz_modelo": modelo, "config": cfg, "fluxo": fluxo, "run": run,
         "achados": [a.__dict__ for a in achados],
         "problemas": [p.__dict__ for p in problemas], "matches": matches}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return c


PESO = {"full": 1.0, "partial": 0.5, "none": 0.0}


def metricas_casamento(casamentos: list[dict]) -> dict:
    P = sum(len(c["problemas"]) for c in casamentos)
    F = sum(len(c["achados"]) for c in casamentos)
    full = sum(m["match"] == "full" for c in casamentos for m in c["matches"])
    part = sum(m["match"] == "partial" for c in casamentos for m in c["matches"])
    ach_full: set[tuple] = set()
    ach_any: dict[tuple, float] = {}
    pares: list[tuple[int, int]] = []
    for c in casamentos:
        sev_esp = {p["code"]: p["severity"] for p in c["problemas"]}
        sev_sis = {a["id"]: a["severidade"] for a in c["achados"]}
        for m in c["matches"]:
            if m["match"] == "none":
                continue
            k = (c["fluxo"], m["finding_id"])
            ach_any[k] = max(ach_any.get(k, 0.0), PESO[m["match"]])
            if m["match"] == "full":
                ach_full.add(k)
            pares.append((sev_sis[m["finding_id"]], sev_esp[m["problem_code"]]))
    rec_e, rec_p = (full / P if P else 0.0), ((full + 0.5 * part) / P if P else 0.0)
    pre_e = len(ach_full) / F if F else 0.0
    pre_p = sum(ach_any.values()) / F if F else 0.0
    f1 = lambda p, r: (2 * p * r / (p + r)) if (p + r) else 0.0
    return {"problemas": P, "achados": F, "casou": full, "parcial": part,
            "recall_estrito": rec_e, "recall_ponderado": rec_p,
            "precisao_estrita": pre_e, "precisao_ponderada": pre_p,
            "f1_estrito": f1(pre_e, rec_e), "f1_ponderado": f1(pre_p, rec_p),
            "n_pares_severidade": len(pares),
            "kappa_severidade": quadratic_weighted_kappa(pares, 4)}


def mediana_metricas(por_run: list[dict]) -> dict:
    saida = {}
    for k in por_run[0]:
        vals = [m[k] for m in por_run if m[k] is not None]
        saida[k] = statistics.median(vals) if vals else None
    return saida


def runs_disponiveis(out_dir: Path, cfg: str, fluxo: str) -> list[int]:
    return sorted(int(p.stem.split("_")[1])
                  for p in (out_dir / "runs" / cfg / fluxo).glob("run_*.json"))


def gerar_amostra(casamentos: list[dict], n_casou: int = 46, n_nao: int = 68,
                  semente: int = 7) -> tuple[list[dict], list[dict]]:
    rng = random.Random(semente)
    pos, neg = [], []
    for c in casamentos:
        ach = {a["id"]: a for a in c["achados"]}
        prob = {p["code"]: p for p in c["problemas"]}
        lista = "\n".join(f"{a['id']}. [{a['estado']}] {a['local']} — {a['descricao']}"
                          for a in c["achados"])
        for m in c["matches"]:
            base = {"fluxo": c["fluxo"], "problema": prob[m["problem_code"]]["description"],
                    "_cfg": c["config"], "_run": c["run"], "_code": m["problem_code"],
                    "_juiz": m["match"], "_achado": m["finding_id"]}
            if m["match"] == "none":
                neg.append(base | {"tipo": "nao_casou", "achados": lista, "achado": ""})
            else:
                a = ach[m["finding_id"]]
                pos.append(base | {"tipo": "casou", "achados": "",
                                   "achado": f"[{a['estado']}] {a['local']} — {a['descricao']}"})
    rng.shuffle(pos); rng.shuffle(neg)
    linhas = pos[:n_casou] + neg[:n_nao]
    rng.shuffle(linhas)
    publica, chave = [], []
    for i, l in enumerate(linhas, 1):
        publica.append({"id": i, "tipo": l["tipo"], "fluxo": l["fluxo"],
                        "problema_do_especialista": l["problema"],
                        "achado_do_sistema": l["achado"],
                        "lista_de_achados": l["achados"],
                        "SEU_VEREDITO": ""})
        chave.append({"id": i, "tipo": l["tipo"], "config": l["_cfg"], "run": l["_run"],
                      "problema": l["_code"], "juiz": l["_juiz"], "achado_juiz": l["_achado"]})
    return publica, chave


def concordancia(publica: list[dict], chave: list[dict], populacao: dict | None = None) -> dict:
    k = {int(c["id"]): c for c in chave}
    juiz_h, humano_h, fim = [], [], {"casou": [0, 0], "nao_casou": [0, 0]}
    for r in publica:
        v = str(r["SEU_VEREDITO"]).strip().lower()
        if not v:
            continue
        tipo = r["tipo"]
        if tipo == "casou":
            h = 1 if v.startswith("c") else 0
            j = 1
        else:
            h = 0 if v in ("0", "nao", "não") else 1
            j = 0
        juiz_h.append(j); humano_h.append(h)
        fim[tipo][1] += 1
        fim[tipo][0] += int(h == j)
    n = len(juiz_h)
    if n == 0:
        return {"n": 0}
    acordo = sum(a == b for a, b in zip(juiz_h, humano_h)) / n
    pj, ph = sum(juiz_h) / n, sum(humano_h) / n
    pe = pj * ph + (1 - pj) * (1 - ph)
    kappa = (acordo - pe) / (1 - pe) if pe < 1 else None
    res = {"n": n, "acordo": acordo, "kappa": kappa,
           "acordo_casou": fim["casou"][0] / fim["casou"][1] if fim["casou"][1] else None,
           "acordo_nao_casou": fim["nao_casou"][0] / fim["nao_casou"][1] if fim["nao_casou"][1] else None,
           "n_casou": fim["casou"][1], "n_nao_casou": fim["nao_casou"][1]}
    if populacao:
        from .stats import wilson_fpc
        for tipo in ("casou", "nao_casou"):
            k, m = fim[tipo]
            if m and populacao.get(tipo):
                res[f"acordo_{tipo}_ic95"] = wilson_fpc(k, m, int(populacao[tipo]))
                res[f"populacao_{tipo}"] = int(populacao[tipo])
    return res


_ORD = {"none": 0, "partial": 1, "full": 2}


def concordancia_juizes(raiz: Path, out_dir: Path, modelo_alt: str, runs: int = 0) -> dict:
    pasta = f"matching_{modelo_alt}"
    alt = juiz_com_modelo(modelo_alt)
    pares: dict[str, list[tuple[int, int]]] = {c: [] for c in CONFIGS}
    for cfg in CONFIGS:
        for fl in PASTA_GABARITO:
            ks = runs_disponiveis(out_dir, cfg, fl)
            for k in (ks[:runs] if runs else ks):
                a = casar(raiz, out_dir, cfg, fl, k)
                b = casar(raiz, out_dir, cfg, fl, k, juiz=alt, pasta=pasta)
                pb = {m["problem_code"]: m["match"] for m in b["matches"]}
                for m in a["matches"]:
                    pares[cfg].append((_ORD[m["match"]], _ORD[pb.get(m["problem_code"], "none")]))
    def resumo(ps):
        if not ps:
            return None
        return {"pares": len(ps), "concordancia": round(sum(x == y for x, y in ps) / len(ps), 4),
                "kappa_quadratico": quadratic_weighted_kappa(ps, max_severity=2)}
    saida = {"juiz_principal": modelo_juiz_padrao(), "juiz_alternativo": modelo_alt,
             **{c: resumo(p) for c, p in pares.items()}, "total": resumo([x for p in pares.values() for x in p])}
    return saida
