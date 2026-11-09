import re
from collections import Counter
from bs4 import BeautifulSoup
from ..models import ExtractionResult, Violation, Heuristic, Severity, Source
from .base import rule


def _soup(extraction: ExtractionResult) -> BeautifulSoup:
    return BeautifulSoup(extraction.html, "lxml")


def _describe_control(c) -> str:
    if c.get("id"):
        return f'{c.name}#{c.get("id")}'
    if c.get("name"):
        return f'{c.name}[name="{c.get("name")}"]'
    t = c.get("type")
    return f"<{c.name}" + (f' type="{t}"' if t else "") + ">"


def _has_accessible_label(c, soup) -> bool:
    if (c.get("aria-label") or "").strip():
        return True
    if c.get("aria-labelledby"):
        return True
    if c.find_parent("label") is not None:
        return True
    cid = c.get("id")
    if cid and soup.find("label", attrs={"for": cid}):
        return True
    return False


_CLASSES_OCULTAS = {"hidden", "d-none", "ng-hide", "hide", "invisible", "sr-only", "visually-hidden"}


def _oculto(el) -> bool:
    for i, n in enumerate([el, *el.parents]):
        if not hasattr(n, "attrs"):
            continue
        estilo = (n.get("style") or "").replace(" ", "").lower()
        if "display:none" in estilo or "visibility:hidden" in estilo or n.has_attr("hidden"):
            return True
        if _CLASSES_OCULTAS & set(n.get("class") or []):
            return True
        if i > 0 and n.get("aria-hidden") == "true":
            return True
    return False


@rule
def titulo_ausente(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    title = soup.find("title")
    if title is None or not title.get_text(strip=True):
        return [Violation(
            heuristic=Heuristic.H01_VISIBILIDADE,
            severity=Severity.MENOR,
            location="<head><title>",
            description="A página não possui um <title> descritivo.",
            justification=(
                "O título é o primeiro feedback de contexto do usuário e é "
                "usado por abas, histórico e favoritos; sua ausência prejudica "
                "a orientação sobre onde se está."
            ),
            recommendation="Adicionar um <title> claro e específico à página.",
            source=Source.REGRAS,
            confidence=1.0,
        )]
    return []


@rule
def hierarquia_de_titulos(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    violations: list[Violation] = []

    previous_level = 0
    for h in headings:
        level = int(h.name[1])
        if previous_level and level > previous_level + 1:
            violations.append(Violation(
                heuristic=Heuristic.H04_CONSISTENCIA,
                severity=Severity.MENOR,
                location=f'<{h.name}> "{h.get_text(strip=True)[:40]}"',
                description=(
                    f"Salto na hierarquia de títulos: <h{previous_level}> "
                    f"seguido diretamente de <{h.name}>."
                ),
                justification=(
                    "Pular níveis de heading quebra a estrutura esperada do "
                    "documento, prejudicando a consistência e a navegação por "
                    "leitores de tela."
                ),
                recommendation=(
                    f"Usar <h{previous_level + 1}> no lugar de <{h.name}> ou "
                    "reorganizar a hierarquia sem saltos."
                ),
                source=Source.REGRAS,
                confidence=1.0,
            ))
        previous_level = level

    return violations


def _hints_match(el, hints: list[str]) -> bool:
    blob = " ".join(filter(None, [
        el.get("name", ""), el.get("id", ""),
        el.get("placeholder", ""), el.get("aria-label", ""),
    ])).lower()
    return any(h in blob for h in hints)


def _has_close_control(dialog) -> bool:
    for el in dialog.find_all(["button", "a"]):
        aria = (el.get("aria-label") or "").lower()
        text = el.get_text(strip=True).lower()
        if any(k in aria for k in ["close", "fechar", "dismiss", "cancel", "cancelar", "voltar"]):
            return True
        if text in {"×", "x", "✕", "✖", "close", "fechar", "cancelar", "cancel", "voltar",
                    "entendi", "dispensar", "dismiss"}:
            return True
        if el.get("data-dismiss") or el.get("data-bs-dismiss"):
            return True
    return dialog.find("form", attrs={"method": re.compile("^dialog$", re.I)}) is not None


@rule
def input_sem_label(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    ignorar = {"hidden", "submit", "button", "reset", "image"}
    violations = []
    for c in soup.find_all(["input", "select", "textarea"]):
        if c.name == "input" and (c.get("type") or "").lower() in ignorar:
            continue
        if _has_accessible_label(c, soup) or _oculto(c):
            continue
        violations.append(Violation(
            heuristic=Heuristic.H05_RECONHECIMENTO,
            severity=Severity.MAIOR,
            location=_describe_control(c),
            description="Campo de formulário sem rótulo (<label>) associado.",
            justification=(
                "Sem rótulo persistente, o usuário precisa memorizar o que "
                "cada campo espera, e leitores de tela não anunciam sua função."
            ),
            recommendation="Associar um <label for> ou aria-label ao campo.",
            source=Source.REGRAS,
            confidence=0.9,
        ))
    return _limitar(violations)


_TYPE_HINTS = {
    "email": ["email", "e-mail", "mail"],
    "tel": ["telefone", "celular", "whatsapp", "fone"],
    "url": ["website", "url"],
}


@rule
def campo_sem_tipo_semantico(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for inp in soup.find_all("input"):
        if (inp.get("type") or "text").lower() != "text":
            continue
        for tipo, hints in _TYPE_HINTS.items():
            if _hints_match(inp, hints):
                violations.append(Violation(
                    heuristic=Heuristic.H08_PREVENCAO_ERROS,
                    severity=Severity.MENOR,
                    location=_describe_control(inp),
                    description=f'Campo aparenta coletar "{tipo}" mas usa type="text".',
                    justification=(
                        "Sem o type semântico, o navegador não valida o formato "
                        "nem oferece teclado apropriado, elevando o risco de erro."
                    ),
                    recommendation=f'Usar type="{tipo}" no campo.',
                    source=Source.REGRAS,
                    confidence=0.7,
                ))
                break
    return violations


@rule
def dialogo_sem_fechar(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    dialogs = soup.find_all(attrs={"aria-modal": "true"})
    seen, violations = set(), []
    for d in dialogs:
        if id(d) in seen:
            continue
        seen.add(id(d))
        if _has_close_control(d) or _oculto(d):
            continue
        violations.append(Violation(
            heuristic=Heuristic.H03_CONTROLE,
            severity=Severity.MAIOR,
            location='[aria-modal="true"]',
            description="Diálogo modal sem controle visível para fechá-lo.",
            justification=(
                "Modais sem saída aprisionam o usuário no estado atual, "
                "violando o controle e a liberdade sobre a navegação."
            ),
            recommendation="Incluir botão de fechar acessível (aria-label).",
            source=Source.REGRAS,
            confidence=0.7,
        ))
    return violations


@rule
def ausencia_de_ajuda_ou_busca(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)

    tem_busca = bool(
        soup.find("input", attrs={"type": "search"})
        or soup.find(attrs={"role": "search"})
        or any(_hints_match(i, ["search", "busca", "buscar", "pesquis"])
               for i in soup.find_all("input"))
    )
    tem_ajuda = any(
        any(k in (a.get_text(strip=True).lower() + " " + (a.get("href") or "").lower())
            for k in ["ajuda", "help", "suporte", "support", "faq", "documenta"])
        for a in soup.find_all("a")
    )
    if tem_busca or tem_ajuda:
        return []
    return [Violation(
        heuristic=Heuristic.H10_AJUDA,
        severity=Severity.COSMETICO,
        location="documento",
        description="Nenhum mecanismo de ajuda ou busca foi encontrado.",
        justification=(
            "Sem ajuda ou busca, o usuário fica sem recurso de apoio quando "
            "trava numa tarefa."
        ),
        recommendation="Oferecer link de ajuda/FAQ ou campo de busca.",
        source=Source.REGRAS,
        confidence=0.4,
    )]


LIMIAR_LINHAS_TABELA = 10
LIMIAR_ITENS_LISTA = 15

_IGNORAR_TEXTO = ("script", "style", "noscript", "template", "svg", "code", "pre")


def _texto(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


def _texto_visivel(soup: BeautifulSoup) -> str:
    copia = BeautifulSoup(str(soup), "lxml")
    for t in copia.find_all(_IGNORAR_TEXTO):
        t.decompose()
    return _texto(copia.body or copia)


def _cls(el) -> str:
    return " ".join(el.get("class") or []).lower()


def _viol(h, sev, loc, desc, just, rec, conf):
    return Violation(heuristic=h, severity=sev, location=loc, description=desc,
                     justification=just, recommendation=rec,
                     source=Source.REGRAS, confidence=conf)


MAX_OCORRENCIAS = 3


def _limitar(violations: list[Violation]) -> list[Violation]:
    if len(violations) <= MAX_OCORRENCIAS:
        return violations
    omitidas = len(violations) - MAX_OCORRENCIAS
    mantidas = violations[:MAX_OCORRENCIAS]
    ultima = mantidas[-1]
    mantidas[-1] = ultima.model_copy(update={
        "description": f"{ultima.description} (+{omitidas} ocorrência(s) omitida(s) do relatório)"})
    return mantidas


_RE_VALOR_ISOLADO = re.compile(r"[\W_]*(undefined|NaN|null|\[object Object\])[\W_]*")


@rule
def valor_nao_tratado_visivel(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    achado = None
    for el in soup.find_all(True):
        if el.name in _IGNORAR_TEXTO or el.find_parent(_IGNORAR_TEXTO) or el.find(True) is not None:
            continue
        m = _RE_VALOR_ISOLADO.fullmatch(_texto(el))
        if m and not _oculto(el):
            achado = m.group(1)
            break
    if achado is None:
        m = re.search(r"lorem ipsum", _texto_visivel(soup), re.I)
        achado = m.group(0) if m else None
    if achado is None:
        return []
    return [_viol(
        Heuristic.H02_CORRESPONDENCIA, Severity.MENOR, "texto da página",
        f'Texto de teste ou valor não tratado visível: "{achado}".',
        "Valores internos ou texto de preenchimento expostos quebram a correspondência com o mundo real.",
        "Substituir por conteúdo real ou ocultar o campo.", 0.8)]


@rule
def controle_so_com_icone_sem_nome(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for el in soup.find_all(["button", "a"]) + soup.find_all(attrs={"role": "button"}):
        if _texto(el) or (el.get("aria-label") or "").strip() or el.get("aria-labelledby") \
                or (el.get("title") or "").strip():
            continue
        if any((i.get("alt") or "").strip() for i in el.find_all("img")):
            continue
        if el.name == "a" and not el.get("href"):
            continue
        if _oculto(el):
            continue
        violations.append(_viol(
            Heuristic.H05_RECONHECIMENTO, Severity.MAIOR, _describe_control(el),
            "Controle sem texto nem nome acessível (só ícone).",
            "Sem rótulo, o usuário precisa lembrar ou adivinhar a função do ícone.",
            "Adicionar texto visível ou aria-label/title ao controle.", 0.7))
    for el in soup.find_all("input"):
        tipo = (el.get("type") or "").lower()
        if tipo not in ("button", "submit", "reset", "image") or _oculto(el):
            continue
        if (el.get("aria-label") or "").strip() or el.get("aria-labelledby") \
                or (el.get("title") or "").strip():
            continue
        if tipo == "image":
            if (el.get("alt") or "").strip():
                continue
        else:
            valor = el.get("value")
            if valor is not None and valor.strip():
                continue
            if tipo in ("submit", "reset") and valor is None:
                continue
        violations.append(_viol(
            Heuristic.H05_RECONHECIMENTO, Severity.MAIOR, _describe_control(el),
            "Botão de formulário sem valor, texto nem nome acessível.",
            "Sem rótulo, o usuário precisa lembrar ou adivinhar a função do botão.",
            "Preencher value (ou alt, no caso de input type=image) ou aria-label.", 0.7))
    return _limitar(violations)


_RE_BUSCA_FILTRO = re.compile(r"filtr|ordenar|classificar|buscar|pesquis|search|sort|filter")


def _tem_busca_ou_filtro(soup: BeautifulSoup) -> bool:
    if soup.find("input", attrs={"type": "search"}) or soup.find(attrs={"role": "search"}):
        return True
    if soup.find("select") or soup.find(attrs={"aria-sort": True}):
        return True
    blob = " ".join(
        [_texto(e) for e in soup.find_all(["button", "a", "label"])]
        + [(i.get("placeholder") or "") + " " + (i.get("aria-label") or "")
           for i in soup.find_all("input")]).lower()
    return bool(_RE_BUSCA_FILTRO.search(blob))


@rule
def lista_longa_sem_busca_ou_filtro(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    longa = [t for t in soup.find_all("table")
             if len(t.find_all("tr")) - (1 if t.find("thead") else 0) >= LIMIAR_LINHAS_TABELA]
    listas = [l for l in soup.find_all(["ul", "ol"])
              if not l.find_parent(["nav", "footer", "header"]) and len(l.find_all("li")) >= LIMIAR_ITENS_LISTA]
    if not (longa or listas) or _tem_busca_ou_filtro(soup):
        return []
    return [_viol(
        Heuristic.H06_FLEXIBILIDADE, Severity.COSMETICO,
        "tabela" if longa else "lista",
        "Lista/tabela longa sem busca, filtro ou ordenação.",
        "Sem aceleradores, o usuário experiente precisa percorrer todos os itens para achar um.",
        "Oferecer busca, filtros e ordenação por colunas.", 0.6)]


_RE_DESTRUTIVA = re.compile(
    r"\b(excluir|apagar|remover|deletar|encerrar conta|cancelar (conta|assinatura|pedido)"
    r"|desativar conta|delete|remove)\b")
_RE_AVISO_IRREVERSIVEL = re.compile(r"irrevers|permanent|não pode ser desfeit|cannot be undone")


@rule
def acao_destrutiva_sem_protecao(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for el in soup.find_all(["button", "a", "input"]):
        rotulo = (_texto(el) or el.get("value") or el.get("aria-label") or "").lower()
        if not _RE_DESTRUTIVA.search(rotulo):
            continue
        protegido = (
            el.get("data-confirm") or el.get("aria-describedby") or el.get("aria-haspopup")
            or el.get("data-bs-toggle") == "modal" or el.get("data-toggle") == "modal"
            or "confirm" in (el.get("onclick") or "").lower())
        contexto = _texto(el.parent.parent or el.parent).lower() if el.parent else ""
        if protegido or _RE_AVISO_IRREVERSIVEL.search(contexto) or _oculto(el):
            continue
        violations.append(_viol(
            Heuristic.H08_PREVENCAO_ERROS, Severity.MAIOR, _describe_control(el),
            f'Ação destrutiva ("{_texto(el) or rotulo}") sem confirmação nem aviso de irreversibilidade.',
            "Ações irreversíveis ao alcance de um clique favorecem o erro; "
            "a prevenção exige confirmação ou separação visual.",
            "Pedir confirmação (diálogo) e avisar que a ação não pode ser desfeita.", 0.6))
    return _limitar(violations)


_RE_CODIGO_ERRO = re.compile(
    r"\b(erro|error|c[óo]d\.?|c[óo]digo|code)\s*[:#]?\s*(0x[0-9a-f]+|\d{3,}|[A-Z_]{3,}\d*)"
    r"|\b0x[0-9a-f]{4,}\b|\bE\d{3,}\b", re.I)
_ORIENTACAO = ("tente", "verifique", "confira", "revise", "corrija", "entre em contato",
               "novamente", "outro", "try", "check", "please", "contact", "preencha",
               "use ")


@rule
def mensagem_de_erro_so_com_codigo(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    candidatos = [e for e in soup.find_all(True)
                  if e.get("role") == "alert"
                  or re.search(r"error|erro|danger|invalid|falha", _cls(e))]
    externos = [e for e in candidatos if not any(p in candidatos for p in e.parents)]
    violations = []
    for e in externos:
        t = _texto(e)
        if not t or not _RE_CODIGO_ERRO.search(t) or _oculto(e):
            continue
        if any(o in t.lower() for o in _ORIENTACAO):
            continue
        violations.append(_viol(
            Heuristic.H09_RECUPERACAO_ERROS, Severity.MAIOR, f'mensagem de erro "{t[:50]}"',
            "Mensagem de erro exibe código técnico e não orienta o usuário sobre causa ou próxima ação.",
            "Mensagens de erro devem usar linguagem simples, indicar o problema com precisão "
            "e sugerir uma solução.",
            "Reescrever a mensagem dizendo o que houve e como tentar de novo.", 0.7))
    return _limitar(violations)


@rule
def campo_invalido_sem_mensagem(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for c in soup.find_all(attrs={"aria-invalid": "true"}):
        if c.get("aria-describedby") or c.get("aria-errormessage"):
            continue
        violations.append(_viol(
            Heuristic.H09_RECUPERACAO_ERROS, Severity.MENOR, _describe_control(c),
            "Campo marcado como inválido sem mensagem que explique o erro.",
            "Sinalizar o erro sem dizer o motivo impede o usuário de se recuperar.",
            "Associar ao campo uma mensagem de erro específica (aria-describedby).", 0.7))
    return _limitar(violations)


_RE_INDICADOR_CARGA = re.compile(r"spinner|loader|loading|skeleton|progress|carregando")


def _em_regiao_de_status(el) -> bool:
    for n in [el, *el.parents]:
        if not hasattr(n, "attrs"):
            continue
        if n.get("role") in ("status", "alert", "progressbar", "log") \
                or (n.get("aria-live") or "off") in ("polite", "assertive") \
                or n.get("aria-busy") == "true":
            return True
    return False


@rule
def indicador_de_carregamento_sem_status(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for el in soup.find_all(True):
        if not _RE_INDICADOR_CARGA.search(_cls(el)) and el.get("role") != "progressbar":
            continue
        if _oculto(el) or _texto(el) or (el.get("aria-label") or "").strip() \
                or el.get("aria-valuetext") or el.get("aria-labelledby"):
            continue
        if _em_regiao_de_status(el):
            continue
        violations.append(_viol(
            Heuristic.H01_VISIBILIDADE, Severity.MAIOR,
            f"{el.name}.{'.'.join(el.get('class') or [])}".rstrip("."),
            "Indicador de carregamento/progresso sem texto, nome acessível ou região de status.",
            "O estado em andamento não é comunicado em texto nem de forma programática; "
            "o usuário não sabe o que ocorre.",
            "Associar ao indicador um texto de estado ou role=\"status\"/aria-live.", 0.6))
    return _limitar(violations)


@rule
def identificador_tecnico_visivel(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    achados: set[str] = set()
    for el in soup.find_all(["label", "legend", "option", "button", "th", "h1", "h2",
                             "h3", "p", "span", "small", "li", "a"]):
        if el.find_parent(_IGNORAR_TEXTO) or _oculto(el):
            continue
        t = _texto(el)
        if t and len(t) <= 200:
            achados.update(re.findall(r"\b[a-z]{2,}_[a-z0-9_]{2,}\b", t))
    if not achados:
        return []
    return [_viol(
        Heuristic.H02_CORRESPONDENCIA, Severity.MENOR, "rótulos e textos da página",
        f"Identificadores de implementação visíveis ao usuário: {', '.join(sorted(achados)[:6])}.",
        "Nomes de variáveis/campos internos não pertencem à linguagem do usuário final.",
        "Reescrever rótulos, opções e dicas em linguagem do domínio do usuário.", 0.6)]


@rule
def pagina_sem_titulos(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    if soup.find(["h1", "h2", "h3", "h4", "h5", "h6"]) or soup.find(attrs={"role": "heading"}):
        return []
    return [_viol(
        Heuristic.H04_CONSISTENCIA, Severity.COSMETICO, "documento",
        "A página não possui nenhum título (h1–h6).",
        "Sem títulos, a estrutura padrão do documento e a navegação por seções se perdem.",
        "Estruturar o conteúdo com títulos.", 0.5)]


_RE_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$")


@rule
def lang_ausente(extraction: ExtractionResult) -> list[Violation]:
    html = _soup(extraction).find("html")
    valor = ((html.get("lang") or html.get("xml:lang") or "").strip()) if html is not None else ""
    if valor and _RE_LANG.match(valor):
        return []
    desc = ("O idioma da página não está declarado (atributo lang)." if not valor
            else f'O atributo lang tem valor inválido: "{valor[:20]}".')
    return [_viol(
        Heuristic.H02_CORRESPONDENCIA, Severity.MENOR, "<html>", desc,
        "Sem o idioma correto, leitores de tela e tradutores não falam a língua do usuário.",
        'Declarar o idioma com um código válido, por exemplo <html lang="pt-BR">.', 1.0)]


@rule
def imagem_sem_alternativa(extraction: ExtractionResult) -> list[Violation]:
    imgs = [i for i in _soup(extraction).find_all("img")
            if i.get("alt") is None and i.get("role") not in ("presentation", "none")
            and not _oculto(i)]
    if not imgs:
        return []
    return [_viol(
        Heuristic.H04_CONSISTENCIA, Severity.MENOR, f"{len(imgs)} <img>",
        f"{len(imgs)} imagem(ns) sem atributo alt.",
        "O padrão da plataforma exige alternativa textual (ou alt vazio, se decorativa).",
        "Adicionar alt descritivo ou alt=\"\" para imagens decorativas.", 0.9)]


@rule
def link_texto_ambiguo(extraction: ExtractionResult) -> list[Violation]:
    destinos: dict[str, set[str]] = {}
    for a in _soup(extraction).find_all("a", href=True):
        href = a["href"].strip()
        t = _texto(a).lower()
        if not t or href in ("", "#") or href.lower().startswith("javascript") or _oculto(a):
            continue
        destinos.setdefault(t, set()).add(href)
    ambiguos = sorted(t for t, d in destinos.items() if len(d) > 1)
    if not ambiguos:
        return []
    return [_viol(
        Heuristic.H05_RECONHECIMENTO, Severity.COSMETICO, f'link "{ambiguos[0][:40]}"',
        f"{len(ambiguos)} texto(s) de link levam a destinos diferentes (ex.: \"{ambiguos[0][:40]}\").",
        "O mesmo rótulo para destinos distintos obriga o usuário a lembrar ou inferir o destino.",
        "Dar a cada link um texto que identifique seu destino.", 0.6)]


@rule
def campo_obrigatorio_sem_marcacao(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for lab in soup.find_all("label"):
        if _oculto(lab) or not re.search(r"\*|obrigat|required", _texto(lab).lower()):
            continue
        alvo = lab.find(["input", "select", "textarea"])
        if alvo is None and lab.get("for"):
            alvo = soup.find(id=lab["for"])
        if alvo is None or alvo.has_attr("required") or alvo.get("aria-required") == "true":
            continue
        violations.append(_viol(
            Heuristic.H08_PREVENCAO_ERROS, Severity.MENOR, _describe_control(alvo),
            "O rótulo indica campo obrigatório, mas o campo não usa required/aria-required.",
            "Sem a marcação, o navegador não impede o envio vazio e o erro só aparece depois.",
            "Adicionar required (ou aria-required) aos campos obrigatórios.", 0.7))
    return _limitar(violations)


@rule
def tabela_sem_cabecalhos(extraction: ExtractionResult) -> list[Violation]:
    violations = []
    for t in _soup(extraction).find_all("table"):
        if t.get("role") in ("presentation", "none") or _oculto(t) or t.find("th"):
            continue
        if len(t.find_all("tr")) < 2:
            continue
        violations.append(_viol(
            Heuristic.H05_RECONHECIMENTO, Severity.MENOR, "tabela",
            "Tabela com várias linhas sem células de cabeçalho (<th>).",
            "Sem cabeçalhos, o usuário precisa lembrar o que cada coluna representa.",
            "Marcar os cabeçalhos de coluna/linha com <th>.", 0.7))
    return _limitar(violations)


@rule
def conteudo_automatico_sem_controle(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    violations = []
    for m in soup.find_all(["video", "audio"]):
        if m.has_attr("autoplay") and not m.has_attr("controls") and not _oculto(m):
            violations.append(_viol(
                Heuristic.H03_CONTROLE, Severity.MAIOR, f"<{m.name}>",
                "Mídia inicia sozinha e não oferece controles para pausar ou parar.",
                "O usuário não consegue interromper o conteúdo iniciado sem sua ação.",
                "Remover o autoplay ou incluir o atributo controls.", 0.8))
    for meta in soup.find_all("meta", attrs={"http-equiv": re.compile("refresh", re.I)}):
        c = (meta.get("content") or "").strip()
        if re.match(r"^[1-9]\d*", c):
            violations.append(_viol(
                Heuristic.H03_CONTROLE, Severity.MAIOR, "<meta http-equiv=refresh>",
                "A página recarrega ou redireciona automaticamente após um tempo.",
                "O usuário perde o controle sobre quando a tela muda.",
                "Remover o refresh automático ou permitir que o usuário o controle.", 0.8))
    return _limitar(violations)


@rule
def blocos_repetidos_sem_atalho(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    if soup.find("nav") is None and soup.find(attrs={"role": "navigation"}) is None:
        return []
    if soup.find("main") or soup.find(attrs={"role": "main"}):
        return []
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("#") and re.search(
                r"pular|ir para o conte|skip|conte[úu]do principal", _texto(a).lower()):
            return []
    return [_viol(
        Heuristic.H06_FLEXIBILIDADE, Severity.COSMETICO, "início da página",
        "Não há link para pular a navegação nem marco <main> para ir direto ao conteúdo.",
        "Sem atalho, o usuário que navega por teclado repassa todo o menu a cada página.",
        'Incluir "Ir para o conteúdo" ou marcar o conteúdo principal com <main>.', 0.5)]


@rule
def conteudo_em_movimento_automatico(extraction: ExtractionResult) -> list[Violation]:
    soup = _soup(extraction)
    achados: list[str] = []
    if soup.find(["marquee", "blink"]):
        achados.append("<marquee>/<blink>")
    for c in soup.find_all(attrs={"data-ride": "carousel"}) \
            + soup.find_all(attrs={"data-bs-ride": ["carousel", "true"]}):
        if not _oculto(c):
            achados.append("carrossel automático")
            break
    css = " ".join(t.get_text() for t in soup.find_all("style"))
    classes_animadas = {c for seletor, corpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                        if re.search(r"animation[^;{}]*\binfinite\b", corpo, re.I)
                        for c in re.findall(r"\.([\w-]+)", seletor)}
    em_uso = any(set(e.get("class") or []) & classes_animadas and not _oculto(e)
                 for e in soup.find_all(class_=True)) if classes_animadas else False
    inline = any(re.search(r"animation[^;{}]*\binfinite\b", e.get("style") or "", re.I)
                 and not _oculto(e) for e in soup.find_all(style=True))
    if em_uso or inline:
        achados.append("animação CSS infinita em elemento visível")
    if not achados:
        return []
    tem_pausa = any(re.search(r"paus|pause|stop|parar", (_texto(b) + " " + (b.get("aria-label") or "")).lower())
                    for b in soup.find_all(["button", "a"]))
    if tem_pausa:
        return []
    return [_viol(
        Heuristic.H07_ESTETICA, Severity.COSMETICO, ", ".join(achados),
        f"Conteúdo em movimento automático sem controle de pausa: {', '.join(achados)}.",
        "Elementos que se movem sozinhos disputam atenção com a informação relevante e "
        "não podem ser interrompidos pelo usuário.",
        "Oferecer controle para pausar/parar ou remover o movimento automático.", 0.5)]


ESCALA_MAXIMA_MINIMA = 2.0


@rule
def viewport_bloqueia_zoom(extraction: ExtractionResult) -> list[Violation]:
    for meta in _soup(extraction).find_all("meta", attrs={"name": re.compile("^viewport$", re.I)}):
        props: dict[str, str] = {}
        for parte in re.split(r"[,;]", meta.get("content") or ""):
            if "=" in parte:
                k, v = parte.split("=", 1)
                props[k.strip().lower()] = v.strip().lower()
        bloqueia = props.get("user-scalable") in ("no", "0")
        try:
            limitado = float(props.get("maximum-scale", "")) < ESCALA_MAXIMA_MINIMA
        except ValueError:
            limitado = False
        if bloqueia or limitado:
            return [_viol(
                Heuristic.H03_CONTROLE, Severity.MENOR, "<meta name=viewport>",
                "O viewport impede ou limita o zoom do usuário (user-scalable=no ou maximum-scale baixo).",
                "O usuário perde o controle sobre a ampliação do conteúdo; quem precisa ampliar o texto não consegue.",
                "Remover user-scalable=no e maximum-scale do viewport.", 1.0)]
    return []


_RE_DADO_PESSOAL = re.compile(
    r"e-?mail|telefone|celular|\bfone\b|\bphone\b|sobrenome|nome completo|full.?name|"
    r"endere[cç]o|\baddress\b|\bcep\b|postal|\bzip\b")


def _coleta_dado_pessoal(c) -> bool:
    tipo = (c.get("type") or "text").lower()
    if tipo in ("email", "tel", "password"):
        return True
    if tipo != "text":
        return False
    blob = " ".join(filter(None, [c.get("name", ""), c.get("id", ""),
                                  c.get("placeholder", ""), c.get("aria-label", "")])).lower()
    return bool(_RE_DADO_PESSOAL.search(blob))


@rule
def campo_sem_autocomplete(extraction: ExtractionResult) -> list[Violation]:
    violations = []
    for c in _soup(extraction).find_all("input"):
        if not _coleta_dado_pessoal(c) or (c.get("autocomplete") or "").strip() or _oculto(c):
            continue
        violations.append(_viol(
            Heuristic.H08_PREVENCAO_ERROS, Severity.COSMETICO, _describe_control(c),
            "Campo de dado pessoal sem o atributo autocomplete.",
            "Sem declarar a finalidade, o navegador não preenche o campo e o usuário digita à mão, "
            "o que aumenta o esforço e o risco de erro.",
            "Declarar a finalidade com autocomplete (por exemplo email, tel, name).", 0.7))
    return _limitar(violations)


LIMIAR_CONTRASTE_NORMAL = 4.5
LIMIAR_CONTRASTE_GRANDE = 3.0
LADO_MINIMO_ALVO = 24.0


def _lin(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminancia(rgb) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def _razao_contraste(a, b) -> float:
    la, lb = _luminancia(a), _luminancia(b)
    claro, escuro = max(la, lb), min(la, lb)
    return (claro + 0.05) / (escuro + 0.05)


def _compor(frente, fundo):
    a = frente[3]
    return [frente[i] * a + fundo[i] * (1 - a) for i in range(3)]


def _fundo_efetivo(nos: dict, no: dict):
    camadas = []
    atual = no
    while atual is not None:
        if atual is not no and atual.get("op", 1) < 1:
            return None
        if atual.get("bgimg"):
            return None
        bg = atual.get("bg")
        if bg is None:
            return None
        if bg[3] > 0:
            camadas.append(bg)
            if bg[3] >= 0.99:
                break
        atual = nos.get(atual.get("p", -1))
    base = [255, 255, 255]
    if camadas and camadas[-1][3] >= 0.99:
        base = camadas.pop()[:3]
    for camada in reversed(camadas):
        base = _compor(camada, base)
    return base


@rule
def contraste_insuficiente(extraction: ExtractionResult) -> list[Violation]:
    nos = {n["i"]: n for n in extraction.render_facts}
    violations, vistos = [], set()
    for n in extraction.render_facts:
        texto = (n.get("text") or "").strip()
        if not texto or n.get("dis") or n.get("fg") is None or n.get("w", 0) <= 1 or n.get("h", 0) <= 1:
            continue
        fundo = _fundo_efetivo(nos, n)
        if fundo is None:
            continue
        fg = n["fg"]
        alfa = fg[3] * n.get("op", 1)
        frente = _compor([fg[0], fg[1], fg[2], alfa], fundo)
        grande = n["fs"] >= 24 or (n["fs"] >= 18.66 and n.get("fw", 400) >= 700)
        minimo = LIMIAR_CONTRASTE_GRANDE if grande else LIMIAR_CONTRASTE_NORMAL
        razao = _razao_contraste(frente, fundo)
        chave = (tuple(round(x) for x in frente), tuple(round(x) for x in fundo))
        if razao >= minimo or chave in vistos:
            continue
        vistos.add(chave)
        violations.append(_viol(
            Heuristic.H05_RECONHECIMENTO, Severity.MENOR, f'{n.get("sel", n.get("tag", "texto"))} "{texto[:30]}"',
            f"Contraste insuficiente: {razao:.2f}:1 (mínimo {minimo:g}:1) no texto \"{texto[:30]}\".",
            "Texto de baixo contraste torna difícil enxergar e reconhecer opções e informações na interface.",
            "Aumentar o contraste entre a cor do texto e a do fundo.", 0.7))
    return _limitar(violations)


def _distancia_circulo_retangulo(cx, cy, r, ret) -> float:
    dx = max(ret["x"] - cx, 0, cx - (ret["x"] + ret["w"]))
    dy = max(ret["y"] - cy, 0, cy - (ret["y"] + ret["h"]))
    return (dx * dx + dy * dy) ** 0.5 - r


@rule
def alvo_de_toque_pequeno(extraction: ExtractionResult) -> list[Violation]:
    alvos = [n for n in extraction.render_facts
             if n.get("inter") and not n.get("dis") and n.get("w", 0) > 0 and n.get("h", 0) > 0
             and not n.get("inl")]
    pequenos = [n for n in alvos if n["w"] < LADO_MINIMO_ALVO or n["h"] < LADO_MINIMO_ALVO]
    violations = []
    raio = LADO_MINIMO_ALVO / 2
    for a in pequenos:
        cx, cy = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
        invade = False
        for b in alvos:
            if b is a:
                continue
            if b in pequenos:
                bx, by = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
                if ((cx - bx) ** 2 + (cy - by) ** 2) ** 0.5 < 2 * raio:
                    invade = True
            elif _distancia_circulo_retangulo(cx, cy, raio, b) < 0:
                invade = True
            if invade:
                break
        if invade:
            violations.append(_viol(
                Heuristic.H08_PREVENCAO_ERROS, Severity.COSMETICO, f'{a.get("sel", a.get("tag", "controle"))}',
                f"Alvo interativo pequeno ({a['w']:.0f}x{a['h']:.0f} px) e próximo de outros alvos.",
                "Alvos pequenos e juntos aumentam o risco de acionar o controle errado.",
                "Aumentar o alvo para 24x24 px ou ampliar o espaçamento entre os controles.", 0.7))
    return _limitar(violations)
