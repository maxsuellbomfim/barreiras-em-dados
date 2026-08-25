from __future__ import annotations

import unittest
from dataclasses import replace

from barreiras_collectors.connectors.tcm_ba import (
    TcmBaContractError,
    TcmBaPublicAccountsClient,
    validate_tcm_ba_catalog,
)
from barreiras_collectors.http import HttpResponse
from barreiras_collectors.resilience import CircuitBreaker, RetryPolicy

FORM = "consultaPublicaTabPanel:consultaPublicaPCSearchForm"


def _form(*, monthly: bool, year: bool, city: bool, unit: bool = False) -> bytes:
    months = '<option value="9">04/2023</option>' if city or unit else ""
    selected_period = ' selected="selected"' if monthly else ""
    selected_year = ' selected="selected"' if year else ""
    selected_city = ' selected="selected"' if city else ""
    selected_unit = ' selected="selected"' if unit else ""
    return f"""
    <form id="{FORM}" action="/epp/ConsultaPublica/listView.seam">
      <input name="{FORM}" value="{FORM}" />
      <input name="{FORM}:j_idt40-value" value="true" />
      <select name="{FORM}:PeriodicidadePC_input">
        <option>Clique para selecionar</option>
        <option value="1">Anual</option>
        <option value="2"{selected_period}>Mensal</option>
      </select>
      <select name="{FORM}:competenciaPCAno_input">
        <option>Clique para selecionar</option>
        <option value="4"{selected_year}>2023</option>
      </select>
      <select name="{FORM}:competenciaPCMes_input">
        <option>Clique para selecionar</option>{months}
      </select>
      <select name="{FORM}:municipio_input">
        <option>Clique para selecionar</option>
        <option value="38"{selected_city}>BARREIRAS</option>
      </select>
      <select name="{FORM}:unidadeJurisdicionada_input">
        <option>Clique para selecionar</option>
        <option value="641"{selected_unit}>Prefeitura Municipal de BARREIRAS</option>
      </select>
      <select name="{FORM}:tipoPC_input">
        <option>Clique para selecionar</option>
        <option value="1">Gestão</option>
      </select>
      <select name="{FORM}:status_input">
        <option>Clique para selecionar</option>
      </select>
      <input name="{FORM}:searchButton" value="Pesquisar" type="submit" />
      <input name="{FORM}:clearButton" value="Limpar" type="submit" />
      <input name="javax.faces.ViewState"
             value="state-{int(monthly)}-{int(year)}-{int(city)}" />
    </form>
    """.encode()


def _partial(body: bytes, state: str, *, update_id: str | None = None) -> bytes:
    update = (
        f'<update id="{update_id}"><![CDATA['.encode()
        if update_id
        else b"<update><![CDATA["
    )
    return (
        b"<partial-response><changes>"
        + update
        + body
        + b']]></update><update id="javax.faces.ViewState"><![CDATA['
        + state.encode()
        + b"]]></update></changes></partial-response>"
    )


def _state_only(state: str) -> bytes:
    return (
        b'<partial-response><changes><update id="javax.faces.ViewState"><![CDATA['
        + state.encode()
        + b"]]></update></changes></partial-response>"
    )


SEARCH = b"""
<tbody id="consultaPublicaTabPanel:consultaPublicaDataTable:tb">
  <tr><td><form id="submission-form"><a>Selecionar</a></form></td>
  <td>04/2023</td><td>Gestao</td><td>Prefeitura Municipal de BARREIRAS</td>
  <td>05/06/2023</td><td>Entregue no prazo</td></tr>
</tbody><input name="javax.faces.ViewState" value="search-state" />
"""


DETAIL_1 = b"""
<form id="consultaPublicaTabPanel:j_idt36">
  <input name="consultaPublicaTabPanel:j_idt36"
         value="consultaPublicaTabPanel:j_idt36" />
</form>
<span
 id="consultaPublicaTabPanel:unidadeJurisdicionadaDecoration:unidadeJurisdicionada">
Prefeitura Municipal de BARREIRAS</span>
<script id="consultaPublicaTabPanel:tabelaDocumentos_s">rowCount:11</script>
<tbody id="consultaPublicaTabPanel:tabelaDocumentos_data">
  <tr><td><form id="doc-1"><a>arquivo</a></form></td><td>Documentos Adicionais</td>
  <td>PMB BALANCETE PARTE 1-2.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-2"><a>arquivo</a></form></td><td>Documentos Adicionais</td>
  <td>PMB BALANCETE PARTE 2-2.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-3"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>03-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-4"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>04-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-5"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>05-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-6"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>06-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-7"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>07-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-8"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>08-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-9"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>09-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
  <tr><td><form id="doc-10"><a>arquivo</a></form></td><td>Relatorios</td>
  <td>10-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
</tbody><input name="javax.faces.ViewState" value="detail-state-1" />
"""


DETAIL_2 = b"""
<tr><td><form id="doc-11"><a>arquivo</a></form></td><td>Relatorios</td>
<td>11-RELATORIO.pdf</td><td>nome omitido</td><td>31/05/2023</td></tr>
"""


class SequenceSessionTransport:
    def __init__(self, bodies: list[bytes]) -> None:
        self.bodies = list(bodies)
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []
        self.reset_calls = 0

    def reset_session(self) -> None:
        self.reset_calls += 1

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.calls.append(("GET", url, None))
        return self._response(url)

    def post(self, url, *, form, headers, timeout_seconds, max_body_bytes):
        del headers, timeout_seconds, max_body_bytes
        self.calls.append(("POST", url, dict(form)))
        return self._response(url)

    def _response(self, url: str) -> HttpResponse:
        return HttpResponse(
            status=200,
            headers={"Content-Type": "text/html; charset=UTF-8"},
            body=self.bodies.pop(0),
            final_url=url,
        )


class RetryOnceSessionTransport(SequenceSessionTransport):
    def __init__(self, bodies: list[bytes]) -> None:
        super().__init__(bodies)
        self.failed = False

    def get(self, url, *, headers, timeout_seconds, max_body_bytes):
        if not self.failed:
            self.failed = True
            self.calls.append(("GET", url, None))
            return HttpResponse(
                status=503,
                headers={"Retry-After": "0", "X-Api-Key": "never-preserve"},
                body=b"temporarily unavailable",
                final_url=url,
            )
        return super().get(
            url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_body_bytes=max_body_bytes,
        )


class TcmBaPublicAccountsTests(unittest.TestCase):
    def test_fetches_every_catalog_page_and_preserves_each_raw_response(self) -> None:
        transport = SequenceSessionTransport(
            [
                _form(monthly=False, year=False, city=False),
                _state_only("period-preflight-state"),
                _partial(_form(monthly=True, year=False, city=False), "period-state"),
                _state_only("year-preflight-state"),
                _partial(_form(monthly=True, year=True, city=False), "year-state"),
                _state_only("city-preflight-state"),
                _partial(_form(monthly=True, year=True, city=True), "city-state"),
                _state_only("unit-preflight-state"),
                _partial(
                    _form(monthly=True, year=True, city=False, unit=True),
                    "unit-state",
                ),
                _partial(SEARCH, "search-state"),
                _partial(DETAIL_1, "detail-state-1"),
                _partial(
                    DETAIL_2,
                    "detail-state-2",
                    update_id="consultaPublicaTabPanel:tabelaDocumentos",
                ),
            ]
        )

        catalog = TcmBaPublicAccountsClient(
            transport=transport,
            requests_per_minute=600,
        ).fetch_monthly_catalog(year=2023, month=4)

        self.assertEqual(catalog.competence, "04/2023")
        self.assertEqual(catalog.submission.sent_at, "05/06/2023")
        self.assertEqual(catalog.submission.status, "Entregue no prazo")
        self.assertEqual(catalog.total_documents, 11)
        self.assertEqual(len(catalog.documents), 11)
        self.assertEqual(catalog.documents[0].name, "PMB BALANCETE PARTE 1-2.pdf")
        self.assertEqual(catalog.documents[-1].page_number, 2)
        self.assertEqual(len(catalog.interactions), 12)
        self.assertTrue(
            all(len(item.body_sha256) == 64 for item in catalog.interactions)
        )
        validate_tcm_ba_catalog(catalog)
        with self.assertRaises(TcmBaContractError):
            validate_tcm_ba_catalog(replace(catalog, documents=()))

        posted_forms = [call[2] for call in transport.calls if call[0] == "POST"]
        self.assertTrue(
            all(f"{FORM}:clearButton" not in posted for posted in posted_forms)
        )
        self.assertEqual(posted_forms[0][f"{FORM}:PeriodicidadePC_input"], "2")
        self.assertEqual(posted_forms[2][f"{FORM}:competenciaPCAno_input"], "4")
        self.assertEqual(posted_forms[4][f"{FORM}:municipio_input"], "38")
        self.assertEqual(posted_forms[6][f"{FORM}:unidadeJurisdicionada_input"], "641")
        self.assertEqual(posted_forms[7][f"{FORM}:unidadeJurisdicionada_input"], "641")
        self.assertEqual(posted_forms[8][f"{FORM}:competenciaPCMes_input"], "9")
        self.assertEqual(
            posted_forms[8][f"{FORM}:municipio_input"], "Clique para selecionar"
        )
        self.assertEqual(
            posted_forms[9]["javax.faces.source"],
            "submission-form:selecionarPrestacao",
        )
        self.assertEqual(
            posted_forms[-1]["consultaPublicaTabPanel:j_idt36"],
            "consultaPublicaTabPanel:j_idt36",
        )
        self.assertEqual(
            posted_forms[-1]["consultaPublicaTabPanel:tabelaDocumentos_first"], "10"
        )

    def test_renews_long_session_and_resumes_at_next_document_page(self) -> None:
        page_two = b"".join(
            f"""
            <tr><td><form id="doc-{number}"><a>arquivo</a></form></td>
            <td>Relatorios</td><td>{number:02d}-RELATORIO.pdf</td>
            <td>nome omitido</td><td>31/12/2023</td></tr>
            """.encode()
            for number in range(11, 21)
        )
        page_three = b"""
        <tr><td><form id="doc-21"><a>arquivo</a></form></td><td>Relatorios</td>
        <td>21-RELATORIO.pdf</td><td>nome omitido</td><td>31/12/2023</td></tr>
        """
        first_detail = DETAIL_1.replace(b"rowCount:11", b"rowCount:21")
        resumed_detail = first_detail.replace(b"detail-state-1", b"resumed-detail")
        bootstrap = [
            _form(monthly=False, year=False, city=False),
            _state_only("period-preflight-state"),
            _partial(_form(monthly=True, year=False, city=False), "period-state"),
            _state_only("year-preflight-state"),
            _partial(_form(monthly=True, year=True, city=False), "year-state"),
            _state_only("city-preflight-state"),
            _partial(_form(monthly=True, year=True, city=True), "city-state"),
            _state_only("unit-preflight-state"),
            _partial(
                _form(monthly=True, year=True, city=False, unit=True),
                "unit-state",
            ),
            _partial(SEARCH, "search-state"),
        ]
        resumed_bootstrap = [
            body.replace(b"state", b"resumed-state") for body in bootstrap
        ]
        transport = SequenceSessionTransport(
            [
                *bootstrap,
                _partial(first_detail, "detail-state-1"),
                _partial(
                    page_two,
                    "detail-state-2",
                    update_id="consultaPublicaTabPanel:tabelaDocumentos",
                ),
                *resumed_bootstrap,
                _partial(resumed_detail, "resumed-detail"),
                _partial(
                    page_three,
                    "resumed-page-3",
                    update_id="consultaPublicaTabPanel:tabelaDocumentos",
                ),
            ]
        )

        client = TcmBaPublicAccountsClient(
            transport=transport,
            requests_per_minute=600,
        )
        client.max_document_pages_per_session = 2
        try:
            catalog = client.fetch_monthly_catalog(year=2023, month=4)
        except TcmBaContractError as error:
            self.fail(f"A sessão longa não foi retomada: {type(error).__name__}")

        self.assertEqual(transport.reset_calls, 1)
        self.assertEqual(len(catalog.documents), 21)
        self.assertEqual(catalog.documents[-1].page_number, 3)
        page_three_form = next(
            form
            for method, _url, form in reversed(transport.calls)
            if method == "POST"
            and form is not None
            and form.get("consultaPublicaTabPanel:tabelaDocumentos_first") == "20"
        )
        self.assertEqual(page_three_form["javax.faces.ViewState"], "resumed-detail")
        validate_tcm_ba_catalog(catalog)

    def test_rejects_search_result_for_another_competence(self) -> None:
        wrong = SEARCH.replace(b"04/2023", b"03/2023")
        transport = SequenceSessionTransport(
            [
                _form(monthly=False, year=False, city=False),
                _state_only("period-preflight-state"),
                _partial(_form(monthly=True, year=False, city=False), "period-state"),
                _state_only("year-preflight-state"),
                _partial(_form(monthly=True, year=True, city=False), "year-state"),
                _state_only("city-preflight-state"),
                _partial(_form(monthly=True, year=True, city=True), "city-state"),
                _state_only("unit-preflight-state"),
                _partial(
                    _form(monthly=True, year=True, city=False, unit=True),
                    "unit-state",
                ),
                _partial(wrong, "search-state"),
            ]
        )

        with self.assertRaises(TcmBaContractError):
            TcmBaPublicAccountsClient(
                transport=transport,
                requests_per_minute=600,
            ).fetch_monthly_catalog(year=2023, month=4)

    def test_rejects_out_of_scope_month_or_year_before_network(self) -> None:
        transport = SequenceSessionTransport([])
        client = TcmBaPublicAccountsClient(transport=transport)

        with self.assertRaises(ValueError):
            client.fetch_monthly_catalog(year=2014, month=12)
        with self.assertRaises(ValueError):
            client.fetch_monthly_catalog(year=2023, month=13)

        self.assertEqual(transport.calls, [])

    def test_retries_transient_status_and_preserves_sanitized_attempt(self) -> None:
        transport = RetryOnceSessionTransport(
            [
                _form(monthly=False, year=False, city=False),
                _state_only("period-preflight-state"),
                _partial(_form(monthly=True, year=False, city=False), "period-state"),
                _state_only("year-preflight-state"),
                _partial(_form(monthly=True, year=True, city=False), "year-state"),
                _state_only("city-preflight-state"),
                _partial(_form(monthly=True, year=True, city=True), "city-state"),
                _state_only("unit-preflight-state"),
                _partial(
                    _form(monthly=True, year=True, city=False, unit=True),
                    "unit-state",
                ),
                _partial(SEARCH, "search-state"),
                _partial(DETAIL_1.replace(b"rowCount:11", b"rowCount:10"), "detail"),
            ]
        )

        catalog = TcmBaPublicAccountsClient(
            transport=transport,
            requests_per_minute=600,
            retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
            circuit_breaker=CircuitBreaker(failure_threshold=2),
            sleep=lambda _seconds: None,
            random_value=lambda: 0,
        ).fetch_monthly_catalog(year=2023, month=4)

        self.assertEqual([call[0] for call in transport.calls[:2]], ["GET", "GET"])
        self.assertEqual(catalog.interactions[0].stage, "initial-form-attempt-1")
        self.assertEqual(catalog.interactions[0].http_status, 503)
        self.assertEqual(catalog.interactions[0].response_headers, {})
        self.assertEqual(catalog.interactions[1].stage, "initial-form")
        validate_tcm_ba_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
