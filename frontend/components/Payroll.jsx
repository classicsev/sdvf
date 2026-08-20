"use client";

import { useMemo, useState } from "react";
import { Plus, X, Pencil, Trash2, Wallet, ArrowUpRight, AlertTriangle, RotateCcw } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditPayroll } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";

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

const EMPLOYEE_EMPTY = { full_name: "", department: "", position: "", employment_type: "", bank_details: "" };

function EmployeesPanel({ token, employees, reload, companyFilter }) {
  const { user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const editableCompanies = companies.filter((m) => canEditPayroll(m.role));
  const showCompanyColumn = multiCompany && !companyFilter;

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPLOYEE_EMPTY);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [originalCompanyId, setOriginalCompanyId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function openAdd() {
    setEditingId(null);
    setForm(EMPLOYEE_EMPTY);
    const preselected = editableCompanies.find((m) => m.company.id === companyFilter) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setOriginalCompanyId("");
    setError("");
    setModalOpen(true);
  }
  function openEdit(emp) {
    setEditingId(emp.id);
    setForm({
      full_name: emp.full_name,
      department: emp.department || "",
      position: emp.position || "",
      employment_type: emp.employment_type || "",
      bank_details: emp.bank_details || "",
    });
    setFormCompanyId(emp.company_id || "");
    setOriginalCompanyId(emp.company_id || "");
    setError("");
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (editingId) {
        // Перенос в другую компанию — отдельным вызовом раньше остальных правок
        // (бэкенд блокирует его, если у сотрудника уже есть начисления/выплаты).
        if (multiCompany && formCompanyId && formCompanyId !== originalCompanyId) {
          await api.moveEmployeeCompany(token, editingId, formCompanyId);
        }
        await api.updateEmployee(token, editingId, form);
      } else {
        await api.createEmployee(token, form, formCompanyId || undefined);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(emp) {
    if (!window.confirm(`Удалить сотрудника «${emp.full_name}»?`)) return;
    try {
      const result = await api.deleteEmployee(token, emp.id);
      if (result?.deactivated) {
        window.alert(
          `«${emp.full_name}» уже есть начисления/выплаты, поэтому не удалён, а помечен как уволенный — ` +
            `история сохранена. Восстановить можно кнопкой в списке.`
        );
      }
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleToggleStatus(emp) {
    try {
      await api.toggleEmployeeStatus(token, emp.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-panel fp-table-panel">
      <div className="fp-panel-head fp-panel-head-row" style={{ padding: "18px 18px 0" }}>
        <h3>Сотрудники</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Добавить сотрудника
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>Компания</th>}
            <th>ФИО</th>
            <th>Отдел</th>
            <th>Тип занятости</th>
            <th>Статус</th>
            <th className="fp-table-actions-col"></th>
          </tr>
        </thead>
        <tbody>
          {(employees || []).map((emp) => {
            const canEditRow = canEditPayroll(roleForCompany(emp.company_id));
            const dismissed = emp.status === "dismissed";
            return (
            <tr key={emp.id}>
              {showCompanyColumn && (
                <td>{companies.find((m) => m.company.id === emp.company_id)?.company.name || "—"}</td>
              )}
              <td>{emp.full_name}</td>
              <td className="fp-muted">{emp.department || "—"}</td>
              <td className="fp-muted">{emp.employment_type || "—"}</td>
              <td>
                <span className={`fp-status-badge ${dismissed ? "warn" : "ok"}`}>
                  {dismissed ? "Уволен" : "Работает"}
                </span>
              </td>
              <td className="fp-table-actions-col">
                {canEditRow && (
                  <span className="fp-row-actions">
                    <button className="fp-icon-btn" onClick={() => openEdit(emp)}>
                      <Pencil size={14} />
                    </button>
                    <button
                      className="fp-icon-btn"
                      onClick={() => handleToggleStatus(emp)}
                      title={dismissed ? "Восстановить" : "Пометить уволенным"}
                    >
                      <RotateCcw size={14} />
                    </button>
                    <button className="fp-icon-btn" onClick={() => handleDelete(emp)}>
                      <Trash2 size={14} />
                    </button>
                  </span>
                )}
              </td>
            </tr>
            );
          })}
          {(employees || []).length === 0 && (
            <tr>
              <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                Сотрудников пока нет
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? "Редактировать сотрудника" : "Новый сотрудник"}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
                  {editingId ? (
                    <>
                      <select value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)} required>
                        {!editableCompanies.some((m) => m.company.id === originalCompanyId) &&
                          originalCompanyId &&
                          companies
                            .filter((m) => m.company.id === originalCompanyId)
                            .map((m) => (
                              <option key={m.company.id} value={m.company.id}>
                                {m.company.name}
                              </option>
                            ))}
                        {editableCompanies.map((m) => (
                          <option key={m.company.id} value={m.company.id}>
                            {m.company.name}
                          </option>
                        ))}
                      </select>
                      {formCompanyId !== originalCompanyId && (
                        <span className="fp-muted" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                          Перенос сработает, только если у сотрудника ещё нет начислений/выплат.
                        </span>
                      )}
                    </>
                  ) : (
                    <select value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)} required>
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
                ФИО
                <input
                  required
                  value={form.full_name}
                  onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))}
                />
              </label>
              <label>
                Отдел
                <input
                  value={form.department}
                  onChange={(e) => setForm((p) => ({ ...p, department: e.target.value }))}
                />
              </label>
              <label>
                Тип занятости
                <input
                  value={form.employment_type}
                  onChange={(e) => setForm((p) => ({ ...p, employment_type: e.target.value }))}
                  placeholder="ИП / Самозанятый"
                />
              </label>
              <label className="fp-span-2">
                Банковские реквизиты
                <input
                  value={form.bank_details}
                  onChange={(e) => setForm((p) => ({ ...p, bank_details: e.target.value }))}
                  placeholder="Банк, номер карты/счёта"
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

const ACCRUAL_EMPTY = { employee_id: "", project_id: "", period: new Date().toISOString().slice(0, 10), salary: "0", bonus: "0", deductions: "0" };

function AccrualsPanel({ token, employees, projects, accruals, reload, companyFilter }) {
  const { user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const showCompanyColumn = multiCompany && !companyFilter;

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(ACCRUAL_EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const employeesById = useMemo(() => Object.fromEntries((employees || []).map((e) => [e.id, e])), [employees]);

  // Проект должен принадлежать той же компании, что и выбранный сотрудник.
  const selectedEmployee = employeesById[form.employee_id];
  const selectableProjects = (projects || []).filter(
    (p) =>
      !selectedEmployee ||
      p.company_id === selectedEmployee.company_id ||
      p.is_global ||
      (p.visible_company_ids || []).includes(selectedEmployee.company_id)
  );

  function openAdd() {
    setForm(ACCRUAL_EMPTY);
    setError("");
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.createAccrual(token, {
        employee_id: form.employee_id,
        project_id: form.project_id || null,
        period: form.period,
        salary: Number(form.salary || 0),
        bonus: Number(form.bonus || 0),
        deductions: Number(form.deductions || 0),
      });
      setModalOpen(false);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fp-panel fp-table-panel">
      <div className="fp-panel-head fp-panel-head-row" style={{ padding: "18px 18px 0" }}>
        <h3>Начисления</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Начислить
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>Компания</th>}
            <th>Сотрудник</th>
            <th>Период</th>
            <th className="right">Оклад</th>
            <th className="right">Бонус</th>
            <th className="right">Удержания</th>
            <th className="right">Итого</th>
          </tr>
        </thead>
        <tbody>
          {(accruals || []).map((a) => (
            <tr key={a.id}>
              {showCompanyColumn && (
                <td>{companies.find((m) => m.company.id === a.company_id)?.company.name || "—"}</td>
              )}
              <td>{employeesById[a.employee_id]?.full_name || "—"}</td>
              <td>{fmtDate(a.period)}</td>
              <td className="right fp-mono">{fmt(a.salary, "RUB")}</td>
              <td className="right fp-mono">{fmt(a.bonus, "RUB")}</td>
              <td className="right fp-mono">{fmt(a.deductions, "RUB")}</td>
              <td className="right fp-mono">{fmt(a.total, "RUB")}</td>
            </tr>
          ))}
          {(accruals || []).length === 0 && (
            <tr>
              <td colSpan={showCompanyColumn ? 7 : 6} className="fp-empty">
                Начислений пока нет
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Новое начисление</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label className="fp-span-2">
                Сотрудник
                <select
                  required
                  value={form.employee_id}
                  onChange={(e) => setForm((p) => ({ ...p, employee_id: e.target.value, project_id: "" }))}
                >
                  <option value="" disabled>
                    Выберите сотрудника
                  </option>
                  {(employees || []).map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name}
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
                Период
                <input
                  type="date"
                  required
                  value={form.period}
                  onChange={(e) => setForm((p) => ({ ...p, period: e.target.value }))}
                />
              </label>
              <label>
                Оклад
                <input
                  type="number"
                  step="0.01"
                  value={form.salary}
                  onChange={(e) => setForm((p) => ({ ...p, salary: e.target.value }))}
                />
              </label>
              <label>
                Бонус
                <input
                  type="number"
                  step="0.01"
                  value={form.bonus}
                  onChange={(e) => setForm((p) => ({ ...p, bonus: e.target.value }))}
                />
              </label>
              <label>
                Удержания
                <input
                  type="number"
                  step="0.01"
                  value={form.deductions}
                  onChange={(e) => setForm((p) => ({ ...p, deductions: e.target.value }))}
                />
              </label>
              {error && <div className="fp-form-error fp-span-2">{error}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? "Сохраняем…" : "Начислить"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

const PAYMENT_EMPTY = { employee_id: "", accrual_id: "", account_id: "", date: new Date().toISOString().slice(0, 10), amount: "0", payment_type: "ЗП" };

function PaymentsPanel({ token, employees, accounts, accruals, payments, reload, companyFilter }) {
  const { user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const showCompanyColumn = multiCompany && !companyFilter;

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(PAYMENT_EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const employeesById = useMemo(() => Object.fromEntries((employees || []).map((e) => [e.id, e])), [employees]);
  const accountsById = useMemo(() => Object.fromEntries((accounts || []).map((a) => [a.id, a])), [accounts]);

  const selectedEmployee = employeesById[form.employee_id];
  const selectableAccounts = (accounts || []).filter(
    (a) => !selectedEmployee || a.company_id === selectedEmployee.company_id
  );

  function openAdd() {
    setForm(PAYMENT_EMPTY);
    setError("");
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.createPayment(token, {
        employee_id: form.employee_id,
        accrual_id: form.accrual_id || null,
        account_id: form.account_id,
        date: form.date,
        amount: Number(form.amount || 0),
        payment_type: form.payment_type,
      });
      setModalOpen(false);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const employeeAccruals = (accruals || []).filter((a) => a.employee_id === form.employee_id);

  return (
    <div className="fp-panel fp-table-panel">
      <div className="fp-panel-head fp-panel-head-row" style={{ padding: "18px 18px 0" }}>
        <h3>Выплаты</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Выплатить
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>Компания</th>}
            <th>Сотрудник</th>
            <th>Дата</th>
            <th>Счёт</th>
            <th>Тип</th>
            <th className="right">Сумма</th>
          </tr>
        </thead>
        <tbody>
          {(payments || []).map((p) => (
            <tr key={p.id}>
              {showCompanyColumn && (
                <td>{companies.find((m) => m.company.id === p.company_id)?.company.name || "—"}</td>
              )}
              <td>{employeesById[p.employee_id]?.full_name || "—"}</td>
              <td>{fmtDate(p.date)}</td>
              <td>{accountsById[p.account_id]?.name || "—"}</td>
              <td className="fp-muted">{p.payment_type}</td>
              <td className="right fp-mono">{fmt(p.amount, "RUB")}</td>
            </tr>
          ))}
          {(payments || []).length === 0 && (
            <tr>
              <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                Выплат пока нет
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Новая выплата</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label className="fp-span-2">
                Сотрудник
                <select
                  required
                  value={form.employee_id}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, employee_id: e.target.value, accrual_id: "", account_id: "" }))
                  }
                >
                  <option value="" disabled>
                    Выберите сотрудника
                  </option>
                  {(employees || []).map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Начисление (опц.)
                <select value={form.accrual_id} onChange={(e) => setForm((p) => ({ ...p, accrual_id: e.target.value }))}>
                  <option value="">— не привязано —</option>
                  {employeeAccruals.map((a) => (
                    <option key={a.id} value={a.id}>
                      {fmtDate(a.period)} · {fmt(a.total, "RUB")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Счёт списания
                <select
                  required
                  value={form.account_id}
                  onChange={(e) => setForm((p) => ({ ...p, account_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите счёт
                  </option>
                  {selectableAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Дата
                <input
                  type="date"
                  required
                  value={form.date}
                  onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                Тип выплаты
                <select
                  value={form.payment_type}
                  onChange={(e) => setForm((p) => ({ ...p, payment_type: e.target.value }))}
                >
                  <option value="ЗП">ЗП</option>
                  <option value="Аванс">Аванс</option>
                  <option value="Долг">Долг</option>
                  <option value="Бонус">Бонус</option>
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
                  {saving ? "Сохраняем…" : "Выплатить"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function PayrollDetailed({ token }) {
  const { user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const [companyId, setCompanyId] = useState("");
  const query = { company_id: companyId || undefined };

  const { data: employees, reload: reloadEmployees } = useResource(
    () => api.listEmployees(token, query),
    [token, companyId]
  );
  const { data: accruals, reload: reloadAccruals } = useResource(
    () => api.listAccruals(token, query),
    [token, companyId]
  );
  const { data: payments, reload: reloadPayments } = useResource(
    () => api.listPayments(token, query),
    [token, companyId]
  );
  const { data: accounts } = useResource(() => api.listAccounts(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);

  const totalAccrued = (accruals || []).reduce((s, a) => s + a.total, 0);
  const totalPaid = (payments || []).reduce((s, p) => s + p.amount, 0);
  const remaining = totalAccrued - totalPaid;

  return (
    <div className="fp-dash">
      {multiCompany && (
        <div style={{ marginBottom: 14 }}>
          <select value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
            <option value="">Все компании</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <section className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <KpiCard label="Начислено" value={fmt(totalAccrued, "RUB")} tone="neutral" icon={<Wallet size={16} />} />
        <KpiCard label="Выплачено" value={fmt(totalPaid, "RUB")} tone="income" icon={<ArrowUpRight size={16} />} />
        <KpiCard
          label="Остаток к выплате"
          value={fmt(remaining, "RUB")}
          tone={remaining > 0 ? "expense" : "income"}
          icon={<AlertTriangle size={16} />}
        />
      </section>

      <EmployeesPanel token={token} employees={employees} reload={reloadEmployees} companyFilter={companyId} />
      <div style={{ height: 16 }} />
      <AccrualsPanel
        token={token}
        employees={employees}
        projects={projects}
        accruals={accruals}
        reload={reloadAccruals}
        companyFilter={companyId}
      />
      <div style={{ height: 16 }} />
      <PaymentsPanel
        token={token}
        employees={employees}
        accounts={accounts}
        accruals={accruals}
        payments={payments}
        reload={reloadPayments}
        companyFilter={companyId}
      />
    </div>
  );
}

function PayrollSummary({ token }) {
  const { user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.payrollSummary(token, { company_id: companyId || undefined }),
    [token, companyId]
  );

  return (
    <div className="fp-dash">
      {multiCompany && (
        <div style={{ marginBottom: 14 }}>
          <select value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
            <option value="">Все компании</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {loading ? (
        <div className="fp-loading">Загрузка…</div>
      ) : error ? (
        <div className="fp-error-banner">{error}</div>
      ) : (
        data && (
          <>
            <section className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
              <KpiCard label="Начислено" value={fmt(data.total_accrued, "RUB")} tone="neutral" icon={<Wallet size={16} />} />
              <KpiCard label="Выплачено" value={fmt(data.total_paid, "RUB")} tone="income" icon={<ArrowUpRight size={16} />} />
              <KpiCard
                label="Остаток к выплате"
                value={fmt(data.outstanding, "RUB")}
                tone={data.outstanding > 0 ? "expense" : "income"}
                icon={<AlertTriangle size={16} />}
              />
            </section>
            <p className="fp-note">
              Сводка без ФИО и реквизитов сотрудников · {data.employees_count} сотрудников с начислениями
            </p>
          </>
        )
      )}
    </div>
  );
}

export default function Payroll() {
  const { token, user } = useAuth();
  const canEditAnyCompany = (user.companies || []).some((m) => canEditPayroll(m.role));
  return canEditAnyCompany ? <PayrollDetailed token={token} /> : <PayrollSummary token={token} />
}
