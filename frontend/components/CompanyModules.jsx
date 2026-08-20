"use client";

import { useState } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { ROLE_LABELS, ROLE_DESCRIPTIONS } from "../lib/roles";

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
  {
    key: "module_china_enabled",
    title: "Китай (中国)",
    description: "Реквизиты компаний КНР, двуязычные RU/中文 документы и учёт по CNY.",
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

const CN_FIELDS = [
  { key: "cn_org_name_zh", label: "Название (中文名称)", required: true },
  { key: "cn_org_credit_code", label: "Единый соц.-кредитный код (统一社会信用代码)", required: true },
  { key: "cn_org_legal_rep", label: "Директор/учредитель (法定代表人)", required: true },
  { key: "cn_org_address_zh", label: "Юридический адрес (住所)" },
  { key: "cn_org_registered_capital", label: "Уставный капитал, CNY (注册资本)", type: "number" },
  { key: "cn_org_established_date", label: "Дата регистрации (成立日期)", type: "date" },
  { key: "cn_org_business_scope_zh", label: "Виды деятельности (经营范围)", textarea: true },
];

const EDIT_FORM_EMPTY = { name: "", company_type: "legal_entity" };
const SDVF_FORM_EMPTY = Object.fromEntries(SDVF_FIELDS.map((f) => [f.key, ""]));
const CN_FORM_EMPTY = Object.fromEntries(CN_FIELDS.map((f) => [f.key, ""]));

export default function CompanyModules() {
  const { token, user, refreshUser } = useAuth();
  const [error, setError] = useState("");

  const [companies, setCompanies] = useState(user.companies || []);
  const [newCompanyOpen, setNewCompanyOpen] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyType, setNewCompanyType] = useState("legal_entity");
  const [companySaving, setCompanySaving] = useState(false);
  const [inviteOpenFor, setInviteOpenFor] = useState(null);
  const [inviteForm, setInviteForm] = useState({ email: "", role: "viewer", full_name: "", password: "" });
  const [inviteSaving, setInviteSaving] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [rolesHelpOpen, setRolesHelpOpen] = useState(false);

  // Настройки конкретной компании (правка названия, модули, реквизиты СДВФ,
  // удаление) — разворачиваются под карточкой, только одна панель за раз.
  const [settingsFor, setSettingsFor] = useState(null);
  const [editForm, setEditForm] = useState(EDIT_FORM_EMPTY);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState("");
  const [moduleBusyKey, setModuleBusyKey] = useState(null);
  const [sdvfForm, setSdvfForm] = useState(SDVF_FORM_EMPTY);
  const [sdvfSaving, setSdvfSaving] = useState(false);
  const [sdvfSaved, setSdvfSaved] = useState(false);
  const [innLookup, setInnLookup] = useState({ loading: false, message: "", error: "" });
  const [cnForm, setCnForm] = useState(CN_FORM_EMPTY);
  const [cnSaving, setCnSaving] = useState(false);
  const [cnSaved, setCnSaved] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const activeCompany = companies.find((m) => m.company.id === settingsFor)?.company || null;

  function cancelNewCompany() {
    setNewCompanyOpen(false);
    setNewCompanyName("");
    setNewCompanyType("legal_entity");
    setError("");
  }

  function cancelInvite() {
    setInviteOpenFor(null);
    setInviteForm({ email: "", role: "viewer", full_name: "", password: "" });
    setInviteError("");
    setRolesHelpOpen(false);
  }

  async function refreshCompanies() {
    const list = await api.listCompanies(token);
    setCompanies(list);
    return list;
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

  function openSettings(company) {
    setSettingsFor(settingsFor === company.id ? null : company.id);
    setEditForm({ name: company.name, company_type: company.company_type || "legal_entity" });
    setEditError("");
    setSdvfForm(Object.fromEntries(SDVF_FIELDS.map((f) => [f.key, company[f.key] || ""])));
    setSdvfSaved(false);
    setInnLookup({ loading: false, message: "", error: "" });
    setCnForm(Object.fromEntries(CN_FIELDS.map((f) => [f.key, company[f.key] || ""])));
    setCnSaved(false);
    setDeleteError("");
  }

  async function saveCompanyEdit(e) {
    e.preventDefault();
    setEditError("");
    setEditSaving(true);
    try {
      await api.updateCompany(token, settingsFor, editForm);
      await refreshCompanies();
      await refreshUser();
    } catch (err) {
      setEditError(err.message || "Не удалось сохранить");
    } finally {
      setEditSaving(false);
    }
  }

  async function toggleModule(moduleKey, value) {
    setModuleBusyKey(moduleKey);
    try {
      await api.updateCompanyModulesFor(token, settingsFor, { [moduleKey]: value });
      await refreshCompanies();
      await refreshUser();
    } catch (err) {
      setEditError(err.message || "Не удалось сохранить");
    } finally {
      setModuleBusyKey(null);
    }
  }

  const innIsValid = /^(\d{10}|\d{12})$/.test((sdvfForm.sdvf_org_inn || "").trim());

  async function fillFromInn() {
    const inn = (sdvfForm.sdvf_org_inn || "").trim();
    setInnLookup({ loading: true, message: "", error: "" });
    try {
      const found = await api.findPartyByInn(token, inn);
      setSdvfForm((p) => ({
        ...p,
        sdvf_org_naming: found.name || p.sdvf_org_naming,
        sdvf_org_inn: found.inn || p.sdvf_org_inn,
        sdvf_org_kpp: found.kpp || p.sdvf_org_kpp,
        sdvf_org_ogrn: found.ogrn || p.sdvf_org_ogrn,
        sdvf_org_address: found.address || p.sdvf_org_address,
      }));
      setSdvfSaved(false);
      setInnLookup({
        loading: false,
        message: `Найдено: ${found.name}. Проверьте и нажмите «Сохранить».`,
        error: "",
      });
    } catch (err) {
      setInnLookup({ loading: false, message: "", error: err.message || "Не удалось найти по ИНН" });
    }
  }

  async function saveSdvfForm(e) {
    e.preventDefault();
    setEditError("");
    setSdvfSaving(true);
    setSdvfSaved(false);
    try {
      await api.updateCompanyModulesFor(token, settingsFor, sdvfForm);
      await refreshCompanies();
      await refreshUser();
      setSdvfSaved(true);
    } catch (err) {
      setEditError(err.message || "Не удалось сохранить");
    } finally {
      setSdvfSaving(false);
    }
  }

  async function saveCnForm(e) {
    e.preventDefault();
    setEditError("");
    setCnSaving(true);
    setCnSaved(false);
    try {
      await api.updateCompanyModulesFor(token, settingsFor, cnForm);
      await refreshCompanies();
      await refreshUser();
      setCnSaved(true);
    } catch (err) {
      setEditError(err.message || "Не удалось сохранить");
    } finally {
      setCnSaving(false);
    }
  }

  async function deleteCompany() {
    if (!window.confirm(`Удалить компанию «${activeCompany.name}»? Это необратимо.`)) return;
    setDeleteError("");
    setDeleting(true);
    try {
      await api.deleteCompany(token, settingsFor);
      setSettingsFor(null);
      await refreshCompanies();
      await refreshUser();
    } catch (err) {
      setDeleteError(err.message || "Не удалось удалить компанию");
    } finally {
      setDeleting(false);
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
          <button type="button" className="fp-btn-primary" onClick={() => setNewCompanyOpen((v) => !v)}>
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
                <option value="cn_legal_entity">Юрлицо в КНР (中国公司)</option>
              </select>
            </label>
            <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
              <button type="submit" className="fp-btn-primary" disabled={companySaving}>
                {companySaving ? "Создаём…" : "Создать"}
              </button>
              <button type="button" className="fp-btn-ghost" onClick={cancelNewCompany} disabled={companySaving}>
                Отмена
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
                  gap: 8,
                }}
              >
                <div>
                  <div style={{ fontWeight: 600 }}>{m.company.name}</div>
                  <div className="fp-muted" style={{ fontSize: 12 }}>
                    {m.company.company_type === "individual"
                      ? "Личные счета"
                      : m.company.company_type === "cn_legal_entity"
                      ? "Юрлицо в КНР"
                      : "Юрлицо/ИП"}{" "}
                    ·{" "}
                    {ROLE_LABELS[m.role] || m.role}
                    {m.company.sdvf_org_inn ? " · связана с СДВФ" : ""}
                  </div>
                </div>
                {m.role === "admin" && (
                  <span style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                    <button type="button" className="fp-btn-ghost" onClick={() => openSettings(m.company)}>
                      {settingsFor === m.company.id ? "Скрыть настройки" : "Настроить"}
                    </button>
                    <button
                      type="button"
                      className="fp-btn-ghost"
                      onClick={() => setInviteOpenFor(inviteOpenFor === m.company.id ? null : m.company.id)}
                    >
                      + Пользователь
                    </button>
                  </span>
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

                  {/* Пояснение к выбранной роли — сразу под селектом, плюс раскрывающийся
                      список всех ролей: без него выбор роли вслепую (см. живые тесты). */}
                  <div className="fp-span-2" style={{ marginTop: -4 }}>
                    <div className="fp-muted" style={{ fontSize: 12.5 }}>
                      {ROLE_DESCRIPTIONS[inviteForm.role]}
                    </div>
                    <button
                      type="button"
                      className="fp-link-btn"
                      onClick={() => setRolesHelpOpen((v) => !v)}
                      style={{
                        background: "none",
                        border: "none",
                        padding: "4px 0 0",
                        color: "var(--accent, #2f7d63)",
                        cursor: "pointer",
                        fontSize: 12.5,
                        textDecoration: "underline",
                      }}
                    >
                      {rolesHelpOpen ? "Скрыть описание ролей" : "Что даёт каждая роль?"}
                    </button>
                    {rolesHelpOpen && (
                      <div
                        style={{
                          marginTop: 8,
                          padding: 10,
                          border: "1px solid var(--line)",
                          borderRadius: 8,
                          display: "flex",
                          flexDirection: "column",
                          gap: 8,
                        }}
                      >
                        {Object.entries(ROLE_LABELS).map(([value, label]) => (
                          <div key={value}>
                            <div style={{ fontWeight: 600, fontSize: 12.5 }}>{label}</div>
                            <div className="fp-muted" style={{ fontSize: 12.5 }}>
                              {ROLE_DESCRIPTIONS[value]}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
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
                    <button type="button" className="fp-btn-ghost" onClick={cancelInvite} disabled={inviteSaving}>
                      Отмена
                    </button>
                  </div>
                </form>
              )}

              {settingsFor === m.company.id && activeCompany && (
                <div
                  style={{
                    border: "1px solid var(--line)",
                    borderTop: "none",
                    borderRadius: "0 0 8px 8px",
                    padding: 12,
                    display: "flex",
                    flexDirection: "column",
                    gap: 16,
                  }}
                >
                  {editError && <div className="fp-form-error">{editError}</div>}

                  <form className="fp-form-grid" onSubmit={saveCompanyEdit}>
                    <label className="fp-span-2">
                      Название
                      <input
                        required
                        value={editForm.name}
                        onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                      />
                    </label>
                    <label>
                      Тип
                      <select
                        value={editForm.company_type}
                        onChange={(e) => setEditForm((f) => ({ ...f, company_type: e.target.value }))}
                      >
                        <option value="legal_entity">Юрлицо/ИП</option>
                        <option value="individual">Личные счета (физлицо)</option>
                        <option value="cn_legal_entity">Юрлицо в КНР (中国公司)</option>
                      </select>
                    </label>
                    <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                      <button type="submit" className="fp-btn-primary" disabled={editSaving}>
                        {editSaving ? "Сохраняем…" : "Сохранить название"}
                      </button>
                    </div>
                  </form>

                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Модули</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {MODULES.map((mod) => (
                        <label
                          key={mod.key}
                          className="fp-switch"
                          style={{
                            display: "flex",
                            alignItems: "flex-start",
                            gap: 10,
                            padding: 12,
                            border: "1px solid var(--line)",
                            borderRadius: 8,
                            cursor: moduleBusyKey ? "default" : "pointer",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={Boolean(activeCompany[mod.key])}
                            disabled={moduleBusyKey === mod.key}
                            onChange={(e) => toggleModule(mod.key, e.target.checked)}
                            style={{ marginTop: 3 }}
                          />
                          <div>
                            <div style={{ fontWeight: 600 }}>{mod.title}</div>
                            <div className="fp-muted" style={{ fontSize: 12.5 }}>
                              {mod.description}
                            </div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  {activeCompany.company_type !== "cn_legal_entity" && (
                  <div>
                    <div style={{ fontWeight: 600 }}>Реквизиты для СДВФ</div>
                    <p className="fp-note" style={{ margin: "4px 0 12px" }}>
                      Нужны для генерации Счёт/УПД и для синхронизации контрагентов — заполняются один раз.
                    </p>
                    <form className="fp-form-grid" onSubmit={saveSdvfForm}>
                      {SDVF_FIELDS.map((f) =>
                        f.key === "sdvf_org_inn" ? (
                          <label key={f.key}>
                            {f.label}
                            <div style={{ display: "flex", gap: 6 }}>
                              <input
                                required={f.required}
                                value={sdvfForm[f.key]}
                                inputMode="numeric"
                                onChange={(e) => {
                                  setSdvfSaved(false);
                                  setInnLookup({ loading: false, message: "", error: "" });
                                  setSdvfForm((p) => ({ ...p, [f.key]: e.target.value }));
                                }}
                                style={{ flex: 1, minWidth: 0 }}
                              />
                              <button
                                type="button"
                                className="fp-btn-ghost"
                                onClick={fillFromInn}
                                disabled={!innIsValid || innLookup.loading}
                                title={innIsValid ? "Подставить реквизиты из ЕГРЮЛ/ЕГРИП" : "Введите ИНН: 10 цифр или 12 для ИП"}
                                style={{ whiteSpace: "nowrap" }}
                              >
                                {innLookup.loading ? "Ищем…" : "Заполнить по ИНН"}
                              </button>
                            </div>
                          </label>
                        ) : (
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
                        )
                      )}
                      {innLookup.message && (
                        <div className="fp-span-2 fp-muted" style={{ fontSize: 12.5 }}>
                          {innLookup.message}
                        </div>
                      )}
                      {innLookup.error && <div className="fp-form-error fp-span-2">{innLookup.error}</div>}
                      <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                        <button type="submit" className="fp-btn-primary" disabled={sdvfSaving}>
                          {sdvfSaving ? "Сохраняем…" : "Сохранить реквизиты"}
                        </button>
                        {sdvfSaved && <span className="fp-muted" style={{ fontSize: 12.5 }}>Сохранено</span>}
                      </div>
                    </form>
                  </div>
                  )}

                  {activeCompany.company_type === "cn_legal_entity" && (
                  <div>
                    <div style={{ fontWeight: 600 }}>Реквизиты 营业执照 (свидетельство о регистрации КНР)</div>
                    <p className="fp-note" style={{ margin: "4px 0 12px" }}>
                      Из свидетельства о регистрации бизнеса КНР — нужны для двуязычных документов и отчётности.
                    </p>
                    <form className="fp-form-grid" onSubmit={saveCnForm}>
                      {CN_FIELDS.map((f) => (
                        <label key={f.key} className={f.textarea ? "fp-span-2" : undefined}>
                          {f.label}
                          {f.textarea ? (
                            <textarea
                              rows={3}
                              value={cnForm[f.key]}
                              onChange={(e) => {
                                setCnSaved(false);
                                setCnForm((p) => ({ ...p, [f.key]: e.target.value }));
                              }}
                            />
                          ) : (
                            <input
                              required={f.required}
                              type={f.type || "text"}
                              value={cnForm[f.key]}
                              onChange={(e) => {
                                setCnSaved(false);
                                setCnForm((p) => ({ ...p, [f.key]: e.target.value }));
                              }}
                            />
                          )}
                        </label>
                      ))}
                      <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                        <button type="submit" className="fp-btn-primary" disabled={cnSaving}>
                          {cnSaving ? "Сохраняем…" : "Сохранить реквизиты"}
                        </button>
                        {cnSaved && <span className="fp-muted" style={{ fontSize: 12.5 }}>Сохранено</span>}
                      </div>
                    </form>
                  </div>
                  )}

                  <div style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
                    {deleteError && <div className="fp-form-error" style={{ marginBottom: 8 }}>{deleteError}</div>}
                    <button
                      type="button"
                      className="fp-btn-ghost"
                      style={{ color: "var(--danger, #c0392b)" }}
                      onClick={deleteCompany}
                      disabled={deleting}
                    >
                      {deleting ? "Удаляем…" : "Удалить компанию"}
                    </button>
                    <p className="fp-note" style={{ margin: "6px 0 0" }}>
                      Удалить можно только компанию без данных (счетов, операций, контрагентов и т.п.) —
                      если данные уже есть, отключите модули вместо удаления.
                    </p>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
