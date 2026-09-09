import type { PharmacyPublication } from '../../../lib/pharmacy-publication.mjs';
import { formatBrlDecimal } from '../../../lib/revenues';
import type { ReactNode } from 'react';
import type { PharmacyCoverage } from '../../../lib/pharmacy-coverage.mjs';


export function PharmacyPayments({ publication, coverage, filters, navigation }: { publication: PharmacyPublication; coverage?: PharmacyCoverage; filters?: ReactNode; navigation?: ReactNode }) {
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
      {coverage.status==='unavailable' ? <p>A contagem do ano está temporariamente indisponível. Isso não significa ausência de pagamentos.</p> :
        coverage.status==='pending' ? <p>Ainda não há pagamentos aprovados para exibição neste ano. Isso não significa que a fonte oficial informou zero.</p> : <>
          <p><strong>{coverage.published_documents} pagamentos publicados em {coverage.year}</strong>, de {coverage.establishments} estabelecimentos com identidade conferida.</p>
          <p>Documentos de {coverage.first_date?.split('-').reverse().join('/')} a {coverage.last_date?.split('-').reverse().join('/')}.
            A contagem considera todas as páginas do ano selecionado.</p>
          <p><strong>Cobertura parcial.</strong> Documentos cuja identidade do estabelecimento ainda não foi comprovada ficam fora da lista.
            As datas acima não comprovam coleta completa de todos os meses. O cadastro atual não confirma o credenciamento no passado.</p>
        </>}
    </aside>}
    {publication.status !== 'ready' ? <aside className="transfer-reading-guide" aria-labelledby="pharmacy-status">
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
    </ul>
    <p>O cadastro de estabelecimentos ativos informa a situação atual. Ele não prova que
      uma farmácia estava credenciada durante todo um período passado.</p>
  </section>;
}
