export const EXPENSE_CLASSIFICATION_SOURCE_URL: string;

export type ExpenseDescriptionClassification = Readonly<{
  displayDescription: string;
  sourceDescription: string;
  sourceWasTruncated: boolean;
  classificationStatus: "official_code_match" | "source_only" | "source_conflict";
}>;

export function classifyExpenseDescription(
  expenseCode: string,
  sourceDescription: string,
): ExpenseDescriptionClassification;
