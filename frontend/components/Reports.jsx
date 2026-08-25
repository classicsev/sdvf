"use client";

import { Fragment, useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt } from "../lib/format";
import { canEditReference } from "../lib/roles";
import { useTranslation } from "../lib/i18n";
import ProjectCard from "./ProjectCard";
import { Combobox } from "./Combobox";
import AmountInput from "./AmountInput";

const TAB_KEYS = ["cashflow", "pnl", "balance", "debt", "profitability", "companyBudget", "calendar"];

// Селектор компании для отчётов — общий для всех вкладок (см. план "Мульти-компании").
// Пусто по умолчанию = сводно по всем доступным компаниям.
function CompanyFilter({ companyId, onChange }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  if (companies.length <= 1) return null;
  return (
    <select value={companyId} onChange={(e) => onChange(e.target.value)} style={{ marginRight: 8 }}>
      <option value="">{t("dashboard.allCompanies")}</option>
      {companies.map((m) => (
        <option key={m.company.id} value={m.company.id}>
          {m.company.name}
        </option>
      ))}
    </select>
  );
}

function CashflowTab({ token }) {
  const { t } = useTranslation();
  const [period, setPeriod] = useState("");
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.cashflowReport(token, { period: period || undefined, company_id: companyId || undefined }),
    [token, period, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
        {period && (
          <button className="fp-btn-tiny" style={{ marginLeft: 8 }} onClick={() => setPeriod("")}>
            {t("reports.resetMonthly")}
          </button>
        )}
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{period ? t("reports.col.category") : t("reports.col.period")}</th>
                <th className="right">{t("dashboard.table.income")}</th>
                <th className="right">{t("dashboard.table.expense")}</th>
                <th className="right">{t("dashboard.table.netFlow")}</th>
              </tr>
            </thead>
            <tbody>
              {(period ? data?.by_category : data?.by_month || []).map((row) => (
                <tr key={row.category_id || row.period}>
                  <td>{row.category || row.period}</td>
                  <td className="right fp-mono fp-amount-income">{fmt(row.income, "RUB")}</td>
                  <td className="right fp-mono fp-amount-expense">{fmt(row.expense, "RUB")}</td>
                  <td className="right fp-mono">{fmt(row.net, "RUB")}</td>
                </tr>
              ))}
              {(period ? data?.by_category : data?.by_month || [])?.length === 0 && (
                <tr>
                  <td colSpan={4} className="fp-empty">
                    {t("reports.noData")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PnlTab({ token }) {
  const { t } = useTranslation();
  const [period, setPeriod] = useState("");
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.pnlReport(token, { period: period || undefined, company_id: companyId || undefined }),
    [token, period, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input
          type="month"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          placeholder={t("reports.currentMonth")}
        />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        data && (
          <div className="fp-panel">
            <div className="fp-panel-head">
              <h3>
                {t("reports.pnlTitle")} · {data.period_from} — {data.period_to}
              </h3>
            </div>
            <div className="fp-ledger">
              <div className="ledger-row">
                <span className="label">{t("reports.revenue")}</span>
                <span className="fill" />
                <span className="value fp-amount-income">{fmt(data.revenue, "RUB")}</span>
              </div>
              {data.expenses.map((row) => (
                <div className="ledger-row" key={row.group}>
                  <span className="label">{row.group}</span>
                  <span className="fill" />
                  <span className="value">{fmt(row.amount, "RUB")}</span>
                </div>
              ))}
              <div className="ledger-row">
                <span className="label">{t("reports.totalExpenses")}</span>
                <span className="fill" />
                <span className="value fp-amount-expense">{fmt(data.total_expense, "RUB")}</span>
              </div>
              <div className="ledger-row fp-ledger-total">
                <span className="label">{t("reports.netProfit")}</span>
                <span className="fill" />
                <span className="value">{fmt(data.net_profit, "RUB")}</span>
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function BalanceTab({ token }) {
  const { t } = useTranslation();
  const [asOf, setAsOf] = useState("");
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.balanceReport(token, { as_of: asOf || undefined, company_id: companyId || undefined }),
    [token, asOf, companyId]
  );
  const { data: analysis } = useResource(
    () => api.balanceAnalysis(token, { as_of: asOf || undefined, company_id: companyId || undefined }),
    [token, asOf, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder={t("reports.today")} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        data && (
          <div className="fp-grid-2">
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>{t("reports.assetsAsOf", { date: data.as_of })}</h3>
              </div>
              <div className="fp-ledger">
                <div className="ledger-row">
                  <span className="label">{t("reports.cash")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.cash_rub, "RUB")}</span>
                </div>
                <div className="ledger-row">
                  <span className="label">{t("reports.inventory")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.inventory_rub, "RUB")}</span>
                </div>
                <div className="ledger-row">
                  <span className="label">{t("reports.fixedAssets")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.fixed_assets_rub, "RUB")}</span>
                </div>
                <div className="ledger-row fp-ledger-total">
                  <span className="label">{t("reports.totalAssets")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.total_rub, "RUB")}</span>
                </div>
              </div>
            </div>
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>{t("reports.liabilities")}</h3>
              </div>
              <div className="fp-ledger">
                <div className="ledger-row">
                  <span className="label">{t("reports.payableToStaff")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.payable_to_staff_rub, "RUB")}</span>
                </div>
                <div className="ledger-row">
                  <span className="label">{t("reports.loans")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.loans_rub, "RUB")}</span>
                </div>
                <div className="ledger-row fp-ledger-total">
                  <span className="label">{t("reports.totalLiabilities")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.total_rub, "RUB")}</span>
                </div>
                <div className="ledger-row">
                  <span className="label">{t("reports.retainedEarnings")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.retained_earnings_rub, "RUB")}</span>
                </div>
              </div>
            </div>
          </div>
        )
      )}
      {analysis && (
        <div className="fp-panel" style={{ marginTop: 18 }}>
          <div className="fp-panel-head">
            <h3>{t("reports.proMetrics")}</h3>
          </div>
          <div className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
            <div className="fp-kpi">
              <div className="fp-kpi-label">{t("reports.roe")}</div>
              <div className="fp-kpi-value">{analysis.roe_pct == null ? "—" : `${analysis.roe_pct.toFixed(1)}%`}</div>
            </div>
            <div className="fp-kpi">
              <div className="fp-kpi-label">{t("reports.workingCapital")}</div>
              <div className="fp-kpi-value">{fmt(analysis.working_capital_rub, "RUB")}</div>
            </div>
            <div className="fp-kpi">
              <div className="fp-kpi-label">{t("reports.netProfitPeriod")}</div>
              <div className="fp-kpi-value">{fmt(analysis.net_profit_rub, "RUB")}</div>
            </div>
            <div className="fp-kpi">
              <div className="fp-kpi-label">
                {t("reports.horizontalVsDate", { date: analysis.compare_to })}
              </div>
              <div className="fp-kpi-value">{fmt(analysis.horizontal.assets_total_delta_rub, "RUB")}</div>
            </div>
          </div>
          <div className="fp-ledger" style={{ marginTop: 14 }}>
            <div className="ledger-row">
              <span className="label">{t("reports.cash")}</span>
              <span className="fill" />
              <span className="value">{analysis.vertical.assets.cash_rub}%</span>
            </div>
            <div className="ledger-row">
              <span className="label">{t("reports.inventory")}</span>
              <span className="fill" />
              <span className="value">{analysis.vertical.assets.inventory_rub}%</span>
            </div>
            <div className="ledger-row">
              <span className="label">{t("reports.fixedAssets")}</span>
              <span className="fill" />
              <span className="value">{analysis.vertical.assets.fixed_assets_rub}%</span>
            </div>
            <div className="ledger-row">
              <span className="label">{t("reports.loans")}</span>
              <span className="fill" />
              <span className="value">{analysis.vertical.liabilities_and_equity.loans_rub}%</span>
            </div>
            <div className="ledger-row">
              <span className="label">{t("reports.retainedEarnings")}</span>
              <span className="fill" />
              <span className="value">{analysis.vertical.liabilities_and_equity.equity_rub}%</span>
            </div>
          </div>
          <p className="fp-note">{t("reports.proMetricsNote")}</p>
        </div>
      )}
      <p className="fp-note">{t("reports.balanceNote")}</p>
    </div>
  );
}

// БДДС/БДР — компанийный (не проектный) план по статьям на месяц, тот же
// "категория+сумма, добавить/удалить строку" UI-паттерн, что уже сделан для
// бюджета проекта (см. ProjectCard.jsx) — переиспользуем его, не изобретаем
// новый.
function CompanyBudgetTab({ token }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canEdit = (user.companies || []).some((m) => canEditReference(m.role));
  const [companyId, setCompanyId] = useState("");
  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 7));

  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data, loading, error, reload } = useResource(
    () => api.companyBudgetReport(token, period, companyId || undefined),
    [token, period, companyId]
  );

  const [rows, setRows] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (data) {
      setRows(data.lines.filter((l) => l.plan_rub).map((l) => ({ category_id: l.category_id, amount: String(l.plan_rub) })));
    }
  }, [data]);

  function addRow() {
    setRows((prev) => [...prev, { category_id: "", amount: "" }]);
  }
  function updateRow(i, field, value) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)));
  }
  function removeRow(i) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function handleSave() {
    setSaving(true);
    setSaveError("");
    try {
      const payload = rows
        .filter((r) => r.category_id && r.amount !== "")
        .map((r) => ({ category_id: r.category_id, amount: Number(r.amount) }));
      await api.replaceCompanyBudgetLines(token, period, payload, companyId || undefined);
      reload();
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        data && (
          <div className="fp-grid-2">
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>{t("reports.companyBudget.factByCategory")}</h3>
              </div>
              <div className="fp-ledger">
                {data.lines.map((row) => (
                  <div className="ledger-row" key={row.category_id}>
                    <span className="label">{row.category_name}</span>
                    <span className="fill" />
                    <span className="value">
                      {fmt(row.fact_rub, "RUB")} / {fmt(row.plan_rub, "RUB")}
                    </span>
                  </div>
                ))}
                {data.lines.length === 0 && <div className="fp-empty">{t("reports.noCalendarData", { year: period })}</div>}
                <div className="ledger-row fp-ledger-total">
                  <span className="label">{t("reports.companyBudget.total")}</span>
                  <span className="fill" />
                  <span className="value">
                    {fmt(data.fact_total_rub, "RUB")} / {fmt(data.plan_total_rub, "RUB")}
                  </span>
                </div>
              </div>
            </div>

            <div className="fp-panel">
              <div className="fp-panel-head fp-panel-head-row">
                <h3>{t("reference.projects.plan")}</h3>
                {canEdit && (
                  <button type="button" className="fp-btn-tiny" onClick={handleSave} disabled={saving}>
                    <Save size={13} /> {saving ? t("common.saving") : t("common.save")}
                  </button>
                )}
              </div>
              {rows.map((row, i) => (
                <div key={i} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
                  <div style={{ flex: 1 }}>
                    <Combobox
                      value={row.category_id}
                      onChange={(val) => updateRow(i, "category_id", val)}
                      options={(categories || []).map((c) => ({ id: c.id, name: c.name }))}
                      placeholder={t("tx.form.selectCategory")}
                    />
                  </div>
                  <AmountInput style={{ width: 120 }} value={row.amount} onChange={(v) => updateRow(i, "amount", v)} />
                  {canEdit && (
                    <button type="button" className="fp-icon-btn" onClick={() => removeRow(i)}>
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              {canEdit && (
                <button type="button" className="fp-btn-ghost" onClick={addRow} style={{ marginTop: 4 }}>
                  <Plus size={13} /> {t("reference.projects.addBudgetLine")}
                </button>
              )}
              {saveError && <div className="fp-form-error">{saveError}</div>}
            </div>
          </div>
        )
      )}
    </div>
  );
}

function DebtTab({ token }) {
  const { t } = useTranslation();
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.debtReport(token, { company_id: companyId || undefined }),
    [token, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("reports.counterparty")}</th>
                <th>{t("reports.type")}</th>
                <th className="right">{t("reports.netTurnover")}</th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((row) => (
                <tr key={row.counterparty_id}>
                  <td>{row.name}</td>
                  <td className="fp-muted">{row.type === "debtor" ? t("reports.debtor") : t("reports.creditor")}</td>
                  <td className="right fp-mono">{fmt(row.net_amount_rub, "RUB")}</td>
                </tr>
              ))}
              {(data || []).length === 0 && (
                <tr>
                  <td colSpan={3} className="fp-empty">
                    {t("reports.noCounterpartyOps")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ProfitabilityTab({ token }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canEdit = (user.companies || []).some((m) => canEditReference(m.role));
  const [companyId, setCompanyId] = useState("");
  const [projectCardId, setProjectCardId] = useState(null);
  const { data, loading, error } = useResource(
    () => api.profitabilityReport(token, { company_id: companyId || undefined }),
    [token, companyId]
  );

  if (projectCardId) {
    return (
      <ProjectCard token={token} projectId={projectCardId} onBack={() => setProjectCardId(null)} canEdit={canEdit} />
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("reports.project")}</th>
                <th className="right">{t("reports.revenue")}</th>
                <th className="right">{t("dashboard.table.expense")}</th>
                <th className="right">{t("reports.profit")}</th>
                <th className="right">{t("reports.margin")}</th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((row) => (
                <tr key={row.project_id || "unallocated"}>
                  <td>
                    {row.project_id ? (
                      <button type="button" className="fp-link-button" onClick={() => setProjectCardId(row.project_id)}>
                        {row.project}
                      </button>
                    ) : (
                      row.project
                    )}
                  </td>
                  <td className="right fp-mono fp-amount-income">{fmt(row.revenue, "RUB")}</td>
                  <td className="right fp-mono fp-amount-expense">{fmt(row.expense, "RUB")}</td>
                  <td className="right fp-mono">{fmt(row.profit, "RUB")}</td>
                  <td className="right fp-mono">{row.margin === null ? "—" : `${(row.margin * 100).toFixed(1)}%`}</td>
                </tr>
              ))}
              {(data || []).length === 0 && (
                <tr>
                  <td colSpan={5} className="fp-empty">
                    {t("reports.noProjectOps")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CalendarTab({ token }) {
  const { t } = useTranslation();
  const [year, setYear] = useState(new Date().getFullYear());
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.paymentCalendar(token, { quarter: String(year), company_id: companyId || undefined }),
    [token, year, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 100 }} />
      </div>
      <p className="fp-note" style={{ marginBottom: 14 }}>
        {t("reports.planningHint")}
      </p>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table fp-calendar-table">
            <thead>
              <tr>
                <th>{t("reports.col.category")}</th>
                {[1, 2, 3, 4].map((q) => (
                  <th key={q} className="center" colSpan={2}>
                    Q{q}
                  </th>
                ))}
              </tr>
              <tr>
                <th></th>
                {[1, 2, 3, 4].map((q) => (
                  <Fragment key={q}>
                    <th className="right">{t("reports.plan")}</th>
                    <th className="right">{t("reports.fact")}</th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data?.rows || []).map((row) => (
                <tr key={row.category_id}>
                  <td>{row.category}</td>
                  {row.quarters.map((q) => (
                    <Fragment key={q.quarter}>
                      <td className="right fp-mono fp-muted">{fmt(q.plan, "RUB")}</td>
                      <td className={`right fp-mono ${q.deviation < 0 ? "fp-amount-expense" : "fp-amount-income"}`}>
                        {fmt(q.fact, "RUB")}
                      </td>
                    </Fragment>
                  ))}
                </tr>
              ))}
              {(data?.rows || []).length === 0 && (
                <tr>
                  <td colSpan={9} className="fp-empty">
                    {t("reports.noCalendarData", { year })}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const TAB_COMPONENTS = {
  cashflow: CashflowTab,
  pnl: PnlTab,
  balance: BalanceTab,
  debt: DebtTab,
  profitability: ProfitabilityTab,
  companyBudget: CompanyBudgetTab,
  calendar: CalendarTab,
};

export default function Reports() {
  const { token } = useAuth();
  const { t } = useTranslation();
  const [tab, setTab] = useState("cashflow");
  const ActiveTab = TAB_COMPONENTS[tab];

  return (
    <div className="fp-dash">
      <div className="fp-tabs">
        {TAB_KEYS.map((key) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {t(`reports.tab.${key}`)}
          </button>
        ))}
      </div>
      <ActiveTab token={token} />
    </div>
  );
}
