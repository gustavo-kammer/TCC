import os
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

TEMPERATURE = None
SEED = None

JUIZ_MODEL = os.getenv("JUIZ_MODEL", MODEL)

MAX_TOKENS = 12000

RETRY_CODES = {429, 500, 502, 503, 504, 529}
RETRY_ESPERAS_S = (5, 15, 30, 60, 90, 120)


def build_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não encontrada — confira o .env")
    return anthropic.Anthropic(api_key=api_key, max_retries=0)


def _to_block(block: dict) -> dict:
    if block["type"] == "text":
        return {"type": "text", "text": block["text"]}
    if block["type"] == "image":
        return {"type": "image", "source": {
            "type": "base64", "media_type": block["mime_type"],
            "data": block["data"]}}
    raise ValueError(f"Tipo de bloco não suportado: {block['type']}")


def analyze(client: anthropic.Anthropic, input_blocks, schema, model: str | None = None) -> str:
    kwargs = dict(
        model=model or MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user",
                   "content": [_to_block(b) for b in input_blocks]}],
        output_config={"format": {
            "type": "json_schema",
            "schema": anthropic.transform_schema(schema.model_json_schema()),
        }},
    )
    for tentativa, espera in enumerate((*RETRY_ESPERAS_S, None)):
        try:
            resp = client.messages.create(**kwargs)
            if resp.stop_reason == "max_tokens":
                raise RuntimeError(
                    "Resposta cortada por max_tokens; aumente MAX_TOKENS em client.py")
            if resp.stop_reason == "refusal":
                raise RuntimeError(
                    f"Recusa do modelo (stop_reason=refusal, "
                    f"entrada={resp.usage.input_tokens} tokens)")
            texto = "".join(b.text for b in resp.content if b.type == "text")
            if not texto.strip():
                diag = (f"stop_reason={resp.stop_reason!r} usage={resp.usage} "
                        f"content={resp.content}")
                if espera is None:
                    raise RuntimeError(f"Resposta sem texto JSON: {diag}")
                print(f"    [claude] resposta vazia ({diag}); nova tentativa "
                      f"{tentativa + 1} em {espera}s", flush=True)
                time.sleep(espera)
                continue
            return texto
        except anthropic.APIStatusError as e:
            msg = str(e)
            if e.status_code == 400 and "credit balance" in msg.lower():
                raise RuntimeError(
                    "Saldo de créditos da Anthropic esgotado: adicione créditos em "
                    "Faturamento. As execuções já gravadas são reaproveitadas.") from e
            if e.status_code not in RETRY_CODES or espera is None:
                raise
            print(f"    [claude] erro {e.status_code}; nova tentativa {tentativa + 1} "
                  f"em {espera}s", flush=True)
            time.sleep(espera)
        except anthropic.APIConnectionError:
            if espera is None:
                raise
            print(f"    [claude] falha de conexão; nova tentativa {tentativa + 1} "
                  f"em {espera}s", flush=True)
            time.sleep(espera)
    raise RuntimeError("inalcançável")
