import type { IntegralGazetteEdition } from "./integral-gazette-documents";

export type IntegralGazetteIndexDocument = Readonly<{
  documentId: string;
  literalTitle: string;
  documentType: string | null;
  pageStart: number;
  pageEnd: number;
  textSha256: string;
  publicationStatus: "validated" | "edition_fallback";
  permalink: string;
}>;

export type IntegralGazetteIndexEdition = Readonly<{
  edition: number;
  editionYear: number;
  editionDate: string | null;
  artifactSha256: string;
  officialPublicationUrl: string | null;
  catalogUrl: string | null;
  catalogDate: string | null;
  documents: readonly IntegralGazetteIndexDocument[];
}>;

export function toIntegralGazetteIndex(
  editions: readonly IntegralGazetteEdition[],
): readonly IntegralGazetteIndexEdition[];
