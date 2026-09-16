/** The source control identifies the owner; a municipal fund has its own CNPJ. */
export function pncpProcurementSourceUrl(control: string): string | null {
  const match = /^([0-9]{14})-1-([0-9]{1,12})\/([0-9]{4})$/.exec(control);
  if (!match || match[0] !== control || Number(match[2]) <= 0) return null;
  return `https://pncp.gov.br/app/editais/${match[1]}/${match[3]}/${Number(match[2])}`;
}
