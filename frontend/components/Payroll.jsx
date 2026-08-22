"use client";

import { useMemo, useState } from "react";
import { Plus, X, Pencil, Trash2, Wallet, ArrowUpRight, AlertTriangle, RotateCcw } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditPayroll } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";
import { useTranslation } from "../lib/i18n";

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

const EMPLOYEE_EMPTY = { full_name: "", aliases: "", department: "", position: "", employment_type: "", bank_details: "" };

function EmployeesPanel({ token, employees, reload, companyFilter }) {
  const { user } = useAuth();
  const { t } = useTranslation();
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
      aliases: emp.aliases || "",
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
    if (!window.confirm(t("payroll.employees.deleteConfirm", { name: emp.full_name }))) return;
    try {
      const result = await api.deleteEmployee(token, emp.id);
      if (result?.deactivated) {
        window.alert(t("payroll.employees.autoDismissed", { name: emp.full_name }));
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
        <h3>{t("payroll.employees.title")}</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> {t("payroll.employees.add")}
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
            <th>{t("payroll.col.fullName")}</th>
            <th>{t("payroll.col.department")}</th>
            <th>{t("payroll.col.employmentType")}</th>
            <th>{t("payroll.col.status")}</th>
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
                  {dismissed ? t("payroll.status.dismissed") : t("payroll.status.active")}
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
                      title={dismissed ? t("payroll.restore") : t("payroll.markDismissed")}
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
                {t("payroll.noEmployees")}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? t("payroll.editEmployee") : t("payroll.newEmployee")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  {t("tx.form.company")}
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
                          {t("payroll.moveNote")}
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
                {t("payroll.col.fullName")}
                <input
                  required
                  value={form.full_name}
                  onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))}
                />
              </label>
              <label className="fp-span-2">
                {t("payroll.aliases")}
                <input
                  value={form.aliases}
                  onChange={(e) => setForm((p) => ({ ...p, aliases: e.target.value }))}
                  placeholder={t("payroll.aliasesPlaceholder")}
                />
              </label>
              <label>
                {t("payroll.col.department")}
                <input
                  value={form.department}
                  onChange={(e) => setForm((p) => ({ ...p, department: e.target.value }))}
                />
              </label>
              <label>
                {t("payroll.col.employmentType")}
                <input
                  value={form.employment_type}
                  onChange={(e) => setForm((p) => ({ ...p, employment_type: e.target.value }))}
                  placeholder={t("payroll.employmentTypePlaceholder")}
                />
              </label>
              <label className="fp-span-2">
                {t("payroll.bankDetails")}
                <input
                  value={form.bank_details}
                  onChange={(e) => setForm((p) => ({ ...p, bank_details: e.target.value }))}
                  placeholder={t("payroll.bankDetailsPlaceholder")}
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

const ACCRUAL_EMPTY = { employee_id: "", project_id: "", period: new Date().toISOString().slice(0, 10), salary: "0", bonus: "0", deductions: "0" };

function AccrualsPanel({ token, employees, projects, accruals, reload, companyFilter }) {
  const { user } = useAuth();
  const { t } = useTranslation();
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
        <h3>{t("payroll.accruals.title")}</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> {t("payroll.accruals.add")}
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
            <th>{t("payroll.col.employee")}</th>
            <th>{t("payroll.col.period")}</th>
            <th className="right">{t("payroll.col.salary")}</th>
            <th className="right">{t("payroll.col.bonus")}</th>
            <th className="right">{t("payroll.col.deductions")}</th>
            <th className="right">{t("payroll.col.total")}</th>
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
                {t("payroll.noAccruals")}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("payroll.newAccrual")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label className="fp-span-2">
                {t("payroll.col.employee")}
                <select
                  required
                  value={form.employee_id}
                  onChange={(e) => setForm((p) => ({ ...p, employee_id: e.target.value, project_id: "" }))}
                >
                  <option value="" disabled>
                    {t("payroll.selectEmployee")}
                  </option>
                  {(employees || []).map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("tx.form.project")}
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
                {t("payroll.col.period")}
                <input
                  type="date"
                  required
                  value={form.period}
                  onChange={(e) => setForm((p) => ({ ...p, period: e.target.value }))}
                />
              </label>
              <label>
                {t("payroll.col.salary")}
                <input
                  type="number"
                  step="0.01"
                  value={form.salary}
                  onChange={(e) => setForm((p) => ({ ...p, salary: e.target.value }))}
                />
              </label>
              <label>
                {t("payroll.col.bonus")}
                <input
                  type="number"
                  step="0.01"
                  value={form.bonus}
                  onChange={(e) => setForm((p) => ({ ...p, bonus: e.target.value }))}
                />
              </label>
              <label>
                {t("payroll.col.deductions")}
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
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("payroll.accruals.add")}
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

// Значения хранятся в БД как русские строки (payment_type — свободный текст,
// не enum) — при переводе меняем только отображаемую подпись, не value.
const PAYMENT_TYPE_LABEL_KEYS = {
  "ЗП": "payroll.paymentType.salary",
  "Аванс": "payroll.paymentType.advance",
  "Долг": "payroll.paymentType.debt",
  "Бонус": "payroll.paymentType.bonus",
};

function PaymentsPanel({ token, employees, accounts, accruals, payments, reload, companyFilter }) {
  const { user } = useAuth();
  const { t } = useTranslation();
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
        <h3>{t("payroll.payments.title")}</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> {t("payroll.payments.add")}
        </button>
      </div>
      <table className="fp-table">
        <thead>
          <tr>
            {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
            <th>{t("payroll.col.employee")}</th>
            <th>{t("payroll.col.date")}</th>
            <th>{t("payroll.col.account")}</th>
            <th>{t("payroll.col.type")}</th>
            <th className="right">{t("payroll.col.amount")}</th>
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
              <td className="fp-muted">
                {PAYMENT_TYPE_LABEL_KEYS[p.payment_type] ? t(PAYMENT_TYPE_LABEL_KEYS[p.payment_type]) : p.payment_type}
              </td>
              <td className="right fp-mono">{fmt(p.amount, "RUB")}</td>
            </tr>
          ))}
          {(payments || []).length === 0 && (
            <tr>
              <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                {t("payroll.noPayments")}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("payroll.newPayment")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label className="fp-span-2">
                {t("payroll.col.employee")}
                <select
                  required
                  value={form.employee_id}
                  onChange={(e) =>
                    setForm((p) => ({ ...p, employee_id: e.target.value, accrual_id: "", account_id: "" }))
                  }
                >
                  <option value="" disabled>
                    {t("payroll.selectEmployee")}
                  </option>
                  {(employees || []).map((emp) => (
                    <option key={emp.id} value={emp.id}>
                      {emp.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payroll.accrualOptional")}
                <select value={form.accrual_id} onChange={(e) => setForm((p) => ({ ...p, accrual_id: e.target.value }))}>
                  <option value="">{t("payroll.notLinked")}</option>
                  {employeeAccruals.map((a) => (
                    <option key={a.id} value={a.id}>
                      {fmtDate(a.period)} · {fmt(a.total, "RUB")}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payroll.writeOffAccount")}
                <select
                  required
                  value={form.account_id}
                  onChange={(e) => setForm((p) => ({ ...p, account_id: e.target.value }))}
                >
                  <option value="" disabled>
                    {t("payroll.selectAccount")}
                  </option>
                  {selectableAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payroll.col.date")}
                <input
                  type="date"
                  required
                  value={form.date}
                  onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                {t("payroll.paymentType")}
                <select
                  value={form.payment_type}
                  onChange={(e) => setForm((p) => ({ ...p, payment_type: e.target.value }))}
                >
                  {Object.entries(PAYMENT_TYPE_LABEL_KEYS).map(([value, labelKey]) => (
                    <option key={value} value={value}>
                      {t(labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payroll.col.amount")}
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
                  {saving ? t("common.saving") : t("payroll.payments.add")}
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
  const { t } = useTranslation();
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
            <option value="">{t("dashboard.allCompanies")}</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <section className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <KpiCard label={t("payroll.kpi.accrued")} value={fmt(totalAccrued, "RUB")} tone="neutral" icon={<Wallet size={16} />} />
        <KpiCard label={t("payroll.kpi.paid")} value={fmt(totalPaid, "RUB")} tone="income" icon={<ArrowUpRight size={16} />} />
        <KpiCard
          label={t("payroll.kpi.outstanding")}
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
  const { t } = useTranslation();
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
            <option value="">{t("dashboard.allCompanies")}</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : error ? (
        <div className="fp-error-banner">{error}</div>
      ) : (
        data && (
          <>
            <section className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
              <KpiCard label={t("payroll.kpi.accrued")} value={fmt(data.total_accrued, "RUB")} tone="neutral" icon={<Wallet size={16} />} />
              <KpiCard label={t("payroll.kpi.paid")} value={fmt(data.total_paid, "RUB")} tone="income" icon={<ArrowUpRight size={16} />} />
              <KpiCard
                label={t("payroll.kpi.outstanding")}
                value={fmt(data.outstanding, "RUB")}
                tone={data.outstanding > 0 ? "expense" : "income"}
                icon={<AlertTriangle size={16} />}
              />
            </section>
            <p className="fp-note">{t("payroll.summaryNote", { count: data.employees_count })}</p>
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
