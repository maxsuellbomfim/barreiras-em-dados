const DECIMAL = /^(0|[1-9]\d*)(?:\.(\d{1,2}))?$/;

function decimalToCents(value) {
  const match = DECIMAL.exec(value);
  if (!match) throw new TypeError("invalid parliamentary transfer amount");
  const fraction = (match[2] ?? "").padEnd(2, "0");
  return (BigInt(match[1]) * 100n) + BigInt(fraction || "0");
}

function centsToDecimal(value) {
  const whole = value / 100n;
  const fraction = String(value % 100n).padStart(2, "0");
  return `${whole}.${fraction}`;
}

/**
 * Resume somente o ano mais recente da API atual. Todos os cálculos usam
 * centavos inteiros; campos ausentes continuam ausentes e nunca viram zero.
 *
 * @param {readonly {
 *   fiscalYear: number,
 *   destinationAmount: string,
 *   committedAmount: string | null,
 *   paidAmount: string | null,
 * }[]} transfers
 */
export function buildCurrentTransferCitizenSummary(transfers) {
  if (transfers.length === 0) return null;

  const fiscalYear = Math.max(...transfers.map((transfer) => transfer.fiscalYear));
  const current = transfers.filter((transfer) => transfer.fiscalYear === fiscalYear);
  let destinationCents = 0n;
  let committedCents = 0n;
  let paidCents = 0n;
  let destinationWithoutPaymentCents = 0n;
  let commitmentFoundCount = 0;
  let paymentFoundCount = 0;

  for (const transfer of current) {
    const destination = decimalToCents(transfer.destinationAmount);
    destinationCents += destination;

    if (transfer.committedAmount !== null) {
      committedCents += decimalToCents(transfer.committedAmount);
      commitmentFoundCount += 1;
    }
    if (transfer.paidAmount !== null) {
      paidCents += decimalToCents(transfer.paidAmount);
      paymentFoundCount += 1;
    } else {
      destinationWithoutPaymentCents += destination;
    }
  }

  return {
    fiscalYear,
    transferCount: current.length,
    destinationAmount: centsToDecimal(destinationCents),
    committedAmount: commitmentFoundCount === 0
      ? null
      : centsToDecimal(committedCents),
    paidAmount: paymentFoundCount === 0 ? null : centsToDecimal(paidCents),
    commitmentFoundCount,
    paymentFoundCount,
    paymentNotFoundCount: current.length - paymentFoundCount,
    destinationWithoutPaymentAmount: centsToDecimal(destinationWithoutPaymentCents),
  };
}
