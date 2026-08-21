"use client";

import { Fragment, useState } from "react";
import { Plus, X, Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditPlanning } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";
import { useTranslation } from "../lib/i18n";

const TAB_KEYS = ["cashflow", "pnl", "balance", "debt", "profitability", "calendar"];

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
      <p className="fp-note">{t("reports.balanceNote")}</p>
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
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.profitabilityReport(token, { company_id: companyId || undefined }),
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
                  <td>{row.project}</td>
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

const PLAN_EMPTY = {
  category_id: "",
  project_id: "",
  amount: "",
  frequency: "monthly",
  scheduled_date: new Date().toISOString().slice(0, 10),
};

function PlanningPanel({ token, year, categories, projects, planning, reload, companyFilter }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const editableCompanies = companies.filter((m) => canEditPlanning(m.role));
  const showCompanyColumn = multiCompany && !companyFilter;

  const categoriesById = Object.fromEntries((categories || []).map((c) => [c.id, c]));
  const projectsById = Object.fromEntries((projects || []).map((p) => [p.id, p]));

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(PLAN_EMPTY);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const selectableCategories = (categories || []).filter(
    (c) =>
      !multiCompany ||
      !formCompanyId ||
      c.company_id === formCompanyId ||
      c.is_global ||
      (c.visible_company_ids || []).includes(formCompanyId)
  );
  const selectableProjects = (projects || []).filter(
    (p) =>
      !multiCompany ||
      !formCompanyId ||
      p.company_id === formCompanyId ||
      p.is_global ||
      (p.visible_company_ids || []).includes(formCompanyId)
  );

  function openAdd() {
    setEditingId(null);
    setForm(PLAN_EMPTY);
    const preselected = editableCompanies.find((m) => m.company.id === companyFilter) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setError("");
    setModalOpen(true);
  }

  function openEdit(row) {
    setEditingId(row.id);
    setForm({
      category_id: row.category_id,
      project_id: row.project_id || "",
      amount: String(row.amount),
      frequency: row.frequency,
      scheduled_date: row.scheduled_date,
    });
    setFormCompanyId(row.company_id || "");
    setError("");
    setModalOpen(true);
  }

  function updateFormCompany(companyId) {
    setFormCompanyId(companyId);
    setForm((p) => ({ ...p, category_id: "", project_id: "" }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = {
        category_id: form.category_id,
        project_id: form.project_id || null,
        amount: Number(form.amount || 0),
        frequency: form.frequency,
        scheduled_date: form.scheduled_date,
      };
      if (editingId) await api.updatePlanning(token, editingId, payload);
      else await api.createPlanning(token, payload, formCompanyId || undefined);
      setModalOpen(false);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(row) {
    if (!window.confirm(t("reports.deletePlanConfirm"))) return;
    try {
      await api.deletePlanning(token, row.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-panel fp-table-panel" style={{ marginTop: 16 }}>
      <div className="fp-panel-head fp-panel-head-row" style={{ padding: "18px 18px 0" }}>
        <h3>{t("reports.planningTitle", { year })}</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> {t("reports.addPlan")}
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
            <th>{t("reports.col.category")}</th>
            <th>{t("reports.project")}</th>
            <th>{t("payroll.col.date")}</th>
            <th>{t("reports.frequency")}</th>
            <th className="right">{t("tx.form.amount")}</th>
            <th className="fp-table-actions-col"></th>
          </tr>
        </thead>
        <tbody>
          {(planning || []).map((row) => {
            const canEditRow = canEditPlanning(roleForCompany(row.company_id));
            return (
            <tr key={row.id}>
              {showCompanyColumn && (
                <td>{companies.find((m) => m.company.id === row.company_id)?.company.name || "—"}</td>
              )}
              <td>{categoriesById[row.category_id]?.name || "—"}</td>
              <td>{row.project_id ? projectsById[row.project_id]?.name || "—" : <span className="fp-muted">—</span>}</td>
              <td>{fmtDate(row.scheduled_date)}</td>
              <td className="fp-muted">{t(`reports.frequency.${row.frequency}`)}</td>
              <td className="right fp-mono">{fmt(row.amount, "RUB")}</td>
              <td className="fp-table-actions-col">
                {canEditRow && (
                  <span className="fp-row-actions">
                    <button className="fp-icon-btn" onClick={() => openEdit(row)}>
                      <Pencil size={14} />
                    </button>
                    <button className="fp-icon-btn" onClick={() => handleDelete(row)}>
                      <Trash2 size={14} />
                    </button>
                  </span>
                )}
              </td>
            </tr>
            );
          })}
          {(planning || []).length === 0 && (
            <tr>
              <td colSpan={showCompanyColumn ? 7 : 6} className="fp-empty">
                {t("reports.noPlanning", { year })}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? t("reports.editPlan") : t("reports.newPlan")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  {t("tx.form.company")}
                  {editingId ? (
                    <input
                      type="text"
                      disabled
                      value={companies.find((m) => m.company.id === formCompanyId)?.company.name || ""}
                    />
                  ) : (
                    <select value={formCompanyId} onChange={(e) => updateFormCompany(e.target.value)} required>
                      {editableCompanies.map((m) => (
                        <option key={m.company.id} value={m.company.id}>
                          {m.company.name}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              )}
              <label className="fp-span-2">
                {t("reports.col.category")}
                <select
                  required
                  value={form.category_id}
                  onChange={(e) => setForm((p) => ({ ...p, category_id: e.target.value }))}
                >
                  <option value="" disabled>
                    {t("reports.selectCategory")}
                  </option>
                  {selectableCategories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("reports.project")}
                <select value={form.project_id} onChange={(e) => setForm((p) => ({ ...p, project_id: e.target.value }))}>
                  <option value="">{t("tx.form.notSpecified")}</option>
                  {selectableProjects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payroll.col.date")}
                <input
                  type="date"
                  required
                  value={form.scheduled_date}
                  onChange={(e) => setForm((p) => ({ ...p, scheduled_date: e.target.value }))}
                />
              </label>
              <label>
                {t("reports.frequency")}
                <select value={form.frequency} onChange={(e) => setForm((p) => ({ ...p, frequency: e.target.value }))}>
                  <option value="monthly">{t("reports.frequency.monthly")}</option>
                  <option value="weekly">{t("reports.frequency.weekly")}</option>
                  <option value="once">{t("reports.frequency.once")}</option>
                </select>
              </label>
              <label>
                {t("tx.form.amount")}
                <input
                  type="number"
                  step="0.01"
                  required
                  value={form.amount}
                  onChange={(e) => setForm((p) => ({ ...p, amount: e.target.value }))}
                />
              </label>
              {error && <div className="fp-form-error fp-span-2">{error}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function CalendarTab({ token }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const canEditAnyCompany = (user.companies || []).some((m) => canEditPlanning(m.role));
  const [year, setYear] = useState(new Date().getFullYear());
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error, reload: reloadCalendar } = useResource(
    () => api.paymentCalendar(token, { quarter: String(year), company_id: companyId || undefined }),
    [token, year, companyId]
  );
  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);
  const {
    data: planning,
    reload: reloadPlanning,
  } = useResource(
    () => api.listPlanning(token, { year, company_id: companyId || undefined }),
    [token, year, companyId]
  );

  function reloadAll() {
    reloadCalendar();
    reloadPlanning();
  }

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 100 }} />
      </div>
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

      {canEditAnyCompany && (
        <PlanningPanel
          token={token}
          year={year}
          categories={categories}
          projects={projects}
          planning={planning}
          reload={reloadAll}
          companyFilter={companyId}
        />
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
