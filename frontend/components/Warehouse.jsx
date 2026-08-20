"use client";

import { useMemo, useState } from "react";
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
} from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";
import { canEditWarehouse } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";

const DIRECTION_LABELS = {
  in: "Приход",
  out: "Расход",
  adjustment: "Корректировка",
  production_consume: "Списано в производство",
  production_yield: "Получено с производства",
  transfer_in: "Перемещение (приход)",
  transfer_out: "Перемещение (расход)",
};

const SECTIONS = [
  { key: "balances", label: "Остатки", icon: Boxes },
  { key: "movements", label: "Движения", icon: Package },
  { key: "orders", label: "Заказы", icon: ClipboardList },
  { key: "production", label: "Производство", icon: Factory },
  { key: "catalog", label: "Справочники", icon: Settings },
];

const ORDER_STATUS_LABELS = {
  draft: "Черновик",
  reserved: "Резерв",
  shipped: "Отгружен",
  cancelled: "Отменён",
};

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
  { key: "warehouse_name", label: "Склад", type: "text" },
  { key: "product_name", label: "Товар", type: "text" },
  { key: "variant_name", label: "Калибр", type: "natural" },
  { key: "quantity", label: "Остаток", type: "number", align: "right" },
  { key: "reserved", label: "В резерве", type: "number", align: "right" },
  { key: "available", label: "Доступно", type: "number", align: "right" },
];

function BalancesPanel({ token, companyId, companies, showCompanyColumn }) {
  const [hideZero, setHideZero] = useState(false);
  const {
    data: balances,
    loading,
    error,
  } = useResource(
    () => api.listWhBalances(token, { include_empty: true, company_id: companyId || undefined }),
    [token, companyId]
  );
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

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
  }, [balances, sortKey, sortDir, hideZero]);

  return (
    <div className="fp-panel fp-table-panel">
      <div style={{ display: "flex", gap: 18, padding: "12px 16px 0", fontSize: 13 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} />
          Скрыть нулевые остатки
        </label>
      </div>
      {loading ? (
        <div className="fp-loading">Загрузка…</div>
      ) : (
        <table className="fp-table">
          <thead>
            <tr>
              {showCompanyColumn && <th>Компания</th>}
              {BALANCE_COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={col.align === "right" ? "right" : ""}
                  onClick={() => toggleSort(col)}
                  style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}
                  title="Сортировать"
                >
                  {col.label}{" "}
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
                  Остатков пока нет
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
  warehousesById,
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
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
  const movementVariants = (variants || []).filter(
    (v) => !multiCompany || !form.warehouse_id || v.company_id === warehousesById[form.warehouse_id]?.company_id
  );
  const transferToWarehouses = (warehouses || []).filter(
    (w) =>
      !multiCompany ||
      !transferForm.from_warehouse_id ||
      w.company_id === warehousesById[transferForm.from_warehouse_id]?.company_id
  );
  const transferVariants = (variants || []).filter(
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
    if (!window.confirm("Удалить движение? Если с ним связано начисление зарплаты — оно тоже будет удалено.")) return;
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
              <Plus size={13} /> Приход
            </button>
            <button className="fp-btn-tiny" onClick={() => openMovement("out")}>
              <Plus size={13} /> Расход
            </button>
            <button className="fp-btn-tiny" onClick={() => openMovement("adjustment")}>
              <Pencil size={13} /> Корректировка
            </button>
            <button className="fp-btn-tiny" onClick={openTransfer}>
              <ArrowRightLeft size={13} /> Перемещение
            </button>
          </div>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>Компания</th>}
                <th>Дата</th>
                <th>Склад</th>
                <th>Товар / калибр</th>
                <th>Тип</th>
                <th className="right">Кол-во</th>
                <th>Примечание</th>
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
                    <td className="fp-muted">{DIRECTION_LABELS[m.direction] || m.direction}</td>
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
                    Движений пока нет
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
              <h3>{DIRECTION_LABELS[form.direction]}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitMovement}>
              <label>
                Дата
                <input
                  type="date"
                  required
                  value={form.date}
                  onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                Склад
                <select
                  required
                  value={form.warehouse_id}
                  onChange={(e) => setForm((p) => ({ ...p, warehouse_id: e.target.value, product_variant_id: "" }))}
                >
                  <option value="" disabled>
                    Выберите склад
                  </option>
                  {(warehouses || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="fp-span-2">
                Товар / калибр
                <select
                  required
                  value={form.product_variant_id}
                  onChange={(e) => setForm((p) => ({ ...p, product_variant_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите вариант
                  </option>
                  {movementVariants.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.productName} · {v.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Количество{form.direction === "adjustment" ? " (можно отрицательное)" : ""}
                <input
                  required
                  type="number"
                  step="0.001"
                  value={form.quantity}
                  onChange={(e) => setForm((p) => ({ ...p, quantity: e.target.value }))}
                />
              </label>
              <label>
                Примечание
                <input value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} />
              </label>

              {form.direction === "in" && (
                <>
                  <label>
                    Исполнитель (для зарплаты)
                    <select
                      value={form.executor_id}
                      onChange={(e) => setForm((p) => ({ ...p, executor_id: e.target.value }))}
                    >
                      <option value="">— не указан —</option>
                      {(employees || []).map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.full_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Ставка за единицу
                    <input
                      type="number"
                      step="0.01"
                      disabled={!form.executor_id}
                      value={form.payroll_rate}
                      onChange={(e) => setForm((p) => ({ ...p, payroll_rate: e.target.value }))}
                    />
                  </label>
                  <div className="fp-note fp-span-2">
                    Если указать исполнителя и ставку — начисление автоматически появится в модуле «Зарплата».
                  </div>
                </>
              )}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(null)}>
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

      {modalOpen === "transfer" && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Перемещение между складами</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitTransfer}>
              <label>
                Дата
                <input
                  type="date"
                  required
                  value={transferForm.date}
                  onChange={(e) => setTransferForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                Товар / калибр
                <select
                  required
                  value={transferForm.product_variant_id}
                  onChange={(e) => setTransferForm((p) => ({ ...p, product_variant_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите вариант
                  </option>
                  {transferVariants.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.productName} · {v.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Со склада
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
                    Выберите склад
                  </option>
                  {(warehouses || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                На склад
                <select
                  required
                  value={transferForm.to_warehouse_id}
                  onChange={(e) => setTransferForm((p) => ({ ...p, to_warehouse_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите склад
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
                Количество
                <input
                  required
                  type="number"
                  step="0.001"
                  value={transferForm.quantity}
                  onChange={(e) => setTransferForm((p) => ({ ...p, quantity: e.target.value }))}
                />
              </label>
              <label>
                Примечание
                <input
                  value={transferForm.note}
                  onChange={(e) => setTransferForm((p) => ({ ...p, note: e.target.value }))}
                />
              </label>

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(null)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? "Сохраняем…" : "Переместить"}
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
  note: "",
  lines: [{ product_variant_id: "", quantity: "" }],
};

function OrdersPanel({
  token,
  canEdit,
  warehouses,
  variants,
  variantsById,
  warehousesById,
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
  const { data: orders, loading, error, reload } = useResource(
    () => api.listOrders(token, { company_id: companyId || undefined }),
    [token, companyId]
  );
  const { data: counterparties } = useResource(() => api.listCounterparties(token), [token]);
  const counterpartiesById = useMemo(
    () => Object.fromEntries((counterparties || []).map((c) => [c.id, c])),
    [counterparties]
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState(ORDER_FORM_EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const orderWarehouseCompany = warehousesById[form.warehouse_id]?.company_id;
  const orderCounterparties = (counterparties || []).filter(
    (c) => !multiCompany || !form.warehouse_id || c.company_id === orderWarehouseCompany
  );
  const orderVariants = (variants || []).filter(
    (v) => !multiCompany || !form.warehouse_id || v.company_id === orderWarehouseCompany
  );

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
    setForm(ORDER_FORM_EMPTY);
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
    try {
      await api.createOrder(token, {
        counterparty_id: form.counterparty_id,
        warehouse_id: form.warehouse_id,
        requested_date: form.requested_date || null,
        note: form.note || null,
        lines: form.lines.map((l) => ({ product_variant_id: l.product_variant_id, quantity: Number(l.quantity) })),
      });
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

  async function handleShip(order) {
    if (!window.confirm("Отгрузить заказ? Остаток на складе уменьшится.")) return;
    try {
      await api.shipOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleCancel(order) {
    if (!window.confirm("Отменить заказ?")) return;
    try {
      await api.cancelOrder(token, order.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleDelete(order) {
    if (!window.confirm("Удалить черновик заказа?")) return;
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
            <Plus size={13} /> Новый заказ
          </button>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">Загрузка…</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {showCompanyColumn && <th>Компания</th>}
                <th>Дата</th>
                <th>Клиент</th>
                <th>Склад</th>
                <th>Состав</th>
                <th className="center">Статус</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(orders || []).map((o) => {
                const canEditRow = canEditWarehouse(roleForCompany(o.company_id));
                return (
                <tr key={o.id}>
                  {showCompanyColumn && (
                    <td>{companies.find((c) => c.company.id === o.company_id)?.company.name || "—"}</td>
                  )}
                  <td>{o.requested_date ? fmtDate(o.requested_date) : fmtDate(o.created_at)}</td>
                  <td>{counterpartiesById[o.counterparty_id]?.name || "—"}</td>
                  <td className="fp-muted">{warehousesById[o.warehouse_id]?.name || "—"}</td>
                  <td className="fp-muted">
                    {o.lines
                      .map((l) => {
                        const v = variantsById[l.product_variant_id];
                        return v ? `${v.productName} ${v.name} × ${l.quantity}` : `${l.quantity}`;
                      })
                      .join(", ")}
                  </td>
                  <td className="center">
                    <span className={`fp-status-badge ${ORDER_STATUS_BADGE[o.status] || ""}`}>
                      {ORDER_STATUS_LABELS[o.status] || o.status}
                    </span>
                  </td>
                  {canEditRow && (
                    <td className="fp-table-actions-col">
                      <span className="fp-row-actions">
                        {o.status === "draft" && (
                          <>
                            <button className="fp-btn-tiny" onClick={() => handleReserve(o)}>
                              Резерв
                            </button>
                            <button className="fp-icon-btn" onClick={() => handleShip(o)} title="Отгрузить">
                              <Send size={14} />
                            </button>
                            <button className="fp-icon-btn" onClick={() => handleDelete(o)} title="Удалить">
                              <Trash2 size={14} />
                            </button>
                          </>
                        )}
                        {o.status === "reserved" && (
                          <button className="fp-icon-btn" onClick={() => handleShip(o)} title="Отгрузить">
                            <Send size={14} />
                          </button>
                        )}
                        {(o.status === "draft" || o.status === "reserved") && (
                          <button className="fp-icon-btn" onClick={() => handleCancel(o)} title="Отменить">
                            <Ban size={14} />
                          </button>
                        )}
                        {o.sdvf_invoice_ref ? (
                          <button
                            className="fp-icon-btn"
                            onClick={() => api.openSdvfPdf(token, o.id, "invoice")}
                            title="Открыть Счёт (PDF)"
                          >
                            <FileText size={14} />
                          </button>
                        ) : (
                          <button className="fp-icon-btn" onClick={() => openDocModal(o, "invoice")} title="Сформировать счёт">
                            <FileText size={14} />
                          </button>
                        )}
                        {o.sdvf_utd_ref ? (
                          <button
                            className="fp-icon-btn"
                            onClick={() => api.openSdvfPdf(token, o.id, "utd")}
                            title="Открыть УПД (PDF)"
                          >
                            <Receipt size={14} />
                          </button>
                        ) : (
                          <button className="fp-icon-btn" onClick={() => openDocModal(o, "utd")} title="Сформировать УПД">
                            <Receipt size={14} />
                          </button>
                        )}
                      </span>
                    </td>
                  )}
                </tr>
                );
              })}
              {(orders || []).length === 0 && (
                <tr>
                  <td colSpan={showCompanyColumn ? 7 : 6} className="fp-empty">
                    Заказов пока нет
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
              <h3>Новый заказ</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              <label>
                Склад
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
                    Выберите склад
                  </option>
                  {(warehouses || []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Клиент
                <select
                  required
                  value={form.counterparty_id}
                  onChange={(e) => setForm((p) => ({ ...p, counterparty_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите клиента
                  </option>
                  {orderCounterparties.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Дата отгрузки (опц.)
                <input
                  type="date"
                  value={form.requested_date}
                  onChange={(e) => setForm((p) => ({ ...p, requested_date: e.target.value }))}
                />
              </label>
              <label>
                Примечание
                <input value={form.note} onChange={(e) => setForm((p) => ({ ...p, note: e.target.value }))} />
              </label>

              <div className="fp-span-2">
                <div style={{ fontSize: 12, color: "var(--ink-soft)", marginBottom: 6 }}>Состав заказа</div>
                {form.lines.map((line, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 2 }}>
                      {idx === 0 && "Товар / калибр"}
                      <select
                        required
                        value={line.product_variant_id}
                        onChange={(e) => updateLine(idx, { product_variant_id: e.target.value })}
                      >
                        <option value="" disabled>
                          Выберите вариант
                        </option>
                        {orderVariants.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.productName} · {v.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && "Кол-во"}
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
                  <Plus size={13} /> Добавить позицию
                </button>
              </div>

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

      {docModal && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setDocModal(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{docModal.type === "invoice" ? "Сформировать счёт" : "Сформировать УПД"}</h3>
              <button className="fp-icon-btn" onClick={() => setDocModal(null)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleDocSubmit}>
              <div className="fp-span-2" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
                Склад не хранит цену товаров — укажите её для каждой позиции этого документа.
              </div>

              <div className="fp-span-2">
                {docModal.order.lines.map((line) => {
                  const v = variantsById[line.product_variant_id];
                  return (
                    <div key={line.id} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                      <label style={{ flex: 2 }}>
                        {v ? `${v.productName} · ${v.name}` : "—"} (кол-во: {line.quantity})
                        <input
                          required
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="Цена за ед."
                          value={docPrices[line.id] ?? ""}
                          onChange={(e) => setDocPrices((p) => ({ ...p, [line.id]: e.target.value }))}
                        />
                      </label>
                    </div>
                  );
                })}
              </div>

              <label>
                НДС
                <select value={docNds} onChange={(e) => setDocNds(e.target.value)}>
                  <option value="-1">Без НДС</option>
                  <option value="0">0%</option>
                  <option value="10">10%</option>
                  <option value="20">20%</option>
                  <option value="22">22%</option>
                </select>
              </label>
              <label>
                Тип НДС
                <select value={docNdsType} onChange={(e) => setDocNdsType(e.target.value)}>
                  <option value="onTop">Сверху</option>
                  <option value="included">В сумме</option>
                </select>
              </label>

              {docError && <div className="fp-form-error fp-span-2">{docError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setDocModal(null)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={docSaving}>
                  {docSaving ? "Формируем…" : "Сформировать"}
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
    if (!window.confirm(`Удалить техкарту «${recipe.name}»?`)) return;
    try {
      const result = await api.deleteRecipe(token, recipe.id);
      if (result?.deactivated) {
        window.alert(`«${recipe.name}» уже использовалась в производстве — деактивирована вместо удаления.`);
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
    if (!window.confirm("Удалить партию производства? Связанные складские движения тоже будут удалены.")) return;
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
          {Object.entries({ recipes: "Техкарты", runs: "Партии" }).map(([key, label]) => (
            <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        {canEdit && tab === "recipes" && (
          <button type="button" className="fp-btn-tiny" onClick={openAddRecipe}>
            <Plus size={13} /> Новая техкарта
          </button>
        )}
        {canEdit && tab === "runs" && (
          <button type="button" className="fp-btn-tiny" onClick={openAddRun}>
            <Plus size={13} /> Новая партия
          </button>
        )}
      </div>

      {tab === "recipes" && (
        <div className="fp-panel fp-table-panel">
          {recipesLoading ? (
            <div className="fp-loading">Загрузка…</div>
          ) : (
            <table className="fp-table">
              <thead>
                <tr>
                  {showCompanyColumn && <th>Компания</th>}
                  <th>Название</th>
                  <th>Выход</th>
                  <th>Состав (норма на 1 ед. выхода)</th>
                  <th>Статус</th>
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
                        {r.is_active === false ? "Неактивна" : "Активна"}
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
                      Техкарт пока нет
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
            <div className="fp-loading">Загрузка…</div>
          ) : (
            <table className="fp-table">
              <thead>
                <tr>
                  {showCompanyColumn && <th>Компания</th>}
                  <th>Дата</th>
                  <th>Склад</th>
                  <th>Техкарта</th>
                  <th className="right">Кол-во выхода</th>
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
                      Партий пока нет
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
              <h3>{editingRecipeId ? "Редактировать техкарту" : "Новая техкарта"}</h3>
              <button className="fp-icon-btn" onClick={() => setRecipeModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitRecipe}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
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
                Название
                <input
                  required
                  value={recipeForm.name}
                  onChange={(e) => setRecipeForm((p) => ({ ...p, name: e.target.value }))}
                />
              </label>
              <label className="fp-span-2">
                Выходной товар / калибр
                <select
                  required
                  value={recipeForm.output_variant_id}
                  onChange={(e) => setRecipeForm((p) => ({ ...p, output_variant_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите вариант
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
                  Сырьё (норма расхода на 1 ед. выхода)
                </div>
                {recipeForm.inputs.map((line, idx) => (
                  <div key={idx} style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "flex-end" }}>
                    <label style={{ flex: 2 }}>
                      {idx === 0 && "Товар / калибр"}
                      <select
                        required
                        value={line.input_variant_id}
                        onChange={(e) => updateRecipeInput(idx, { input_variant_id: e.target.value })}
                      >
                        <option value="" disabled>
                          Выберите вариант
                        </option>
                        {recipeVariants.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.productName} · {v.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ flex: 1 }}>
                      {idx === 0 && "Норма"}
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
                  <Plus size={13} /> Добавить сырьё
                </button>
              </div>

              {recipeError && <div className="fp-form-error fp-span-2">{recipeError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setRecipeModalOpen(false)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={savingRecipe}>
                  {savingRecipe ? "Сохраняем…" : "Сохранить"}
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
              <h3>Новая партия производства</h3>
              <button className="fp-icon-btn" onClick={() => setRunModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmitRun}>
              <label>
                Техкарта
                <select
                  required
                  value={runForm.recipe_id}
                  onChange={(e) => setRunForm((p) => ({ ...p, recipe_id: e.target.value, warehouse_id: "" }))}
                >
                  <option value="" disabled>
                    Выберите техкарту
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
                Склад
                <select
                  required
                  value={runForm.warehouse_id}
                  onChange={(e) => setRunForm((p) => ({ ...p, warehouse_id: e.target.value }))}
                >
                  <option value="" disabled>
                    Выберите склад
                  </option>
                  {runWarehouses.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Дата
                <input
                  type="date"
                  required
                  value={runForm.date}
                  onChange={(e) => setRunForm((p) => ({ ...p, date: e.target.value }))}
                />
              </label>
              <label>
                Кол-во выхода
                <input
                  required
                  type="number"
                  step="0.001"
                  value={runForm.output_qty}
                  onChange={(e) => setRunForm((p) => ({ ...p, output_qty: e.target.value }))}
                />
              </label>
              <label className="fp-span-2">
                Примечание
                <input value={runForm.note} onChange={(e) => setRunForm((p) => ({ ...p, note: e.target.value }))} />
              </label>

              {runError && <div className="fp-form-error fp-span-2">{runError}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setRunModalOpen(false)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={savingRun}>
                  {savingRun ? "Сохраняем…" : "Создать"}
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
  companies,
  multiCompany,
  companyId,
  showCompanyColumn,
  roleForCompany,
}) {
  const [tab, setTab] = useState("warehouses");
  // Только склады и товары создаются напрямую с выбором компании — вариант
  // всегда наследует компанию от выбранного товара (см. warehouse.py::create_variant).
  const NEEDS_COMPANY_FIELD = { warehouses: true, products: true, variants: false };

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
      label: "Склады",
      items: warehouses,
      reload: reloadWarehouses,
      fields: [{ key: "name", label: "Название склада" }],
      create: (payload) => api.createWarehouse(token, payload, formCompanyId || undefined),
      update: (id, payload) => api.updateWarehouse(token, id, payload),
      remove: (id) => api.deleteWarehouse(token, id),
      moveCompany: (id, companyId) => api.moveWarehouseCompany(token, id, companyId),
    },
    products: {
      label: "Товары",
      items: products,
      reload: reloadProducts,
      fields: [
        { key: "name", label: "Название товара" },
        { key: "unit", label: "Единица измерения", default: "кг" },
        { key: "category", label: "Категория (опц.)" },
      ],
      create: (payload) => api.createWhProduct(token, payload, formCompanyId || undefined),
      update: (id, payload) => api.updateWhProduct(token, id, payload),
      remove: (id) => api.deleteWhProduct(token, id),
      moveCompany: (id, companyId) => api.moveWhProductCompany(token, id, companyId),
    },
    variants: {
      label: "Варианты (калибры)",
      items: rawVariants,
      reload: reloadVariants,
      fields: [
        {
          key: "product_id",
          label: "Товар",
          type: "select",
          options: (products || [])
            .filter((p) => !multiCompany || !companyId || p.company_id === companyId)
            .map((p) => ({ value: p.id, label: p.name })),
        },
        { key: "name", label: "Калибр/модификация" },
      ],
      create: (payload) => api.createWhVariant(token, payload),
      update: (id, payload) => api.updateWhVariant(token, id, payload),
      remove: (id) => api.deleteWhVariant(token, id),
      moveCompany: null,
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
      if (editingId) {
        // Перенос в другую компанию — отдельным вызовом раньше остальных правок
        // (бэкенд блокирует его, если запись уже где-то используется).
        if (config.moveCompany && multiCompany && formCompanyId && formCompanyId !== originalCompanyId) {
          await config.moveCompany(editingId, formCompanyId);
        }
        await config.update(editingId, form);
      } else {
        await config.create(form);
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
    if (!window.confirm(`Удалить «${item.name}»?`)) return;
    try {
      const result = await config.remove(item.id);
      if (result?.deactivated) {
        window.alert(`«${item.name}» уже используется — деактивировано вместо удаления.`);
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
          {Object.entries({ warehouses: "Склады", products: "Товары", variants: "Варианты" }).map(([key, label]) => (
            <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        {canEdit && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> Добавить
          </button>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        <table className="fp-table">
          <thead>
            <tr>
              {showCompanyColumn && <th>Компания</th>}
              {config.fields.map((f) => (
                <th key={f.key}>{f.label}</th>
              ))}
              <th>Статус</th>
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
                    {item.is_active === false ? "Неактивен" : "Активен"}
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
                  Список пуст
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
              <h3>{editingId ? "Редактировать" : "Добавить"}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && NEEDS_COMPANY_FIELD[tab] && (
                <label>
                  Компания
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
                          Перенос сработает, только если запись ещё нигде не используется.
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
                        Выберите
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
                      required={f.key === "name"}
                      value={form[f.key] || ""}
                      onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    />
                  </label>
                )
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
    </>
  );
}

// ---------------------------------------------------------------------------

export default function Warehouse() {
  const { token, user } = useAuth();
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

  const productsById = useMemo(() => Object.fromEntries((products || []).map((p) => [p.id, p])), [products]);
  const warehousesById = useMemo(() => Object.fromEntries((warehouses || []).map((w) => [w.id, w])), [warehouses]);
  const variants = useMemo(
    () => (rawVariants || []).map((v) => ({ ...v, productName: productsById[v.product_id]?.name || "?" })),
    [rawVariants, productsById]
  );
  const variantsById = useMemo(() => Object.fromEntries(variants.map((v) => [v.id, v])), [variants]);

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
  };

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <div className="fp-tabs">
          {SECTIONS.map((s) => (
            <button key={s.key} className={section === s.key ? "active" : ""} onClick={() => setSection(s.key)}>
              <s.icon size={14} />
              {s.label}
            </button>
          ))}
        </div>
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
        />
      )}
    </div>
  );
}
