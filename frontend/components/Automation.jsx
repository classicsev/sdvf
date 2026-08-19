"use client";

import { useMemo, useState } from "react";
import { Plus, X, Trash2, Plug, RefreshCw, Upload, Check } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";

const PROVIDER_LABELS = {
  tinkoff: "Т-Банк",
  alfa: "Альфа-Банк",
  wildberries: "Wildberries",
  ozon: "Ozon",
  yookassa: "ЮKassa",
  amocrm: "amoCRM",
  "1c": "1С:УНФ",
};

const SYNC_SUPPORTED = ["tinkoff", "alfa", "amocrm"];

const FIELD_OPTIONS = [
  { value: "counterparty", label: "Контрагент" },
  { value: "comment", label: "Комментарий" },
  { value: "amount", label: "Сумма" },
];

const OPS_BY_FIELD = {
  counterparty: [
    { value: "contains", label: "содержит" },
    { value: "equals", label: "равен" },
  ],
  comment: [
    { value: "contains", label: "содержит" },
    { value: "equals", label: "равен" },
  ],
  amount: [
    { value: "gt", label: ">" },
    { value: "lt", label: "<" },
    { value: "gte", label: ">=" },
    { value: "lte", label: "<=" },
    { value: "equals", label: "=" },
  ],
};

const FIELD_LABELS = Object.fromEntries(FIELD_OPTIONS.map((f) => [f.value, f.label]));
const OP_LABELS = Object.fromEntries(
  Object.values(OPS_BY_FIELD)
    .flat()
    .map((o) => [o.value, o.label])
);
const CONDITION_EMPTY = { field: "counterparty", op: "contains", value: "" };
const FORM_EMPTY = { conditions: [CONDITION_EMPTY], set_category: "", set_project: "" };

function describeCondition(condition) {
  const list = Array.isArray(condition) ? condition : [condition];
  return list
    .filter(Boolean)
    .map((c) => `${FIELD_LABELS[c.field] || c.field} ${OP_LABELS[c.op] || c.op} «${c.value}»`)
    .join(" И ");
}

const AMO_CONNECT_EMPTY = { subdomain: "", client_id: "", client_secret: "", access_token: "", refresh_token: "" };
const ALFA_CONNECT_EMPTY = { api_key: "", cert_pem: "", key_pem: "", key_password: "" };
const ALFA_FILE_NAMES_EMPTY = { cert: "", key: "" };

function IntegrationsPanel({ token, integrations, reload, companyFilter }) {
  const { user } = useAuth();
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
    if (!window.confirm(`Отключить «${PROVIDER_LABELS[integration.provider] || integration.provider}»?`)) return;
    try {
      await api.disconnectIntegration(token, integration.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  function openSync(integration) {
    setSyncTarget(integration);
    setSyncForm({ account_id: "", date_from: "", date_to: "" });
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
          : await api.syncIntegration(token, syncTarget.id, {
              account_id: syncForm.account_id,
              date_from: syncForm.date_from,
              date_to: syncForm.date_to || null,
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
      <h3 style={{ fontFamily: "'Fraunces', serif" }}>Интеграции</h3>
      <div className="fp-panel fp-table-panel">
        <table className="fp-table">
          <thead>
            <tr>
              {showCompanyColumn && <th>Компания</th>}
              <th>Название</th>
              <th>Тип</th>
              <th className="center">Статус</th>
              <th>Последний синк</th>
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
                    {i.is_connected ? "Подключено" : "Не подключено"}
                  </span>
                </td>
                <td className="fp-muted">{i.last_sync_at ? fmtDate(i.last_sync_at) : "—"}</td>
                <td className="fp-table-actions-col">
                  <span className="fp-row-actions">
                    {i.is_connected ? (
                      <>
                        {SYNC_SUPPORTED.includes(i.provider) && (
                          <button className="fp-btn-tiny" onClick={() => openSync(i)}>
                            <RefreshCw size={12} /> Синк
                          </button>
                        )}
                        <button className="fp-btn-tiny" onClick={() => handleDisconnect(i)}>
                          Отключить
                        </button>
                      </>
                    ) : (
                      <button className="fp-btn-tiny" onClick={() => openConnect(i)}>
                        Подключить
                      </button>
                    )}
                  </span>
                </td>
              </tr>
            ))}
            {(integrations || []).length === 0 && (
              <tr>
                <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                  Интеграций пока нет
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          Реальная синхронизация реализована для Т-Банка и Альфа-Банка (выписки по счёту) и amoCRM (контакты →
          контрагенты, сделки в статусе «Успешно реализовано» → доходные транзакции). Остальные — заглушки
          каталога на будущее.
        </p>
      </div>

      {connectTarget && (
        <div className="fp-modal-backdrop" onClick={() => setConnectTarget(null)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Подключить «{PROVIDER_LABELS[connectTarget.provider] || connectTarget.provider}»</h3>
              <button className="fp-icon-btn" onClick={() => setConnectTarget(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleConnect}>
              {connectTarget.provider === "amocrm" ? (
                <>
                  <label className="fp-span-2">
                    Поддомен (например, mvkusno из mvkusno.amocrm.ru)
                    <input
                      required
                      value={amoConnectForm.subdomain}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, subdomain: e.target.value }))}
                    />
                  </label>
                  <label>
                    Client ID
                    <input
                      required
                      value={amoConnectForm.client_id}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, client_id: e.target.value }))}
                    />
                  </label>
                  <label>
                    Client Secret
                    <input
                      required
                      value={amoConnectForm.client_secret}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, client_secret: e.target.value }))}
                    />
                  </label>
                  <label>
                    Access token
                    <input
                      required
                      value={amoConnectForm.access_token}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, access_token: e.target.value }))}
                    />
                  </label>
                  <label>
                    Refresh token
                    <input
                      required
                      value={amoConnectForm.refresh_token}
                      onChange={(e) => setAmoConnectForm((p) => ({ ...p, refresh_token: e.target.value }))}
                    />
                  </label>
                  <div className="fp-note fp-span-2">
                    amoCRM не выдаёт статичный токен для внешних интеграций — access/refresh получаются через
                    обмен кода авторизации на вкладке «Ключи и доступы» вашей интеграции в amoMarket.
                  </div>
                </>
              ) : connectTarget.provider === "alfa" ? (
                <>
                  <label className="fp-span-2">
                    API-ключ (Alfa API, Портал разработчика)
                    <input
                      required
                      value={alfaConnectForm.api_key}
                      onChange={(e) => setAlfaConnectForm((p) => ({ ...p, api_key: e.target.value }))}
                    />
                  </label>
                  <div className="fp-span-2">
                    Сертификат клиента (файл .cer, который прислал банк)
                    <div style={{ marginTop: 5 }}>
                      <label
                        className="fp-btn-ghost"
                        style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                      >
                        {alfaConnectForm.cert_pem ? <Check size={14} /> : <Upload size={14} />}
                        {alfaFileNames.cert || "Выбрать файл .cer"}
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
                    Приватный ключ (файл .key, который прислал банк)
                    <div style={{ marginTop: 5 }}>
                      <label
                        className="fp-btn-ghost"
                        style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                      >
                        {alfaConnectForm.key_pem ? <Check size={14} /> : <Upload size={14} />}
                        {alfaFileNames.key || "Выбрать файл .key"}
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
                    Пароль от приватного ключа
                    <input
                      required
                      type="password"
                      value={alfaConnectForm.key_password}
                      onChange={(e) => setAlfaConnectForm((p) => ({ ...p, key_password: e.target.value }))}
                    />
                  </label>
                  <div className="fp-note fp-span-2">
                    Сертификат, ключ и пароль к нему выдаёт Альфа-Банк вместе с API-ключом (личный кабинет
                    разработчика / письмо от банка).
                  </div>
                </>
              ) : (
                <label className="fp-span-2">
                  API-токен
                  <input
                    required
                    value={connectTokenValue}
                    onChange={(e) => setConnectTokenValue(e.target.value)}
                    placeholder="Для теста Т-Банка: TBankSandboxToken"
                  />
                </label>
              )}
              {connectError && <div className="fp-form-error fp-span-2">{connectError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setConnectTarget(null)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={connectSaving}>
                  {connectSaving ? "Сохраняем…" : "Подключить"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {syncTarget && (
        <div className="fp-modal-backdrop" onClick={() => setSyncTarget(null)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Синхронизация «{PROVIDER_LABELS[syncTarget.provider] || syncTarget.provider}»</h3>
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
                    {syncTarget.provider === "amocrm" ? "Счёт (куда записать доход по сделкам)" : "Счёт (с заполненным номером счёта)"}
                    {relevantAccounts.length === 0 ? (
                      <div className="fp-form-error" style={{ marginTop: 6 }}>
                        {needsAccountNumber
                          ? "В этой компании нет счетов с заполненным номером. Добавьте номер счёта в справочнике «Счета»."
                          : "В этой компании нет счетов. Добавьте счёт в справочнике «Счета»."}
                      </div>
                    ) : (
                      <select
                        required
                        value={syncForm.account_id}
                        onChange={(e) => setSyncForm((p) => ({ ...p, account_id: e.target.value }))}
                      >
                        <option value="" disabled>
                          Выберите счёт
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
                {syncTarget.provider === "amocrm" ? "Сделки, закрытые с даты (опц.)" : "С даты"}
                <input
                  type="date"
                  required={syncTarget.provider !== "amocrm"}
                  value={syncForm.date_from}
                  onChange={(e) => setSyncForm((p) => ({ ...p, date_from: e.target.value }))}
                />
              </label>
              {syncTarget.provider !== "amocrm" && (
                <label>
                  По дату (опц.)
                  <input
                    type="date"
                    value={syncForm.date_to}
                    onChange={(e) => setSyncForm((p) => ({ ...p, date_to: e.target.value }))}
                  />
                </label>
              )}
              {syncError && <div className="fp-form-error fp-span-2">{syncError}</div>}
              {syncResult && syncTarget.provider === "amocrm" && (
                <div className="fp-note fp-span-2">
                  Контрагенты: создано {syncResult.contacts_created}, уже были {syncResult.contacts_matched}.
                  <br />
                  Сделки («Успешно реализовано»): загружено {syncResult.deals_created}, пропущено{" "}
                  {syncResult.deals_skipped}.
                </div>
              )}
              {syncResult && syncTarget.provider !== "amocrm" && (
                <div className="fp-note fp-span-2">
                  <div>
                    Загружено новых операций: {syncResult.created}. Пропущено: {syncResult.skipped}.{" "}
                    <button
                      type="button"
                      className="fp-btn-tiny"
                      style={{ marginLeft: 4 }}
                      onClick={() => setSyncDetailsOpen((v) => !v)}
                    >
                      {syncDetailsOpen ? "Скрыть" : "Подробнее"}
                    </button>
                  </div>
                  {syncDetailsOpen && (
                    <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                      <li>Уже были загружены раньше: {syncResult.skipped_duplicate}</li>
                      <li>Нет курса валюты на дату операции: {syncResult.skipped_no_fx_rate}</li>
                      <li>Не удалось распознать операцию: {syncResult.skipped_unparseable}</li>
                    </ul>
                  )}
                </div>
              )}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setSyncTarget(null)}>
                  Закрыть
                </button>
                <button type="submit" className="fp-btn-primary" disabled={syncSaving}>
                  {syncSaving ? "Синхронизируем…" : "Синхронизировать"}
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
    (c) => !multiCompany || !formCompanyId || c.company_id === formCompanyId
  );
  const selectableProjects = (projects || []).filter(
    (p) => !multiCompany || !formCompanyId || p.company_id === formCompanyId
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
    if (!window.confirm("Удалить правило?")) return;
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
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>Правила автоматизации</h3>
        <div style={{ display: "flex", gap: 10 }}>
          {multiCompany && (
            <select value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
              <option value="">Все компании</option>
              {companies.map((m) => (
                <option key={m.company.id} value={m.company.id}>
                  {m.company.name}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> Новое правило
          </button>
        </div>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>Компания</th>}
                <th>Условие</th>
                <th>Действие</th>
                <th className="center">Активно</th>
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
                  <td>{describeCondition(rule.condition_json)}</td>
                  <td className="fp-muted">
                    {rule.action_json?.set_category && `Статья → ${categoriesById[rule.action_json.set_category]?.name || "?"}`}
                    {rule.action_json?.set_category && rule.action_json?.set_project && ", "}
                    {rule.action_json?.set_project && `Проект → ${projectsById[rule.action_json.set_project]?.name || "?"}`}
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
                    Правил пока нет
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          Правило применяется при создании новой операции: если условие совпадает, статья и/или проект
          переопределяются автоматически.
        </p>
      </div>

      <IntegrationsPanel
        token={token}
        integrations={integrations}
        reload={reloadIntegrations}
        companyFilter={companyId}
      />

      {modalOpen && (
        <div className="fp-modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Новое правило</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
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
                  Условия (все должны совпасть)
                </div>
                {form.conditions.map((cond, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && "Поле"}
                      <select
                        value={cond.field}
                        onChange={(e) =>
                          updateCondition(idx, { field: e.target.value, op: OPS_BY_FIELD[e.target.value][0].value })
                        }
                      >
                        {FIELD_OPTIONS.map((f) => (
                          <option key={f.value} value={f.value}>
                            {f.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && "Условие"}
                      <select value={cond.op} onChange={(e) => updateCondition(idx, { op: e.target.value })}>
                        {OPS_BY_FIELD[cond.field].map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && "Значение"}
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
                  <Plus size={13} /> Добавить условие (И)
                </button>
              </div>

              <label>
                Установить статью
                <select value={form.set_category} onChange={(e) => setForm((p) => ({ ...p, set_category: e.target.value }))}>
                  <option value="">— не менять —</option>
                  {selectableCategories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Установить проект
                <select value={form.set_project} onChange={(e) => setForm((p) => ({ ...p, set_project: e.target.value }))}>
                  <option value="">— не менять —</option>
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
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? "Сохраняем…" : "Создать"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
