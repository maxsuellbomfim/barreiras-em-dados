import json
import unittest

from barreiras_docproc.act_quality_ai import (
    PROMPT_VERSION,
    annotator_id,
    build_payload,
    parse_annotation,
)
from barreiras_docproc.commands.annotate_act_quality import (
    QUOTA_RETRY_SECONDS,
    QuotaExhausted,
    annotate_page,
)

ACTS = [
    {
        "result_id": "a1",
        "act_type": "nomeacao",
        "person_name": "Fulana",
        "position": "Diretora",
    },
    {
        "result_id": "b2",
        "act_type": "exoneracao",
        "person_name": "Beltrano",
        "position": None,
    },
]


def envelope(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


class ParseAnnotationTests(unittest.TestCase):
    def test_accepts_contract_and_code_fences(self) -> None:
        body = envelope(
            '```json\n{"acts": {"a1": "correct", "b2": "incorrect"},'
            ' "missed_nomeacoes": 1, "missed_exoneracoes": 0}\n```'
        )
        annotation = parse_annotation(body, ["a1", "b2"])
        self.assertEqual(annotation.verdicts, {"a1": "correct", "b2": "incorrect"})
        self.assertEqual(
            (annotation.missed_nomeacoes, annotation.missed_exoneracoes), (1, 0)
        )

    def test_rejects_anything_outside_the_contract(self) -> None:
        for content in (
            '{"acts": {"a1": "correct"},'
            ' "missed_nomeacoes": 0, "missed_exoneracoes": 0}',
            '{"acts": {"a1": "talvez", "b2": "correct"},'
            ' "missed_nomeacoes": 0, "missed_exoneracoes": 0}',
            '{"acts": {"a1": "correct", "b2": "correct"},'
            ' "missed_nomeacoes": -1, "missed_exoneracoes": 0}',
            '{"acts": {"a1": "correct", "b2": "correct"},'
            ' "missed_nomeacoes": 1.5, "missed_exoneracoes": 0}',
            "não sei",
        ):
            with (
                self.subTest(content=content),
                self.assertRaises((ValueError, KeyError)),
            ):
                parse_annotation(envelope(content), ["a1", "b2"])


class PayloadTests(unittest.TestCase):
    def test_sends_image_acts_and_versioned_annotator(self) -> None:
        payload = build_payload("gemini-2.5-flash", "data:image/jpeg;base64,AAA", ACTS)
        user = payload["messages"][1]["content"]
        self.assertIn('"result_id": "a1"', user[0]["text"])
        self.assertEqual(user[1]["image_url"]["url"], "data:image/jpeg;base64,AAA")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(
            annotator_id("gemini-2.5-flash"), f"ai:gemini-2.5-flash:{PROMPT_VERSION}"
        )


class AnnotatePageTests(unittest.TestCase):
    def test_falls_back_to_next_model_on_bad_json(self) -> None:
        good = envelope(
            '{"acts": {"a1": "correct", "b2": "partial"},'
            ' "missed_nomeacoes": 0, "missed_exoneracoes": 2}'
        )
        responses = [(200, envelope("texto livre")), (200, good)]
        models = []

        class Caller:
            def post(self, url, headers, payload):
                models.append(payload["model"])
                return responses.pop(0)

        model, annotation, raw_sha = annotate_page(
            caller=Caller(),
            api_key="k",
            image_uri="data:x",
            acts=ACTS,
            sleep=lambda _s: None,
        )
        self.assertEqual(models, ["gemini-flash-latest", "gemini-flash-lite-latest"])
        self.assertEqual(model, models[-1])
        self.assertEqual(annotation.missed_exoneracoes, 2)
        self.assertRegex(raw_sha, r"^[a-f0-9]{64}$")

    def test_contract_failure_raises_without_stopping_the_batch(self) -> None:
        class Caller:
            def post(self, url, headers, payload):
                return 200, envelope("não sei")

        with self.assertRaises(RuntimeError) as raised:
            annotate_page(
                caller=Caller(),
                api_key="k",
                image_uri="data:x",
                acts=ACTS,
                sleep=lambda _s: None,
            )
        self.assertNotIsInstance(raised.exception, QuotaExhausted)

    def test_quota_on_every_model_waits_once_then_stops_the_batch(self) -> None:
        class Caller:
            calls = 0

            def post(self, url, headers, payload):
                Caller.calls += 1
                # Cota num alias, modelo aposentado no outro.
                if payload["model"] == "gemini-flash-latest":
                    return 429, b'{"error": "quota"}'
                return 404, b'{"error": "gone"}'

        slept = []
        with self.assertRaises(QuotaExhausted) as raised:
            annotate_page(
                caller=Caller(),
                api_key="k",
                image_uri="data:x",
                acts=ACTS,
                sleep=slept.append,
            )
        self.assertEqual(Caller.calls, 4)
        self.assertIn(QUOTA_RETRY_SECONDS, slept)
        self.assertIn("HTTP 429", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
