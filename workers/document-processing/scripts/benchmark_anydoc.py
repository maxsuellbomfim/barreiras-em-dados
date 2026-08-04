"""Benchmark local do AnyDoc sem imprimir conteúdo documental.

Uso:
  python benchmark_anydoc.py fixtures/anydoc --output artifacts/anydoc.json

O diretório de entrada deve conter documentos públicos selecionados para o
benchmark. O relatório guarda somente hashes, formato, tamanhos, latência e
status; nunca grava o texto dos documentos.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from barreiras_docproc.anydoc_adapter import (
    AnyDocConversionError,
    AnyDocUnavailable,
    convert_to_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    files = sorted(
        path
        for path in arguments.input_dir.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    rows = []
    started_all = time.perf_counter()
    for path in files:
        body = path.read_bytes()
        started = time.perf_counter()
        hint = path.suffix.lower().lstrip(".") or None
        try:
            result = convert_to_markdown(body, format_hint=hint)
        except (AnyDocConversionError, AnyDocUnavailable) as error:
            rows.append(
                {
                    "file": path.as_posix(),
                    "input_sha256": hashlib.sha256(body).hexdigest(),
                    "input_bytes": len(body),
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
            continue
        rows.append(
            {
                "file": path.as_posix(),
                "input_sha256": result.input_sha256,
                "input_bytes": result.input_bytes,
                "detected_format": result.detected_format,
                "output_sha256": result.output_sha256,
                "output_bytes": len(result.markdown.encode("utf-8")),
                "parser_version": result.parser_version,
                "status": "ok",
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )

    report = {
        "schema": "anydoc-benchmark/1.0.0",
        "files": rows,
        "summary": {
            "total": len(rows),
            "ok": sum(row["status"] == "ok" for row in rows),
            "failed": sum(row["status"] == "failed" for row in rows),
            "elapsed_ms": round((time.perf_counter() - started_all) * 1000, 3),
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
