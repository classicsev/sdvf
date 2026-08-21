"use client";

import { useMemo, useState } from "react";
import { Plus, X, Trash2, Plug, RefreshCw, Upload, Check } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";
import { backdropClickProps } from "../lib/modalBackdrop";
import { useTranslation } from "../lib/i18n";

const PROVIDER_LABELS = {
  tinkoff: "Т-Банк",
  alfa: "Альфа-Банк",
  wildberries: "Wildberries",
  ozon: "Ozon",
  yookassa: "ЮKassa",
  amocrm: "amoCRM",
  "1c": "1С:УНФ",
  jump: "Jump.Finance",
};

const SYNC_SUPPORTED = ["tinkoff", "alfa", "amocrm", "jump"];

const FIELD_OPTIONS = [
  { value: "counterparty", labelKey: "automation.field.counterparty" },
  { value: "comment", labelKey: "automation.field.comment" },
  { value: "amount", labelKey: "automation.field.amount" },
];

const OPS_BY_FIELD = {
  counterparty: [
    { value: "contains", labelKey: "automation.op.contains" },
    { value: "equals", labelKey: "automation.op.equalsText" },
  ],
  comment: [
    { value: "contains", labelKey: "automation.op.contains" },
    { value: "equals", labelKey: "automation.op.equalsText" },
  ],
  amount: [
    { value: "gt", labelKey: "automation.op.gt" },
    { value: "lt", labelKey: "automation.op.lt" },
    { value: "gte", labelKey: "automation.op.gte" },
    { value: "lte", labelKey: "automation.op.lte" },
    { value: "equals", labelKey: "automation.op.equalsAmount" },
  ],
};

const CONDITION_EMPTY = { field: "counterparty", op: "contains", value: "" };
const FORM_EMPTY = { conditions: [CONDITION_EMPTY], set_category: "", set_project: "" };

// t передаётся явно (не через хук) — функция вызывается из обычного JS, не
// из тела компонента, а порядок последнего совпадения по value сохраняет
// прежнее (до перевода) поведение: "equals" у amount ("=") перекрывает
// "equals" у counterparty/comment ("равен") — так было и раньше.
function describeCondition(condition, t) {
  const list = Array.isArray(condition) ? condition : [condition];
  const allOps = Object.values(OPS_BY_FIELD).flat();
  const fieldLabel = (field) => {
    const match = FIELD_OPTIONS.find((f) => f.value === field);
    return match ? t(match.labelKey) : field;
  };
  const opLabel = (op) => {
    const match = allOps.filter((o) => o.value === op).pop();
    return match ? t(match.labelKey) : op;
  };
  return list
    .filter(Boolean)
    .map((c) => `${fieldLabel(c.field)} ${opLabel(c.op)} «${c.value}»`)
    .join(t("automation.and"));
}

const AMO_CONNECT_EMPTY = { subdomain: "", client_id: "", client_secret: "", access_token: "", refresh_token: "" };
const ALFA_CONNECT_EMPTY = { api_key: "", cert_pem: "", key_pem: "", key_password: "" };
// Песочница Alfa API принимает только эти фиксированные номера счетов —
// см. "Тестирование Выписок по счетам ЮЛ" в документации, проверено вживую.
const ALFA_SANDBOX_TEST_ACCOUNTS = [
  "40702810102300000001",
  "40702810402300000002",
  "40702810002300000003",
  "40702978902300000004",
];
const ALFA_FILE_NAMES_EMPTY = { cert: "", key: "" };

function IntegrationsPanel({ token, integrations, reload, companyFilter }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const showCompanyColumn = multiCompany && !companyFilter;

  const { data: accounts } = useResource(
    () => api.listAccounts(token, { company_id: companyFilter || undefined }),
    [token, companyFilter]
  );

  const [connectTarget, setConnectTarget] = useState(null);
  const [connectTokenValue, setConnectTokenValue] = useState("");
  const [amoConnectForm, setAmoConnectForm] = useState(AMO_CONNECT_EMPTY);
  const [alfaConnectForm, setAlfaConnectForm] = useState(ALFA_CONNECT_EMPTY);
  const [alfaFileNames, setAlfaFileNames] = useState(ALFA_FILE_NAMES_EMPTY);
  const [connectError, setConnectError] = useState("");
  const [connectSaving, setConnectSaving] = useState(false);

  const [syncTarget, setSyncTarget] = useState(null);
  const [syncForm, setSyncForm] = useState({ account_id: "", date_from: "", date_to: "" });
  const [syncError, setSyncError] = useState("");
  const [syncResult, setSyncResult] = useState(null);
  const [syncSaving, setSyncSaving] = useState(false);
  const [syncDetailsOpen, setSyncDetailsOpen] = useState(false);

  function openConnect(integration) {
    setConnectTarget(integration);
    setConnectTokenValue("");
    setAmoConnectForm(AMO_CONNECT_EMPTY);
    setAlfaConnectForm(ALFA_CONNECT_EMPTY);
    setAlfaFileNames(ALFA_FILE_NAMES_EMPTY);
    setConnectError("");
  }

  // Сертификат/ключ читаем прямо из выбранного файла (а не просим вставлять
  // текст руками) — пользователь и так открывает файл в проводнике, копипаст
  // блока PEM только добавлял путаницы (см. фидбек после первого подключения
  // Альфа-Банка).
  function handleAlfaFilePicked(field, nameKey) {
    return (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        setAlfaConnectForm((p) => ({ ...p, [field]: String(reader.result || "").trim() }));
      };
      reader.readAsText(file);
      setAlfaFileNames((p) => ({ ...p, [nameKey]: file.name }));
    };
  }

  async function handleConnect(e) {
    e.preventDefault();
    setConnectSaving(true);
    setConnectError("");
    try {
      if (connectTarget.provider === "amocrm") {
        await api.connectAmoCrm(token, connectTarget.id, amoConnectForm);
      } else if (connectTarget.provider === "alfa") {
        await api.connectAlfaBank(token, connectTarget.id, alfaConnectForm);
      } else {
        await api.connectIntegration(token, connectTarget.id, { token: connectTokenValue });
      }
      setConnectTarget(null);
      reload();
    } catch (err) {
      setConnectError(err.message);
    } finally {
      setConnectSaving(false);
    }
  }

  async function handleDisconnect(integration) {
    if (
      !window.confirm(
        t("automation.disconnectConfirm", { provider: PROVIDER_LABELS[integration.provider] || integration.provider })
      )
    )
      return;
    try {
      await api.disconnectIntegration(token, integration.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  function openSync(integration) {
    setSyncTarget(integration);
    setSyncForm({ account_id: "", date_from: "", date_to: "", account_number_override: "" });
    setSyncError("");
    setSyncResult(null);
    setSyncDetailsOpen(false);
  }

  async function handleSync(e) {
    e.preventDefault();
    setSyncSaving(true);
    setSyncError("");
    setSyncResult(null);
    setSyncDetailsOpen(false);
    try {
      const result =
        syncTarget.provider === "amocrm"
          ? await api.syncAmoCrm(token, syncTarget.id, {
              account_id: syncForm.account_id,
              date_from: syncForm.date_from || null,
            })
          : syncTarget.provider === "jump"
          ? await api.syncJumpFinance(token, syncTarget.id, {
              account_id: syncForm.account_id,
              date_from: syncForm.date_from,
              date_to: syncForm.date_to || null,
            })
          : await api.syncIntegration(token, syncTarget.id, {
              account_id: syncForm.account_id,
              date_from: syncForm.date_from,
              date_to: syncForm.date_to || null,
              account_number_override: syncForm.account_number_override || null,
            });
      setSyncResult(result);
      reload();
    } catch (err) {
      setSyncError(err.message);
    } finally {
      setSyncSaving(false);
    }
  }

  return (
    <>
      <div style={{ height: 20 }} />
      <h3 style={{ fontFamily: "'Fraunces', serif" }}>{t("automation.integrationsTitle")}</h3>
      <div className="fp-panel fp-table-panel">
        <table className="fp-table">
          <thead>
            <tr>
              {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
              <th>{t("automation.col.name")}</th>
              <th>{t("automation.col.type")}</th>
              <th className="center">{t("automation.col.status")}</th>
              <th>{t("automation.col.lastSync")}</th>
              <th className="fp-table-actions-col"></th>
            </tr>
          </thead>
          <tbody>
            {(integrations || []).map((i) => (
              <tr key={i.id}>
                {showCompanyColumn && (
                  <td>{companies.find((m) => m.company.id === i.company_id)?.company.name || "—"}</td>
                )}
                <td>
                  <Plug size={13} style={{ marginRight: 6, verticalAlign: "middle" }} />
                  {PROVIDER_LABELS[i.provider] || i.provider}
                </td>
                <td className="fp-muted">{i.type}</td>
                <td className="center">
                  <span className={`fp-status-badge ${i.is_connected ? "ok" : "warn"}`}>
                    {i.is_connected ? t("automation.connected") : t("automation.notConnected")}
                  </span>
                </td>
                <td className="fp-muted">{i.last_sync_at ? fmtDate(i.last_sync_at) : "—"}</td>
                <td className="fp-table-actions-col">
                  <span className="fp-row-actions">
                    {i.is_connected ? (
                      <>
                        {SYNC_SUPPORTED.includes(i.provider) && (
                          <button className="fp-btn-tiny" onClick={() => openSync(i)}>
                            <RefreshCw size={12} /> {t("automation.sync")}
                          </button>
                        )}
                        <button className="fp-btn-tiny" onClick={() => handleDisconnect(i)}>
                          {t("automation.disconnect")}
                        </button>
                      </>
                    ) : (
                      <button className="fp-btn-tiny" onClick={() => openConnect(i)}>
                        {t("automation.connect")}
                      </button>
                    )}
                  </span>
                </td>
              </tr>
            ))}
            {(integrations || []).length === 0 && (
              <tr>
                <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                  {t("automation.noIntegrations")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          {t("automation.integrationsNote")}
        </p>
      </div>

      {connectTarget && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setConnectTarget(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>
                {t("automation.connectTitle", {
                  provider: PROVIDER_LABELS[connectTarget.provider] || connectTarget.provider,
                })}
              </h3>
              <button className="fp-icon-btn" onClick={() => setConnectTarget(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleConnect}>
              {connectTarget.provider === "amocrm" ? (
                <>
                  <label className="fp-span-2">
                    {t("automation.subdomainLabel")}
                    <input
                      required
                      value={amoConnectForm.subdomain}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, subdomain: e.target.value }))}
                    />
                  </label>
                  <label>
                    {t("automation.clientId")}
                    <input
                      required
                      value={amoConnectForm.client_id}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, client_id: e.target.value }))}
                    />
                  </label>
                  <label>
                    {t("automation.clientSecret")}
                    <input
                      required
                      value={amoConnectForm.client_secret}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, client_secret: e.target.value }))}
                    />
                  </label>
                  <label>
                    {t("automation.accessToken")}
                    <input
                      required
                      value={amoConnectForm.access_token}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, access_token: e.target.value }))}
                    />
                  </label>
                  <label>
                    {t("automation.refreshToken")}
                    <input
                      required
                      value={amoConnectForm.refresh_token}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, refresh_token: e.target.value }))}
                    />
                  </label>
                  <div className="fp-note fp-span-2">{t("automation.amoNote")}</div>
                </>
              ) : connectTarget.provider === "alfa" ? (
                <>
                  <label className="fp-span-2">
                    {t("automation.alfaApiKey")}
                    <input
                      required
                      value={alfaConnectForm.api_key}
                      onChange={(e) => setAlfaConnectForm((p) => ({ ...p, api_key: e.target.value }))}
                    />
                  </label>
                  <div className="fp-span-2">
                    {t("automation.alfaCert")}
                    <div style={{ marginTop: 5 }}>
                      <label
                        className="fp-btn-ghost"
                        style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                      >
                        {alfaConnectForm.cert_pem ? <Check size={14} /> : <Upload size={14} />}
                        {alfaFileNames.cert || t("automation.chooseCertFile")}
                        <input
                          type="file"
                          accept=".cer,.pem,.crt"
                          required={!alfaConnectForm.cert_pem}
                          onChange={handleAlfaFilePicked("cert_pem", "cert")}
                          style={{ display: "none" }}
                        />
                      </label>
                    </div>
                  </div>
                  <div className="fp-span-2">
                    {t("automation.alfaKey")}
                    <div style={{ marginTop: 5 }}>
                      <label
                        className="fp-btn-ghost"
                        style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                      >
                        {alfaConnectForm.key_pem ? <Check size={14} /> : <Upload size={14} />}
                        {alfaFileNames.key || t("automation.chooseKeyFile")}
                        <input
                          type="file"
                          accept=".key,.pem"
                          required={!alfaConnectForm.key_pem}
                          onChange={handleAlfaFilePicked("key_pem", "key")}
                          style={{ display: "none" }}
                        />
                      </label>
                    </div>
                  </div>
                  <label className="fp-span-2">
                    {t("automation.keyPassword")}
                    <input
                      required
                      type="password"
                      value={alfaConnectForm.key_password}
                      onChange={(e) => setAlfaConnectForm((p) => ({ ...p, key_password: e.target.value }))}
                    />
                  </label>
                  <div className="fp-note fp-span-2">{t("automation.alfaNote")}</div>
                </>
              ) : (
                <label className="fp-span-2">
                  {connectTarget.provider === "jump" ? t("automation.jumpClientKey") : t("automation.apiToken")}
                  <input
                    required
                    value={connectTokenValue}
                    onChange={(e) => setConnectTokenValue(e.target.value)}
                    placeholder={connectTarget.provider === "jump" ? "" : t("automation.tbankSandboxPlaceholder")}
                  />
                </label>
              )}
              {connectError && <div className="fp-form-error fp-span-2">{connectError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setConnectTarget(null)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={connectSaving}>
                  {connectSaving ? t("common.saving") : t("automation.connect")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {syncTarget && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setSyncTarget(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>
                {t("automation.syncTitle", { provider: PROVIDER_LABELS[syncTarget.provider] || syncTarget.provider })}
              </h3>
              <button className="fp-icon-btn" onClick={() => setSyncTarget(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSync}>
              {(() => {
                const relevantAccounts = (accounts || [])
                  .filter((a) => !multiCompany || a.company_id === syncTarget.company_id)
                  .filter((a) => syncTarget.provider === "amocrm" || a.account_number);
                const needsAccountNumber = syncTarget.provider !== "amocrm";
                return (
                  <label className="fp-span-2">
                    {syncTarget.provider === "amocrm"
                      ? t("automation.accountForDeals")
                      : t("automation.accountWithNumber")}
                    {relevantAccounts.length === 0 ? (
                      <div className="fp-form-error" style={{ marginTop: 6 }}>
                        {needsAccountNumber
                          ? t("automation.noAccountsWithNumber")
                          : t("automation.noAccounts")}
                      </div>
                    ) : (
                      <select
                        required
                        value={syncForm.account_id}
                        onChange={(e) => setSyncForm((p) => ({ ...p, account_id: e.target.value }))}
                      >
                        <option value="" disabled>
                          {t("payroll.selectAccount")}
                        </option>
                        {relevantAccounts.map((a) => (
                          <option key={a.id} value={a.id}>
                            {syncTarget.provider === "amocrm"
                              ? a.name
                              : `${a.name} (${a.account_number})`}
                          </option>
                        ))}
                      </select>
                    )}
                  </label>
                );
              })()}
              <label className={syncTarget.provider === "amocrm" ? "fp-span-2" : ""}>
                {syncTarget.provider === "amocrm" ? t("automation.dealsClosedFrom") : t("automation.dateFrom")}
                <input
                  type="date"
                  required={syncTarget.provider !== "amocrm"}
                  value={syncForm.date_from}
                  onChange={(e) => setSyncForm((p) => ({ ...p, date_from: e.target.value }))}
                />
              </label>
              {syncTarget.provider !== "amocrm" && (
                <label>
                  {t("automation.dateTo")}
                  <input
                    type="date"
                    value={syncForm.date_to}
                    onChange={(e) => setSyncForm((p) => ({ ...p, date_to: e.target.value }))}
                  />
                </label>
              )}
              {syncTarget.provider === "jump" && (
                <div className="fp-note fp-span-2">{t("automation.jumpNote")}</div>
              )}
              {syncTarget.provider === "alfa" && (
                <label className="fp-span-2">
                  {t("automation.sandboxAccountNumber")}
                  <select
                    value={syncForm.account_number_override}
                    onChange={(e) => setSyncForm((p) => ({ ...p, account_number_override: e.target.value }))}
                  >
                    <option value="">{t("automation.sandboxNone")}</option>
                    {ALFA_SANDBOX_TEST_ACCOUNTS.map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                  <span className="fp-note" style={{ display: "block", marginTop: 4 }}>
                    {t("automation.sandboxNote")}
                  </span>
                </label>
              )}
              {syncError && <div className="fp-form-error fp-span-2">{syncError}</div>}
              {syncResult && syncTarget.provider === "amocrm" && (
                <div className="fp-note fp-span-2">
                  {t("automation.amoResult.contacts", {
                    created: syncResult.contacts_created,
                    matched: syncResult.contacts_matched,
                  })}
                  <br />
                  {t("automation.amoResult.deals", {
                    created: syncResult.deals_created,
                    skipped: syncResult.deals_skipped,
                  })}
                </div>
              )}
              {syncResult && syncTarget.provider === "jump" && (
                <div className="fp-note fp-span-2">
                  {t("automation.jumpResult", {
                    matched: syncResult.matched,
                    byDefault: syncResult.category_set_from_default,
                    byRule: syncResult.category_set_from_rule,
                    unmatched: syncResult.unmatched,
                  })}
                  {syncResult.ambiguous > 0
                    ? t("automation.jumpResult.ambiguous", { count: syncResult.ambiguous })
                    : ""}
                  .
                </div>
              )}
              {syncResult && syncTarget.provider !== "amocrm" && syncTarget.provider !== "jump" && (
                <div className="fp-note fp-span-2">
                  <div>
                    {t("automation.genericResult", { created: syncResult.created, skipped: syncResult.skipped })}{" "}
                    <button
                      type="button"
                      className="fp-btn-tiny"
                      style={{ marginLeft: 4 }}
                      onClick={() => setSyncDetailsOpen((v) => !v)}
                    >
                      {syncDetailsOpen ? t("automation.hide") : t("automation.more")}
                    </button>
                  </div>
                  {syncDetailsOpen && (
                    <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                      <li>{t("automation.alreadyLoaded", { count: syncResult.skipped_duplicate })}</li>
                      <li>{t("automation.noFxRate", { count: syncResult.skipped_no_fx_rate })}</li>
                      <li>{t("automation.unparseable", { count: syncResult.skipped_unparseable })}</li>
                    </ul>
                  )}
                </div>
              )}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setSyncTarget(null)}>
                  {t("automation.close")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={syncSaving}>
                  {syncSaving ? t("dashboard.syncing") : t("dashboard.sync")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

export default function Automation() {
  const { token, user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const editableCompanies = companies.filter((m) => m.role === "admin");
  const [companyId, setCompanyId] = useState("");
  const query = { company_id: companyId || undefined };
  const showCompanyColumn = multiCompany && !companyId;

  const { data: rules, loading, error, reload } = useResource(
    () => api.listAutomationRules(token, query),
    [token, companyId]
  );
  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);
  const { data: integrations, reload: reloadIntegrations } = useResource(
    () => api.listIntegrations(token, query),
    [token, companyId]
  );

  const categoriesById = useMemo(() => Object.fromEntries((categories || []).map((c) => [c.id, c])), [categories]);
  const projectsById = useMemo(() => Object.fromEntries((projects || []).map((p) => [p.id, p])), [projects]);

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(FORM_EMPTY);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [formError, setFormError] = useState("");
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
    setForm(FORM_EMPTY);
    const preselected = editableCompanies.find((m) => m.company.id === companyId) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setFormError("");
    setModalOpen(true);
  }

  function addCondition() {
    setForm((p) => ({ ...p, conditions: [...p.conditions, CONDITION_EMPTY] }));
  }

  function removeCondition(index) {
    setForm((p) => ({ ...p, conditions: p.conditions.filter((_, i) => i !== index) }));
  }

  function updateCondition(index, patch) {
    setForm((p) => ({
      ...p,
      conditions: p.conditions.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const action_json = {};
      if (form.set_category) action_json.set_category = form.set_category;
      if (form.set_project) action_json.set_project = form.set_project;

      const condition_json = form.conditions.map((c) => ({
        field: c.field,
        op: c.op,
        value: c.field === "amount" ? Number(c.value) : c.value,
      }));

      await api.createAutomationRule(
        token,
        {
          condition_json: condition_json.length === 1 ? condition_json[0] : condition_json,
          action_json,
          is_active: true,
        },
        formCompanyId || undefined
      );
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(rule) {
    try {
      await api.updateAutomationRule(token, rule.id, {
        condition_json: rule.condition_json,
        action_json: rule.action_json,
        is_active: !rule.is_active,
      });
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleDelete(rule) {
    if (!window.confirm(t("automation.deleteRuleConfirm"))) return;
    try {
      await api.deleteAutomationRule(token, rule.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>{t("automation.rulesTitle")}</h3>
        <div style={{ display: "flex", gap: 10 }}>
          {multiCompany && (
            <select value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
              <option value="">{t("dashboard.allCompanies")}</option>
              {companies.map((m) => (
                <option key={m.company.id} value={m.company.id}>
                  {m.company.name}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> {t("automation.newRule")}
          </button>
        </div>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                <th>{t("automation.col.condition")}</th>
                <th>{t("automation.col.action")}</th>
                <th className="center">{t("automation.col.active")}</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(rules || []).map((rule) => {
                const canEditRow = roleForCompany(rule.company_id) === "admin";
                return (
                <tr key={rule.id}>
                  {showCompanyColumn && (
                    <td>{companies.find((m) => m.company.id === rule.company_id)?.company.name || "—"}</td>
                  )}
                  <td>{describeCondition(rule.condition_json, t)}</td>
                  <td className="fp-muted">
                    {rule.action_json?.set_category &&
                      t("automation.categoryArrow", { name: categoriesById[rule.action_json.set_category]?.name || "?" })}
                    {rule.action_json?.set_category && rule.action_json?.set_project && ", "}
                    {rule.action_json?.set_project &&
                      t("automation.projectArrow", { name: projectsById[rule.action_json.set_project]?.name || "?" })}
                  </td>
                  <td className="center">
                    <label className="fp-mini-switch">
                      <input
                        type="checkbox"
                        checked={rule.is_active}
                        disabled={!canEditRow}
                        onChange={() => toggleActive(rule)}
                      />
                      <span />
                    </label>
                  </td>
                  <td className="fp-table-actions-col">
                    {canEditRow && (
                      <button className="fp-icon-btn" onClick={() => handleDelete(rule)}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
                );
              })}
              {(rules || []).length === 0 && (
                <tr>
                  <td colSpan={showCompanyColumn ? 5 : 4} className="fp-empty">
                    {t("automation.noRules")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          {t("automation.rulesNote")}
        </p>
      </div>

      <IntegrationsPanel
        token={token}
        integrations={integrations}
        reload={reloadIntegrations}
        companyFilter={companyId}
      />

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("automation.newRule")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  {t("tx.form.company")}
                  <select
                    value={formCompanyId}
                    onChange={(e) => {
                      setFormCompanyId(e.target.value);
                      setForm((p) => ({ ...p, set_category: "", set_project: "" }));
                    }}
                    required
                  >
                    {editableCompanies.map((m) => (
                      <option key={m.company.id} value={m.company.id}>
                        {m.company.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="fp-span-2">
                <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>
                  {t("automation.conditionsLabel")}
                </div>
                {form.conditions.map((cond, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && t("automation.field")}
                      <select
                        value={cond.field}
                        onChange={(e) =>
                          updateCondition(idx, { field: e.target.value, op: OPS_BY_FIELD[e.target.value][0].value })
                        }
                      >
                        {FIELD_OPTIONS.map((f) => (
                          <option key={f.value} value={f.value}>
                            {t(f.labelKey)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && t("automation.col.condition")}
                      <select value={cond.op} onChange={(e) => updateCondition(idx, { op: e.target.value })}>
                        {OPS_BY_FIELD[cond.field].map((o) => (
                          <option key={o.value} value={o.value}>
                            {t(o.labelKey)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && t("automation.value")}
                      <input
                        required
                        type={cond.field === "amount" ? "number" : "text"}
                        value={cond.value}
                        onChange={(e) => updateCondition(idx, { value: e.target.value })}
                      />
                    </label>
                    {form.conditions.length > 1 && (
                      <button
                        type="button"
                        className="fp-icon-btn"
                        style={{ marginBottom: 8 }}
                        onClick={() => removeCondition(idx)}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="fp-btn-tiny" onClick={addCondition}>
                  <Plus size={13} /> {t("automation.addCondition")}
                </button>
              </div>

              <label>
                {t("automation.setCategory")}
                <select value={form.set_category} onChange={(e) => setForm((p) => ({ ...p, set_category: e.target.value }))}>
                  <option value="">{t("automation.dontChange")}</option>
                  {selectableCategories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("automation.setProject")}
                <select value={form.set_project} onChange={(e) => setForm((p) => ({ ...p, set_project: e.target.value }))}>
                  <option value="">{t("automation.dontChange")}</option>
                  {selectableProjects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}

              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("automation.create")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
