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

// "Сегодня" по МЕСТНОМУ времени браузера, в формате YYYY-MM-DD — так же,
// как хранятся date_odds (обычные календарные даты без часового пояса).
// `new Date().toISOString()` даёт дату по UTC, а не по местному времени —
// для Владивостока (UTC+10) это создаёт разрыв в 10 часов: ночью/утром по
// местному времени UTC-дата ещё "вчерашняя", из-за чего сегодняшние
// операции ошибочно считались бы будущими (см. HANDOVER.md, 2026-09-11).
export function todayIso() {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
