"""Conferência automática por IA da amostra de qualidade de atos (ADR 0091).

A IA olha a imagem da página do PDF oficial — não o nosso OCR — e julga cada
ato extraído; também conta nomeações e exonerações que ficaram de fora. A
resposta é validada por código e gravada como anotação rotulada de IA. Os
números são calculados por código a partir dessas anotações.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROMPT_VERSION = "act-quality-prompt/1.0.0"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODELS = ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash")
MAX_IMAGE_SIDE = 2000
VERDICTS = frozenset({"correct", "partial", "incorrect"})

INSTRUCTIONS = """\
Você confere a extração automática de atos de pessoal do Diário Oficial de
Barreiras (BA). A imagem é UMA página do PDF oficial. A lista traz os atos que
um sistema extraiu desta página (tipo, pessoa e cargo).

Para cada ato da lista, responda:
- "correct": a página traz esse ato, do mesmo tipo, para essa pessoa, e o cargo
  confere (ou a lista não traz cargo);
- "partial": é esse ato, mas a pessoa ou o cargo estão incompletos ou errados;
- "incorrect": a página não traz esse ato, ou o tipo está trocado
  (nomeação no lugar de exoneração ou o contrário).

Depois conte as NOMEAÇÕES e as EXONERAÇÕES presentes na página que NÃO estão
na lista (cada pessoa nomeada ou exonerada conta uma vez). Designações,
cessões, férias, licenças e outros atos não contam.

Responda somente com JSON neste formato, sem texto fora dele:
{"acts": {"<result_id>": "correct|partial|incorrect"},
 "missed_nomeacoes": <inteiro>, "missed_exoneracoes": <inteiro>}
"""


@dataclass(frozen=True)
class AiAnnotation:
    verdicts: dict[str, str]
    missed_nomeacoes: int
    missed_exoneracoes: int


def page_image_data_uri(png_bytes: bytes) -> str:
    """Reduz a página para JPEG legível e leve (lado máximo 2.000 px)."""
    from PIL import Image

    image = Image.open(io.BytesIO(png_bytes)).convert("L")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def build_payload(
    model: str, image_data_uri: str, acts: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    listed = [
        {
            "result_id": act["result_id"],
            "tipo": "nomeação" if act["act_type"] == "nomeacao" else "exoneração",
            "pessoa": act.get("person_name"),
            "cargo": act.get("position"),
        }
        for act in acts
    ]
    return {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Atos extraídos desta página: "
                        + json.dumps(listed, ensure_ascii=False),
                    },
                    {"type": "image_url", "image_url": {"url": image_data_uri}},
                ],
            },
        ],
    }


def parse_annotation(body: bytes, expected_ids: Sequence[str]) -> AiAnnotation:
    """Resposta fora do contrato é recusada: nada é gravado."""
    envelope = json.loads(body)
    content = envelope["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("Resposta sem texto.")
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", content.strip()).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Resposta não é objeto JSON.")
    acts = data.get("acts", {})
    if not isinstance(acts, dict) or sorted(acts) != sorted(expected_ids):
        raise ValueError("Vereditos não correspondem aos atos da página.")
    if any(value not in VERDICTS for value in acts.values()):
        raise ValueError("Veredito fora de correct/partial/incorrect.")
    missed = []
    for key in ("missed_nomeacoes", "missed_exoneracoes"):
        value = data.get(key)
        if type(value) is not int or not 0 <= value <= 200:
            raise ValueError(f"{key} inválido.")
        missed.append(value)
    return AiAnnotation(dict(acts), missed[0], missed[1])


def annotator_id(model: str) -> str:
    return f"ai:{model}:{PROMPT_VERSION}"


def response_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
