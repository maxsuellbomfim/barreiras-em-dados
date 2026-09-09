import json
import unittest
from unittest.mock import MagicMock, Mock, patch

from barreiras_collectors.collection_control import CollectionOutcome
from barreiras_collectors.commands.refresh_fns_pharmacy import refresh_year


class PharmacyPipelineTests(unittest.TestCase):
    def test_cli_configuration_failure_is_nonzero_and_sanitized(self):
        import io
        from contextlib import redirect_stdout

        from barreiras_collectors.commands.refresh_fns_pharmacy import main

        output = io.StringIO()
        with (
            patch(
                "barreiras_collectors.settings.PersistenceSettings.from_env",
                side_effect=RuntimeError("PRIVATE_CONFIGURATION"),
            ),
            redirect_stdout(output),
        ):
            code = main(["--year", "2025", "--directory", "unused"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "failed")
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_acquisition_to_verified_import_with_real_parsers(self):
        from barreiras_collectors.http import HttpResponse

        from tests.collectors.test_fns_collection_resume import Store
        from tests.collectors.test_fns_pharmacy_identity import register
        from tests.collectors.test_fns_pharmacy_reconciliation import observation
        from tests.collectors.test_fns_pharmacy_refresh import append_payment

        before = observation()
        before["payment_capture"]["received_at"] = "2026-09-09T00:00:00Z"
        after = append_payment(before)
        reg = register()
        reg["retrieved_at"] = "2026-09-09T00:00:00Z"
        self.repository.load_baseline.return_value = dict(
            snapshot_id=1, approved=True, observation=before, register=reg
        )
        self.repository.transaction.return_value = MagicMock()
        self.repository.verify_publication.return_value = True
        bodies = {}
        self.args["object_store"].put_if_absent.side_effect = lambda **kw: (
            bodies.update({kw["object_key"]: kw["body"]})
        )
        self.args["object_store"].read.side_effect = bodies.__getitem__
        self.args["store"] = Store()
        self.args["sleep"] = lambda _: None

        def get(url, **kw):
            self.control.__enter__.assert_called_once()
            body = after["payment_capture"]["body"]
            if "/entidades?" in url:
                body = json.dumps(
                    dict(
                        resultado=dict(
                            dados=[
                                dict(
                                    cpfCnpj=before["beneficiary"],
                                    uf="BA",
                                    codigoMunicipioIBGE="290320",
                                )
                            ],
                            total=1,
                            pagina=0,
                            totalPaginas=1,
                            itensPorPagina=10,
                        )
                    )
                ).encode()
            return HttpResponse(200, {"Content-Type": "application/json"}, body, url)

        self.args["transport"].get.side_effect = get
        result = refresh_year(**self.args)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["verified_documents"], 2)
        self.repository.import_plan.assert_called_once()
        self.repository.verify_publication.assert_called_once()
        self.assertEqual(len(bodies), 2)
        self.assertEqual(self.args["transport"].get.call_count, 2)
        self.assertNotIn("DO_NOT_EXPOSE", json.dumps(result))

    def setUp(self):
        self.control = MagicMock()
        self.control.__enter__.return_value = self.control
        self.repository = Mock()
        self.repository.known_scope_keys.return_value = set()
        self.args = dict(
            year=2025,
            control=self.control,
            store=Mock(),
            transport=Mock(),
            repository=self.repository,
            object_store=Mock(),
        )

    def acquire(self, year, store, transport, **kwargs):
        self.control.__enter__.assert_called_once()
        kwargs["observations"].extend(self.observations)
        return dict(
            status=self.acquisition_status,
            pages_preserved=3,
            catalog_entities=len(self.observations),
            requests=3,
        )

    def run_pipeline(
        self, observations=None, acquisition_status="complete", status="published"
    ):
        self.observations = (
            observations if observations is not None else [self.observation()]
        )
        self.acquisition_status = acquisition_status
        with (
            patch(
                "barreiras_collectors.commands.refresh_fns_pharmacy.collect_year",
                self.acquire,
            ),
            patch(
                "barreiras_collectors.commands.refresh_fns_pharmacy.execute_refresh",
                return_value=dict(
                    status=status, retained_documents=1, added_documents=1
                ),
            ) as execute,
        ):
            result = refresh_year(**self.args)
        return result, execute

    def observation(self, program="FARMACIA POPULAR", pages=1):
        return dict(
            beneficiary="private-id",
            payment_year=2025,
            payment_captures=[
                dict(
                    body=json.dumps(
                        dict(resultado=dict(dados=[dict(nomeComponente=program)]))
                    ).encode()
                )
            ]
            * pages,
        )

    def test_complete_requires_public_verification_not_just_acquisition(self):
        result, execute = self.run_pipeline()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["verified_documents"], 2)
        execute.assert_called_once()
        self.assertEqual(
            self.control.complete.call_args.kwargs["outcome"],
            CollectionOutcome.COMPLETE,
        )
        self.assertNotIn("private-id", json.dumps(result))

    def test_pause_and_failure_never_publish(self):
        result, execute = self.run_pipeline(acquisition_status="partial")
        self.assertEqual(result["status"], "partial")
        execute.assert_not_called()
        self.control.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "^Pharmacy acquisition failed$"):
            self.run_pipeline(acquisition_status="failed")

    def test_multi_page_identity_review_and_missing_scope_stay_partial(self):
        result, execute = self.run_pipeline([self.observation(pages=2)])
        self.assertEqual(result["pending_scopes"], 1)
        self.assertEqual(result["status"], "partial")
        execute.assert_not_called()
        self.control.reset_mock()
        result, _ = self.run_pipeline(status="review_required")
        self.assertEqual(result["status"], "partial")
        self.control.reset_mock()
        self.repository.known_scope_keys.return_value = {"missing-scope"}
        result, _ = self.run_pipeline()
        self.assertEqual(result["missing_scopes"], 1)
        self.assertEqual(result["status"], "partial")

    def test_other_program_never_becomes_pharmacy_or_zero(self):
        result, execute = self.run_pipeline(
            [self.observation(program="OUTRO PROGRAMA")]
        )
        self.assertEqual(result["excluded_scopes"], 1)
        self.assertEqual(result["verified_documents"], 0)
        self.assertEqual(result["status"], "complete")
        execute.assert_not_called()

    def test_pending_review_is_preserved_privately_without_public_identifiers(self):
        result, _ = self.run_pipeline(status="review_required")
        self.args["store"].save.assert_called_once()
        key, review = self.args["store"].save.call_args.args
        self.assertEqual(len(key), 64)
        self.assertEqual(review["kind"], "pharmacy_review")
        self.assertEqual(len(review["items"]), 1)
        self.assertEqual(review["items"][0]["reason"], "identity_or_document_conflict")
        self.assertNotIn("items", result)

    def test_official_empty_without_history_is_empty_not_failed(self):
        result, execute = self.run_pipeline([], acquisition_status="empty")
        self.assertEqual(result["status"], "empty")
        execute.assert_not_called()
        self.control.reset_mock()
        self.repository.known_scope_keys.return_value = {"missing"}
        result, _ = self.run_pipeline([], acquisition_status="empty")
        self.assertEqual(result["status"], "partial")
