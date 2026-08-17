"use client";

import { useState } from "react";
import { Wallet, ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown } from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  AreaChart,
  Area,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";

const RANGE_OPTIONS = [
  { key: "today", label: "Сегодня" },
  { key: "week", label: "Неделя" },
  { key: "month", label: "Месяц" },
  { key: "quarter", label: "Квартал" },
  { key: "year", label: "Год" },
];

function formatPeriodLabel(from, to) {
  if (!from || !to) return "";
  if (from === to) return fmtDate(from);
  return `${fmtDate(from)} — ${fmtDate(to)}`;
}

// Процент изменения к прошлому периоду. null = нет базы для сравнения
// (прошлый период был нулевым) — тогда бейдж просто не показываем, а не
// врём "+бесконечность%".
function trendPct(current, prev) {
  if (!prev) return null;
  return ((current - prev) / Math.abs(prev)) * 100;
}

function TrendBadge({ pct, invert }) {
  if (pct === null || !Number.isFinite(pct)) return null;
  // invert: для расхода рост числа — это "хуже", красным, даже если pct > 0
  const isGood = invert ? pct <= 0 : pct >= 0;
  const Icon = pct >= 0 ? TrendingUp : TrendingDown;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        fontSize: 11.5,
        fontFamily: "'IBM Plex Mono', monospace",
        color: isGood ? "var(--accent)" : "var(--expense)",
      }}
      title="К прошлому периоду"
    >
      <Icon size={12} />
      {pct >= 0 ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

function KpiCard({ label, value, tone, icon, periodLabel, trendPctValue, invertTrend }) {
  return (
    <div className={`fp-kpi fp-kpi-${tone}`}>
      <div className="fp-kpi-top">
        <span className="fp-kpi-label">{label}</span>
        <span className="fp-kpi-icon">{icon}</span>
      </div>
      <div className="fp-kpi-value">{value}</div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
        {periodLabel && (
          <span className="fp-muted" style={{ fontSize: 11 }}>
            {periodLabel}
          </span>
        )}
        <TrendBadge pct={trendPctValue} invert={invertTrend} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { token } = useAuth();

  const [range, setRange] = useState("month");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const isCustom = range === "custom";

  const summaryQuery = isCustom
    ? { date_from: customFrom || undefined, date_to: customTo || undefined }
    : { range };
  const { data: summary, loading, error } = useResource(
    () => api.dashboardSummary(token, summaryQuery),
    [token, range, customFrom, customTo]
  );
  const { data: cashflow } = useResource(() => api.cashflowReport(token), [token]);
  const { data: forecast } = useResource(() => api.cashflowForecast(token, { days: 30 }), [token]);

  if (loading) return <div className="fp-loading">Загрузка…</div>;
  if (error) return <div className="fp-error-banner">{error}</div>;
  if (!summary) return null;

  const netFlow = summary.net_flow_rub;
  const prevNetFlow = summary.prev_net_flow_rub;
  const chartData = (cashflow?.by_month || []).slice(-12);
  const periodLabel = formatPeriodLabel(summary.period_from, summary.period_to);
  const forecastData = forecast?.series || [];
  const forecastDelta = forecast ? forecast.projected_balance_rub - forecast.current_balance_rub : 0;

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row" style={{ marginBottom: 4 }}>
        <div className="fp-tabs">
          {RANGE_OPTIONS.map((opt) => (
            <button key={opt.key} className={range === opt.key ? "active" : ""} onClick={() => setRange(opt.key)}>
              {opt.label}
            </button>
          ))}
          <button className={isCustom ? "active" : ""} onClick={() => setRange("custom")}>
            Свой период
          </button>
        </div>
        {isCustom && (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="date" value={customFrom} onChange={(e) => setCustomFrom(e.target.value)} />
            <span className="fp-muted">—</span>
            <input type="date" value={customTo} onChange={(e) => setCustomTo(e.target.value)} />
          </div>
        )}
      </div>

      <section className="fp-kpi-row">
        <KpiCard
          label="Общий остаток"
          value={fmt(summary.total_balance_rub, "RUB")}
          tone="neutral"
          icon={<Wallet size={16} />}
          periodLabel="на сегодня"
        />
        <KpiCard
          label="Приход"
          value={fmt(summary.period_income_rub, "RUB")}
          tone="income"
          icon={<ArrowUpRight size={16} />}
          periodLabel={periodLabel}
          trendPctValue={trendPct(summary.period_income_rub, summary.prev_period_income_rub)}
        />
        <KpiCard
          label="Расход"
          value={fmt(summary.period_expense_rub, "RUB")}
          tone="expense"
          icon={<ArrowDownRight size={16} />}
          periodLabel={periodLabel}
          trendPctValue={trendPct(summary.period_expense_rub, summary.prev_period_expense_rub)}
          invertTrend
        />
        <KpiCard
          label="Чистый поток"
          value={`${netFlow >= 0 ? "+" : ""}${fmt(netFlow, "RUB")}`}
          tone={netFlow >= 0 ? "income" : "expense"}
          icon={netFlow >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
          periodLabel="Приход − Расход за период"
          trendPctValue={trendPct(netFlow, prevNetFlow)}
        />
      </section>

      <section className="fp-grid-2">
        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>Движение денег по месяцам</h3>
          </div>
          {chartData.length === 0 ? (
            <div className="fp-empty">Пока нет операций для построения графика</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#E7E1D3" vertical={false} />
                <XAxis
                  dataKey="period"
                  tick={{ fontFamily: "IBM Plex Sans", fontSize: 12, fill: "#5B6472" }}
                  axisLine={{ stroke: "#E7E1D3" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                  axisLine={false}
                  tickLine={false}
                  width={70}
                  tickFormatter={(v) => v.toLocaleString("ru-RU")}
                />
                <Tooltip
                  formatter={(v) => fmt(v, "RUB")}
                  contentStyle={{ fontFamily: "IBM Plex Sans", fontSize: 13, border: "1px solid #E7E1D3", borderRadius: 6 }}
                />
                <Legend
                  wrapperStyle={{ fontFamily: "IBM Plex Sans", fontSize: 12.5 }}
                  formatter={(value) => (value === "Приход" ? "Приход" : "Расход")}
                />
                <Area type="monotone" dataKey="income" name="Приход" stroke="#2F6F5E" fill="#DCEAE4" strokeWidth={2} />
                <Bar dataKey="expense" name="Расход" fill="#A8503F" radius={[3, 3, 0, 0]} barSize={22} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>Остатки по счетам</h3>
          </div>
          {summary.accounts.length === 0 ? (
            <div className="fp-empty">Нет счетов</div>
          ) : (
            <div className="fp-ledger">
              {summary.accounts.map((a) => (
                <div className="ledger-row" key={a.id}>
                  <span className="label">
                    {a.name}
                    <span className={`fp-currency-badge ${a.currency}`}>{a.currency}</span>
                  </span>
                  <span className="fill" />
                  <span className="value" style={{ color: a.balance < 0 ? "#A8503F" : "#1B2430" }}>
                    {fmt(a.balance, a.currency)}
                    {a.currency !== "RUB" && a.balance_rub !== null && (
                      <span className="fp-sub-value"> ≈ {fmt(a.balance_rub, "RUB")}</span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {forecastData.length > 1 && (
        <section className="fp-panel">
          <div className="fp-panel-head" style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <h3>Прогноз остатка на 30 дней</h3>
            <span className="fp-muted" style={{ fontSize: 12.5 }}>
              По плановым операциям (Отчёты → Планирование): {forecastDelta >= 0 ? "+" : ""}
              {fmt(forecastDelta, "RUB")} к {fmtDate(forecast.horizon_end)}
            </span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={forecastData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#E7E1D3" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={(v) => fmtDate(v)}
                tick={{ fontFamily: "IBM Plex Sans", fontSize: 11, fill: "#5B6472" }}
                axisLine={{ stroke: "#E7E1D3" }}
                tickLine={false}
                minTickGap={30}
              />
              <YAxis
                tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                axisLine={false}
                tickLine={false}
                width={70}
                tickFormatter={(v) => v.toLocaleString("ru-RU")}
              />
              <Tooltip
                labelFormatter={(v) => fmtDate(v)}
                formatter={(v) => fmt(v, "RUB")}
                contentStyle={{ fontFamily: "IBM Plex Sans", fontSize: 13, border: "1px solid #E7E1D3", borderRadius: 6 }}
              />
              <ReferenceLine y={0} stroke="#A8503F" strokeDasharray="3 3" />
              <Area
                type="monotone"
                dataKey="projected_balance_rub"
                name="Прогнозный остаток"
                stroke="#2F6F5E"
                fill="#DCEAE4"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </section>
      )}

      {summary.by_company && summary.by_company.length > 1 && (
        <section className="fp-panel fp-table-panel">
          <div className="fp-panel-head" style={{ padding: "16px 16px 0" }}>
            <h3>По компаниям</h3>
            <span className="fp-muted" style={{ fontSize: 12 }}>
              {periodLabel}
            </span>
          </div>
          <table className="fp-table">
            <thead>
              <tr>
                <th>Компания</th>
                <th className="right">Остаток</th>
                <th className="right">Приход</th>
                <th className="right">Расход</th>
                <th className="right">Чистый поток</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_company.map((row) => {
                const rowNet = row.period_income_rub - row.period_expense_rub;
                return (
                  <tr key={row.company_id}>
                    <td>{row.company_name}</td>
                    <td className="right">{fmt(row.total_balance_rub, "RUB")}</td>
                    <td className="right" style={{ color: "var(--accent)" }}>
                      {fmt(row.period_income_rub, "RUB")}
                    </td>
                    <td className="right" style={{ color: "var(--expense)" }}>
                      {fmt(row.period_expense_rub, "RUB")}
                    </td>
                    <td className="right" style={{ color: rowNet >= 0 ? "var(--accent)" : "var(--expense)" }}>
                      {rowNet >= 0 ? "+" : ""}
                      {fmt(rowNet, "RUB")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
