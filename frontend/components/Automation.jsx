"use client";

import { useMemo, useState } from "react";
import { Plus, X, Trash2, Plug, RefreshCw } from "lucide-react";
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

const SYNC_SUPPORTED = ["tinkoff", "amocrm"];

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

function IntegrationsPanel({ token, integrations, accounts, reload }) {
  const [connectTarget, setConnectTarget] = useState(null);
  const [connectTokenValue, setConnectTokenValue] = useState("");
  const [amoConnectForm, setAmoConnectForm] = useState(AMO_CONNECT_EMPTY);
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
    setConnectError("");
  }

  async function handleConnect(e) {
    e.preventDefault();
    setConnectSaving(true);
    setConnectError("");
    try {
      if (connectTarget.provider === "amocrm") {
        await api.connectAmoCrm(token, connectTarget.id, amoConnectForm);
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
                <td colSpan={5} className="fp-empty">
                  Интеграций пока нет
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          Реальная синхронизация реализована для Т-Банка (API «Операции по счету») и amoCRM (контакты →
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
              <label className="fp-span-2">
                {syncTarget.provider === "amocrm" ? "Счёт (куда записать доход по сделкам)" : "Счёт (с заполненным номером счёта)"}
                <select
                  required
                  value={syncForm.account_id}
                  onChange={(e) => setSyncForm((p) => ({ ...p, account_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите счёт
                  </option>
                  {(accounts || []).map((a) => (
                    <option key={a.id} value={a.id} disabled={syncTarget.provider !== "amocrm" && !a.account_number}>
                      {syncTarget.provider === "amocrm"
                        ? a.name
                        : `${a.name} ${a.account_number ? `(${a.account_number})` : "— нет номера счёта"}`}
                    </option>
                  ))}
                </select>
              </label>
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
  const { token } = useAuth();
  const { data: rules, loading, error, reload } = useResource(() => api.listAutomationRules(token), [token]);
  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);
  const { data: integrations, reload: reloadIntegrations } = useResource(() => api.listIntegrations(token), [token]);
  const { data: accounts } = useResource(() => api.listAccounts(token), [token]);

  const categoriesById = useMemo(() => Object.fromEntries((categories || []).map((c) => [c.id, c])), [categories]);
  const projectsById = useMemo(() => Object.fromEntries((projects || []).map((p) => [p.id, p])), [projects]);

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(FORM_EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  function openAdd() {
    setForm(FORM_EMPTY);
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

      await api.createAutomationRule(token, {
        condition_json: condition_json.length === 1 ? condition_json[0] : condition_json,
        action_json,
        is_active: true,
      });
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
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Новое правило
        </button>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                <th>Условие</th>
                <th>Действие</th>
                <th className="center">Активно</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(rules || []).map((rule) => (
                <tr key={rule.id}>
                  <td>{describeCondition(rule.condition_json)}</td>
                  <td className="fp-muted">
                    {rule.action_json?.set_category && `Статья → ${categoriesById[rule.action_json.set_category]?.name || "?"}`}
                    {rule.action_json?.set_category && rule.action_json?.set_project && ", "}
                    {rule.action_json?.set_project && `Проект → ${projectsById[rule.action_json.set_project]?.name || "?"}`}
                  </td>
                  <td className="center">
                    <label className="fp-mini-switch">
                      <input type="checkbox" checked={rule.is_active} onChange={() => toggleActive(rule)} />
                      <span />
                    </label>
                  </td>
                  <td className="fp-table-actions-col">
                    <button className="fp-icon-btn" onClick={() => handleDelete(rule)}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
              {(rules || []).length === 0 && (
                <tr>
                  <td colSpan={4} className="fp-empty">
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

      <IntegrationsPanel token={token} integrations={integrations} accounts={accounts} reload={reloadIntegrations} />

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
                  {(categories || []).map((c) => (
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
                  {(projects || []).map((p) => (
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
