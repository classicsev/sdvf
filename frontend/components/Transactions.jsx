"use client";

import { useMemo, useState, useEffect } from "react";
import { Plus, Download, X, Pencil, Trash2, Lock } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditTransactions } from "../lib/roles";
import { Combobox } from "./Combobox";

const SOURCE_LABELS = { tbank: "Т-Банк", amocrm: "amoCRM", alfabank: "Альфа-Банк" };

function sourceBadge(externalRef) {
  if (!externalRef) return null;
  const provider = externalRef.split(":")[0];
  const label = SOURCE_LABELS[provider];
  if (!label) return null;
  return (
    <span className={`fp-source-badge ${provider}`} title="Источник операции">
      {label}
    </span>
  );
}

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
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const canEditAnyCompany = companies.some((m) => canEditTransactions(m.role));
  // Обратная совместимость для однокомпанийного случая — совпадает со старым canEdit.
  const canEdit = canEditAnyCompany;

  const [filters, setFilters] = useState({
    company: "",
    project: "",
    account: "",
    category: "",
    date_from: "",
    date_to: "",
  });
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(0);
  const [useAllForDates, setUseAllForDates] = useState(false);
  const [selectedTransactionIds, setSelectedTransactionIds] = useState(new Set());
  const [selectedAllMatching, setSelectedAllMatching] = useState(false);
  const [matchingCount, setMatchingCount] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const { data: accounts } = useResource(() => api.listAccounts(token), [token]);
  const { data: categories } = useResource(() => api.listCategories(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);
  const { data: counterparties } = useResource(() => api.listCounterparties(token), [token]);

  const query = {
    company_id: filters.company || undefined,
    project: filters.project || undefined,
    account: filters.account || undefined,
    category: filters.category || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    limit: useAllForDates ? undefined : pageSize,
    skip: useAllForDates ? undefined : currentPage * pageSize,
    all_records: useAllForDates || undefined,
  };
  const {
    data: transactions,
    loading,
    error,
    reload,
  } = useResource(() => api.listTransactions(token, query), [token, JSON.stringify(query)]);

  const countQuery = {
    company_id: filters.company || undefined,
    project: filters.project || undefined,
    account: filters.account || undefined,
    category: filters.category || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
  };
  useEffect(() => {
    if (!token) return;
    api.countTransactions(token, countQuery)
      .then((count) => setMatchingCount(Number(count) || 0))
      .catch(() => setMatchingCount(null));
  }, [token, JSON.stringify(countQuery)]);

  const accountsById = useMemo(() => Object.fromEntries((accounts || []).map((a) => [a.id, a])), [accounts]);
  const categoriesById = useMemo(() => Object.fromEntries((categories || []).map((c) => [c.id, c])), [categories]);
  const projectsById = useMemo(() => Object.fromEntries((projects || []).map((p) => [p.id, p])), [projects]);
  const counterpartiesById = useMemo(
    () => Object.fromEntries((counterparties || []).map((c) => [c.id, c])),
    [counterparties]
  );

  const hasDateFilter = !!(filters.date_from || filters.date_to);

  // Сброс выбора и страницы при изменении фильтров
  useEffect(() => {
    setSelectedTransactionIds(new Set());
    setSelectedAllMatching(false);
    setCurrentPage(0);
    if (!hasDateFilter) setUseAllForDates(false);
  }, [JSON.stringify(filters), pageSize, hasDateFilter]);

  function openAdd() {
    setEditing(null);
    setForm(EMPTY_FORM);
    const editableCompanies = companies.filter((m) => canEditTransactions(m.role));
    const preselected = editableCompanies.find((m) => m.company.id === filters.company) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setFormError("");
    setModalOpen(true);
    // Сбросить выбор при добавлении новой операции
    setSelectedTransactionIds(new Set());
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
    setFormCompanyId(tx.company_id || "");
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

  function updateFormCompany(companyId) {
    setFormCompanyId(companyId);
    // Счёт/статья/проект/контрагент из прошлой компании могут не подойти к новой — сбрасываем.
    setForm((prev) => ({ ...prev, account_id: "", category_id: "", project_id: "", counterparty_id: "" }));
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
        await api.createTransaction(token, payload, formCompanyId || undefined);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
    // Сбросить выбор после сохранения
    setSelectedTransactionIds(new Set());
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

  function toggleTransactionSelection(txId) {
    setSelectedAllMatching(false);
    setSelectedTransactionIds((prev) => {
      const next = new Set(prev);
      if (next.has(txId)) {
        next.delete(txId);
      } else {
        next.add(txId);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedAllMatching || selectedTransactionIds.size === transactions.length) {
      // Если всё выбрано — отменяем выбор
      setSelectedTransactionIds(new Set());
      setSelectedAllMatching(false);
    } else {
      // Выбираем все на текущей странице
      setSelectedTransactionIds(new Set((transactions || []).map((t) => t.id)));
    }
  }

  function selectAllMatching() {
    // Выбираем все операции, соответствующие текущим фильтрам (не только на странице)
    setSelectedTransactionIds(new Set((transactions || []).map((t) => t.id)));
    setSelectedAllMatching(true);
  }

  async function handleBatchDelete() {
    if (!selectedAllMatching && selectedTransactionIds.size === 0) {
      window.alert("Выберите операции для удаления");
      return;
    }

    const confirmText = selectedAllMatching
      ? `Удалить все подходящие операции (${matchingCount ?? "?"})?`
      : `Удалить ${selectedTransactionIds.size} операций?`;
    if (!window.confirm(confirmText)) return;

    setDeleting(true);
    try {
      let result;
      if (selectedAllMatching) {
        result = await api.batchDeleteTransactionsByFilter(token, {
          company_id: filters.company || undefined,
          project: filters.project || undefined,
          account: filters.account || undefined,
          category: filters.category || undefined,
          date_from: filters.date_from || undefined,
          date_to: filters.date_to || undefined,
        });
      } else {
        result = await api.batchDeleteTransactions(token, Array.from(selectedTransactionIds));
      }
      setSelectedTransactionIds(new Set());
      setSelectedAllMatching(false);
      reload();
      window.alert(`Удалено ${result.deleted} операций`);
    } catch (err) {
      window.alert(err.message);
    } finally {
      setDeleting(false);
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

  const selectable = (list, selectedId) =>
    (list || [])
      .filter((x) => x.is_active !== false || x.id === selectedId)
      .filter((x) => !multiCompany || !formCompanyId || x.company_id === formCompanyId || x.id === selectedId);

  const filteredCategories = selectable(categories, form.category_id).filter((c) => c.type === form.type);
  const selectableAccounts = selectable(accounts, form.account_id);
  const selectableProjects = selectable(projects, form.project_id);
  const selectableCounterparties = selectable(counterparties, form.counterparty_id);
  const editableCompanies = companies.filter((m) => canEditTransactions(m.role));
  const showCompanyColumn = multiCompany && !filters.company;

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {multiCompany && (
            <div className="fp-filter-combobox">
              <Combobox
                value={filters.company}
                onChange={(val) => setFilters((f) => ({ ...f, company: val }))}
                options={companies.map((m) => ({ id: m.company.id, name: m.company.name }))}
                placeholder="Все компании"
              />
            </div>
          )}
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.project}
              onChange={(val) => setFilters((f) => ({ ...f, project: val }))}
              options={(projects || []).map((p) => ({ id: p.id, name: p.name }))}
              placeholder="Все проекты"
            />
          </div>
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.account}
              onChange={(val) => setFilters((f) => ({ ...f, account: val }))}
              options={(accounts || []).map((a) => ({ id: a.id, name: `${a.name} (${a.currency})` }))}
              placeholder="Все счета"
            />
          </div>
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.category}
              onChange={(val) => setFilters((f) => ({ ...f, category: val }))}
              options={(categories || []).map((c) => ({ id: c.id, name: c.name }))}
              placeholder="Все статьи"
            />
          </div>
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

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button className="fp-btn-ghost" onClick={handleExport} disabled={exporting}>
            <Download size={15} /> {exporting ? "Экспорт…" : "Экспорт в Excel"}
          </button>
          {canEdit && (selectedAllMatching || selectedTransactionIds.size > 0) && (
            <button
              className="fp-btn-danger"
              onClick={handleBatchDelete}
              disabled={deleting}
              title={selectedAllMatching ? `Удалить все подходящие операции (${matchingCount ?? "?"})` : `Удалить ${selectedTransactionIds.size} операций`}
            >
              <Trash2 size={16} /> {deleting ? "Удаляем…" : selectedAllMatching ? `Удалить все подходящие (${matchingCount ?? "?"})` : `Удалить (${selectedTransactionIds.size})`}
            </button>
          )}
          {canEdit && (
            <button className="fp-btn-primary" onClick={openAdd}>
              <Plus size={16} /> Новая операция
            </button>
          )}
        </div>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 12, justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <label style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
            Строк на странице:
            <select
              value={useAllForDates ? "dates" : String(pageSize)}
              onChange={(e) => {
                if (e.target.value === "dates") {
                  setUseAllForDates(true);
                } else {
                  setUseAllForDates(false);
                  setPageSize(Number(e.target.value));
                }
                setCurrentPage(0);
              }}
              style={{
                marginLeft: 8,
                padding: "4px 8px",
                border: "1px solid var(--line)",
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              <option value="20">20</option>
              <option value="50">50</option>
              <option value="100">100</option>
              {hasDateFilter && <option value="dates">Выбранные даты</option>}
            </select>
          </label>
        </div>
        {selectedAllMatching ? (
          <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
            Выбрано: все подходящие ({matchingCount ?? "?"})
            <button
              type="button"
              onClick={() => {
                setSelectedAllMatching(false);
                setSelectedTransactionIds(new Set());
              }}
              style={{
                marginLeft: 10,
                background: "none",
                border: "none",
                color: "var(--accent)",
                cursor: "pointer",
                textDecoration: "underline",
                fontSize: "13px",
                padding: 0,
              }}
            >
              Снять выбор
            </button>
          </div>
        ) : selectedTransactionIds.size > 0 ? (
          <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
            Выбрано: {selectedTransactionIds.size}
            {matchingCount > selectedTransactionIds.size && !useAllForDates && (
              <button
                type="button"
                onClick={selectAllMatching}
                style={{
                  marginLeft: 10,
                  background: "none",
                  border: "none",
                  color: "var(--accent)",
                  cursor: "pointer",
                  textDecoration: "underline",
                  fontSize: "13px",
                  padding: 0,
                }}
              >
                Выбрать все подходящие ({matchingCount ?? "?"})
              </button>
            )}
          </div>
        ) : null}
      </div>

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (transactions || []).length === 0 ? (
          <div className="fp-empty">Операций не найдено</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {canEdit && (
                  <th style={{ width: 40, textAlign: "center", paddingLeft: 8 }}>
                    <input
                      type="checkbox"
                      checked={selectedAllMatching || (selectedTransactionIds.size === (transactions || []).length && transactions.length > 0)}
                      onChange={toggleSelectAll}
                      title={selectedAllMatching || selectedTransactionIds.size > 0 ? "Отменить выбор всех" : "Выбрать все"}
                      style={{ cursor: "pointer" }}
                    />
                  </th>
                )}
                {showCompanyColumn && <th>Компания</th>}
                <th>Дата</th>
                <th>Счёт</th>
                <th>Статья</th>
                <th>Проект</th>
                <th>Контрагент</th>
                <th>Комментарий</th>
                <th>Источник</th>
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
                const rowRole = roleForCompany(t.company_id);
                const canEditRow =
                  canEditTransactions(rowRole) && (rowRole === "admin" || t.created_by === user.id);
                return (
                  <tr key={t.id}>
                    {canEdit && (
                      <td style={{ width: 40, textAlign: "center", paddingLeft: 8 }}>
                        <input
                          type="checkbox"
                          checked={selectedAllMatching || selectedTransactionIds.has(t.id)}
                          onChange={() => toggleTransactionSelection(t.id)}
                          style={{ cursor: "pointer" }}
                        />
                      </td>
                    )}
                    {showCompanyColumn && (
                      <td>{companies.find((m) => m.company.id === t.company_id)?.company.name || "—"}</td>
                    )}
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
                    <td>{sourceBadge(t.external_ref) || <span className="fp-muted">Вручную</span>}</td>
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
        {(transactions || []).length > 0 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderTop: "1px solid var(--line)" }}>
            <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
              {useAllForDates
                ? `Все ${(transactions || []).length} результатов за выбранный период`
                : `Страница ${currentPage + 1} • ${(transactions || []).length} результатов на странице`}
            </div>
            {!useAllForDates && (
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className="fp-btn-ghost"
                  onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                  disabled={currentPage === 0 || loading}
                >
                  ← Предыдущая
                </button>
                <button
                  className="fp-btn-ghost"
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={(transactions || []).length < pageSize || loading}
                >
                  Следующая →
                </button>
              </div>
            )}
          </div>
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
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
                  {editing ? (
                    <input
                      type="text"
                      disabled
                      value={companies.find((m) => m.company.id === formCompanyId)?.company.name || ""}
                    />
                  ) : (
                    <select
                      value={formCompanyId}
                      onChange={(e) => updateFormCompany(e.target.value)}
                      required
                    >
                      {editableCompanies.map((m) => (
                        <option key={m.company.id} value={m.company.id}>
                          {m.company.name}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              )}
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
                <Combobox
                  value={form.account_id}
                  onChange={(val) => updateField("account_id", val)}
                  options={selectableAccounts.map((a) => ({
                    id: a.id,
                    name: `${a.name} (${a.currency})${a.is_active === false ? " — деактивирован" : ""}`
                  }))}
                  placeholder="Выберите счёт"
                  required
                />
              </label>

              <label>
                Статья
                <Combobox
                  value={form.category_id}
                  onChange={(val) => updateField("category_id", val)}
                  options={filteredCategories.map((c) => ({
                    id: c.id,
                    name: `${c.name}${c.is_active === false ? " — деактивирована" : ""}`
                  }))}
                  placeholder="Выберите статью"
                  required
                />
              </label>
              <label>
                Проект
                <Combobox
                  value={form.project_id}
                  onChange={(val) => updateField("project_id", val)}
                  options={selectableProjects.map((p) => ({
                    id: p.id,
                    name: `${p.name}${p.is_active === false ? " — деактивирован" : ""}`
                  }))}
                  placeholder="— не указан —"
                />
              </label>

              <label>
                Контрагент
                <Combobox
                  value={form.counterparty_id}
                  onChange={(val) => updateField("counterparty_id", val)}
                  options={selectableCounterparties.map((c) => ({
                    id: c.id,
                    name: `${c.name}${c.is_active === false ? " — деактивирован" : ""}`
                  }))}
                  placeholder="— не указан —"
                />
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
