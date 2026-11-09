import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

REQUER_CAPTURAS = {
    "test_load_flow_p12",
    "test_fluxos_externos_carregam_sem_bloqueio",
    "test_extracao_congelada_sem_rede",
    "test_extracao_congelada_fallback_beautifulsoup",
}
REQUER_CHAVE = {"test_evidencia_chega_ao_relatorio"}


def pytest_collection_modifyitems(config, items):
    sem_capturas = not any((RAIZ / "coletas" / "p12").glob("*"))
    sem_chave = not os.getenv("ANTHROPIC_API_KEY")
    for item in items:
        nome = item.name.split("[")[0]
        if sem_capturas and nome in REQUER_CAPTURAS:
            item.add_marker(pytest.mark.skip(reason="requer capturas em coletas/ (ver README)"))
        if sem_chave and nome in REQUER_CHAVE:
            item.add_marker(pytest.mark.skip(reason="requer ANTHROPIC_API_KEY no .env"))
