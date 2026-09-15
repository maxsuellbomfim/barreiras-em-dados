import type { PharmacyPublication } from '../../../lib/pharmacy-publication.mjs';
import { formatBrlDecimal } from '../../../lib/revenues';
import type { ReactNode } from 'react';
import type { PharmacyCoverage } from '../../../lib/pharmacy-coverage.mjs';


export function PharmacyPayments({ publication, coverage, filters, navigation, filtered=false, firstPageHref }: { publication: PharmacyPublication; coverage?: PharmacyCoverage; filters?: ReactNode; navigation?: ReactNode; filtered?:boolean; firstPageHref?:string }) {
  return <section className="section" aria-labelledby="pharmacy-title">
    <div className="section-heading">
      <span className="eyebrow">Saúde · Farmácia Popular</span>
      <h1 id="pharmacy-title">Pagamentos a estabelecimentos em Barreiras</h1>
      <p>Esta consulta é separada das receitas da Prefeitura e dos rankings de emendas.
        Pagamento a uma farmácia privada não significa dinheiro recebido pelo município.</p>
    </div>
    {filters}
    {coverage && <aside className="transfer-reading-guide" aria-labelledby="pharmacy-coverage">
      <h2 id="pharmacy-coverage">Cobertura da publicação</h2>
      {coverage.status==='unavailable' ? <p>A contagem {filtered?'deste filtro':'do ano'} está temporariamente indisponível. Isso não significa ausência de pagamentos.</p> :
        coverage.status==='pending' ? <p>Ainda não há pagamentos aprovados para exibição neste ano. Isso não significa que a fonte oficial informou zero.</p> : <>
          <p><strong>{coverage.published_documents} pagamentos publicados em {coverage.year}</strong>, de {coverage.establishments} {coverage.establishments===1?'estabelecimento':'estabelecimentos'} com identidade conferida.</p>
          <p>Documentos de {coverage.first_date?.split('-').reverse().join('/')} a {coverage.last_date?.split('-').reverse().join('/')}.
            {coverage.filter_applied ? ' A contagem considera todas as páginas do estabelecimento selecionado neste ano.' : ' A contagem considera todas as páginas do ano selecionado.'}</p>
          <p><strong>Cobertura parcial.</strong> Documentos sem validação suficiente ficam fora da lista.
            As datas acima não comprovam coleta completa de todos os meses. O cadastro atual não confirma o credenciamento no passado.</p>
        </>}
    </aside>}
    <aside className="transfer-reading-guide pharmacy-scope-guide" aria-labelledby="pharmacy-scope-title">
      <h2 id="pharmacy-scope-title">Por que uma farmácia pode não aparecer?</h2>
      <p>Esta lista é parcial: mostra pagamentos com documentos e identidade conferidos,
        não a relação completa de farmácias credenciadas.</p>
      <p>Quando uma rede recebe pela matriz, o pagamento não informa, por si só, quanto
        corresponde a cada filial. Sem esse detalhamento, o total da rede não é atribuído a Barreiras.</p>
      <p><strong>Não encontrar uma farmácia aqui não comprova que ela deixou de receber
        ou de atender pelo programa.</strong> Consulte também o cadastro oficial nas fontes abaixo.</p>
    </aside>
    {publication.status === 'empty_page' ? <aside className="transfer-reading-guide pharmacy-page-status" aria-labelledby="pharmacy-status">
      <h2 id="pharmacy-status">Nenhum pagamento nesta página</h2>
      <p>A consulta não retornou registros para esta página do ano {publication.year}.
        Isso não comprova ausência de pagamentos no ano ou na fonte oficial.</p>
      <p><a href={firstPageHref??`?ano=${publication.year}`}>Voltar à primeira página</a> para conferir os registros {filtered?'do estabelecimento e ano selecionados':'do ano selecionado'}.</p>
    </aside> : publication.status !== 'ready' ? <aside className="transfer-reading-guide" aria-labelledby="pharmacy-status">
      <h2 id="pharmacy-status">{publication.status === 'pending' ? 'Publicação dos pagamentos em preparação' : 'Dados temporariamente indisponíveis'}</h2>
      <p>{publication.status === 'pending' ? 'Ainda não há registros liberados nesta página. Estamos conferindo os estabelecimentos e as evidências antes de exibir os valores.' : 'Não foi possível validar os registros para exibição. Os valores foram omitidos até a conferência.'}</p>
      <p>Isso não significa que os pagamentos foram zero ou que não existem na fonte oficial.</p>
    </aside> : <>
      <h2>Registros de {publication.year}</h2>
      <p>Valores informados pelo FNS. Não comprovam, isoladamente, a execução do serviço.
        Este recorte não representa necessariamente todos os pagamentos do ano.</p>
      <ul>{publication.records.map(row => <li key={row.id} className="transfer-reading-guide">
        <h3>{row.establishment}</h3>
        <dl><dt>Data do documento de pagamento</dt><dd>{row.date.split('-').reverse().join('/')}</dd>
          <dt>Valor líquido informado pelo FNS</dt><dd>{formatBrlDecimal(row.amount)}</dd></dl>
        <details><summary>Identificação da evidência preservada</summary>
          <p style={{overflowWrap:'anywhere'}}>SHA-256: <code>{row.sha256}</code></p></details>
      </li>)}</ul>
    </>}
    {navigation}
    <h2>Consulte as fontes oficiais</h2>
    <ul>
      <li><a href="https://consultafns.saude.gov.br/#/detalhada" target="_blank" rel="noreferrer">Consulta detalhada de pagamentos do FNS (abre outra aba)</a></li>
      <li><a href="https://infoms.saude.gov.br/extensions/SEIDIGI_DEMAS_PFPB_ENDERECOS/index.html" target="_blank" rel="noreferrer">Estabelecimentos ativos no Farmácia Popular (abre outra aba)</a></li>
      <li><a href="https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/renovacao-de-estabelecimentos-participantes/empresas-credenciadas-para-realizar-a-renovacao-2025/view" target="_blank" rel="noreferrer">Lista oficial de renovação cadastral de 2025 (abre outra aba)</a></li>
    </ul>
    <p>O cadastro de estabelecimentos ativos informa a situação atual. Ele não prova que
      uma farmácia estava credenciada durante todo um período passado.</p>
    <p>A lista de renovação de 2025 ajuda a conferir a identidade dos estabelecimentos.
      Ela não comprova credenciamento nos anos anteriores.</p>
  </section>;
}
