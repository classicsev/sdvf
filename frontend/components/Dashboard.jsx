"use client";

import { Wallet, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { ResponsiveContainer, ComposedChart, Area, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt } from "../lib/format";

function KpiCard({ label, value, tone, icon }) {
  return (
    <div className={`fp-kpi fp-kpi-${tone}`}>
      <div className="fp-kpi-top">
        <span className="fp-kpi-label">{label}</span>
        <span className="fp-kpi-icon">{icon}</span>
      </div>
      <div className="fp-kpi-value">{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const { token } = useAuth();
  const { data: summary, loading, error } = useResource(() => api.dashboardSummary(token), [token]);
  const { data: cashflow } = useResource(() => api.cashflowReport(token), [token]);

  if (loading) return <div className="fp-loading">Загрузка…</div>;
  if (error) return <div className="fp-error-banner">{error}</div>;
  if (!summary) return null;

  const netFlow = summary.net_flow_rub;
  const chartData = (cashflow?.by_month || []).slice(-12);

  return (
    <div className="fp-dash">
      <section className="fp-kpi-row">
        <KpiCard
          label="Общий остаток"
          value={fmt(summary.total_balance_rub, "RUB")}
          tone="neutral"
          icon={<Wallet size={16} />}
        />
        <KpiCard
          label="Приход за месяц"
          value={fmt(summary.period_income_rub, "RUB")}
          tone="income"
          icon={<ArrowUpRight size={16} />}
        />
        <KpiCard
          label="Расход за месяц"
          value={fmt(summary.period_expense_rub, "RUB")}
          tone="expense"
          icon={<ArrowDownRight size={16} />}
        />
        <KpiCard
          label="Чистый поток"
          value={`${netFlow >= 0 ? "+" : ""}${fmt(netFlow, "RUB")}`}
          tone={netFlow >= 0 ? "income" : "expense"}
          icon={netFlow >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
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
    </div>
  );
}
