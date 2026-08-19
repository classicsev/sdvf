"use client";

import { useState, useEffect } from "react";
import { Plus, X, Pencil, Trash2, Tag, LayoutDashboard, Building2, Contact, Ban, RotateCcw, RefreshCw, Upload } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditReference } from "../lib/roles";
import Counterparties from "./Counterparties";

const STATUS_COLUMN = {
  key: "is_active",
  label: "Статус",
  render: (v) => (
    <span className={`fp-status-badge ${v === false ? "warn" : "ok"}`}>{v === false ? "Неактивен" : "Активен"}</span>
  ),
};

const BANK_LABELS = {
  tbank: "Т-Банк",
  sberbank: "Сбербанк",
  alfabank: "Альфа-Банк",
  vtb: "ВТБ",
};

const TABS = {
  categories: {
    label: "Статьи",
    icon: Tag,
    noun: "статью",
    list: (token, companyId) => api.listCategories(token, { company_id: companyId }),
    create: (token, payload, companyId) => api.createCategory(token, payload, companyId),
    update: (token, id, payload) => api.updateCategory(token, id, payload),
    remove: (token, id) => api.deleteCategory(token, id),
    moveCompany: (token, id, companyId) => api.moveCategoryCompany(token, id, companyId),
    fields: [
      { key: "name", label: "Название статьи", type: "text", required: true },
      { key: "group_name", label: "Группа", type: "text" },
      {
        key: "type",
        label: "Тип",
        type: "select",
        options: [
          { value: "income", label: "Приход" },
          { value: "expense", label: "Расход" },
        ],
      },
    ],
    columns: [
      { key: "name", label: "Статья" },
      { key: "group_name", label: "Группа" },
      { key: "type", label: "Тип", render: (v) => (v === "income" ? "Приход" : "Расход") },
      STATUS_COLUMN,
    ],
  },
  projects: {
    label: "Проекты",
    icon: LayoutDashboard,
    noun: "проект",
    list: (token, companyId) => api.listProjects(token, { company_id: companyId }),
    create: (token, payload, companyId) => api.createProject(token, payload, companyId),
    update: (token, id, payload) => api.updateProject(token, id, payload),
    remove: (token, id) => api.deleteProject(token, id),
    moveCompany: (token, id, companyId) => api.moveProjectCompany(token, id, companyId),
    fields: [{ key: "name", label: "Название проекта", type: "text", required: true }],
    columns: [{ key: "name", label: "Проект" }, STATUS_COLUMN],
  },
  accounts: {
    label: "Счета",
    icon: Building2,
    noun: "счёт",
    list: (token, companyId) => api.listAccounts(token, { company_id: companyId }),
    create: (token, payload, companyId) => api.createAccount(token, payload, companyId),
    update: (token, id, payload) => api.updateAccount(token, id, payload),
    remove: (token, id) => api.deleteAccount(token, id),
    moveCompany: (token, id, companyId) => api.moveAccountCompany(token, id, companyId),
    fields: [
      { key: "name", label: "Название счёта", type: "text", required: true },
      {
        key: "currency",
        label: "Валюта",
        type: "select",
        options: [
          { value: "RUB", label: "RUB" },
          { value: "USD", label: "USD" },
          { value: "EUR", label: "EUR" },
          { value: "CNY", label: "CNY" },
        ],
      },
      { key: "opening_balance", label: "Начальный остаток", type: "number" },
      { key: "account_number", label: "Номер счёта (для синка с банком)", type: "text" },
    ],
    columns: [
      { key: "name", label: "Счёт" },
      { key: "currency", label: "Валюта" },
      { key: "opening_balance", label: "Начальный остаток", render: (v, row) => fmt(v, row.currency) },
      { key: "account_number", label: "Номер счёта", render: (v) => v || "—" },
      STATUS_COLUMN,
    ],
  },
};

// Контрагенты живут в отдельном компоненте: карточка организации с реквизитами,
// контактными лицами и связью с СДВФ уже не укладывается в generic-таблицу выше.
const COUNTERPARTIES_TAB = "counterparties";
const TAB_BUTTONS = [
  ...Object.entries(TABS).map(([key, meta]) => ({ key, label: meta.label, icon: meta.icon })),
  { key: COUNTERPARTIES_TAB, label: "Контрагенты", icon: Contact },
];

function defaultFormFor(fields) {
  const form = {};
  fields.forEach((f) => {
    form[f.key] = f.type === "number" ? "0" : f.options ? f.options[0].value : "";
  });
  return form;
}

export default function Reference() {
  const { token, user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const canEditAny = companies.some((m) => canEditReference(m.role));

  const [tab, setTab] = useState("categories");
  // Для вкладки контрагентов generic-конфига нет — она рендерится отдельным
  // компонентом ниже; TABS.categories тут только чтобы хуки ниже не падали.
  const config = TABS[tab] || TABS.categories;
  const isCounterparties = tab === COUNTERPARTIES_TAB;

  // "" = все доступные компании сразу (сводный список); иначе — id конкретной.
  const [companyFilter, setCompanyFilter] = useState("");

  const { data: items, loading, error, reload } = useResource(
    () => (isCounterparties ? Promise.resolve([]) : config.list(token, companyFilter || undefined)),
    [token, tab, companyFilter]
  );

  // Автосинк банковских интеграций — только на вкладке Счетов, только для тех,
  // кто вообще может ими управлять. Бэкенд сам решает, не рано ли реально идти
  // в банк (integration.autosync_interval_minutes) — большинство таких вызовов
  // при обычной навигации мгновенно возвращают "пропущено по таймеру".
  const [syncBanner, setSyncBanner] = useState("");
  const [syncing, setSyncing] = useState(false);

  async function runIntegrationSync(force) {
    setSyncing(true);
    if (force) setSyncBanner("");
    try {
      const r = await api.syncAllIntegrations(token, companyFilter || undefined, force);
      if (force || r.processed > 0) setSyncBanner(r.message);
      if (r.processed > 0) reload();
    } catch (err) {
      if (force) setSyncBanner(err.message);
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    if (tab === "accounts" && canEditAny) {
      runIntegrationSync(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, companyFilter, canEditAny]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(defaultFormFor(config.fields));
  const [formCompanyId, setFormCompanyId] = useState("");
  const [originalCompanyId, setOriginalCompanyId] = useState("");
  const [formIsActive, setFormIsActive] = useState(true);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  // Счета: вместо поиска исторического остатка на дату первой синхронизированной
  // операции — вводим то, что видно в банке сейчас, бэкенд сам пересчитывает
  // "Начальный остаток" (см. AccountSetCurrentBalanceIn на бэкенде).
  const [currentBalanceInput, setCurrentBalanceInput] = useState("");
  const [settingBalance, setSettingBalance] = useState(false);
  const [balanceMessage, setBalanceMessage] = useState("");

  async function handleSetCurrentBalance() {
    setSettingBalance(true);
    setBalanceMessage("");
    try {
      const updated = await api.setAccountCurrentBalance(token, editingId, Number(currentBalanceInput));
      setForm((p) => ({ ...p, opening_balance: String(updated.opening_balance) }));
      setBalanceMessage("Начальный остаток пересчитан и сохранён.");
      setCurrentBalanceInput("");
      reload();
    } catch (err) {
      setBalanceMessage(err.message);
    } finally {
      setSettingBalance(false);
    }
  }

  // Импорт PDF-справки/выписки для счетов физлиц без банковского API (Т-Банк,
  // Сбербанк, Альфа-Банк, ВТБ) — банк определяется бэкендом по содержимому файла.
  // Сначала dry-run-предпросмотр (ничего не пишет в БД), затем подтверждение.
  const [statementFile, setStatementFile] = useState(null);
  const [statementPreview, setStatementPreview] = useState(null);
  const [statementResult, setStatementResult] = useState(null);
  const [statementBusy, setStatementBusy] = useState(false);
  const [statementError, setStatementError] = useState("");

  function resetStatementImport() {
    setStatementFile(null);
    setStatementPreview(null);
    setStatementResult(null);
    setStatementError("");
  }

  // Если файл выбран ещё до сохранения счёта (создание "с нуля"), сначала тихо
  // создаём счёт текущими значениями формы — иначе пришлось бы сначала жать
  // "Сохранить", а потом снова открывать счёт на редактирование ради импорта.
  // Дальше модалка ведёт себя как обычное редактирование уже созданного счёта.
  async function ensureAccountIdForStatement() {
    if (editingId) return editingId;
    if (!form.name?.trim()) {
      throw new Error("Сначала укажите название счёта");
    }
    const payload = { ...form, is_active: true };
    config.fields.forEach((f) => {
      if (f.type === "number") payload[f.key] = Number(payload[f.key] || 0);
    });
    const created = await config.create(token, payload, formCompanyId || undefined);
    setEditingId(created.id);
    setOriginalCompanyId(created.company_id);
    reload();
    return created.id;
  }

  async function handleStatementFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setStatementFile(file);
    setStatementResult(null);
    setStatementPreview(null);
    setStatementError("");
    setStatementBusy(true);
    try {
      const accountId = await ensureAccountIdForStatement();
      const preview = await api.importStatement(token, accountId, file, true);
      setStatementPreview(preview);
    } catch (err) {
      setStatementError(err.message);
    } finally {
      setStatementBusy(false);
    }
  }

  async function handleConfirmStatementImport() {
    if (!statementFile) return;
    setStatementBusy(true);
    setStatementError("");
    try {
      const accountId = await ensureAccountIdForStatement();
      // Остаток из справки применяется на бэкенде — тем же запросом и тем же
      // коммитом, что и сам импорт операций (см. routers/statements.py), а не
      // отдельным вызовом отсюда: раньше это было два шага, и порядок/сам факт
      // второго шага ничем не гарантировался.
      const result = await api.importStatement(token, accountId, statementFile, false);
      // Критично: синхронизируем поле формы с реальным значением из БД. Иначе
      // форма продолжает показывать старое "Начальный остаток", и если после
      // этого нажать общую кнопку "Сохранить", она отправит устаревшее число и
      // затрёт только что применённый остаток обратно — именно это и произошло
      // на реальных счетах пользователя.
      if (result.account_opening_balance != null) {
        setForm((p) => ({ ...p, opening_balance: String(result.account_opening_balance) }));
      }
      setStatementResult(result);
      setStatementPreview(null);
      setStatementFile(null);
      reload();
    } catch (err) {
      setStatementError(err.message);
    } finally {
      setStatementBusy(false);
    }
  }

  // Область видимости статьи/проекта по компаниям холдинга — отдельно от
  // generic form (у Account/Counterparty таких полей нет вовсе, схема бы не
  // приняла is_global/visible_company_ids). См. TABS.categories/projects.
  const [formIsGlobal, setFormIsGlobal] = useState(false);
  const [formVisibleCompanyIds, setFormVisibleCompanyIds] = useState([]);
  const supportsCompanyScope = tab === "categories" || tab === "projects";

  function openAdd() {
    setEditingId(null);
    setForm(defaultFormFor(config.fields));
    const editableCompanies = companies.filter((m) => canEditReference(m.role));
    const preselected = editableCompanies.find((m) => m.company.id === companyFilter) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setOriginalCompanyId("");
    setFormIsActive(true);
    setFormIsGlobal(false);
    setFormVisibleCompanyIds([]);
    setFormError("");
    setCurrentBalanceInput("");
    setBalanceMessage("");
    resetStatementImport();
    setModalOpen(true);
  }

  function openEdit(item) {
    setEditingId(item.id);
    const next = {};
    config.fields.forEach((f) => (next[f.key] = item[f.key] ?? ""));
    setForm(next);
    setFormCompanyId(item.company_id || "");
    setOriginalCompanyId(item.company_id || "");
    setFormIsActive(item.is_active !== false);
    setFormIsGlobal(!!item.is_global);
    setFormVisibleCompanyIds(item.visible_company_ids || []);
    setFormError("");
    setCurrentBalanceInput("");
    setBalanceMessage("");
    resetStatementImport();
    setModalOpen(true);
  }

  function switchTab(key) {
    setTab(key);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const payload = { ...form, is_active: formIsActive };
      config.fields.forEach((f) => {
        if (f.type === "number") payload[f.key] = Number(payload[f.key] || 0);
      });
      if (supportsCompanyScope) {
        payload.is_global = formIsGlobal;
        payload.visible_company_ids = formIsGlobal ? [] : formVisibleCompanyIds;
      }
      if (editingId) {
        // Перенос в другую компанию — отдельным вызовом (бэкенд блокирует его,
        // если запись уже где-то используется, см. move_to_company) и раньше
        // остальных правок, чтобы не сохранить их в исходной компании, если
        // перенос не удался.
        if (multiCompany && formCompanyId && formCompanyId !== originalCompanyId) {
          await config.moveCompany(token, editingId, formCompanyId);
        }
        await config.update(token, editingId, payload);
      } else {
        await config.create(token, payload, formCompanyId || undefined);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(`Удалить «${item.name}»?`)) return;
    try {
      const result = await config.remove(token, item.id);
      if (result?.deactivated) {
        window.alert(
          `«${item.name}» уже используется в операциях, поэтому не удалено, а деактивировано — ` +
            `больше не будет предлагаться при выборе, но история сохранена. Восстановить можно кнопкой в списке.`
        );
      }
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleToggleActive(item) {
    const payload = Object.fromEntries(config.fields.map((f) => [f.key, item[f.key]]));
    payload.is_active = item.is_active === false;
    try {
      await config.update(token, item.id, payload);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  const showCompanyColumn = multiCompany && !companyFilter;
  const editableCompanies = companies.filter((m) => canEditReference(m.role));

  const tabsRow = (
    <div className="fp-tabs">
      {TAB_BUTTONS.map((meta) => (
        <button key={meta.key} className={tab === meta.key ? "active" : ""} onClick={() => switchTab(meta.key)}>
          <meta.icon size={14} />
          {meta.label}
        </button>
      ))}
    </div>
  );

  if (isCounterparties) {
    return (
      <div className="fp-dash">
        <div className="fp-tabs-row">{tabsRow}</div>
        <Counterparties />
      </div>
    );
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        {tabsRow}
        {multiCompany && (
          <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
            <option value="">Все компании</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        )}
        {tab === "accounts" && canEditAny && (
          <button type="button" className="fp-btn-tiny" onClick={() => runIntegrationSync(true)} disabled={syncing}>
            <RefreshCw size={13} /> {syncing ? "Синхронизируем…" : "Синхронизировать"}
          </button>
        )}
        {canEditAny && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> Добавить
          </button>
        )}
      </div>

      {tab === "accounts" && syncBanner && (
        <div className="fp-panel" style={{ padding: "10px 14px", fontSize: 13 }}>
          {syncBanner}
        </div>
      )}
      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (items || []).length === 0 ? (
          <div className="fp-empty">Список пуст</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>Компания</th>}
                {config.columns.map((c) => (
                  <th key={c.key}>{c.label}</th>
                ))}
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const canEditRow = canEditReference(roleForCompany(item.company_id));
                return (
                  <tr key={item.id}>
                    {showCompanyColumn && (
                      <td>
                        {item.is_global ? (
                          <span className="fp-status-badge ok">Все компании</span>
                        ) : (
                          <>
                            {companies.find((m) => m.company.id === item.company_id)?.company.name || "—"}
                            {item.visible_company_ids?.length > 0 && (
                              <span className="fp-muted" style={{ marginLeft: 6, fontSize: 11.5 }}>
                                +{item.visible_company_ids.length}
                              </span>
                            )}
                          </>
                        )}
                      </td>
                    )}
                    {config.columns.map((c) => (
                      <td key={c.key}>{c.render ? c.render(item[c.key], item) : item[c.key] || "—"}</td>
                    ))}
                    <td className="fp-table-actions-col">
                      {canEditRow && (
                        <span className="fp-row-actions">
                          <button className="fp-icon-btn" onClick={() => openEdit(item)}>
                            <Pencil size={14} />
                          </button>
                          <button
                            className="fp-icon-btn"
                            onClick={() => handleToggleActive(item)}
                            title={item.is_active === false ? "Восстановить" : "Деактивировать"}
                          >
                            {item.is_active === false ? <RotateCcw size={14} /> : <Ban size={14} />}
                          </button>
                          <button className="fp-icon-btn" onClick={() => handleDelete(item)}>
                            <Trash2 size={14} />
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? `Редактировать ${config.noun}` : `Новый(ая) ${config.noun}`}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
                  <select value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)} required>
                    {/* Текущая компания записи может быть уже недоступна для
                        переноса (не admin) — всё равно показываем её в списке,
                        иначе выбранное значение "потеряется" при открытии формы. */}
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
                  {editingId && formCompanyId !== originalCompanyId && (
                    <span className="fp-muted" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                      Перенос сработает, только если запись ещё нигде не используется.
                    </span>
                  )}
                </label>
              )}
              {config.fields.map((f) => (
                <label key={f.key} className={f.type === "text" && f.key === "name" ? "fp-span-2" : ""}>
                  {f.label}
                  {f.type === "select" ? (
                    <select value={form[f.key]} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}>
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={f.type === "number" ? "number" : "text"}
                      step={f.type === "number" ? "0.01" : undefined}
                      required={f.required}
                      value={form[f.key]}
                      onChange={(e) => {
                        setForm((p) => ({ ...p, [f.key]: e.target.value }));
                        if (f.key === "opening_balance") setStatementResult(null);
                      }}
                    />
                  )}
                  {f.key === "opening_balance" && statementResult?.account_opening_balance != null && (
                    <span style={{ color: "var(--expense)", fontSize: 11.5, display: "block", marginTop: 3 }}>
                      Совпадает с банком — менять не нужно
                    </span>
                  )}
                </label>
              ))}

              {supportsCompanyScope && multiCompany && (
                <div
                  className="fp-span-2"
                  style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Видимость по компаниям</div>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400 }}>
                    <input
                      type="checkbox"
                      checked={formIsGlobal}
                      onChange={(e) => setFormIsGlobal(e.target.checked)}
                      style={{ width: "auto" }}
                    />
                    Все компании (включая те, что появятся позже)
                  </label>
                  {!formIsGlobal && (
                    <>
                      <p className="fp-note" style={{ margin: "8px 0 6px" }}>
                        Кроме «своей» компании — где ещё выбирать эт{tab === "categories" ? "у статью" : "от проект"}:
                      </p>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {companies
                          .filter((m) => canEditReference(m.role) && m.company.id !== formCompanyId)
                          .map((m) => (
                            <label
                              key={m.company.id}
                              style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400 }}
                            >
                              <input
                                type="checkbox"
                                checked={formVisibleCompanyIds.includes(m.company.id)}
                                onChange={(e) =>
                                  setFormVisibleCompanyIds((prev) =>
                                    e.target.checked
                                      ? [...prev, m.company.id]
                                      : prev.filter((id) => id !== m.company.id)
                                  )
                                }
                                style={{ width: "auto" }}
                              />
                              {m.company.name}
                            </label>
                          ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {tab === "accounts" && editingId && (
                <div
                  className="fp-span-2"
                  style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Остаток не совпадает с банком?</div>
                  <p className="fp-note" style={{ margin: "0 0 8px" }}>
                    Не нужно искать исторический баланс — введите остаток, который видно в банке прямо сейчас,
                    «Начальный остаток» выше пересчитается автоматически.
                  </p>
                  <div style={{ display: "flex", gap: 6 }}>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Остаток на сегодня"
                      value={currentBalanceInput}
                      onChange={(e) => {
                        setBalanceMessage("");
                        setCurrentBalanceInput(e.target.value);
                      }}
                      style={{ flex: 1, minWidth: 0 }}
                    />
                    <button
                      type="button"
                      className="fp-btn-ghost"
                      onClick={handleSetCurrentBalance}
                      disabled={!currentBalanceInput || settingBalance}
                      style={{ whiteSpace: "nowrap" }}
                    >
                      {settingBalance ? "Считаем…" : "Указать"}
                    </button>
                  </div>
                  {balanceMessage && (
                    <div className="fp-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                      {balanceMessage}
                    </div>
                  )}
                </div>
              )}

              {tab === "accounts" && (
                <div
                  className="fp-span-2"
                  style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                    Импорт из справки/выписки банка (PDF)
                  </div>
                  <p className="fp-note" style={{ margin: "0 0 8px" }}>
                    Для счетов физлиц без API банка — Т-Банк, Сбербанк, Альфа-Банк, ВТБ. Банк определяется
                    автоматически по содержимому файла.
                    {!editingId && " Счёт сохранится автоматически, как только выберете файл — укажите хотя бы название выше."}
                  </p>
                  <label className="fp-btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                    <Upload size={14} />
                    {statementFile ? statementFile.name : "Выбрать файл"}
                    <input
                      type="file"
                      accept="application/pdf"
                      onChange={handleStatementFileChange}
                      disabled={statementBusy}
                      style={{ display: "none" }}
                    />
                  </label>
                  {statementBusy && (
                    <div className="fp-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                      Разбираем файл…
                    </div>
                  )}
                  {statementError && (
                    <div className="fp-form-error" style={{ marginTop: 6 }}>
                      {statementError}
                    </div>
                  )}
                  {statementPreview && (
                    <div style={{ marginTop: 8, fontSize: 12.5 }}>
                      <div>
                        Банк: <b>{BANK_LABELS[statementPreview.bank] || statementPreview.bank}</b>
                        {statementPreview.period_from && statementPreview.period_to && (
                          <>
                            {" "}
                            · период {fmtDate(statementPreview.period_from)} — {fmtDate(statementPreview.period_to)}
                          </>
                        )}
                      </div>
                      <div style={{ marginTop: 4 }}>
                        Новых операций: <b>{statementPreview.created}</b>
                        {statementPreview.skipped_duplicate > 0 && <> · уже есть в Учёте: {statementPreview.skipped_duplicate}</>}
                        {statementPreview.skipped_no_fx_rate > 0 && <> · нет курса на дату: {statementPreview.skipped_no_fx_rate}</>}
                      </div>
                      {statementPreview.closing_balance != null && (
                        <div style={{ marginTop: 6 }}>
                          Остаток на {fmtDate(statementPreview.closing_balance_date)}:{" "}
                          <b>{fmt(statementPreview.closing_balance, form.currency)}</b> — применится к «Начальному
                          остатку» автоматически{statementPreview.created > 0 ? " после импорта." : "."}
                        </div>
                      )}
                      <div style={{ marginTop: 8 }}>
                        <button
                          type="button"
                          className="fp-btn-primary"
                          onClick={handleConfirmStatementImport}
                          disabled={statementBusy || (statementPreview.created === 0 && statementPreview.closing_balance == null)}
                        >
                          {statementBusy
                            ? "Обрабатываем…"
                            : statementPreview.created > 0
                            ? `Импортировать ${statementPreview.created} операций`
                            : "Применить остаток из справки"}
                        </button>
                      </div>
                    </div>
                  )}
                  {statementResult && (
                    <div className="fp-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                      Импортировано {statementResult.created} операций
                      {statementResult.skipped_duplicate > 0 ? `, пропущено дублей: ${statementResult.skipped_duplicate}` : ""}
                      {statementResult.closing_balance != null ? ". Начальный остаток пересчитан по остатку из справки." : "."}
                    </div>
                  )}
                </div>
              )}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}

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
