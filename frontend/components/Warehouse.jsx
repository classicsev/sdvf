"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  Plus,
  X,
  Trash2,
  Pencil,
  ArrowRightLeft,
  Package,
  Boxes,
  Settings,
  ClipboardList,
  Ban,
  Send,
  Factory,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  FileText,
  Receipt,
  Building2,
  ChevronDown,
  RefreshCw,
  Upload,
  Check,
  Eye,
} from "lucide-react";
import { Combobox } from "./Combobox";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";
import { canEditWarehouse } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";
import { useTranslation } from "../lib/i18n";

// Значения — фиксированный набор (см. StockDirectionEnum на бэкенде), поэтому
// t(`wh.direction.${direction}`) всегда попадает в словарь.
function directionLabel(t, direction) {
  return t(`wh.direction.${direction}`);
}

function orderStatusLabel(t, status) {
  return t(`wh.orderStatus.${status}`);
}

const SECTIONS = [
  { key: "balances", labelKey: "wh.section.balances", icon: Boxes },
  { key: "movements", labelKey: "wh.section.movements", icon: Package },
  { key: "orders", labelKey: "wh.section.orders", icon: ClipboardList },
  { key: "production", labelKey: "wh.section.production", icon: Factory },
  { key: "catalog", labelKey: "wh.section.catalog", icon: Settings },
  { key: "sync", labelKey: "wh.section.sync", icon: RefreshCw },
];

const ORDER_STATUS_BADGE = {
  draft: "warn",
  reserved: "ok",
  shipped: "ok",
  cancelled: "danger",
};

// ---------------------------------------------------------------------------
// Остатки
// ---------------------------------------------------------------------------

// Калибры вида "40/60", "300/500", "500+" должны сортироваться по числу, а не по
// алфавиту строки (иначе "100/150" встаёт перед "40/60") — то же правило, что и в
// сортировке по умолчанию на бэкенде (см. warehouse.py::_variant_sort_key).
function naturalKey(value) {
  const match = /^(\d+)/.exec(String(value ?? ""));
  return match ? [0, Number(match[1]), value] : [1, 0, value];
}

function compareNatural(a, b) {
  const ka = naturalKey(a);
  const kb = naturalKey(b);
  if (ka[0] !== kb[0]) return ka[0] - kb[0];
  if (ka[1] !== kb[1]) return ka[1] - kb[1];
  return String(ka[2]).localeCompare(String(kb[2]), "ru");
}

const BALANCE_COLUMNS = [
  { key: "warehouse_name", labelKey: "wh.col.warehouse", type: "text" },
  { key: "product_name", labelKey: "wh.col.product", type: "text" },
  { key: "variant_name", labelKey: "wh.col.variant", type: "natural" },
  { key: "quantity", labelKey: "wh.col.balance", type: "number", align: "right" },
  { key: "reserved", labelKey: "wh.col.reserved", type: "number", align: "right" },
  { key: "available", labelKey: "wh.col.available", type: "number", align: "right" },
];

// Универсальный выпадающий мультивыбор с чекбоксами и опцией "выбрать всё"
// (пустой selectedIds = "всё"). Стиль/разметка — как в фильтре компаний в
// Reference.jsx (fp-combobox-popup/fp-checkbox-row), для визуальной
// консистентности с остальными списками справочников.
function MultiSelectFilter({ icon: Icon, allLabel, countLabel, options, selectedIds, onChange }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  function toggle(id) {
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);
  }

  const buttonText =
    selectedIds.length === 0
      ? allLabel
      : selectedIds.length === 1
      ? options.find((o) => o.id === selectedIds[0])?.label || "1"
      : `${countLabel}: ${selectedIds.length}`;

  return (
    <div style={{ position: "relative" }} ref={ref}>
      <button type="button" className="fp-btn-tiny" onClick={() => setOpen((v) => !v)}>
        {Icon && <Icon size={13} />}
        {buttonText}
        <ChevronDown size={13} className={`fp-combobox-chevron ${open ? "rotated" : ""}`} />
      </button>
      {open && (
        <div className="fp-combobox-popup" style={{ width: 260, padding: "6px 0", maxHeight: 320, overflowY: "auto" }}>
          <label className="fp-checkbox-row" style={{ fontWeight: selectedIds.length === 0 ? 600 : 400 }}>
            <input type="checkbox" checked={selectedIds.length === 0} onChange={() => onChange([])} />
            {allLabel}
          </label>
          <div style={{ borderTop: "1px solid var(--line)", margin: "4px 0" }} />
          {options.map((o) => (
            <label key={o.id} className="fp-checkbox-row">
              <input type="checkbox" checked={selectedIds.includes(o.id)} onChange={() => toggle(o.id)} />
              {o.label}
            </label>
          ))}
          {options.length === 0 && (
            <div className="fp-note" style={{ padding: "4px 12px" }}>
              {t("wh.noData")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BalancesPanel({ token, companies, multiCompany }) {
  const { t } = useTranslation();
  const [hideZero, setHideZero] = useState(false);
  // Остатки — единственная вкладка склада с полностью независимым набором
  // фильтров (компании/склады/товары, каждый — мультивыбор с "выбрать всё"),
  // не завязанным на общий одиночный переключатель компании в шапке раздела
  // "Склад" (тот продолжает управлять только Движениями/Заказами/Производством/
  // Справочниками — там он определяет контекст создаваемой записи).
  const [companyFilterIds, setCompanyFilterIds] = useState([]);
  const [warehouseFilterIds, setWarehouseFilterIds] = useState([]);
  const [productFilterIds, setProductFilterIds] = useState([]);
  const {
    data: balances,
    loading,
    error,
  } = useResource(() => api.listWhBalances(token, { include_empty: true }), [token]);
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  // Опции складов/товаров считаются из уже загруженных остатков (include_empty
  // гарантирует полный список активных складов/товаров, даже с нулевым
  // остатком), а не отдельным запросом — так набор фильтров всегда точно
  // соответствует тому, что реально можно отфильтровать на этой вкладке.
  const warehouseOptions = useMemo(() => {
    const seen = new Map();
    for (const b of balances || []) {
      if (companyFilterIds.length === 0 || companyFilterIds.includes(b.company_id)) {
        if (!seen.has(b.warehouse_id)) seen.set(b.warehouse_id, b.warehouse_name);
      }
    }
    return [...seen.entries()]
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label, "ru"));
  }, [balances, companyFilterIds]);

  const productOptions = useMemo(() => {
    const seen = new Map();
    for (const b of balances || []) {
      if (companyFilterIds.length === 0 || companyFilterIds.includes(b.company_id)) {
        if (!seen.has(b.product_id)) seen.set(b.product_id, b.product_name);
      }
    }
    return [...seen.entries()]
      .map(([id, label]) => ({ id, label }))
      .sort((a, b) => a.label.localeCompare(b.label, "ru"));
  }, [balances, companyFilterIds]);

  function toggleSort(col) {
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir("asc");
    }
  }

  const sortedBalances = useMemo(() => {
    let rows = [...(balances || [])];
    if (hideZero) rows = rows.filter((b) => b.quantity !== 0 || b.reserved !== 0);
    if (companyFilterIds.length) rows = rows.filter((b) => companyFilterIds.includes(b.company_id));
    if (warehouseFilterIds.length) rows = rows.filter((b) => warehouseFilterIds.includes(b.warehouse_id));
    if (productFilterIds.length) rows = rows.filter((b) => productFilterIds.includes(b.product_id));
    if (!sortKey) return rows; // порядок по умолчанию — уже отсортирован бэкендом
    const col = BALANCE_COLUMNS.find((c) => c.key === sortKey);
    rows.sort((a, b) => {
      let cmp;
      if (col.type === "number") cmp = (a[sortKey] || 0) - (b[sortKey] || 0);
      else if (col.type === "natural") cmp = compareNatural(a[sortKey], b[sortKey]);
      else cmp = String(a[sortKey] ?? "").localeCompare(String(b[sortKey] ?? ""), "ru");
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [balances, sortKey, sortDir, hideZero, companyFilterIds, warehouseFilterIds, productFilterIds]);

  const showCompanyColumn = multiCompany;

  return (
    <div className="fp-panel fp-table-panel">
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", padding: "12px 16px 0", fontSize: 13 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} />
          {t("wh.hideZero")}
        </label>
        {multiCompany && (
          <MultiSelectFilter
            icon={Building2}
            allLabel={t("dashboard.allCompanies")}
            countLabel={t("wh.companiesCount")}
            options={companies.map((m) => ({ id: m.company.id, label: m.company.name }))}
            selectedIds={companyFilterIds}
            onChange={(ids) => {
              setCompanyFilterIds(ids);
              // Смена набора компаний может исключить ранее выбранные склады/
              // товары из доступных опций — убираем те, что больше не видны.
              setWarehouseFilterIds((prev) =>
                prev.filter((id) => ids.length === 0 || warehouseOptions.some((o) => o.id === id))
              );
            }}
          />
        )}
        <MultiSelectFilter
          icon={Boxes}
          allLabel={t("wh.allWarehouses")}
          countLabel={t("wh.warehousesCount")}
          options={warehouseOptions}
          selectedIds={warehouseFilterIds}
          onChange={setWarehouseFilterIds}
        />
        <MultiSelectFilter
          icon={Package}
          allLabel={t("wh.allProducts")}
          countLabel={t("wh.productsCount")}
          options={productOptions}
          selectedIds={productFilterIds}
          onChange={setProductFilterIds}
        />
      </div>
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <table className="fp-table">
          <thead>
            <tr>
              {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
              {BALANCE_COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={col.align === "right" ? "right" : ""}
                  onClick={() => toggleSort(col)}
                  style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
                  title={t("wh.sortTitle")}
                >
                  {t(col.labelKey)}{" "}
                  {sortKey === col.key ? (
                    sortDir === "asc" ? (
                      <ArrowUp size={11} style={{ verticalAlign: "middle" }} />
                    ) : (
                      <ArrowDown size={11} style={{ verticalAlign: "middle" }} />
                    )
                  ) : (
                    <ArrowUpDown size={11} style={{ verticalAlign: "middle", opacity: 0.35 }} />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedBalances.map((b) => (
              <tr key={`${b.warehouse_id}-${b.product_variant_id}`}>
                {showCompanyColumn && (
                  <td>{companies.find((m) => m.company.id === b.company_id)?.company.name || "—"}</td>
                )}
                <td>{b.warehouse_name}</td>
                <td>{b.product_name}</td>
                <td className="fp-muted">{b.variant_name}</td>
                <td className="right">
                  {b.quantity} {b.unit}
                </td>
                <td className="right fp-muted">{b.reserved > 0 ? `${b.reserved} ${b.unit}` : "—"}</td>
                <td className="right">
                  {b.available} {b.unit}
                </td>
              </tr>
            ))}
            {sortedBalances.length === 0 && (
              <tr>
                <td colSpan={showCompanyColumn ? 7 : 6} className="fp-empty">
                  {t("wh.noBalances")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {error && <div className="fp-error-banner">{error}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Движения
// ---------------------------------------------------------------------------

const MOVEMENT_FORM_EMPTY = {
  date: new Date().toISOString().slice(0, 10),
  warehouse_id: "",
  product_variant_id: "",
  direction: "in",
  quantity: "",
  note: "",
  executor_id: "",
  payroll_rate: "",
};

const TRANSFER_FORM_EMPTY = {
  date: new Date().toISOString().slice(0, 10),
  product_variant_id: "",
  from_warehouse_id: "",
  to_warehouse_id: "",
  quantity: "",
  note: "",
};

function MovementsPanel({
  token,
  canEdit,
  warehouses,
  variants,
  variantsById,
  activeVariants,
  warehousesById,
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
  const { t } = useTranslation();
  const { data: movements, loading, error, reload } = useResource(
    () => api.listWhMovements(token, { company_id: companyId || undefined }),
    [token, companyId]
  );
  const { data: employees } = useResource(() => api.listWhEmployees(token), [token]);

  const [modalOpen, setModalOpen] = useState(null); // "movement" | "transfer" | null
  const [form, setForm] = useState(MOVEMENT_FORM_EMPTY);
  const [transferForm, setTransferForm] = useState(TRANSFER_FORM_EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  // Вариант товара должен принадлежать той же компании, что и выбранный склад.
  const movementVariants = (activeVariants || []).filter(
    (v) => !multiCompany || !form.warehouse_id || v.company_id === warehousesById[form.warehouse_id]?.company_id
  );
  const transferToWarehouses = (warehouses || []).filter(
    (w) =>
      !multiCompany ||
      !transferForm.from_warehouse_id ||
      w.company_id === warehousesById[transferForm.from_warehouse_id]?.company_id
  );
  const transferVariants = (activeVariants || []).filter(
    (v) =>
      !multiCompany ||
      !transferForm.from_warehouse_id ||
      v.company_id === warehousesById[transferForm.from_warehouse_id]?.company_id
  );

  function openMovement(direction) {
    setForm({ ...MOVEMENT_FORM_EMPTY, direction });
    setFormError("");
    setModalOpen("movement");
  }

  function openTransfer() {
    setTransferForm(TRANSFER_FORM_EMPTY);
    setFormError("");
    setModalOpen("transfer");
  }

  async function handleSubmitMovement(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      await api.createWhMovement(token, {
        date: form.date,
        warehouse_id: form.warehouse_id,
        product_variant_id: form.product_variant_id,
        direction: form.direction,
        quantity: Number(form.quantity),
        note: form.note || null,
        executor_id: form.direction === "in" && form.executor_id ? form.executor_id : null,
        payroll_rate: form.direction === "in" && form.payroll_rate ? Number(form.payroll_rate) : null,
      });
      setModalOpen(null);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmitTransfer(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      await api.transferWhStock(token, {
        date: transferForm.date,
        product_variant_id: transferForm.product_variant_id,
        from_warehouse_id: transferForm.from_warehouse_id,
        to_warehouse_id: transferForm.to_warehouse_id,
        quantity: Number(transferForm.quantity),
        note: transferForm.note || null,
      });
      setModalOpen(null);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(movement) {
    if (!window.confirm(t("wh.deleteMovementConfirm"))) return;
    try {
      await api.deleteWhMovement(token, movement.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <>
      <div className="fp-tabs-row">
        <div />
        {canEdit && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="fp-btn-tiny" onClick={() => openMovement("in")}>
              <Plus size={13} /> {t("wh.direction.in")}
            </button>
            <button className="fp-btn-tiny" onClick={() => openMovement("out")}>
              <Plus size={13} /> {t("wh.direction.out")}
            </button>
            <button className="fp-btn-tiny" onClick={() => openMovement("adjustment")}>
              <Pencil size={13} /> {t("wh.direction.adjustment")}
            </button>
            <button className="fp-btn-tiny" onClick={openTransfer}>
              <ArrowRightLeft size={13} /> {t("wh.transfer")}
            </button>
          </div>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                <th>{t("payroll.col.date")}</th>
                <th>{t("wh.col.warehouse")}</th>
                <th>{t("wh.col.productVariant")}</th>
                <th>{t("cp.col.type")}</th>
                <th className="right">{t("wh.col.quantity")}</th>
                <th>{t("wh.col.note")}</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(movements || []).map((m) => {
                const variant = variantsById[m.product_variant_id];
                const canEditRow = canEditWarehouse(roleForCompany(m.company_id));
                return (
                  <tr key={m.id}>
                    {showCompanyColumn && (
                      <td>{companies.find((c) => c.company.id === m.company_id)?.company.name || "—"}</td>
                    )}
                    <td>{fmtDate(m.date)}</td>
                    <td>{warehousesById[m.warehouse_id]?.name || "—"}</td>
                    <td>
                      {variant ? `${variant.productName} · ${variant.name}` : "—"}
                    </td>
                    <td className="fp-muted">{directionLabel(t, m.direction)}</td>
                    <td className="right">{m.quantity}</td>
                    <td className="fp-muted">{m.note || "—"}</td>
                    <td className="fp-table-actions-col">
                      {canEditRow && (
                        <button className="fp-icon-btn" onClick={() => handleDelete(m)}>
                          <Trash2 size={14} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {(movements || []).length === 0 && (
                <tr>
                  <td colSpan={showCompanyColumn ? 8 : 7} className="fp-empty">
                    {t("wh.noMovements")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        {error && <div className="fp-error-banner">{error}</div>}
      </div>

      {modalOpen === "movement" && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{directionLabel(t, form.direction)}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitMovement}>
              <label>
                {t("payroll.col.date")}
                <input
                  type="date"
                  required
                  value={form.date}
                  onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.col.warehouse")}
                <select
                  required
                  value={form.warehouse_id}
                  onChange={(e) => setForm((p) => ({ ...p, warehouse_id: e.target.value, product_variant_id: "" }))}
                >
                  <option value="" disabled>
                    {t("wh.selectWarehouse")}
                  </option>
                  {(warehouses || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="fp-span-2">
                {t("wh.col.productVariant")}
                <Combobox
                  value={form.product_variant_id}
                  onChange={(val) => setForm((p) => ({ ...p, product_variant_id: val }))}
                  options={movementVariants.map((v) => ({ id: v.id, name: `${v.productName} · ${v.name}` }))}
                  placeholder={t("wh.selectVariant")}
                  required
                />
              </label>
              <label>
                {t("wh.col.quantity")}{form.direction === "adjustment" ? t("wh.quantityCanBeNegative") : ""}
                <input
                  required
                  type="number"
                  step="0.001"
                  value={form.quantity}
                  onChange={(e) => setForm((p) => ({ ...p, quantity: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.col.note")}
                <input value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} />
              </label>

              {form.direction === "in" && (
                <>
                  <label>
                    {t("wh.executor")}
                    <select
                      value={form.executor_id}
                      onChange={(e) => setForm((p) => ({ ...p, executor_id: e.target.value }))}
                    >
                      <option value="">{t("tx.form.notSpecified")}</option>
                      {(employees || []).map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.full_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("wh.ratePerUnit")}
                    <input
                      type="number"
                      step="0.01"
                      disabled={!form.executor_id}
                      value={form.payroll_rate}
                      onChange={(e) => setForm((p) => ({ ...p, payroll_rate: e.target.value }))}
                    />
                  </label>
                  <div className="fp-note fp-span-2">{t("wh.payrollAutoNote")}</div>
                </>
              )}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(null)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {modalOpen === "transfer" && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("wh.transferBetweenWarehouses")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitTransfer}>
              <label>
                {t("payroll.col.date")}
                <input
                  type="date"
                  required
                  value={transferForm.date}
                  onChange={(e) => setTransferForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.col.productVariant")}
                <Combobox
                  value={transferForm.product_variant_id}
                  onChange={(val) => setTransferForm((p) => ({ ...p, product_variant_id: val }))}
                  options={transferVariants.map((v) => ({ id: v.id, name: `${v.productName} · ${v.name}` }))}
                  placeholder={t("wh.selectVariant")}
                  required
                />
              </label>
              <label>
                {t("wh.fromWarehouse")}
                <select
                  required
                  value={transferForm.from_warehouse_id}
                  onChange={(e) =>
                    setTransferForm((p) => ({
                      ...p,
                      from_warehouse_id: e.target.value,
                      to_warehouse_id: "",
                      product_variant_id: "",
                    }))
                  }
                >
                  <option value="" disabled>
                    {t("wh.selectWarehouse")}
                  </option>
                  {(warehouses || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("wh.toWarehouse")}
                <select
                  required
                  value={transferForm.to_warehouse_id}
                  onChange={(e) => setTransferForm((p) => ({ ...p, to_warehouse_id: e.target.value }))}
                >
                  <option value="" disabled>
                    {t("wh.selectWarehouse")}
                  </option>
                  {transferToWarehouses
                    .filter((w) => w.id !== transferForm.from_warehouse_id)
                    .map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                {t("wh.col.quantity")}
                <input
                  required
                  type="number"
                  step="0.001"
                  value={transferForm.quantity}
                  onChange={(e) => setTransferForm((p) => ({ ...p, quantity: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.col.note")}
                <input
                  value={transferForm.note}
                  onChange={(e) => setTransferForm((p) => ({ ...p, note: e.target.value }))}
                />
              </label>

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(null)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("wh.moveBtn")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Заказы
// ---------------------------------------------------------------------------

const ORDER_FORM_EMPTY = {
  counterparty_id: "",
  warehouse_id: "",
  requested_date: "",
  courier: "",
  note: "",
  incoterms: "",
  incoterms_place: "",
  payment_terms: "",
  lines: [{ product_variant_id: "", quantity: "" }],
};

// "Отгрузки календарь" в реальной таблице пользователя — план по дням
// (Пн/Вт/.../Вс) с именем курьера в каждой строке. Заказы группируем по
// requested_date тем же способом, без даты — отдельным блоком сверху.
function groupOrdersByDate(orders) {
  const withDate = [];
  const withoutDate = [];
  (orders || []).forEach((o) => (o.requested_date ? withDate.push(o) : withoutDate.push(o)));
  withDate.sort((a, b) => a.requested_date.localeCompare(b.requested_date));
  const groups = [];
  let current = null;
  for (const o of withDate) {
    if (!current || current.date !== o.requested_date) {
      current = { date: o.requested_date, orders: [] };
      groups.push(current);
    }
    current.orders.push(o);
  }
  if (withoutDate.length) groups.unshift({ date: null, orders: withoutDate });
  return groups;
}

function weekdayLabel(dateStr) {
  const d = new Date(dateStr);
  const label = d.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function OrdersPanel({
  token,
  canEdit,
  warehouses,
  variants,
  variantsById,
  activeVariants,
  warehousesById,
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
  const { t } = useTranslation();
  const { data: orders, loading, error, reload } = useResource(
    () => api.listOrders(token, { company_id: companyId || undefined }),
    [token, companyId]
  );
  const { data: counterparties, reload: reloadCounterparties } = useResource(() => api.listCounterparties(token), [token]);
  const counterpartiesById = useMemo(
    () => Object.fromEntries((counterparties || []).map((c) => [c.id, c])),
    [counterparties]
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [editingOrder, setEditingOrder] = useState(null);
  const [form, setForm] = useState(ORDER_FORM_EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const orderWarehouseCompany = warehousesById[form.warehouse_id]?.company_id;
  const orderCounterparties = (counterparties || []).filter(
    (c) => !multiCompany || !form.warehouse_id || c.company_id === orderWarehouseCompany
  );
  const orderVariants = (activeVariants || []).filter(
    (v) => !multiCompany || !form.warehouse_id || v.company_id === orderWarehouseCompany
  );
  const orderGroups = useMemo(() => groupOrdersByDate(orders), [orders]);

  async function handleCreateCounterparty(name) {
    const created = await api.createCounterparty(token, { name }, orderWarehouseCompany || undefined);
    reloadCounterparties();
    return created;
  }

  // Генерация Счёт/УПД в СДВФ — Склад не хранит цену позиций (только
  // количество), поэтому цена запрашивается у пользователя в момент генерации.
  const [docModal, setDocModal] = useState(null); // { order, type: "invoice" | "utd" }
  const [docPrices, setDocPrices] = useState({});
  const [docNds, setDocNds] = useState(20);
  const [docNdsType, setDocNdsType] = useState("onTop");
  const [docError, setDocError] = useState("");
  const [docSaving, setDocSaving] = useState(false);

  function openDocModal(order, type) {
    setDocModal({ order, type });
    setDocPrices(Object.fromEntries(order.lines.map((l) => [l.id, ""])));
    setDocNds(20);
    setDocNdsType("onTop");
    setDocError("");
  }

  async function handleDocSubmit(e) {
    e.preventDefault();
    setDocSaving(true);
    setDocError("");
    try {
      const lines = docModal.order.lines.map((l) => ({
        order_line_id: l.id,
        price: Number(docPrices[l.id]),
      }));
      const payload = { nds: Number(docNds), nds_type: docNdsType, lines };
      if (docModal.type === "invoice") {
        await api.generateInvoice(token, docModal.order.id, payload);
      } else {
        await api.generateUtd(token, docModal.order.id, payload);
      }
      setDocModal(null);
      reload();
    } catch (err) {
      setDocError(err.message);
    } finally {
      setDocSaving(false);
    }
  }

  function openAdd() {
    setEditingOrder(null);
    setForm(ORDER_FORM_EMPTY);
    setFormError("");
    setModalOpen(true);
  }

  function openEdit(order) {
    setEditingOrder(order);
    setForm({
      counterparty_id: order.counterparty_id,
      warehouse_id: order.warehouse_id,
      requested_date: order.requested_date || "",
      courier: order.courier || "",
      note: order.note || "",
      incoterms: order.incoterms || "",
      incoterms_place: order.incoterms_place || "",
      payment_terms: order.payment_terms || "",
      lines: order.lines.map((l) => ({ product_variant_id: l.product_variant_id, quantity: String(l.quantity) })),
    });
    setFormError("");
    setModalOpen(true);
  }

  function addLine() {
    setForm((p) => ({ ...p, lines: [...p.lines, { product_variant_id: "", quantity: "" }] }));
  }

  function removeLine(idx) {
    setForm((p) => ({ ...p, lines: p.lines.filter((_, i) => i !== idx) }));
  }

  function updateLine(idx, patch) {
    setForm((p) => ({ ...p, lines: p.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    const payload = {
      counterparty_id: form.counterparty_id,
      warehouse_id: form.warehouse_id,
      requested_date: form.requested_date || null,
      courier: form.courier || null,
      note: form.note || null,
      incoterms: form.incoterms || null,
      incoterms_place: form.incoterms_place || null,
      payment_terms: form.payment_terms || null,
      lines: form.lines.map((l) => ({ product_variant_id: l.product_variant_id, quantity: Number(l.quantity) })),
    };
    try {
      if (editingOrder) {
        await api.updateOrder(token, editingOrder.id, payload);
      } else {
        await api.createOrder(token, payload);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleReserve(order) {
    try {
      await api.reserveOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleUnreserve(order) {
    try {
      await api.unreserveOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleShip(order) {
    if (!window.confirm(t("wh.shipConfirm"))) return;
    try {
      await api.shipOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleCancel(order) {
    if (!window.confirm(t("wh.cancelConfirm"))) return;
    try {
      await api.cancelOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleDelete(order) {
    if (!window.confirm(t("wh.deleteDraftConfirm"))) return;
    try {
      await api.deleteOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <>
      <div className="fp-tabs-row">
        <div />
        {canEdit && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> {t("wh.newOrder")}
          </button>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                <th>{t("wh.col.client")}</th>
                <th>{t("wh.col.warehouse")}</th>
                <th>{t("wh.col.composition")}</th>
                <th>{t("wh.col.courier")}</th>
                <th className="center">{t("reference.status")}</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {orderGroups.map((group) => (
                <Fragment key={group.date || "no-date"}>
                  <tr className="fp-table-group-row">
                    <td colSpan={(showCompanyColumn ? 1 : 0) + 6} className="fp-table-group-label">
                      {group.date ? weekdayLabel(group.date) : t("wh.noDateGroup")}
                    </td>
                  </tr>
                  {group.orders.map((o) => {
                const canEditRow = canEditWarehouse(roleForCompany(o.company_id));
                return (
                <tr key={o.id}>
                  {showCompanyColumn && (
                    <td>{companies.find((c) => c.company.id === o.company_id)?.company.name || "—"}</td>
                  )}
                  <td>{counterpartiesById[o.counterparty_id]?.name || "—"}</td>
                  <td className="fp-muted">{warehousesById[o.warehouse_id]?.name || "—"}</td>
                  <td className="fp-muted fp-table-comment-col" title={o.lines
                      .map((l) => {
                        const v = variantsById[l.product_variant_id];
                        return v ? `${v.productName} ${v.name} × ${l.quantity}` : `${l.quantity}`;
                      })
                      .join(", ")}>
                    {o.lines
                      .map((l) => {
                        const v = variantsById[l.product_variant_id];
                        return v ? `${v.productName} ${v.name} × ${l.quantity}` : `${l.quantity}`;
                      })
                      .join(", ")}
                  </td>
                  <td className="fp-muted">{o.courier || "—"}</td>
                  <td className="center">
                    <span className={`fp-status-badge ${ORDER_STATUS_BADGE[o.status] || ""}`}>
                      {orderStatusLabel(t, o.status)}
                    </span>
                  </td>
                  {canEditRow && (
                    <td className="fp-table-actions-col">
                      <span className="fp-row-actions">
                        {(o.status === "draft" || o.status === "reserved") && (
                          <button className="fp-icon-btn" onClick={() => openEdit(o)} title={t("wh.editTooltip")}>
                            <Pencil size={14} />
                          </button>
                        )}
                        {o.status === "draft" && (
                          <button className="fp-btn-tiny" onClick={() => handleReserve(o)}>
                            {t("wh.reserveBtn")}
                          </button>
                        )}
                        {o.status === "reserved" && (
                          <button className="fp-btn-tiny" onClick={() => handleUnreserve(o)} title={t("wh.unreserveTooltip")}>
                            {t("wh.unreserveBtn")}
                          </button>
                        )}
                        {(o.status === "draft" || o.status === "reserved") && (
                          <button className="fp-icon-btn" onClick={() => handleShip(o)} title={t("wh.shipTooltip")}>
                            <Send size={14} />
                          </button>
                        )}
                        {o.status === "draft" && (
                          <button className="fp-icon-btn" onClick={() => handleDelete(o)} title={t("common.delete")}>
                            <Trash2 size={14} />
                          </button>
                        )}
                        {(o.status === "draft" || o.status === "reserved") && (
                          <button className="fp-icon-btn" onClick={() => handleCancel(o)} title={t("wh.cancelTooltip")}>
                            <Ban size={14} />
                          </button>
                        )}
                        {o.sdvf_invoice_ref ? (
                          <button
                            className="fp-icon-btn"
                            onClick={() => api.openSdvfPdf(token, o.id, "invoice")}
                            title={t("wh.openInvoicePdf")}
                          >
                            <FileText size={14} />
                          </button>
                        ) : (
                          <button className="fp-icon-btn" onClick={() => openDocModal(o, "invoice")} title={t("wh.generateInvoiceTooltip")}>
                            <FileText size={14} />
                          </button>
                        )}
                        {o.sdvf_utd_ref ? (
                          <button
                            className="fp-icon-btn"
                            onClick={() => api.openSdvfPdf(token, o.id, "utd")}
                            title={t("wh.openUtdPdf")}
                          >
                            <Receipt size={14} />
                          </button>
                        ) : (
                          <button className="fp-icon-btn" onClick={() => openDocModal(o, "utd")} title={t("wh.generateUtdTooltip")}>
                            <Receipt size={14} />
                          </button>
                        )}
                      </span>
                    </td>
                  )}
                </tr>
                );
                  })}
                </Fragment>
              ))}
              {(orders || []).length === 0 && (
                <tr>
                  <td colSpan={(showCompanyColumn ? 1 : 0) + 6} className="fp-empty">
                    {t("wh.noOrders")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        {error && <div className="fp-error-banner">{error}</div>}
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingOrder ? t("wh.editOrder") : t("wh.newOrder")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label>
                {t("wh.col.warehouse")}
                <select
                  required
                  value={form.warehouse_id}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      warehouse_id: e.target.value,
                      counterparty_id: "",
                      lines: [{ product_variant_id: "", quantity: "" }],
                    }))
                  }
                >
                  <option value="" disabled>
                    {t("wh.selectWarehouse")}
                  </option>
                  {(warehouses || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("wh.col.client")}
                <Combobox
                  value={form.counterparty_id}
                  onChange={(val) => setForm((p) => ({ ...p, counterparty_id: val }))}
                  options={orderCounterparties.map((c) => ({ id: c.id, name: c.name }))}
                  placeholder={t("wh.selectClient")}
                  required
                  onCreateNew={handleCreateCounterparty}
                />
              </label>
              <label>
                {t("wh.shipDateOptional")}
                <input
                  type="date"
                  value={form.requested_date}
                  onChange={(e) => setForm((p) => ({ ...p, requested_date: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.col.courier")}
                <input value={form.courier} onChange={(e) => setForm((p) => ({ ...p, courier: e.target.value }))} />
              </label>
              <label>
                {t("wh.col.note")}
                <input value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} />
              </label>

              <div className="fp-span-2" style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>{t("wh.tradeTermsHeading")}</div>
                <div className="fp-form-grid" style={{ padding: 0 }}>
                  <label>
                    {t("wh.incoterms")}
                    <input value={form.incoterms} onChange={(e) => setForm((p) => ({ ...p, incoterms: e.target.value }))} />
                  </label>
                  <label>
                    {t("wh.incotermsPlace")}
                    <input
                      value={form.incoterms_place}
                      placeholder={t("wh.incotermsPlacePlaceholder")}
                      onChange={(e) => setForm((p) => ({ ...p, incoterms_place: e.target.value }))}
                    />
                  </label>
                  <label className="fp-span-2">
                    {t("wh.paymentTerms")}
                    <input
                      value={form.payment_terms}
                      placeholder={t("wh.paymentTermsPlaceholder")}
                      onChange={(e) => setForm((p) => ({ ...p, payment_terms: e.target.value }))}
                    />
                  </label>
                </div>
              </div>

              <div className="fp-span-2">
                <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>{t("wh.orderComposition")}</div>
                {form.lines.map((line, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 2 }}>
                      {idx === 0 && t("wh.col.productVariant")}
                      <Combobox
                        value={line.product_variant_id}
                        onChange={(val) => updateLine(idx, { product_variant_id: val })}
                        options={orderVariants.map((v) => ({ id: v.id, name: `${v.productName} · ${v.name}` }))}
                        placeholder={t("wh.selectVariant")}
                        required
                      />
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && t("wh.col.quantity")}
                      <input
                        required
                        type="number"
                        step="0.001"
                        value={line.quantity}
                        onChange={(e) => updateLine(idx, { quantity: e.target.value })}
                      />
                    </label>
                    {form.lines.length > 1 && (
                      <button
                        type="button"
                        className="fp-icon-btn"
                        style={{ marginBottom: 8 }}
                        onClick={() => removeLine(idx)}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="fp-btn-tiny" onClick={addLine}>
                  <Plus size={13} /> {t("wh.addLine")}
                </button>
              </div>

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : editingOrder ? t("common.save") : t("modules.create")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {docModal && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setDocModal(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{docModal.type === "invoice" ? t("wh.generateInvoiceTooltip") : t("wh.generateUtdTooltip")}</h3>
              <button className="fp-icon-btn" onClick={() => setDocModal(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleDocSubmit}>
              <div className="fp-span-2" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                {t("wh.noPriceStoredNote")}
              </div>

              <div className="fp-span-2">
                {docModal.order.lines.map((line) => {
                  const v = variantsById[line.product_variant_id];
                  return (
                    <div key={line.id} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                      <label style={{ flex: 2 }}>
                        {v ? `${v.productName} · ${v.name}` : "—"}{t("wh.qtyLabel", { qty: line.quantity })}
                        <input
                          required
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder={t("wh.pricePerUnit")}
                          value={docPrices[line.id] ?? ""}
                          onChange={(e) => setDocPrices((p) => ({ ...p, [line.id]: e.target.value }))}
                        />
                      </label>
                    </div>
                  );
                })}
              </div>

              <label>
                {t("wh.vat")}
                <select value={docNds} onChange={(e) => setDocNds(e.target.value)}>
                  <option value="-1">{t("wh.vatNone")}</option>
                  <option value="0">0%</option>
                  <option value="10">10%</option>
                  <option value="20">20%</option>
                  <option value="22">22%</option>
                </select>
              </label>
              <label>
                {t("wh.vatType")}
                <select value={docNdsType} onChange={(e) => setDocNdsType(e.target.value)}>
                  <option value="onTop">{t("wh.vatOnTop")}</option>
                  <option value="included">{t("wh.vatIncluded")}</option>
                </select>
              </label>

              {docError && <div className="fp-form-error fp-span-2">{docError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setDocModal(null)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={docSaving}>
                  {docSaving ? t("wh.generating") : t("wh.generate")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Производство
// ---------------------------------------------------------------------------

const RECIPE_FORM_EMPTY = {
  name: "",
  output_variant_id: "",
  inputs: [{ input_variant_id: "", qty_per_unit: "" }],
};

const RUN_FORM_EMPTY = {
  recipe_id: "",
  warehouse_id: "",
  date: new Date().toISOString().slice(0, 10),
  output_qty: "",
  note: "",
};

function ProductionPanel({
  token,
  canEdit,
  warehouses,
  warehousesById,
  variants,
  variantsById,
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("recipes");
  const { data: recipes, loading: recipesLoading, error: recipesError, reload: reloadRecipes } = useResource(
    () => api.listRecipes(token, { company_id: companyId || undefined }),
    [token, companyId]
  );
  const { data: runs, loading: runsLoading, error: runsError, reload: reloadRuns } = useResource(
    () => api.listProductionRuns(token, { company_id: companyId || undefined }),
    [token, companyId]
  );
  const recipesById = useMemo(() => Object.fromEntries((recipes || []).map((r) => [r.id, r])), [recipes]);
  const editableCompanies = companies.filter((m) => canEditWarehouse(m.role));

  const [recipeModalOpen, setRecipeModalOpen] = useState(false);
  const [editingRecipeId, setEditingRecipeId] = useState(null);
  const [recipeForm, setRecipeForm] = useState(RECIPE_FORM_EMPTY);
  const [recipeFormCompanyId, setRecipeFormCompanyId] = useState("");
  const [recipeError, setRecipeError] = useState("");
  const [savingRecipe, setSavingRecipe] = useState(false);

  const recipeVariants = (variants || []).filter(
    (v) => !multiCompany || !recipeFormCompanyId || v.company_id === recipeFormCompanyId
  );

  const [runModalOpen, setRunModalOpen] = useState(false);
  const [runForm, setRunForm] = useState(RUN_FORM_EMPTY);
  const [runError, setRunError] = useState("");
  const [savingRun, setSavingRun] = useState(false);

  const runWarehouses = (warehouses || []).filter(
    (w) =>
      !multiCompany || !runForm.recipe_id || w.company_id === recipesById[runForm.recipe_id]?.company_id
  );

  function openAddRecipe() {
    setEditingRecipeId(null);
    setRecipeForm(RECIPE_FORM_EMPTY);
    const preselected = editableCompanies.find((m) => m.company.id === companyId) || editableCompanies[0];
    setRecipeFormCompanyId(preselected?.company.id || "");
    setRecipeError("");
    setRecipeModalOpen(true);
  }

  function openEditRecipe(recipe) {
    setEditingRecipeId(recipe.id);
    setRecipeForm({
      name: recipe.name,
      output_variant_id: recipe.output_variant_id,
      inputs: recipe.inputs.map((i) => ({ input_variant_id: i.input_variant_id, qty_per_unit: i.qty_per_unit })),
    });
    setRecipeFormCompanyId(recipe.company_id || "");
    setRecipeError("");
    setRecipeModalOpen(true);
  }

  function addRecipeInput() {
    setRecipeForm((p) => ({ ...p, inputs: [...p.inputs, { input_variant_id: "", qty_per_unit: "" }] }));
  }

  function removeRecipeInput(idx) {
    setRecipeForm((p) => ({ ...p, inputs: p.inputs.filter((_, i) => i !== idx) }));
  }

  function updateRecipeInput(idx, patch) {
    setRecipeForm((p) => ({ ...p, inputs: p.inputs.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  }

  async function handleSubmitRecipe(e) {
    e.preventDefault();
    setSavingRecipe(true);
    setRecipeError("");
    try {
      const payload = {
        name: recipeForm.name,
        output_variant_id: recipeForm.output_variant_id,
        inputs: recipeForm.inputs.map((i) => ({
          input_variant_id: i.input_variant_id,
          qty_per_unit: Number(i.qty_per_unit),
        })),
      };
      if (editingRecipeId) {
        await api.updateRecipe(token, editingRecipeId, payload);
      } else {
        await api.createRecipe(token, payload, recipeFormCompanyId || undefined);
      }
      setRecipeModalOpen(false);
      reloadRecipes();
    } catch (err) {
      setRecipeError(err.message);
    } finally {
      setSavingRecipe(false);
    }
  }

  async function handleDeleteRecipe(recipe) {
    if (!window.confirm(t("wh.deleteRecipeConfirm", { name: recipe.name }))) return;
    try {
      const result = await api.deleteRecipe(token, recipe.id);
      if (result?.deactivated) {
        window.alert(t("wh.recipeDeactivatedAlert", { name: recipe.name }));
      }
      reloadRecipes();
    } catch (err) {
      window.alert(err.message);
    }
  }

  function openAddRun() {
    setRunForm(RUN_FORM_EMPTY);
    setRunError("");
    setRunModalOpen(true);
  }

  async function handleSubmitRun(e) {
    e.preventDefault();
    setSavingRun(true);
    setRunError("");
    try {
      await api.createProductionRun(token, {
        recipe_id: runForm.recipe_id,
        warehouse_id: runForm.warehouse_id,
        date: runForm.date,
        output_qty: Number(runForm.output_qty),
        note: runForm.note || null,
      });
      setRunModalOpen(false);
      reloadRuns();
    } catch (err) {
      setRunError(err.message);
    } finally {
      setSavingRun(false);
    }
  }

  async function handleDeleteRun(run) {
    if (!window.confirm(t("wh.deleteRunConfirm"))) return;
    try {
      await api.deleteProductionRun(token, run.id);
      reloadRuns();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <>
      <div className="fp-tabs-row">
        <div className="fp-tabs">
          {[
            ["recipes", t("wh.tab.recipes")],
            ["runs", t("wh.tab.runs")],
          ].map(([key, label]) => (
            <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        {canEdit && tab === "recipes" && (
          <button type="button" className="fp-btn-tiny" onClick={openAddRecipe}>
            <Plus size={13} /> {t("wh.newRecipe")}
          </button>
        )}
        {canEdit && tab === "runs" && (
          <button type="button" className="fp-btn-tiny" onClick={openAddRun}>
            <Plus size={13} /> {t("wh.newRun")}
          </button>
        )}
      </div>

      {tab === "recipes" && (
        <div className="fp-panel fp-table-panel">
          {recipesLoading ? (
            <div className="fp-loading">{t("common.loading")}</div>
          ) : (
            <table className="fp-table">
              <thead>
                <tr>
                  {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                  <th>{t("automation.col.name")}</th>
                  <th>{t("wh.col.output")}</th>
                  <th>{t("wh.col.recipeComposition")}</th>
                  <th>{t("reference.status")}</th>
                  <th className="fp-table-actions-col"></th>
                </tr>
              </thead>
              <tbody>
                {(recipes || []).map((r) => {
                  const canEditRow = canEditWarehouse(roleForCompany(r.company_id));
                  return (
                  <tr key={r.id}>
                    {showCompanyColumn && (
                      <td>{companies.find((c) => c.company.id === r.company_id)?.company.name || "—"}</td>
                    )}
                    <td>{r.name}</td>
                    <td>
                      {variantsById[r.output_variant_id]
                        ? `${variantsById[r.output_variant_id].productName} · ${variantsById[r.output_variant_id].name}`
                        : "—"}
                    </td>
                    <td className="fp-muted">
                      {r.inputs
                        .map((i) => {
                          const v = variantsById[i.input_variant_id];
                          return v ? `${v.productName} ${v.name} × ${i.qty_per_unit}` : `${i.qty_per_unit}`;
                        })
                        .join(", ")}
                    </td>
                    <td>
                      <span className={`fp-status-badge ${r.is_active === false ? "warn" : "ok"}`}>
                        {r.is_active === false ? t("wh.recipeStatus.inactive") : t("wh.recipeStatus.active")}
                      </span>
                    </td>
                    {canEditRow && (
                      <td className="fp-table-actions-col">
                        <span className="fp-row-actions">
                          <button className="fp-icon-btn" onClick={() => openEditRecipe(r)}>
                            <Pencil size={14} />
                          </button>
                          <button className="fp-icon-btn" onClick={() => handleDeleteRecipe(r)}>
                            <Trash2 size={14} />
                          </button>
                        </span>
                      </td>
                    )}
                  </tr>
                  );
                })}
                {(recipes || []).length === 0 && (
                  <tr>
                    <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                      {t("wh.noRecipes")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
          {recipesError && <div className="fp-error-banner">{recipesError}</div>}
        </div>
      )}

      {tab === "runs" && (
        <div className="fp-panel fp-table-panel">
          {runsLoading ? (
            <div className="fp-loading">{t("common.loading")}</div>
          ) : (
            <table className="fp-table">
              <thead>
                <tr>
                  {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                  <th>{t("payroll.col.date")}</th>
                  <th>{t("wh.col.warehouse")}</th>
                  <th>{t("wh.col.recipe")}</th>
                  <th className="right">{t("wh.col.outputQty")}</th>
                  <th className="fp-table-actions-col"></th>
                </tr>
              </thead>
              <tbody>
                {(runs || []).map((run) => {
                  const canEditRow = canEditWarehouse(roleForCompany(run.company_id));
                  return (
                  <tr key={run.id}>
                    {showCompanyColumn && (
                      <td>{companies.find((c) => c.company.id === run.company_id)?.company.name || "—"}</td>
                    )}
                    <td>{fmtDate(run.date)}</td>
                    <td>{warehousesById[run.warehouse_id]?.name || "—"}</td>
                    <td className="fp-muted">{recipesById[run.recipe_id]?.name || "—"}</td>
                    <td className="right">{run.output_qty}</td>
                    {canEditRow && (
                      <td className="fp-table-actions-col">
                        <button className="fp-icon-btn" onClick={() => handleDeleteRun(run)}>
                          <Trash2 size={14} />
                        </button>
                      </td>
                    )}
                  </tr>
                  );
                })}
                {(runs || []).length === 0 && (
                  <tr>
                    <td colSpan={showCompanyColumn ? 6 : 5} className="fp-empty">
                      {t("wh.noRuns")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
          {runsError && <div className="fp-error-banner">{runsError}</div>}
        </div>
      )}

      {recipeModalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setRecipeModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingRecipeId ? t("wh.editRecipe") : t("wh.newRecipe")}</h3>
              <button className="fp-icon-btn" onClick={() => setRecipeModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitRecipe}>
              {multiCompany && (
                <label className="fp-span-2">
                  {t("tx.form.company")}
                  {editingRecipeId ? (
                    <input
                      type="text"
                      disabled
                      value={companies.find((m) => m.company.id === recipeFormCompanyId)?.company.name || ""}
                    />
                  ) : (
                    <select
                      value={recipeFormCompanyId}
                      onChange={(e) => {
                        setRecipeFormCompanyId(e.target.value);
                        setRecipeForm((p) => ({
                          ...p,
                          output_variant_id: "",
                          inputs: [{ input_variant_id: "", qty_per_unit: "" }],
                        }));
                      }}
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
              <label className="fp-span-2">
                {t("automation.col.name")}
                <input
                  required
                  value={recipeForm.name}
                  onChange={(e) => setRecipeForm((p) => ({ ...p, name: e.target.value }))}
                />
              </label>
              <label className="fp-span-2">
                {t("wh.outputVariant")}
                <select
                  required
                  value={recipeForm.output_variant_id}
                  onChange={(e) => setRecipeForm((p) => ({ ...p, output_variant_id: e.target.value }))}
                >
                  <option value="" disabled>
                    {t("wh.selectVariant")}
                  </option>
                  {recipeVariants.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.productName} · {v.name}
                    </option>
                  ))}
                </select>
              </label>

              <div className="fp-span-2">
                <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>
                  {t("wh.rawMaterialsNote")}
                </div>
                {recipeForm.inputs.map((line, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 2 }}>
                      {idx === 0 && t("wh.col.productVariant")}
                      <select
                        required
                        value={line.input_variant_id}
                        onChange={(e) => updateRecipeInput(idx, { input_variant_id: e.target.value })}
                      >
                        <option value="" disabled>
                          {t("wh.selectVariant")}
                        </option>
                        {recipeVariants.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.productName} · {v.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && t("wh.norm")}
                      <input
                        required
                        type="number"
                        step="0.0001"
                        value={line.qty_per_unit}
                        onChange={(e) => updateRecipeInput(idx, { qty_per_unit: e.target.value })}
                      />
                    </label>
                    {recipeForm.inputs.length > 1 && (
                      <button
                        type="button"
                        className="fp-icon-btn"
                        style={{ marginBottom: 8 }}
                        onClick={() => removeRecipeInput(idx)}
                      >
                        <X size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="fp-btn-tiny" onClick={addRecipeInput}>
                  <Plus size={13} /> {t("wh.addRawMaterial")}
                </button>
              </div>

              {recipeError && <div className="fp-form-error fp-span-2">{recipeError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setRecipeModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={savingRecipe}>
                  {savingRecipe ? t("common.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {runModalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setRunModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("wh.newProductionRun")}</h3>
              <button className="fp-icon-btn" onClick={() => setRunModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitRun}>
              <label>
                {t("wh.col.recipe")}
                <select
                  required
                  value={runForm.recipe_id}
                  onChange={(e) => setRunForm((p) => ({ ...p, recipe_id: e.target.value, warehouse_id: "" }))}
                >
                  <option value="" disabled>
                    {t("wh.selectRecipe")}
                  </option>
                  {(recipes || [])
                    .filter((r) => r.is_active !== false)
                    .map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                {t("wh.col.warehouse")}
                <select
                  required
                  value={runForm.warehouse_id}
                  onChange={(e) => setRunForm((p) => ({ ...p, warehouse_id: e.target.value }))}
                >
                  <option value="" disabled>
                    {t("wh.selectWarehouse")}
                  </option>
                  {runWarehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("payroll.col.date")}
                <input
                  type="date"
                  required
                  value={runForm.date}
                  onChange={(e) => setRunForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.col.outputQty")}
                <input
                  required
                  type="number"
                  step="0.001"
                  value={runForm.output_qty}
                  onChange={(e) => setRunForm((p) => ({ ...p, output_qty: e.target.value }))}
                />
              </label>
              <label className="fp-span-2">
                {t("wh.col.note")}
                <input value={runForm.note} onChange={(e) => setRunForm((p) => ({ ...p, note: e.target.value }))} />
              </label>

              {runError && <div className="fp-form-error fp-span-2">{runError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setRunModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={savingRun}>
                  {savingRun ? t("common.saving") : t("modules.create")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Справочники (склады / товары / варианты)
// ---------------------------------------------------------------------------

function CatalogPanel({
  token,
  canEdit,
  warehouses,
  reloadWarehouses,
  products,
  reloadProducts,
  rawVariants,
  reloadVariants,
  equipment,
  reloadEquipment,
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("warehouses");
  // Только склады, товары и оборудование создаются напрямую с выбором компании —
  // вариант всегда наследует компанию от выбранного товара (см. warehouse.py::create_variant).
  const NEEDS_COMPANY_FIELD = { warehouses: true, products: true, variants: false, equipment: true };

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({});
  const [formCompanyId, setFormCompanyId] = useState("");
  const [originalCompanyId, setOriginalCompanyId] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const editableCompanies = companies.filter((m) => canEditWarehouse(m.role));

  const config = {
    warehouses: {
      label: t("wh.tab.warehouses"),
      items: warehouses,
      reload: reloadWarehouses,
      fields: [{ key: "name", label: t("wh.warehouseName") }],
      create: (payload) => api.createWarehouse(token, payload, formCompanyId || undefined),
      update: (id, payload) => api.updateWarehouse(token, id, payload),
      remove: (id) => api.deleteWarehouse(token, id),
      moveCompany: (id, companyId) => api.moveWarehouseCompany(token, id, companyId),
    },
    products: {
      label: t("wh.tab.products"),
      items: products,
      reload: reloadProducts,
      fields: [
        { key: "name", label: t("wh.productName") },
        { key: "unit", label: t("wh.unit"), default: "кг" },
        { key: "category", label: t("wh.category") },
      ],
      create: (payload) => api.createWhProduct(token, payload, formCompanyId || undefined),
      update: (id, payload) => api.updateWhProduct(token, id, payload),
      remove: (id) => api.deleteWhProduct(token, id),
      moveCompany: (id, companyId) => api.moveWhProductCompany(token, id, companyId),
    },
    variants: {
      label: t("wh.variantsFull"),
      items: rawVariants,
      reload: reloadVariants,
      fields: [
        {
          key: "product_id",
          label: t("wh.product"),
          type: "select",
          options: (products || [])
            .filter((p) => !multiCompany || !companyId || p.company_id === companyId)
            .map((p) => ({ value: p.id, label: p.name })),
        },
        { key: "name", label: t("wh.calibre") },
      ],
      create: (payload) => api.createWhVariant(token, payload),
      update: (id, payload) => api.updateWhVariant(token, id, payload),
      remove: (id) => api.deleteWhVariant(token, id),
      moveCompany: null,
    },
    equipment: {
      label: t("wh.tab.equipment"),
      items: equipment,
      reload: reloadEquipment,
      fields: [
        { key: "name", label: t("wh.equipmentName") },
        { key: "quantity", label: t("wh.quantity"), type: "number" },
        { key: "quantity_unit", label: t("wh.quantityUnit") },
        { key: "note", label: t("wh.note") },
      ],
      create: (payload) => api.createEquipment(token, payload, formCompanyId || undefined),
      update: (id, payload) => api.updateEquipment(token, id, payload),
      remove: (id) => api.deleteEquipment(token, id),
      moveCompany: (id, companyId) => api.moveEquipmentCompany(token, id, companyId),
    },
  }[tab];

  function openAdd() {
    setEditingId(null);
    const empty = {};
    config.fields.forEach((f) => (empty[f.key] = f.default ?? ""));
    setForm(empty);
    const preselected = editableCompanies.find((m) => m.company.id === companyId) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setOriginalCompanyId("");
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
    setFormError("");
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      // Числовые поля (пока только "quantity" у оборудования) идут строками из
      // input — пустая строка не проходит Optional[float] на бэкенде, приводим
      // к числу/null перед отправкой.
      const payload = { ...form };
      config.fields.forEach((f) => {
        if (f.type === "number") payload[f.key] = payload[f.key] === "" ? null : Number(payload[f.key]);
      });
      if (editingId) {
        // Перенос в другую компанию — отдельным вызовом раньше остальных правок
        // (бэкенд блокирует его, если запись уже где-то используется).
        if (config.moveCompany && multiCompany && formCompanyId && formCompanyId !== originalCompanyId) {
          await config.moveCompany(editingId, formCompanyId);
        }
        await config.update(editingId, payload);
      } else {
        await config.create(payload);
      }
      setModalOpen(false);
      config.reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(t("reference.deleteConfirm", { name: item.name }))) return;
    try {
      const result = await config.remove(item.id);
      if (result?.deactivated) {
        window.alert(t("wh.deactivatedGenericAlert", { name: item.name }));
      }
      config.reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  const productsById = useMemo(() => Object.fromEntries((products || []).map((p) => [p.id, p])), [products]);

  return (
    <>
      <div className="fp-tabs-row">
        <div className="fp-tabs">
          {[
            ["warehouses", t("wh.tab.warehouses")],
            ["products", t("wh.tab.products")],
            ["variants", t("wh.tab.variants")],
            ["equipment", t("wh.tab.equipment")],
          ].map(([key, label]) => (
            <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        {canEdit && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> {t("common.add")}
          </button>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        <table className="fp-table">
          <thead>
            <tr>
              {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
              {config.fields.map((f) => (
                <th key={f.key}>{f.label}</th>
              ))}
              <th>{t("reference.status")}</th>
              <th className="fp-table-actions-col"></th>
            </tr>
          </thead>
          <tbody>
            {(config.items || []).map((item) => {
              const canEditRow = canEditWarehouse(roleForCompany(item.company_id));
              return (
              <tr key={item.id}>
                {showCompanyColumn && (
                  <td>{companies.find((c) => c.company.id === item.company_id)?.company.name || "—"}</td>
                )}
                {config.fields.map((f) => (
                  <td key={f.key}>
                    {f.key === "product_id" ? productsById[item.product_id]?.name || "—" : item[f.key] || "—"}
                  </td>
                ))}
                <td>
                  <span className={`fp-status-badge ${item.is_active === false ? "warn" : "ok"}`}>
                    {item.is_active === false ? t("reference.status.inactive") : t("reference.status.active")}
                  </span>
                </td>
                {canEditRow && (
                  <td className="fp-table-actions-col">
                    <span className="fp-row-actions">
                      <button className="fp-icon-btn" onClick={() => openEdit(item)}>
                        <Pencil size={14} />
                      </button>
                      <button className="fp-icon-btn" onClick={() => handleDelete(item)}>
                        <Trash2 size={14} />
                      </button>
                    </span>
                  </td>
                )}
              </tr>
              );
            })}
            {(config.items || []).length === 0 && (
              <tr>
                <td colSpan={config.fields.length + 2 + (showCompanyColumn ? 1 : 0)} className="fp-empty">
                  {t("reference.listEmpty")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? t("wh.edit") : t("common.add")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && NEEDS_COMPANY_FIELD[tab] && (
                <label>
                  {t("tx.form.company")}
                  {editingId ? (
                    <>
                      <select value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)} required>
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
                      {formCompanyId !== originalCompanyId && (
                        <span className="fp-muted" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                          {t("reference.moveNote")}
                        </span>
                      )}
                    </>
                  ) : (
                    <select value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)} required>
                      {editableCompanies.map((m) => (
                        <option key={m.company.id} value={m.company.id}>
                          {m.company.name}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              )}
              {config.fields.map((f) =>
                f.type === "select" ? (
                  <label key={f.key}>
                    {f.label}
                    <select
                      required
                      value={form[f.key] || ""}
                      onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    >
                      <option value="" disabled>
                        {t("wh.select")}
                      </option>
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label key={f.key}>
                    {f.label}
                    <input
                      type={f.type === "number" ? "number" : "text"}
                      step={f.type === "number" ? "any" : undefined}
                      required={f.key === "name"}
                      value={form[f.key] ?? ""}
                      onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    />
                  </label>
                )
              )}
              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------

export default function Warehouse() {
  const { token, user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const canEditAnyCompany = companies.some((m) => canEditWarehouse(m.role));
  const canEdit = canEditAnyCompany;

  const [section, setSection] = useState("balances");
  // Один общий фильтр компании на весь раздел "Склад" — все вкладки (Остатки,
  // Движения, Заказы, Производство, Справочники) используют одни и те же
  // склады/товары/варианты, поэтому переключать компанию для каждой вкладки
  // отдельно не имеет смысла (см. план "Мульти-компании").
  const [companyId, setCompanyId] = useState("");
  const query = { company_id: companyId || undefined };

  const { data: warehouses, reload: reloadWarehouses } = useResource(
    () => api.listWarehouses(token, query),
    [token, companyId]
  );
  const { data: products, reload: reloadProducts } = useResource(
    () => api.listWhProducts(token, query),
    [token, companyId]
  );
  const { data: rawVariants, reload: reloadVariants } = useResource(
    () => api.listWhVariants(token, query),
    [token, companyId]
  );
  const { data: equipment, reload: reloadEquipment } = useResource(
    () => api.listEquipment(token, query),
    [token, companyId]
  );

  const productsById = useMemo(() => Object.fromEntries((products || []).map((p) => [p.id, p])), [products]);
  const warehousesById = useMemo(() => Object.fromEntries((warehouses || []).map((w) => [w.id, w])), [warehouses]);
  const variants = useMemo(
    () => (rawVariants || []).map((v) => ({ ...v, productName: productsById[v.product_id]?.name || "?" })),
    [rawVariants, productsById]
  );
  const variantsById = useMemo(() => Object.fromEntries(variants.map((v) => [v.id, v])), [variants]);
  // Для выпадающих списков (создание движения/заказа) — без неактивных
  // вариантов и вариантов деактивированных товаров (напр. мусорных
  // артефактов после разбора широких листов синка). variants/variantsById
  // остаются полными — по ним резолвятся названия в уже существующих
  // записях (Остатки/Движения), исторические записи не должны пропадать.
  const activeVariants = useMemo(
    () => variants.filter((v) => v.is_active !== false && productsById[v.product_id]?.is_active !== false),
    [variants, productsById]
  );

  const showCompanyColumn = multiCompany && !companyId;
  const shared = {
    token,
    companies,
    multiCompany,
    companyId,
    showCompanyColumn,
    roleForCompany,
    warehouses,
    warehousesById,
    products,
    variants,
    variantsById,
    activeVariants,
  };

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <div className="fp-tabs">
          {SECTIONS.map((s) => (
            <button key={s.key} className={section === s.key ? "active" : ""} onClick={() => setSection(s.key)}>
              <s.icon size={14} />
              {t(s.labelKey)}
            </button>
          ))}
        </div>
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
      </div>

      {section === "balances" && <BalancesPanel {...shared} />}
      {section === "movements" && <MovementsPanel {...shared} canEdit={canEdit} />}
      {section === "orders" && <OrdersPanel {...shared} canEdit={canEdit} />}
      {section === "production" && <ProductionPanel {...shared} canEdit={canEdit} />}
      {section === "catalog" && (
        <CatalogPanel
          {...shared}
          canEdit={canEdit}
          reloadWarehouses={reloadWarehouses}
          reloadProducts={reloadProducts}
          rawVariants={rawVariants}
          reloadVariants={reloadVariants}
          equipment={equipment}
          reloadEquipment={reloadEquipment}
        />
      )}
      {section === "sync" && <SheetSyncPanel {...shared} canEdit={canEdit} products={products} />}
    </div>
  );
}

const SHEET_TAB_FORMATS = [
  { value: "movements", labelKey: "wh.sync.format.movements" },
  { value: "wide_calibers_in", labelKey: "wh.sync.format.wideIn" },
  { value: "wide_calibers_out", labelKey: "wh.sync.format.wideOut" },
  { value: "processing_wide", labelKey: "wh.sync.format.processing" },
];

const TAB_FORM_EMPTY = {
  spreadsheet_id: "",
  spreadsheet_label: "",
  tab_name: "",
  format: "movements",
  product_id: "",
  default_warehouse_id: "",
  column_mapping_text: "",
};

function SheetSyncPanel({ token, companies, multiCompany, companyId, warehouses, products, canEdit }) {
  const { t } = useTranslation();
  const singleCompanyId = companyId || (companies.length === 1 ? companies[0].company.id : "");

  const { data: connection, reload: reloadConnection } = useResource(
    () => (singleCompanyId ? api.getWhSheetConnection(token, singleCompanyId) : Promise.resolve(null)),
    [token, singleCompanyId]
  );
  const { data: tabs, reload: reloadTabs } = useResource(
    () => (singleCompanyId ? api.listWhSheetTabs(token, singleCompanyId) : Promise.resolve([])),
    [token, singleCompanyId]
  );

  const [keyFileName, setKeyFileName] = useState("");
  const [credentialsJson, setCredentialsJson] = useState("");
  const [autosyncMinutes, setAutosyncMinutes] = useState(180);
  const [connectSaving, setConnectSaving] = useState(false);
  const [connectError, setConnectError] = useState("");

  const [tabModalOpen, setTabModalOpen] = useState(false);
  const [editingTabId, setEditingTabId] = useState(null);
  const [tabForm, setTabForm] = useState(TAB_FORM_EMPTY);
  const [tabError, setTabError] = useState("");
  const [tabSaving, setTabSaving] = useState(false);

  const [syncBusy, setSyncBusy] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(null);
  const [previewResult, setPreviewResult] = useState(null);

  function handleKeyFilePicked(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setCredentialsJson(String(reader.result || ""));
    reader.readAsText(file);
    setKeyFileName(file.name);
  }

  async function handleConnect(e) {
    e.preventDefault();
    setConnectSaving(true);
    setConnectError("");
    try {
      await api.upsertWhSheetConnection(
        token,
        { credentials_json: credentialsJson, autosync_interval_minutes: Number(autosyncMinutes) },
        singleCompanyId
      );
      setCredentialsJson("");
      setKeyFileName("");
      reloadConnection();
    } catch (err) {
      setConnectError(err.message);
    } finally {
      setConnectSaving(false);
    }
  }

  function openAddTab() {
    setEditingTabId(null);
    setTabForm(TAB_FORM_EMPTY);
    setTabError("");
    setTabModalOpen(true);
  }

  function openEditTab(tab) {
    setEditingTabId(tab.id);
    setTabForm({
      spreadsheet_id: tab.spreadsheet_id,
      spreadsheet_label: tab.spreadsheet_label || "",
      tab_name: tab.tab_name,
      format: tab.format,
      product_id: tab.product_id || "",
      default_warehouse_id: tab.default_warehouse_id || "",
      column_mapping_text: tab.column_mapping && Object.keys(tab.column_mapping).length
        ? JSON.stringify(tab.column_mapping, null, 2)
        : "",
    });
    setTabError("");
    setTabModalOpen(true);
  }

  async function handleTabSubmit(e) {
    e.preventDefault();
    setTabSaving(true);
    setTabError("");
    try {
      let column_mapping = {};
      if (tabForm.column_mapping_text.trim()) {
        try {
          column_mapping = JSON.parse(tabForm.column_mapping_text);
        } catch {
          throw new Error(t("wh.sync.invalidJson"));
        }
      }
      const payload = {
        spreadsheet_id: tabForm.spreadsheet_id,
        spreadsheet_label: tabForm.spreadsheet_label || null,
        tab_name: tabForm.tab_name,
        format: tabForm.format,
        product_id: tabForm.product_id || null,
        default_warehouse_id: tabForm.default_warehouse_id || null,
        column_mapping,
        is_active: true,
      };
      if (editingTabId) {
        await api.updateWhSheetTab(token, editingTabId, payload);
      } else {
        await api.createWhSheetTab(token, payload, singleCompanyId);
      }
      setTabModalOpen(false);
      reloadTabs();
    } catch (err) {
      setTabError(err.message);
    } finally {
      setTabSaving(false);
    }
  }

  async function handleDeleteTab(tab) {
    if (!window.confirm(t("wh.sync.deleteTabConfirm", { name: tab.tab_name }))) return;
    await api.deleteWhSheetTab(token, tab.id);
    reloadTabs();
  }

  async function handlePreview(tab) {
    setPreviewBusy(tab.id);
    setPreviewResult(null);
    try {
      const result = await api.previewWhSheetTab(token, tab.id);
      setPreviewResult({ tabId: tab.id, ...result });
    } catch (err) {
      setPreviewResult({ tabId: tab.id, error: err.message });
    } finally {
      setPreviewBusy(null);
    }
  }

  async function handleSyncNow() {
    setSyncBusy(true);
    setSyncResult(null);
    try {
      const result = await api.syncWhSheetsAll(token, singleCompanyId, true);
      setSyncResult(result);
      reloadTabs();
    } catch (err) {
      setSyncResult({ message: err.message });
    } finally {
      setSyncBusy(false);
    }
  }

  if (!singleCompanyId) {
    return <div className="fp-empty">{t("wh.sync.pickCompany")}</div>;
  }

  return (
    <div>
      <div className="fp-panel" style={{ padding: 16, marginBottom: 16 }}>
        <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 8 }}>{t("wh.sync.connectionTitle")}</div>
        {connection ? (
          <div style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 10 }}>
            {t("wh.sync.connected")}
            {connection.last_sync_at && ` · ${t("wh.sync.lastSync")}: ${fmtDate(connection.last_sync_at)}`}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 10 }}>{t("wh.sync.notConnected")}</div>
        )}
        {canEdit && (
          <form onSubmit={handleConnect} style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
            <label>
              {t("wh.sync.credentialsFile")}
              <div>
                <label className="fp-btn-ghost" style={{ display: "inline-flex", cursor: "pointer" }}>
                  {credentialsJson ? <Check size={14} /> : <Upload size={14} />}
                  {keyFileName || t("wh.sync.chooseFile")}
                  <input type="file" accept=".json" style={{ display: "none" }} onChange={handleKeyFilePicked} />
                </label>
              </div>
            </label>
            <label>
              {t("wh.sync.autosyncMinutes")}
              <input
                type="number"
                min="10"
                value={autosyncMinutes}
                onChange={(e) => setAutosyncMinutes(e.target.value)}
                style={{ width: 90 }}
              />
            </label>
            <button type="submit" className="fp-btn-primary" disabled={connectSaving || !credentialsJson}>
              {connectSaving ? t("common.saving") : t("wh.sync.saveConnection")}
            </button>
          </form>
        )}
        {connectError && <div className="fp-form-error">{connectError}</div>}
      </div>

      {connection && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{t("wh.sync.tabsTitle")}</div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="fp-btn-ghost" onClick={handleSyncNow} disabled={syncBusy}>
                <RefreshCw size={14} /> {syncBusy ? t("wh.sync.syncing") : t("wh.sync.syncNow")}
              </button>
              {canEdit && (
                <button className="fp-btn-tiny" onClick={openAddTab}>
                  <Plus size={13} /> {t("wh.sync.addTab")}
                </button>
              )}
            </div>
          </div>

          {syncResult && (
            <div className="fp-panel" style={{ padding: 12, marginBottom: 12, fontSize: 13 }}>
              <div>{syncResult.message}</div>
              {(syncResult.results || []).map((r) => (
                <div key={r.tab_id} style={{ marginTop: 4, color: r.error ? "var(--expense)" : "var(--ink-soft)" }}>
                  {r.tab_name}: {r.error || t("wh.sync.importedCount", { count: r.imported })}
                  {r.unresolved_employees?.length > 0 && (
                    <span style={{ color: "var(--expense)" }}>
                      {" "}
                      — {t("wh.sync.unresolvedEmployees", { names: r.unresolved_employees.join(", ") })}
                    </span>
                  )}
                  {r.unresolved_warehouses?.length > 0 && (
                    <span style={{ color: "var(--expense)" }}>
                      {" "}
                      — {t("wh.sync.unresolvedWarehouses", { names: r.unresolved_warehouses.join(", ") })}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="fp-panel fp-table-panel">
            <table className="fp-table">
              <thead>
                <tr>
                  <th>{t("wh.sync.col.spreadsheet")}</th>
                  <th>{t("wh.sync.col.tab")}</th>
                  <th>{t("wh.sync.col.format")}</th>
                  <th>{t("wh.sync.col.cursor")}</th>
                  {canEdit && <th></th>}
                </tr>
              </thead>
              <tbody>
                {(tabs || []).map((tab) => (
                  <Fragment key={tab.id}>
                    <tr>
                      <td>{tab.spreadsheet_label || tab.spreadsheet_id}</td>
                      <td>{tab.tab_name}</td>
                      <td>{t(SHEET_TAB_FORMATS.find((f) => f.value === tab.format)?.labelKey || tab.format)}</td>
                      <td>{tab.last_synced_row}</td>
                      {canEdit && (
                        <td style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                          <button className="fp-icon-btn" title={t("wh.sync.preview")} onClick={() => handlePreview(tab)} disabled={previewBusy === tab.id}>
                            <Eye size={14} />
                          </button>
                          <button className="fp-icon-btn" onClick={() => openEditTab(tab)}>
                            <Pencil size={14} />
                          </button>
                          <button className="fp-icon-btn" onClick={() => handleDeleteTab(tab)}>
                            <Trash2 size={14} />
                          </button>
                        </td>
                      )}
                    </tr>
                    {previewResult?.tabId === tab.id && (
                      <tr>
                        <td colSpan={5} style={{ fontSize: 12.5, background: "var(--bg)" }}>
                          {previewResult.error
                            ? previewResult.error
                            : t("wh.sync.previewSummary", { count: previewResult.imported })}
                          {previewResult.unresolved_employees?.length > 0 &&
                            ` — ${t("wh.sync.unresolvedEmployees", { names: previewResult.unresolved_employees.join(", ") })}`}
                          {previewResult.unresolved_warehouses?.length > 0 &&
                            ` — ${t("wh.sync.unresolvedWarehouses", { names: previewResult.unresolved_warehouses.join(", ") })}`}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {(tabs || []).length === 0 && (
                  <tr>
                    <td colSpan={5} className="fp-empty">
                      {t("wh.sync.noTabs")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {tabModalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setTabModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingTabId ? t("wh.sync.editTab") : t("wh.sync.newTab")}</h3>
              <button className="fp-icon-btn" onClick={() => setTabModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleTabSubmit}>
              <label>
                {t("wh.sync.spreadsheetId")}
                <input
                  required
                  value={tabForm.spreadsheet_id}
                  onChange={(e) => setTabForm((p) => ({ ...p, spreadsheet_id: e.target.value }))}
                  placeholder="1MrLrl7e..."
                />
              </label>
              <label>
                {t("wh.sync.spreadsheetLabel")}
                <input
                  value={tabForm.spreadsheet_label}
                  onChange={(e) => setTabForm((p) => ({ ...p, spreadsheet_label: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.sync.tabName")}
                <input
                  required
                  value={tabForm.tab_name}
                  onChange={(e) => setTabForm((p) => ({ ...p, tab_name: e.target.value }))}
                />
              </label>
              <label>
                {t("wh.sync.format")}
                <select value={tabForm.format} onChange={(e) => setTabForm((p) => ({ ...p, format: e.target.value }))}>
                  {SHEET_TAB_FORMATS.map((f) => (
                    <option key={f.value} value={f.value}>
                      {t(f.labelKey)}
                    </option>
                  ))}
                </select>
              </label>
              {tabForm.format !== "movements" && (
                <>
                  <label>
                    {t("wh.sync.product")}
                    <select
                      value={tabForm.product_id}
                      onChange={(e) => setTabForm((p) => ({ ...p, product_id: e.target.value }))}
                    >
                      <option value="">—</option>
                      {(products || []).map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t("wh.sync.defaultWarehouse")}
                    <select
                      value={tabForm.default_warehouse_id}
                      onChange={(e) => setTabForm((p) => ({ ...p, default_warehouse_id: e.target.value }))}
                    >
                      <option value="">—</option>
                      {(warehouses || []).map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="fp-span-2">
                    {t("wh.sync.columnMapping")}
                    <textarea
                      rows={8}
                      style={{ fontFamily: "monospace", fontSize: 12.5 }}
                      value={tabForm.column_mapping_text}
                      onChange={(e) => setTabForm((p) => ({ ...p, column_mapping_text: e.target.value }))}
                      placeholder={'{\n  "date_col": "A",\n  "calibers": {"C": "<variant_id>"},\n  "executor_col": "I",\n  "payroll_col": "N",\n  "warehouse_col": "L",\n  "note_col": "M",\n  "marker_col": "P"\n}'}
                    />
                  </label>
                </>
              )}
              {tabError && <div className="fp-form-error fp-span-2">{tabError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setTabModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={tabSaving}>
                  {tabSaving ? t("common.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
