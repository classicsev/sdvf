"use client";

import { useState } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";

const MODULES = [
  {
    key: "module_finance_enabled",
    title: "Учёт",
    description: "Операции, отчёты, зарплата, автоматизация и интеграции банков/CRM.",
  },
  {
    key: "module_warehouse_enabled",
    title: "Склад",
    description: "Остатки, движения, заказы, производство.",
  },
];

const SDVF_FIELDS = [
  { key: "sdvf_org_naming", label: "Наименование организации", required: true },
  { key: "sdvf_org_inn", label: "ИНН", required: true },
  { key: "sdvf_org_kpp", label: "КПП" },
  { key: "sdvf_org_ogrn", label: "ОГРН/ОГРНИП" },
  { key: "sdvf_org_address", label: "Адрес" },
  { key: "sdvf_org_phone", label: "Телефон" },
];

const ROLE_LABELS = {
  admin: "Администратор",
  operator: "Оператор",
  payroll_operator: "Оператор зарплаты",
  project_manager: "Руководитель проекта",
  viewer: "Наблюдатель",
  warehouse_operator: "Оператор склада",
};

export default function CompanyModules() {
  const { token, user, refreshUser } = useAuth();
  const [busyKey, setBusyKey] = useState(null);
  const [error, setError] = useState("");
  const company = user.company;

  // --- Мульти-компании (см. план "Мульти-компании") ---
  const [companies, setCompanies] = useState(user.companies || []);
  const [newCompanyOpen, setNewCompanyOpen] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyType, setNewCompanyType] = useState("legal_entity");
  const [companySaving, setCompanySaving] = useState(false);
  const [inviteOpenFor, setInviteOpenFor] = useState(null);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "viewer", full_name: "", password: "" });
  const [inviteSaving, setInviteSaving] = useState(false);
  const [inviteError, setInviteError] = useState("");

  async function refreshCompanies() {
    const list = await api.listCompanies(token);
    setCompanies(list);
  }

  async function createCompany(e) {
    e.preventDefault();
    setError("");
    setCompanySaving(true);
    try {
      await api.createCompany(token, { name: newCompanyName, company_type: newCompanyType });
      setNewCompanyName("");
      setNewCompanyOpen(false);
      await refreshCompanies();
      await refreshUser();
    } catch (err) {
      setError(err.message || "Не удалось создать компанию");
    } finally {
      setCompanySaving(false);
    }
  }

  async function inviteMember(e, companyId) {
    e.preventDefault();
    setInviteError("");
    setInviteSaving(true);
    try {
      await api.addCompanyMember(token, companyId, {
        email: inviteForm.email,
        role: inviteForm.role,
        full_name: inviteForm.full_name || undefined,
        password: inviteForm.password || undefined,
      });
      setInviteForm({ email: "", role: "viewer", full_name: "", password: "" });
      setInviteOpenFor(null);
    } catch (err) {
      setInviteError(err.message || "Не удалось добавить пользователя");
    } finally {
      setInviteSaving(false);
    }
  }

  const [sdvfForm, setSdvfForm] = useState(
    Object.fromEntries(SDVF_FIELDS.map((f) => [f.key, company[f.key] || ""]))
  );
  const [sdvfSaving, setSdvfSaving] = useState(false);
  const [sdvfSaved, setSdvfSaved] = useState(false);

  async function toggle(moduleKey, value) {
    setError("");
    setBusyKey(moduleKey);
    try {
      await api.updateCompanyModules(token, { [moduleKey]: value });
      await refreshUser();
    } catch (err) {
      setError(err.message || "Не удалось сохранить");
    } finally {
      setBusyKey(null);
    }
  }

  async function saveSdvfForm(e) {
    e.preventDefault();
    setError("");
    setSdvfSaving(true);
    setSdvfSaved(false);
    try {
      await api.updateCompanyModules(token, sdvfForm);
      await refreshUser();
      setSdvfSaved(true);
    } catch (err) {
      setError(err.message || "Не удалось сохранить");
    } finally {
      setSdvfSaving(false);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>Модули</h3>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Мои компании</div>
          <button
            type="button"
            className="fp-btn-primary"
            onClick={() => setNewCompanyOpen((v) => !v)}
          >
            + Добавить компанию
          </button>
        </div>

        {newCompanyOpen && (
          <form
            className="fp-form-grid"
            onSubmit={createCompany}
            style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}
          >
            <label className="fp-span-2">
              Название
              <input
                required
                value={newCompanyName}
                onChange={(e) => setNewCompanyName(e.target.value)}
                placeholder='Например, ООО "Тихоокеанская Фактория" или "Личные счета"'
              />
            </label>
            <label>
              Тип
              <select value={newCompanyType} onChange={(e) => setNewCompanyType(e.target.value)}>
                <option value="legal_entity">Юрлицо/ИП</option>
                <option value="individual">Личные счета (физлицо)</option>
              </select>
            </label>
            <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
              <button type="submit" className="fp-btn-primary" disabled={companySaving}>
                {companySaving ? "Создаём…" : "Создать"}
              </button>
            </div>
          </form>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {companies.map((m) => (
            <div key={m.company.id}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "8px 12px",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{m.company.name}</div>
                  <div className="fp-muted" style={{ fontSize: 12 }}>
                    {m.company.company_type === "individual" ? "Личные счета" : "Юрлицо/ИП"} ·{" "}
                    {ROLE_LABELS[m.role] || m.role}
                  </div>
                </div>
                {m.role === "admin" && (
                  <button
                    type="button"
                    className="fp-btn-ghost"
                    onClick={() => setInviteOpenFor(inviteOpenFor === m.company.id ? null : m.company.id)}
                  >
                    + Пользователь
                  </button>
                )}
              </div>

              {inviteOpenFor === m.company.id && (
                <form
                  className="fp-form-grid"
                  onSubmit={(e) => inviteMember(e, m.company.id)}
                  style={{ border: "1px solid var(--line)", borderTop: "none", borderRadius: "0 0 8px 8px", padding: 12 }}
                >
                  <label>
                    Email
                    <input
                      required
                      type="email"
                      value={inviteForm.email}
                      onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))}
                    />
                  </label>
                  <label>
                    Роль
                    <select
                      value={inviteForm.role}
                      onChange={(e) => setInviteForm((f) => ({ ...f, role: e.target.value }))}
                    >
                      {Object.entries(ROLE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="fp-span-2 fp-note" style={{ margin: 0 }}>
                    Если у этого email уже есть аккаунт в Учёте — просто получит доступ. Если нет —
                    укажите имя и пароль, чтобы создать новый.
                  </div>
                  <label>
                    Имя (для нового аккаунта)
                    <input
                      value={inviteForm.full_name}
                      onChange={(e) => setInviteForm((f) => ({ ...f, full_name: e.target.value }))}
                    />
                  </label>
                  <label>
                    Пароль (для нового аккаунта)
                    <input
                      type="password"
                      value={inviteForm.password}
                      onChange={(e) => setInviteForm((f) => ({ ...f, password: e.target.value }))}
                    />
                  </label>
                  {inviteError && <div className="fp-form-error fp-span-2">{inviteError}</div>}
                  <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                    <button type="submit" className="fp-btn-primary" disabled={inviteSaving}>
                      {inviteSaving ? "Добавляем…" : "Добавить"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="fp-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="fp-note" style={{ margin: 0 }}>
          Компания «{company.name}». Оплата пока не требуется — включайте и выключайте модули
          свободно, биллинг подключим позже.
        </p>
        {MODULES.map((m) => (
          <label
            key={m.key}
            className="fp-switch"
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: 12,
              border: "1px solid var(--line)",
              borderRadius: 8,
              cursor: busyKey ? "default" : "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={Boolean(company[m.key])}
              disabled={busyKey === m.key}
              onChange={(e) => toggle(m.key, e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <div>
              <div style={{ fontWeight: 600 }}>{m.title}</div>
              <div className="fp-muted" style={{ fontSize: 12.5 }}>
                {m.description}
              </div>
            </div>
          </label>
        ))}
      </div>

      <div className="fp-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ fontWeight: 600 }}>Реквизиты для СДВФ</div>
          <p className="fp-note" style={{ margin: "4px 0 0" }}>
            Нужны для генерации Счёт/УПД из карточки заказа в Складе — заполняются один раз.
          </p>
        </div>
        <form className="fp-form-grid" onSubmit={saveSdvfForm}>
          {SDVF_FIELDS.map((f) => (
            <label key={f.key}>
              {f.label}
              <input
                required={f.required}
                value={sdvfForm[f.key]}
                onChange={(e) => {
                  setSdvfSaved(false);
                  setSdvfForm((p) => ({ ...p, [f.key]: e.target.value }));
                }}
              />
            </label>
          ))}
          <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="fp-btn-primary" disabled={sdvfSaving}>
              {sdvfSaving ? "Сохраняем…" : "Сохранить"}
            </button>
            {sdvfSaved && <span className="fp-muted" style={{ fontSize: 12.5 }}>Сохранено</span>}
          </div>
        </form>
      </div>
    </div>
  );
}
