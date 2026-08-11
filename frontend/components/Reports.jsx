"use client";

import { Fragment, useState } from "react";
import { Plus, X, Pencil, Trash2 } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditPlanning } from "../lib/roles";

const TABS = [
  { key: "cashflow", label: "Движение денег" },
  { key: "pnl", label: "ОПУ" },
  { key: "balance", label: "Баланс" },
  { key: "debt", label: "Задолженность" },
  { key: "profitability", label: "Рентабельность" },
  { key: "calendar", label: "Платёжный календарь" },
];

// Селектор компании для отчётов — общий для всех вкладок (см. план "Мульти-компании").
// Пусто по умолчанию = сводно по всем доступным компаниям.
function CompanyFilter({ companyId, onChange }) {
  const { user } = useAuth();
  const companies = user.companies || [];
  if (companies.length <= 1) return null;
  return (
    <select value={companyId} onChange={(e) => onChange(e.target.value)} style={{ marginRight: 8 }}>
      <option value="">Все компании</option>
      {companies.map((m) => (
        <option key={m.company.id} value={m.company.id}>
          {m.company.name}
        </option>
      ))}
    </select>
  );
}

function CashflowTab({ token }) {
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
            Сбросить (помесячно)
          </button>
        )}
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">Загрузка…</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{period ? "Статья" : "Период"}</th>
                <th className="right">Приход</th>
                <th className="right">Расход</th>
                <th className="right">Чистый поток</th>
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
                    Нет данных
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
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="Текущий месяц" />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">Загрузка…</div>
      ) : (
        data && (
          <div className="fp-panel">
            <div className="fp-panel-head">
              <h3>
                Отчёт о прибылях и убытках · {data.period_from} — {data.period_to}
              </h3>
            </div>
            <div className="fp-ledger">
              <div className="ledger-row">
                <span className="label">Выручка</span>
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
                <span className="label">Итого расходы</span>
                <span className="fill" />
                <span className="value fp-amount-expense">{fmt(data.total_expense, "RUB")}</span>
              </div>
              <div className="ledger-row fp-ledger-total">
                <span className="label">Чистая прибыль</span>
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
        <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="Сегодня" />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">Загрузка…</div>
      ) : (
        data && (
          <div className="fp-grid-2">
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>Активы на {data.as_of}</h3>
              </div>
              <div className="fp-ledger">
                <div className="ledger-row">
                  <span className="label">Денежные средства</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.cash_rub, "RUB")}</span>
                </div>
                <div className="ledger-row fp-ledger-total">
                  <span className="label">Итого активы</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.total_rub, "RUB")}</span>
                </div>
              </div>
            </div>
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>Пассивы</h3>
              </div>
              <div className="fp-ledger">
                <div className="ledger-row">
                  <span className="label">Задолженность перед сотрудниками</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.payable_to_staff_rub, "RUB")}</span>
                </div>
                <div className="ledger-row fp-ledger-total">
                  <span className="label">Итого пассивы</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.total_rub, "RUB")}</span>
                </div>
                <div className="ledger-row">
                  <span className="label">Нераспределённая прибыль</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.retained_earnings_rub, "RUB")}</span>
                </div>
              </div>
            </div>
          </div>
        )
      )}
      <p className="fp-note">
        Дебиторская задолженность и расходы будущих периодов не отражены — в текущей схеме данных нет реестра
        счетов/инвойсов для их расчёта.
      </p>
    </div>
  );
}

function DebtTab({ token }) {
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
        <div className="fp-loading">Загрузка…</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>Контрагент</th>
                <th>Тип</th>
                <th className="right">Чистый оборот</th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((row) => (
                <tr key={row.counterparty_id}>
                  <td>{row.name}</td>
                  <td className="fp-muted">{row.type === "debtor" ? "Дебитор" : "Кредитор"}</td>
                  <td className="right fp-mono">{fmt(row.net_amount_rub, "RUB")}</td>
                </tr>
              ))}
              {(data || []).length === 0 && (
                <tr>
                  <td colSpan={3} className="fp-empty">
                    Нет операций с контрагентами
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
        <div className="fp-loading">Загрузка…</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>Проект</th>
                <th className="right">Выручка</th>
                <th className="right">Расход</th>
                <th className="right">Прибыль</th>
                <th className="right">Маржа</th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((row) => (
                <tr key={row.project_id}>
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
                    Нет операций, привязанных к проектам
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
    (c) => !multiCompany || !formCompanyId || c.company_id === formCompanyId
  );
  const selectableProjects = (projects || []).filter(
    (p) => !multiCompany || !formCompanyId || p.company_id === formCompanyId
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
    if (!window.confirm("Удалить плановую запись?")) return;
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
        <h3>Плановые платежи, {year}</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Добавить план
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>Компания</th>}
            <th>Статья</th>
            <th>Проект</th>
            <th>Дата</th>
            <th>Частота</th>
            <th className="right">Сумма</th>
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
              <td className="fp-muted">{row.frequency}</td>
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
                Плановых записей на {year} год пока нет
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? "Редактировать план" : "Новый план"}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
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
                Статья
                <select
                  required
                  value={form.category_id}
                  onChange={(e) => setForm((p) => ({ ...p, category_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите статью
                  </option>
                  {selectableCategories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Проект
                <select value={form.project_id} onChange={(e) => setForm((p) => ({ ...p, project_id: e.target.value }))}>
                  <option value="">— не указан —</option>
                  {selectableProjects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Дата
                <input
                  type="date"
                  required
                  value={form.scheduled_date}
                  onChange={(e) => setForm((p) => ({ ...p, scheduled_date: e.target.value }))}
                />
              </label>
              <label>
                Частота
                <select value={form.frequency} onChange={(e) => setForm((p) => ({ ...p, frequency: e.target.value }))}>
                  <option value="monthly">Ежемесячно</option>
                  <option value="weekly">Еженедельно</option>
                  <option value="once">Разово</option>
                </select>
              </label>
              <label>
                Сумма
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
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? "Сохраняем…" : "Сохранить"}
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
        <div className="fp-loading">Загрузка…</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table fp-calendar-table">
            <thead>
              <tr>
                <th>Статья</th>
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
                    <th className="right">План</th>
                    <th className="right">Факт</th>
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
                    Нет плановых или фактических данных за {year} год
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
  const [tab, setTab] = useState("cashflow");
  const ActiveTab = TAB_COMPONENTS[tab];

  return (
    <div className="fp-dash">
      <div className="fp-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>
      <ActiveTab token={token} />
    </div>
  );
}
