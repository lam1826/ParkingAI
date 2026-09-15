// Old endpoints omit both credit fields. A partially populated new response is
// invalid: treating it as zero credit could collect the same money twice.
export function settlementAmounts(quote) {
  const gross = quote?.parking_fee;
  if (!Number.isSafeInteger(gross) || gross < 0) return null;
  if (quote.online_paid === undefined && quote.balance_due === undefined) return { gross, paid: 0, due: gross };
  const paid = quote.online_paid, due = quote.balance_due;
  if (!Number.isSafeInteger(paid) || paid < 0 || !Number.isSafeInteger(due) || due < 0
      || due !== Math.max(gross - paid, 0)) return null;
  return { gross, paid, due };
}
