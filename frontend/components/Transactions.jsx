"use client";

import { useMemo, useState } from "react";
import { Plus, Download, X, Pencil, Trash2, Lock } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditTransactions } from "../lib/roles";

const EMPTY_FORM = {
  date_odds: new Date().toISOString().slice(0, 10),
  account_id: "",
  category_id: "",
  project_id: "",
  counterparty_id: "",
  type: "expense",
  amount: "",
  currency: "RUB",
  commission: "0",
  comment: "",
};

export default function Transactions() {
  const { token, user } = useAuth();
  const canEdit = canEditTransactions(user.role);

  const [filters, setFilters] = useState({ project: "", account: "", category: "", date_from: "", date_to: "" });
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  const { data: accounts } = useResource(() => api.listAccounts(token), [token]);
  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);
  const { data: counterparties } = useResource(() => api.listCounterparties(token), [token]);

  const query = {
    project: filters.project || undefined,
    account: filters.account || undefined,
    category: filters.category || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
  };
  const {
    data: transactions,
    loading,
    error,
    reload,
  } = useResource(() => api.listTransactions(token, query), [token, JSON.stringify(query)]);

  const accountsById = useMemo(() => Object.fromEntries((accounts || []).map((a) => [a.id, a])), [accounts]);
  const categoriesById = useMemo(() => Object.fromEntries((categories || []).map((c) => [c.id, c])), [categories]);
  const projectsById = useMemo(() => Object.fromEntries((projects || []).map((p) => [p.id, p])), [projects]);
  const counterpartiesById = useMemo(
    () => Object.fromEntries((counterparties || []).map((c) => [c.id, c])),
    [counterparties]
  );

  function openAdd() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError("");
    setModalOpen(true);
  }

  function openEdit(tx) {
    setEditing(tx);
    setForm({
      date_odds: tx.date_odds,
      account_id: tx.account_id,
      category_id: tx.category_id,
      project_id: tx.project_id || "",
      counterparty_id: tx.counterparty_id || "",
      type: tx.type,
      amount: String(tx.amount),
      currency: tx.currency,
      commission: String(tx.commission || 0),
      comment: tx.comment || "",
    });
    setFormError("");
    setModalOpen(true);
  }

  function updateField(field, value) {
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      if (field === "account_id") {
        const acc = accountsById[value];
        if (acc) next.currency = acc.currency;
      }
      return next;
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError("");
    setSaving(true);
    try {
      const payload = {
        date_odds: form.date_odds,
        account_id: form.account_id,
        category_id: form.category_id,
        project_id: form.project_id || null,
        counterparty_id: form.counterparty_id || null,
        type: form.type,
        amount: Number(form.amount),
        currency: form.currency,
        commission: Number(form.commission || 0),
        comment: form.comment || null,
      };
      if (editing) {
        await api.updateTransaction(token, editing.id, payload);
      } else {
        await api.createTransaction(token, payload);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(tx) {
    if (!window.confirm("Удалить операцию?")) return;
    try {
      await api.deleteTransaction(token, tx.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      await api.exportTransactions(token, query);
    } catch (err) {
      window.alert(err.message);
    } finally {
      setExporting(false);
    }
  }

  const filteredCategories = (categories || []).filter((c) => c.type === form.type);

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <select value={filters.project} onChange={(e) => setFilters((f) => ({ ...f, project: e.target.value }))}>
            <option value="">Все проекты</option>
            {(projects || []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select value={filters.account} onChange={(e) => setFilters((f) => ({ ...f, account: e.target.value }))}>
            <option value="">Все счета</option>
            {(accounts || []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
          <select value={filters.category} onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}>
            <option value="">Все статьи</option>
            {(categories || []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
          />
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <button className="fp-btn-ghost" onClick={handleExport} disabled={exporting}>
            <Download size={15} /> {exporting ? "Экспорт…" : "Экспорт в Excel"}
          </button>
          {canEdit && (
            <button className="fp-btn-primary" onClick={openAdd}>
              <Plus size={16} /> Новая операция
            </button>
          )}
        </div>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (transactions || []).length === 0 ? (
          <div className="fp-empty">Операций не найдено</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>Счёт</th>
                <th>Статья</th>
                <th>Проект</th>
                <th>Контрагент</th>
                <th>Комментарий</th>
                <th className="right">Комиссия</th>
                <th className="right fp-table-amount-col" style={{ right: canEdit ? 90 : 0 }}>
                  Сумма
                </th>
                {canEdit && <th className="fp-table-actions-col"></th>}
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => {
                const acc = accountsById[t.account_id];
                const cat = categoriesById[t.category_id];
                const proj = t.project_id ? projectsById[t.project_id] : null;
                const cp = t.counterparty_id ? counterpartiesById[t.counterparty_id] : null;
                const canEditRow = canEdit && (user.role === "admin" || t.created_by === user.id);
                return (
                  <tr key={t.id}>
                    <td>{fmtDate(t.date_odds)}</td>
                    <td>
                      {acc?.name || "—"}
                      {acc && <span className={`fp-currency-badge ${acc.currency}`}>{acc.currency}</span>}
                    </td>
                    <td>
                      <span className={`fp-cat-dot ${t.type}`} />
                      {cat?.name || "—"}
                    </td>
                    <td>{proj?.name || <span className="fp-muted">—</span>}</td>
                    <td>{cp?.name || <span className="fp-muted">—</span>}</td>
                    <td className="fp-muted fp-table-comment-col" title={t.comment || ""}>
                      {t.comment || "—"}
                    </td>
                    <td className="right fp-mono">{t.commission ? fmt(t.commission, t.currency) : "—"}</td>
                    <td
                      className={`right fp-mono fp-amount-${t.type} fp-table-amount-col`}
                      style={{ right: canEdit ? 90 : 0 }}
                    >
                      {t.type === "expense" ? "-" : ""}
                      {fmt(t.amount, t.currency)}
                      {t.currency !== "RUB" && (
                        <div className="fp-sub-value">≈ {fmt(t.amount_rub, "RUB")}</div>
                      )}
                    </td>
                    {canEdit && (
                      <td className="fp-table-actions-col">
                        {canEditRow ? (
                          <span className="fp-row-actions">
                            <button className="fp-icon-btn" onClick={() => openEdit(t)}>
                              <Pencil size={14} />
                            </button>
                            <button className="fp-icon-btn" onClick={() => handleDelete(t)}>
                              <Trash2 size={14} />
                            </button>
                          </span>
                        ) : (
                          <span className="fp-muted">—</span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {!canEdit && (
          <div className="fp-viewer-note">
            <Lock size={13} /> Режим «Только просмотр» — добавление и редактирование операций недоступно
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editing ? "Редактировать операцию" : "Новая операция"}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="fp-type-toggle">
              <button
                type="button"
                className={form.type === "income" ? "active income" : ""}
                onClick={() => updateField("type", "income")}
              >
                Приход
              </button>
              <button
                type="button"
                className={form.type === "expense" ? "active expense" : ""}
                onClick={() => updateField("type", "expense")}
              >
                Расход
              </button>
            </div>

            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label>
                Дата операции
                <input
                  type="date"
                  required
                  value={form.date_odds}
                  onChange={(e) => updateField("date_odds", e.target.value)}
                />
              </label>
              <label>
                Счёт
                <select required value={form.account_id} onChange={(e) => updateField("account_id", e.target.value)}>
                  <option value="" disabled>
                    Выберите счёт
                  </option>
                  {(accounts || []).map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} ({a.currency})
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Статья
                <select
                  required
                  value={form.category_id}
                  onChange={(e) => updateField("category_id", e.target.value)}
                >
                  <option value="" disabled>
                    Выберите статью
                  </option>
                  {filteredCategories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Проект
                <select value={form.project_id} onChange={(e) => updateField("project_id", e.target.value)}>
                  <option value="">— не указан —</option>
                  {(projects || []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Контрагент
                <select value={form.counterparty_id} onChange={(e) => updateField("counterparty_id", e.target.value)}>
                  <option value="">— не указан —</option>
                  {(counterparties || []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Валюта
                <input value={form.currency} onChange={(e) => updateField("currency", e.target.value.toUpperCase())} />
              </label>

              <label>
                Сумма
                <input
                  type="number"
                  step="0.01"
                  required
                  value={form.amount}
                  onChange={(e) => updateField("amount", e.target.value)}
                />
              </label>
              <label>
                Комиссия
                <input
                  type="number"
                  step="0.01"
                  value={form.commission}
                  onChange={(e) => updateField("commission", e.target.value)}
                />
              </label>

              <label className="fp-span-2">
                Комментарий
                <input value={form.comment} onChange={(e) => updateField("comment", e.target.value)} />
              </label>

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
