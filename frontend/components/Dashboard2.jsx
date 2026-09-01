"use client";

import { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  PieChart,
  Pie,
  Cell,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt } from "../lib/format";
import { useTranslation } from "../lib/i18n";

// Палитра для срезов "Структура платежей" — те же оттенки, что и в остальном
// приложении (accent/expense/transfer/gold), дополненные ещё парой
// приглушённых тонов для случаев с числом статей > 4. "Прочее" всегда
// последним нейтрально-серым — см. buildSlices.
const SLICE_COLORS = ["#2F6F5E", "#A8503F", "#4A6FA5", "#C9A227", "#7A3FA0", "#1F7A8C", "#B4650A", "#5B6472"];
const MAX_SLICES = 7;

function buildSlices(byCategory, field) {
  const rows = (byCategory || [])
    .map((r) => ({ name: r.category || "—", value: r[field] || 0 }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value);
  if (rows.length <= MAX_SLICES) return rows;
  const head = rows.slice(0, MAX_SLICES - 1);
  const restTotal = rows.slice(MAX_SLICES - 1).reduce((s, r) => s + r.value, 0);
  return [...head, { name: "Прочее", value: restTotal }];
}

function PaymentStructurePie({ title, data, total }) {
  const { t } = useTranslation();
  if (data.length === 0) {
    return (
      <div>
        <div className="fp-panel-head">
          <h3>{title}</h3>
        </div>
        <div className="fp-empty">{t("dashboard2.structure.empty")}</div>
      </div>
    );
  }
  return (
    <div>
      <div className="fp-panel-head">
        <h3>{title}</h3>
        <span className="fp-muted" style={{ fontSize: 12.5 }}>{fmt(total, "RUB")}</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={1.5}>
            {data.map((_, i) => (
              <Cell key={i} fill={SLICE_COLORS[i % SLICE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(v) => fmt(v, "RUB")}
            contentStyle={{ fontFamily: "IBM Plex Sans", fontSize: 13, border: "1px solid #E7E1D3", borderRadius: 6 }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 4 }}>
        {data.map((row, i) => (
          <div key={row.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  width: 9,
                  height: 9,
                  borderRadius: 2,
                  background: SLICE_COLORS[i % SLICE_COLORS.length],
                  display: "inline-block",
                }}
              />
              {row.name}
            </span>
            <span className="fp-mono">
              {total ? ((row.value / total) * 100).toFixed(1) : "0.0"}% · {fmt(row.value, "RUB")}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard2() {
  const { token, user } = useAuth();
  const { t } = useTranslation();
  const companies = user?.companies || [];
  const multiCompany = companies.length > 1;

  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 7));
  const [companyFilter, setCompanyFilter] = useState("");
  const [method, setMethod] = useState("accrual");

  const structureQuery = { period, company_id: companyFilter || undefined };
  const { data: structure, loading: structureLoading } = useResource(
    () => api.cashflowReport(token, structureQuery),
    [token, JSON.stringify(structureQuery)]
  );

  const trendQuery = { method, company_id: companyFilter || undefined };
  const { data: trend, loading: trendLoading } = useResource(
    () => api.cashflowReport(token, trendQuery),
    [token, JSON.stringify(trendQuery)]
  );

  const clientsQuery = { period, limit: 10, company_id: companyFilter || undefined };
  const { data: topClients, loading: clientsLoading } = useResource(
    () => api.topClientsReport(token, clientsQuery),
    [token, JSON.stringify(clientsQuery)]
  );

  const profitabilityQuery = { method, company_id: companyFilter || undefined };
  const { data: profitability, loading: profitabilityLoading } = useResource(
    () => api.profitabilityReport(token, profitabilityQuery),
    [token, JSON.stringify(profitabilityQuery)]
  );

  const incomeSlices = buildSlices(structure?.by_category, "income");
  const expenseSlices = buildSlices(structure?.by_category, "expense");
  const incomeTotal = incomeSlices.reduce((s, r) => s + r.value, 0);
  const expenseTotal = expenseSlices.reduce((s, r) => s + r.value, 0);

  const trendData = (trend?.by_month || []).slice(-12).map((row) => ({
    ...row,
    margin_pct: row.income ? (row.net / row.income) * 100 : 0,
  }));

  const projectBars = [...(profitability || [])]
    .filter((r) => r.project_id)
    .sort((a, b) => b.profit - a.profit)
    .slice(0, 10)
    .map((r) => ({ name: r.project, profit: r.profit, revenue: r.revenue, expense: r.expense, margin: (r.margin || 0) * 100 }));

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row" style={{ marginBottom: 4 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
          <select value={method} onChange={(e) => setMethod(e.target.value)}>
            <option value="accrual">{t("dashboard2.method.accrual")}</option>
            <option value="cash">{t("dashboard2.method.cash")}</option>
          </select>
        </div>
        {multiCompany && (
          <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
            <option value="">{t("dashboard.allCompanies")}</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        )}
      </div>

      <section className="fp-grid-2">
        <div className="fp-panel" style={{ padding: 16 }}>
          <PaymentStructurePie title={t("dashboard2.structure.income")} data={incomeSlices} total={incomeTotal} />
        </div>
        <div className="fp-panel" style={{ padding: 16 }}>
          <PaymentStructurePie title={t("dashboard2.structure.expense")} data={expenseSlices} total={expenseTotal} />
        </div>
      </section>

      <section className="fp-panel">
        <div className="fp-panel-head">
          <h3>{t("dashboard2.trend.title")}</h3>
        </div>
        {!trendLoading && trendData.length === 0 ? (
          <div className="fp-empty">{t("dashboard.chart.empty")}</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={trendData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#E7E1D3" vertical={false} />
              <XAxis
                dataKey="period"
                tick={{ fontFamily: "IBM Plex Sans", fontSize: 12, fill: "#5B6472" }}
                axisLine={{ stroke: "#E7E1D3" }}
                tickLine={false}
              />
              <YAxis
                yAxisId="rub"
                tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                axisLine={false}
                tickLine={false}
                width={70}
                tickFormatter={(v) => v.toLocaleString("ru-RU")}
              />
              <YAxis
                yAxisId="pct"
                orientation="right"
                tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                axisLine={false}
                tickLine={false}
                width={50}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                formatter={(v, name) => (name === t("dashboard2.trend.margin") ? `${v.toFixed(1)}%` : fmt(v, "RUB"))}
                contentStyle={{ fontFamily: "IBM Plex Sans", fontSize: 13, border: "1px solid #E7E1D3", borderRadius: 6 }}
              />
              <Legend wrapperStyle={{ fontFamily: "IBM Plex Sans", fontSize: 12.5 }} />
              <Bar yAxisId="rub" dataKey="income" name={t("dashboard.kpi.income")} fill="#DCEAE4" stroke="#2F6F5E" radius={[3, 3, 0, 0]} barSize={18} />
              <Bar yAxisId="rub" dataKey="expense" name={t("dashboard.kpi.expense")} fill="#F3E1DC" stroke="#A8503F" radius={[3, 3, 0, 0]} barSize={18} />
              <Line yAxisId="rub" type="monotone" dataKey="net" name={t("dashboard2.trend.profit")} stroke="#C9A227" strokeWidth={2.5} dot={{ r: 3 }} />
              <Line yAxisId="pct" type="monotone" dataKey="margin_pct" name={t("dashboard2.trend.margin")} stroke="#4A6FA5" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="fp-grid-2">
        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>{t("dashboard2.topClients.title")}</h3>
          </div>
          {!clientsLoading && (topClients?.items || []).length === 0 ? (
            <div className="fp-empty">{t("dashboard2.structure.empty")}</div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={topClients?.items || []} margin={{ top: 8, right: 8, left: 0, bottom: 30 }}>
                <CartesianGrid stroke="#E7E1D3" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontFamily: "IBM Plex Sans", fontSize: 10.5, fill: "#5B6472" }}
                  axisLine={{ stroke: "#E7E1D3" }}
                  tickLine={false}
                  interval={0}
                  angle={-40}
                  textAnchor="end"
                  height={90}
                  tickFormatter={(name) => (name.length > 16 ? `${name.slice(0, 15)}…` : name)}
                />
                <YAxis
                  yAxisId="rub"
                  tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                  axisLine={false}
                  tickLine={false}
                  width={70}
                  tickFormatter={(v) => v.toLocaleString("ru-RU")}
                />
                <YAxis
                  yAxisId="pct"
                  orientation="right"
                  domain={[0, 100]}
                  tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                  axisLine={false}
                  tickLine={false}
                  width={40}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  formatter={(v, name) => (name === t("dashboard2.topClients.cumulative") ? `${v.toFixed(1)}%` : fmt(v, "RUB"))}
                  contentStyle={{ fontFamily: "IBM Plex Sans", fontSize: 13, border: "1px solid #E7E1D3", borderRadius: 6 }}
                />
                <Bar yAxisId="rub" dataKey="revenue_rub" name={t("dashboard2.topClients.revenue")} fill="#2F6F5E" radius={[3, 3, 0, 0]} barSize={22} />
                <Line yAxisId="pct" type="monotone" dataKey="cumulative_pct" name={t("dashboard2.topClients.cumulative")} stroke="#C9A227" strokeWidth={2} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>{t("dashboard2.projects.title")}</h3>
          </div>
          {!profitabilityLoading && projectBars.length === 0 ? (
            <div className="fp-empty">{t("dashboard2.structure.empty")}</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={projectBars} layout="vertical" margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid stroke="#E7E1D3" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => v.toLocaleString("ru-RU")}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={130}
                  tick={{ fontFamily: "IBM Plex Sans", fontSize: 11.5, fill: "#5B6472" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  formatter={(v) => fmt(v, "RUB")}
                  contentStyle={{ fontFamily: "IBM Plex Sans", fontSize: 13, border: "1px solid #E7E1D3", borderRadius: 6 }}
                />
                <Bar dataKey="profit" name={t("reports.profit")} radius={[0, 3, 3, 0]} barSize={16}>
                  {projectBars.map((row, i) => (
                    <Cell key={i} fill={row.profit >= 0 ? "#2F6F5E" : "#A8503F"} />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>
    </div>
  );
}
