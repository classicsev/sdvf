"use client";

import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Trash2, Save } from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { Combobox } from "./Combobox";
import AmountInput from "./AmountInput";
import { useTranslation } from "../lib/i18n";

// Карточка проекта — см. HANDOVER.md "Карточка проекта" (сделано по образцу
// ПланФакта, но с диапазоном дат, которого у их профильного отчёта тоже нет
// в списке, а тут есть с самого начала). Полноценная замена содержимого
// вкладки, не модалка — .fp-modal капнут на 480px, сюда не влезет ни график,
// ни бюджет, ни список операций одновременно.
export default function ProjectCard({ token, projectId, onBack, canEdit }) {
  const { t } = useTranslation();
  const [method, setMethod] = useState("accrual");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [planSource, setPlanSource] = useState("operations");

  const { data: detail, loading, error } = useResource(
    () =>
      api.projectDetail(token, projectId, {
        method,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        plan_source: planSource,
      }),
    [token, projectId, method, dateFrom, dateTo, planSource]
  );

  const { data: operations } = useResource(
    () => api.listTransactions(token, { project: projectId, limit: 20 }),
    [token, projectId]
  );

  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data: accounts } = useResource(() => api.listAccounts(token), [token]);
  const { data: counterparties } = useResource(() => api.listCounterparties(token), [token]);
  const accountsById = Object.fromEntries((accounts || []).map((a) => [a.id, a]));
  const categoriesById = Object.fromEntries((categories || []).map((c) => [c.id, c]));
  const counterpartiesById = Object.fromEntries((counterparties || []).map((c) => [c.id, c]));

  const {
    data: fetchedBudgetLines,
    reload: reloadBudgetLines,
  } = useResource(() => api.listProjectBudgetLines(token, projectId), [token, projectId]);

  const [budgetRows, setBudgetRows] = useState([]);
  const [budgetSaving, setBudgetSaving] = useState(false);
  const [budgetError, setBudgetError] = useState("");

  useEffect(() => {
    if (fetchedBudgetLines) {
      setBudgetRows(fetchedBudgetLines.map((l) => ({ category_id: l.category_id, amount: String(l.amount) })));
    }
  }, [fetchedBudgetLines]);

  function addBudgetRow() {
    setBudgetRows((prev) => [...prev, { category_id: "", amount: "" }]);
  }

  function updateBudgetRow(index, field, value) {
    setBudgetRows((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  function removeBudgetRow(index) {
    setBudgetRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function saveBudget() {
    setBudgetSaving(true);
    setBudgetError("");
    try {
      const payload = budgetRows
        .filter((r) => r.category_id && r.amount !== "")
        .map((r) => ({ category_id: r.category_id, amount: Number(r.amount) }));
      await api.replaceProjectBudgetLines(token, projectId, payload);
      reloadBudgetLines();
    } catch (err) {
      setBudgetError(err.message);
    } finally {
      setBudgetSaving(false);
    }
  }

  if (loading && !detail) {
    return (
      <div className="fp-panel" style={{ marginTop: 16 }}>
        <div className="fp-loading">{t("common.loading")}</div>
      </div>
    );
  }
  if (error || !detail) {
    return (
      <div className="fp-panel" style={{ marginTop: 16 }}>
        <div className="fp-error-banner">{error || t("common.loadError")}</div>
      </div>
    );
  }

  // Кумулятивная прибыль по месяцам — для линии на графике (первое реальное
  // применение <Line> в проекте, компонент уже импортировался в Dashboard.jsx,
  // но нигде не рендерился).
  let running = 0;
  const chartData = (detail.by_month || []).map((row) => {
    running += row.revenue - row.expense;
    return { ...row, cumulative: running };
  });

  const statusVariant = detail.status === "in_progress" ? "ok" : detail.status === "closed" ? "neutral" : "warn";

  return (
    <div style={{ marginTop: 16 }}>
      <button type="button" className="fp-btn-ghost" onClick={onBack} style={{ marginBottom: 14 }}>
        <ArrowLeft size={14} /> {t("reference.projects.backToList")}
      </button>

      <div className="fp-panel" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 4 }}>
          <h2 style={{ fontFamily: "'Fraunces', serif", fontSize: 22, fontWeight: 600, margin: 0 }}>
            {detail.project_name}
          </h2>
          {detail.status && (
            <span className={`fp-status-badge ${statusVariant}`}>
              {t(`reference.projects.status.${detail.status}`)}
            </span>
          )}
        </div>
        {(detail.date_range?.min || detail.date_range?.max) && (
          <div className="fp-muted" style={{ fontSize: 12.5, marginBottom: 16 }}>
            {detail.date_range.min ? fmtDate(detail.date_range.min) : "—"} — {detail.date_range.max ? fmtDate(detail.date_range.max) : "—"}
          </div>
        )}

        <div className="fp-form-grid" style={{ marginBottom: 20 }}>
          <label>
            {t("reference.projects.periodFrom")}
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label>
            {t("reference.projects.periodTo")}
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <label>
            {t("reference.projects.method")}
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="accrual">{t("reference.projects.method.accrual")}</option>
              <option value="cash">{t("reference.projects.method.cash")}</option>
            </select>
          </label>
          <label>
            {t("reference.projects.planSource")}
            <select value={planSource} onChange={(e) => setPlanSource(e.target.value)}>
              <option value="operations">{t("reference.projects.planSource.operations")}</option>
              <option value="budget">{t("reference.projects.planSource.budget")}</option>
            </select>
          </label>
        </div>

        <div className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          <div className="fp-kpi">
            <div className="fp-kpi-top">
              <span className="fp-kpi-label">{t("reports.profit")}</span>
            </div>
            <div className="fp-kpi-value">{fmt(detail.profit, "RUB")}</div>
          </div>
          <div className="fp-kpi">
            <div className="fp-kpi-top">
              <span className="fp-kpi-label">{t("reports.margin")}</span>
            </div>
            <div className="fp-kpi-value">{detail.margin === null ? "—" : `${(detail.margin * 100).toFixed(1)}%`}</div>
          </div>
          <div className="fp-kpi fp-kpi-income">
            <div className="fp-kpi-top">
              <span className="fp-kpi-label">{t("reports.revenue")}</span>
            </div>
            <div className="fp-kpi-value">{fmt(detail.revenue, "RUB")}</div>
          </div>
          <div className="fp-kpi fp-kpi-expense">
            <div className="fp-kpi-top">
              <span className="fp-kpi-label">{t("dashboard.table.expense")}</span>
            </div>
            <div className="fp-kpi-value">{fmt(detail.expense, "RUB")}</div>
          </div>
        </div>
      </div>

      <div className="fp-panel" style={{ marginBottom: 16 }}>
        <div className="fp-panel-head">
          <h3>{t("reference.projects.chartTitle")}</h3>
        </div>
        {chartData.length === 0 ? (
          <div className="fp-empty">{t("dashboard.chart.empty")}</div>
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
              <Legend wrapperStyle={{ fontFamily: "IBM Plex Sans", fontSize: 12.5 }} />
              <Bar dataKey="revenue" name={t("reports.revenue")} fill="#DCEAE4" radius={[3, 3, 0, 0]} barSize={18} />
              <Bar dataKey="expense" name={t("dashboard.table.expense")} fill="#F3E1DC" radius={[3, 3, 0, 0]} barSize={18} />
              <Line
                type="monotone"
                dataKey="cumulative"
                name={t("reference.projects.cumulativeProfit")}
                stroke="#2F6F5E"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="fp-grid-2" style={{ marginBottom: 16 }}>
        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>{t("reference.projects.byCategory")}</h3>
          </div>
          {(detail.by_category || []).length === 0 ? (
            <div className="fp-empty">{t("reference.projects.noExpenses")}</div>
          ) : (
            <div className="fp-ledger">
              {detail.by_category.map((row) => (
                <div className="ledger-row" key={row.category}>
                  <span className="label">{row.category}</span>
                  <span className="fill" />
                  <span className="value">{fmt(row.amount, "RUB")}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="fp-panel">
          <div className="fp-panel-head fp-panel-head-row">
            <h3>{t("reference.projects.plan")}</h3>
            {planSource === "budget" && canEdit && (
              <button type="button" className="fp-btn-tiny" onClick={saveBudget} disabled={budgetSaving}>
                <Save size={13} /> {budgetSaving ? t("common.saving") : t("common.save")}
              </button>
            )}
          </div>
          {planSource === "operations" ? (
            <div className="fp-ledger">
              <div className="ledger-row">
                <span className="label">{t("reports.revenue")}</span>
                <span className="fill" />
                <span className="value">{fmt(detail.plan?.revenue || 0, "RUB")}</span>
              </div>
              <div className="ledger-row">
                <span className="label">{t("dashboard.table.expense")}</span>
                <span className="fill" />
                <span className="value">{fmt(detail.plan?.expense || 0, "RUB")}</span>
              </div>
              <p className="fp-note" style={{ marginTop: 10 }}>{t("reference.projects.planFromOperationsHint")}</p>
            </div>
          ) : (
            <>
              {budgetRows.map((row, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
                  <div style={{ flex: 1 }}>
                    <Combobox
                      value={row.category_id}
                      onChange={(val) => updateBudgetRow(i, "category_id", val)}
                      options={(categories || []).map((c) => ({ id: c.id, name: c.name }))}
                      placeholder={t("tx.form.selectCategory")}
                    />
                  </div>
                  <AmountInput
                    style={{ width: 120 }}
                    value={row.amount}
                    onChange={(v) => updateBudgetRow(i, "amount", v)}
                  />
                  {canEdit && (
                    <button type="button" className="fp-icon-btn" onClick={() => removeBudgetRow(i)}>
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              {canEdit && (
                <button type="button" className="fp-btn-ghost" onClick={addBudgetRow} style={{ marginTop: 4 }}>
                  <Plus size={13} /> {t("reference.projects.addBudgetLine")}
                </button>
              )}
              {budgetError && <div className="fp-form-error">{budgetError}</div>}
            </>
          )}
        </div>
      </div>

      <div className="fp-panel fp-table-panel">
        <div className="fp-panel-head" style={{ padding: "18px 18px 0" }}>
          <h3>{t("reference.projects.operations")}</h3>
        </div>
        {(operations || []).length === 0 ? (
          <div className="fp-empty">{t("tx.notFound")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("tx.col.date")}</th>
                <th>{t("tx.col.account")}</th>
                <th>{t("tx.col.category")}</th>
                <th>{t("tx.col.counterparty")}</th>
                <th className="right">{t("tx.col.amount")}</th>
              </tr>
            </thead>
            <tbody>
              {operations.map((tx) => (
                <tr key={tx.id}>
                  <td>{fmtDate(tx.date_odds)}</td>
                  <td>{accountsById[tx.account_id]?.name || "—"}</td>
                  <td>{categoriesById[tx.category_id]?.name || "—"}</td>
                  <td className="fp-muted">
                    {tx.counterparty_id ? counterpartiesById[tx.counterparty_id]?.name || "—" : "—"}
                  </td>
                  <td className={`right fp-mono fp-amount-${tx.type}`}>
                    {tx.type === "expense" ? "-" : ""}
                    {fmt(tx.amount, tx.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
