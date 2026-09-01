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
