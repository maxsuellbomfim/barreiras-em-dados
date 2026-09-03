export type StateLoaStudyEnvelope = Readonly<{
  amendmentRows: readonly unknown[];
  executionRows: readonly unknown[];
  totalCount: number;
  catalogCount: number;
  availableAuthors: readonly StateLoaStudyAuthor[];
  methodologyVersion: "bahia-state-loa-study/1.1.0";
}>;

export type StateLoaStudyExecutionStatus =
  | "execution_confirmed"
  | "ambiguous_official_key"
  | "not_found_in_execution_source"
  | "official_link_key_unavailable"
  | "scope_not_available";

export type StateLoaStudyAuthor = Readonly<{
  authorKey: string;
  authorName: string;
}>;

export type StateLoaStudyFilters = Readonly<{
  page: number;
  authorKey: string | null;
  executionStatus: StateLoaStudyExecutionStatus | null;
  query: string | null;
}>;

export function parseStateLoaStudyRows(
  rows: unknown,
): StateLoaStudyEnvelope | null;

export function resolveStateLoaStudyPage(rawPage: unknown): number;

export function resolveStateLoaStudyFilters(params: Readonly<{
  estadual_pagina?: unknown;
  estadual_autor?: unknown;
  estadual_situacao?: unknown;
  estadual_q?: unknown;
}>): StateLoaStudyFilters;

export function stateLoaStudyPageHref(
  fiscalYear: number,
  page: number,
  filters?: Partial<StateLoaStudyFilters>,
): string;
