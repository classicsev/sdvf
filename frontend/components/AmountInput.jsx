"use client";

// Текстовое поле суммы с живым разделением тысяч (1 251 021), в отличие от
// нативного <input type="number">, который всегда показывает "1251021" без
// пробелов — это ограничение самого браузера, не поправить CSS/атрибутами.
// Наружу отдаёт обычную числовую строку с точкой ("1251021.5"), формат
// значения для остального кода (Number(form.amount) и т.п.) не меняется.

function formatThousands(intDigits) {
  return intDigits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function toDisplay(raw) {
  const str = String(raw ?? "").trim();
  if (!str) return "";
  const normalized = str.replace(",", ".");
  const [intPart, decPart] = normalized.split(".");
  const sign = intPart.startsWith("-") ? "-" : "";
  const digitsOnly = intPart.replace(/[^\d]/g, "");
  const formattedInt = sign + formatThousands(digitsOnly);
  return decPart !== undefined ? `${formattedInt},${decPart}` : formattedInt;
}

function toRaw(display) {
  const cleaned = display.replace(/[^\d,.\-]/g, "");
  const firstSepIndex = Math.max(cleaned.indexOf(","), cleaned.indexOf("."));
  if (firstSepIndex === -1) return cleaned;
  const intPart = cleaned.slice(0, firstSepIndex).replace(/[,.]/g, "");
  const decPart = cleaned.slice(firstSepIndex + 1).replace(/[,.\-]/g, "");
  return `${intPart}.${decPart}`;
}

export default function AmountInput({ value, onChange, onWheel, style, ...rest }) {
  return (
    <input
      type="text"
      inputMode="decimal"
      value={toDisplay(value)}
      onChange={(e) => onChange(toRaw(e.target.value))}
      onWheel={onWheel ?? ((e) => e.target.blur())}
      style={style}
      {...rest}
    />
  );
}
