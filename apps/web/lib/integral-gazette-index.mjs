export function getIntegralGazetteListState({ state, editionCount, catalogCount, query, pageNumber }) {
  if (state !== "available") return "unavailable";
  if (editionCount > 0) return "available";
  if (query) return "search_empty";
  if (pageNumber > 1) return "page_empty";
  return (catalogCount ?? 0) > 0 ? "catalog_only" : "empty";
}

export function toIntegralGazetteIndex(editions) {
  return editions.map((edition) => ({
    edition: edition.edition,
    editionYear: edition.editionYear,
    editionDate: edition.editionDate,
    artifactSha256: edition.artifactSha256,
    officialPublicationUrl: edition.officialPublicationUrl,
    catalogUrl: edition.catalogUrl,
    catalogDate: edition.catalogDate,
    documents: edition.documents.map((document) => ({
      documentId: document.documentId,
      literalTitle: document.literalTitle,
      documentType: document.documentType,
      pageStart: document.pageStart,
      pageEnd: document.pageEnd,
      textSha256: document.textSha256,
      publicationStatus: document.publicationStatus,
      permalink:
        `/diario/${edition.editionYear}/${edition.edition}` +
        `#document-${document.documentId}`,
    })),
  }));
}
