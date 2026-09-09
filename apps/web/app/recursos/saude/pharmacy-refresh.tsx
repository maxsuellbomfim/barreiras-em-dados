import type { PharmacyRefresh } from '../../../lib/pharmacy-refresh.mjs';

const formatTime=(value:string)=>new Intl.DateTimeFormat('pt-BR',{
  dateStyle:'short',timeStyle:'short',timeZone:'America/Sao_Paulo',
}).format(new Date(value));

export function PharmacyRefreshStatus({refresh}:{refresh:PharmacyRefresh}) {
  return <aside className="transfer-reading-guide" aria-labelledby="pharmacy-update">
    <h2 id="pharmacy-update">Atualização dos pagamentos</h2>
    {refresh.status==='unavailable' ? <p>Não foi possível consultar o estado da atualização. Isso não significa que não existam pagamentos.</p> :
     refresh.status==='not_started' ? <p>Ainda não há uma execução da atualização automática registrada para este ano. Os pagamentos já conferidos continuam disponíveis.</p> : <>
       {refresh.last_attempt_at && <p>Última tentativa: <time dateTime={refresh.last_attempt_at}>{formatTime(refresh.last_attempt_at)}</time> (horário de Brasília).</p>}
       {refresh.status==='failed' && <p>A última tentativa falhou. Ela não confirma atualização dos dados publicados.</p>}
       {refresh.status==='running' && <p>Há uma execução iniciada, ainda sem conclusão registrada. Não é possível confirmar a atualização.</p>}
       {refresh.status==='partial' && <p>A consulta ficou parcial. Nem todos os dados puderam ser conferidos para publicação.</p>}
       {refresh.status==='complete' && <p>A consulta e as verificações previstas nessa execução foram concluídas. Isso não comprova a execução dos serviços nem cobertura histórica integral.</p>}
       {refresh.status==='empty' && <p>A fonte retornou um catálogo vazio nessa consulta. Isso não equivale a afirmar que não houve pagamentos no ano.</p>}
       {refresh.last_verified_at && <p>Última conferência com pagamentos validados: <time dateTime={refresh.last_verified_at}>{formatTime(refresh.last_verified_at)}</time>.</p>}
       {refresh.verified_documents!==null && <p>{refresh.verified_documents} documentos conferidos nessa execução. Esta contagem não deve ser somada aos pagamentos publicados.</p>}
       {refresh.pending_scopes!==null && <p>{refresh.pending_scopes} consultas de estabelecimento/ano pendentes de validação. Não representam uma contagem de pagamentos.</p>}
       {!!refresh.missing_scopes && <p>{refresh.missing_scopes} consultas anteriormente registradas não foram encontradas no catálogo consultado. A ausência precisa ser verificada; não indica, por si só, exclusão ou irregularidade.</p>}
     </>}
  </aside>;
}
