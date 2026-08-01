export function fmt(amount, currency = "RUB") {
  const symbols = { RUB: "₽", CNY: "¥", USD: "$", EUR: "€" };
  const value = Number(amount || 0).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${value} ${symbols[currency] || currency}`;
}

export function fmtDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("ru-RU");
}
