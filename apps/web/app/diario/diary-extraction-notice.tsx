export function DiaryExtractionNotice() {
  return (
    <aside className="collection-unavailable" aria-label="Limitações do texto extraído">
      <div>
        <strong>A extração do texto está em revisão</strong>
        <p>
          Identificamos páginas do acervo com texto incompleto. A leitura automática
          também pode errar nomes, números e tabelas. O texto disponível não substitui
          o documento oficial.
        </p>
        <p>
          Confira a publicação oficial quando o link estiver disponível. Não encontrar
          um nome ou assunto na busca não prova que ele não esteja no Diário.
          O hash identifica o arquivo ou texto preservado; não comprova que a
          extração está completa ou correta.
        </p>
      </div>
    </aside>
  );
}
