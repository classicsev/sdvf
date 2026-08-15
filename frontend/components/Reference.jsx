"use client";

import { useState } from "react";
import { Plus, X, Pencil, Trash2, Tag, LayoutDashboard, Building2, Contact, Ban, RotateCcw } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt } from "../lib/format";
import { canEditReference } from "../lib/roles";
import Counterparties from "./Counterparties";

const STATUS_COLUMN = {
  key: "is_active",
  label: "Статус",
  render: (v) => (
    <span className={`fp-status-badge ${v === false ? "warn" : "ok"}`}>{v === false ? "Неактивен" : "Активен"}</span>
  ),
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

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(defaultFormFor(config.fields));
  const [formCompanyId, setFormCompanyId] = useState("");
  const [originalCompanyId, setOriginalCompanyId] = useState("");
  const [formIsActive, setFormIsActive] = useState(true);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  function openAdd() {
    setEditingId(null);
    setForm(defaultFormFor(config.fields));
    const editableCompanies = companies.filter((m) => canEditReference(m.role));
    const preselected = editableCompanies.find((m) => m.company.id === companyFilter) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setOriginalCompanyId("");
    setFormIsActive(true);
    setFormError("");
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
    setFormError("");
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
        {canEditAny && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> Добавить
          </button>
        )}
      </div>

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
                      <td>{companies.find((m) => m.company.id === item.company_id)?.company.name || "—"}</td>
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
                      onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    />
                  )}
                </label>
              ))}

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
