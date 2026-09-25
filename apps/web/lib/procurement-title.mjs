// Apresentação do objeto da contratação, sem alterar o texto do PNCP: o
// prefixo de plataforma ("[LICITANET] - ") vira etiqueta e títulos todos em
// maiúsculas são marcados para um estilo que grita menos. Não convertemos a
// caixa: siglas (UBS, CBUQ, SME) se perderiam.
const PLATFORM_PREFIX = /^\s*\[([\p{L}\p{N} ]{2,30})\]\s*[-–—:]\s*/u;

export function splitProcurementTitle(objeto) {
  const text = typeof objeto === "string" ? objeto : "";
  const match = text.match(PLATFORM_PREFIX);
  const rest = match ? text.slice(match[0].length) : text;
  const platform = match
    ? match[1].trim().charAt(0).toLocaleUpperCase("pt-BR") +
      match[1].trim().slice(1).toLocaleLowerCase("pt-BR")
    : null;
  const letters = rest.match(/\p{L}/gu) ?? [];
  const upper = letters.filter((letter) => letter !== letter.toLocaleLowerCase("pt-BR"));
  const allCaps = letters.length >= 12 && upper.length / letters.length >= 0.8;
  return { platform, text: rest.trim() || text.trim(), allCaps };
}
