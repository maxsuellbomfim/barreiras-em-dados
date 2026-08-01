from __future__ import annotations

import json
import logging
import unittest

from barreiras_docproc.assist import (
    CascadeUnavailableError,
    ContractViolationError,
    build_messages,
    run_cascade,
)

LOGGER = logging.getLogger("test-assist")


def envelope(content: str) -> bytes:
    return json.dumps(
        {"choices": [{"message": {"content": content}}]}
    ).encode("utf-8")


class ScriptedCaller:
    """Respostas por URL; registra quem foi chamado."""

    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def post(self, url, headers, payload):
        self.calls.append(url)
        assert headers["Authorization"].startswith("Bearer ")
        assert payload["temperature"] == 0
        return self.responses[url]


GROQ = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
GEMINI = (
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
)

VALID = envelope(
    json.dumps(
        {
            "person_name": "FULANO DE TAL",
            "position": None,
            "position_symbol": None,
            "organization": None,
            "act_number": "901",
            "act_date": "2026-06-15",
            "summary": "A prefeitura nomeou Fulano de Tal.",
        }
    )
)

ENV = {
    "GROQ_API_KEY": "chave-groq",
    "OPENROUTER_API_KEY": "chave-or",
    "GEMINI_API_KEY": "chave-gemini",
}

MESSAGES = build_messages(
    "nomeacao",
    "PORTARIA 901. NOMEAR FULANO DE TAL.",
    {},
)


class CascadeTests(unittest.TestCase):
    def test_first_available_provider_answers(self) -> None:
        caller = ScriptedCaller({GROQ: (200, VALID)})

        outcome = run_cascade(caller, ENV, MESSAGES, LOGGER)

        self.assertEqual(outcome.provider, "groq")
        self.assertEqual(outcome.suggestions["person_name"], "FULANO DE TAL")
        self.assertEqual(outcome.suggestions["position"], None)
        self.assertEqual(outcome.suggestions["act_date"], "2026-06-15")
        self.assertIn("nomeou", outcome.summary or "")
        self.assertEqual(caller.calls, [GROQ])

    def test_quota_exhaustion_promotes_next_level(self) -> None:
        caller = ScriptedCaller(
            {GROQ: (429, b"{}"), OPENROUTER: (200, VALID)}
        )

        outcome = run_cascade(caller, ENV, MESSAGES, LOGGER)

        self.assertEqual(outcome.provider, "openrouter")
        self.assertEqual(caller.calls, [GROQ, OPENROUTER])

    def test_missing_key_skips_level(self) -> None:
        caller = ScriptedCaller({GEMINI: (200, VALID)})
        environment = {"GEMINI_API_KEY": "somente-gemini"}

        outcome = run_cascade(caller, environment, MESSAGES, LOGGER)

        self.assertEqual(outcome.provider, "gemini")
        self.assertEqual(caller.calls, [GEMINI])

    def test_all_levels_exhausted_is_explicit(self) -> None:
        caller = ScriptedCaller(
            {GROQ: (429, b"{}"), OPENROUTER: (402, b"{}"), GEMINI: (500, b"")}
        )

        with self.assertRaises(CascadeUnavailableError):
            run_cascade(caller, ENV, MESSAGES, LOGGER)

    def test_contract_violation_does_not_cascade_blindly(self) -> None:
        caller = ScriptedCaller(
            {GROQ: (200, envelope("não sou json")), OPENROUTER: (200, VALID)}
        )

        with self.assertRaises(ContractViolationError):
            run_cascade(caller, ENV, MESSAGES, LOGGER)

        self.assertEqual(caller.calls, [GROQ])

    def test_code_fenced_json_is_accepted(self) -> None:
        fenced = envelope(
            "```json\n"
            + json.dumps({"person_name": "BELTRANA", "summary": "ok"})
            + "\n```"
        )
        caller = ScriptedCaller({GROQ: (200, fenced)})

        outcome = run_cascade(caller, ENV, MESSAGES, LOGGER)

        self.assertEqual(outcome.suggestions["person_name"], "BELTRANA")

    def test_prompt_forbids_invention_and_lists_missing_fields(self) -> None:
        messages = build_messages(
            "exoneracao",
            "trecho",
            {"person_name": {"value": "JÁ TEM", "status": "matched"}},
        )

        system = messages[0]["content"]
        user = messages[1]["content"]
        self.assertIn("null", system)
        self.assertIn("Nunca deduza", system)
        self.assertNotIn("person_name", user.split("Trecho")[0])
        self.assertIn("act_number", user)


if __name__ == "__main__":
    unittest.main()
