"use client";

import { useState } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { ROLE_LABELS, ROLE_DESCRIPTIONS } from "../lib/roles";
import { useTranslation } from "../lib/i18n";

const MODULES = [
  { key: "module_finance_enabled", titleKey: "modules.module.finance.title", descKey: "modules.module.finance.description" },
  { key: "module_warehouse_enabled", titleKey: "modules.module.warehouse.title", descKey: "modules.module.warehouse.description" },
  { key: "module_china_enabled", titleKey: "modules.module.china.title", descKey: "modules.module.china.description" },
];

// Подписи полей 营业执照/СДВФ уже двуязычные (RU/中文) вне зависимости от
// выбранного языка интерфейса — это названия юридических полей документа,
// а не UI-текст, переводить их отдельно не нужно.
const SDVF_FIELDS = [
  { key: "sdvf_org_naming", labelKey: "modules.sdvf.naming", required: true },
  { key: "sdvf_org_inn", labelKey: "modules.sdvf.inn", required: true },
  { key: "sdvf_org_kpp", labelKey: "modules.sdvf.kpp" },
  { key: "sdvf_org_ogrn", labelKey: "modules.sdvf.ogrn" },
  { key: "sdvf_org_address", labelKey: "modules.sdvf.address" },
  { key: "sdvf_org_phone", labelKey: "modules.sdvf.phone" },
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
  const { t } = useTranslation();
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
      setError(err.message || t("modules.err.createCompany"));
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
      setInviteError(err.message || t("modules.err.addMember"));
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
      setEditError(err.message || t("modules.err.save"));
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
      setEditError(err.message || t("modules.err.save"));
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
        message: t("modules.foundByInn", { name: found.name }),
        error: "",
      });
    } catch (err) {
      setInnLookup({ loading: false, message: "", error: err.message || t("modules.err.findByInn") });
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
      setEditError(err.message || t("modules.err.save"));
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
      setEditError(err.message || t("modules.err.save"));
    } finally {
      setCnSaving(false);
    }
  }

  async function deleteCompany() {
    if (!window.confirm(t("modules.deleteConfirm", { name: activeCompany.name }))) return;
    setDeleteError("");
    setDeleting(true);
    try {
      await api.deleteCompany(token, settingsFor);
      setSettingsFor(null);
      await refreshCompanies();
      await refreshUser();
    } catch (err) {
      setDeleteError(err.message || t("modules.err.deleteCompany"));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>{t("modules.pageTitle")}</h3>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>{t("modules.myCompanies")}</div>
          <button type="button" className="fp-btn-primary" onClick={() => setNewCompanyOpen((v) => !v)}>
            {t("modules.addCompany")}
          </button>
        </div>

        {newCompanyOpen && (
          <form
            className="fp-form-grid"
            onSubmit={createCompany}
            style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12 }}
          >
            <label className="fp-span-2">
              {t("modules.name")}
              <input
                required
                value={newCompanyName}
                onChange={(e) => setNewCompanyName(e.target.value)}
                placeholder={t("modules.namePlaceholder")}
              />
            </label>
            <label>
              {t("modules.type")}
              <select value={newCompanyType} onChange={(e) => setNewCompanyType(e.target.value)}>
                <option value="legal_entity">{t("modules.type.legal_entity")}</option>
                <option value="individual">{t("modules.type.individual")}</option>
                <option value="cn_legal_entity">{t("modules.type.cn_legal_entity")}</option>
              </select>
            </label>
            <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
              <button type="submit" className="fp-btn-primary" disabled={companySaving}>
                {companySaving ? t("modules.creating") : t("modules.create")}
              </button>
              <button type="button" className="fp-btn-ghost" onClick={cancelNewCompany} disabled={companySaving}>
                {t("common.cancel")}
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
                      ? t("modules.companyLabel.individual")
                      : m.company.company_type === "cn_legal_entity"
                      ? t("modules.companyLabel.cn")
                      : t("modules.companyLabel.legal")}{" "}
                    ·{" "}
                    {ROLE_LABELS[m.role] || m.role}
                    {m.company.sdvf_org_inn ? ` · ${t("modules.linkedToSdvf")}` : ""}
                  </div>
                </div>
                {m.role === "admin" && (
                  <span style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                    <button type="button" className="fp-btn-ghost" onClick={() => openSettings(m.company)}>
                      {settingsFor === m.company.id ? t("modules.hideSettings") : t("modules.configure")}
                    </button>
                    <button
                      type="button"
                      className="fp-btn-ghost"
                      onClick={() => setInviteOpenFor(inviteOpenFor === m.company.id ? null : m.company.id)}
                    >
                      {t("modules.addUser")}
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
                    {t("modules.email")}
                    <input
                      required
                      type="email"
                      value={inviteForm.email}
                      onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))}
                    />
                  </label>
                  <label>
                    {t("modules.role")}
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
                      {rolesHelpOpen ? t("modules.rolesHelpHide") : t("modules.rolesHelpShow")}
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
                    {t("modules.inviteNote")}
                  </div>
                  <label>
                    {t("modules.fullNameNew")}
                    <input
                      value={inviteForm.full_name}
                      onChange={(e) => setInviteForm((f) => ({ ...f, full_name: e.target.value }))}
                    />
                  </label>
                  <label>
                    {t("modules.passwordNew")}
                    <input
                      type="password"
                      value={inviteForm.password}
                      onChange={(e) => setInviteForm((f) => ({ ...f, password: e.target.value }))}
                    />
                  </label>
                  {inviteError && <div className="fp-form-error fp-span-2">{inviteError}</div>}
                  <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                    <button type="submit" className="fp-btn-primary" disabled={inviteSaving}>
                      {inviteSaving ? t("modules.inviting") : t("modules.invite")}
                    </button>
                    <button type="button" className="fp-btn-ghost" onClick={cancelInvite} disabled={inviteSaving}>
                      {t("common.cancel")}
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
                      {t("modules.name")}
                      <input
                        required
                        value={editForm.name}
                        onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                      />
                    </label>
                    <label>
                      {t("modules.type")}
                      <select
                        value={editForm.company_type}
                        onChange={(e) => setEditForm((f) => ({ ...f, company_type: e.target.value }))}
                      >
                        <option value="legal_entity">{t("modules.type.legal_entity")}</option>
                        <option value="individual">{t("modules.type.individual")}</option>
                        <option value="cn_legal_entity">{t("modules.type.cn_legal_entity")}</option>
                      </select>
                    </label>
                    <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                      <button type="submit" className="fp-btn-primary" disabled={editSaving}>
                        {editSaving ? t("modules.saveNameSaving") : t("modules.saveName")}
                      </button>
                    </div>
                  </form>

                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>{t("modules.modulesHeading")}</div>
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
                            <div style={{ fontWeight: 600 }}>{t(mod.titleKey)}</div>
                            <div className="fp-muted" style={{ fontSize: 12.5 }}>
                              {t(mod.descKey)}
                            </div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  {activeCompany.company_type !== "cn_legal_entity" && (
                  <div>
                    <div style={{ fontWeight: 600 }}>{t("modules.sdvfHeading")}</div>
                    <p className="fp-note" style={{ margin: "4px 0 12px" }}>
                      {t("modules.sdvfNote")}
                    </p>
                    <form className="fp-form-grid" onSubmit={saveSdvfForm}>
                      {SDVF_FIELDS.map((f) =>
                        f.key === "sdvf_org_inn" ? (
                          <label key={f.key}>
                            {t(f.labelKey)}
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
                                title={
                                  innIsValid
                                    ? t("modules.fillFromInnTooltipValid")
                                    : t("modules.fillFromInnTooltipInvalid")
                                }
                                style={{ whiteSpace: "nowrap" }}
                              >
                                {innLookup.loading ? t("modules.fillFromInnSearching") : t("modules.fillFromInn")}
                              </button>
                            </div>
                          </label>
                        ) : (
                          <label key={f.key}>
                            {t(f.labelKey)}
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
                          {sdvfSaving ? t("modules.saveNameSaving") : t("modules.saveRequisites")}
                        </button>
                        {sdvfSaved && <span className="fp-muted" style={{ fontSize: 12.5 }}>{t("modules.saved")}</span>}
                      </div>
                    </form>
                  </div>
                  )}

                  {activeCompany.company_type === "cn_legal_entity" && (
                  <div>
                    <div style={{ fontWeight: 600 }}>{t("modules.cnHeading")}</div>
                    <p className="fp-note" style={{ margin: "4px 0 12px" }}>
                      {t("modules.cnNote")}
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
                          {cnSaving ? t("modules.saveNameSaving") : t("modules.saveRequisites")}
                        </button>
                        {cnSaved && <span className="fp-muted" style={{ fontSize: 12.5 }}>{t("modules.saved")}</span>}
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
                      {deleting ? t("modules.deleting") : t("modules.deleteCompany")}
                    </button>
                    <p className="fp-note" style={{ margin: "6px 0 0" }}>
                      {t("modules.deleteNote")}
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
