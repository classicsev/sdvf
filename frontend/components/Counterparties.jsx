"use client";

import { useState } from "react";
import { Plus, X, Pencil, Trash2, RefreshCw, Link2, UserPlus, AlertTriangle, Check } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { canEditReference } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";

const FORM_EMPTY = {
  name: "",
  type: "debtor",
  inn: "",
  kpp: "",
  ogrn: "",
  address: "",
  phone: "",
  email: "",
};

const CONTACT_EMPTY = { full_name: "", position: "", phone: "", email: "", is_primary: false };

export default function Counterparties() {
  const { token, user } = useAuth();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const editableCompanies = companies.filter((m) => canEditReference(m.role));
  const canEditAny = editableCompanies.length > 0;

  const [companyFilter, setCompanyFilter] = useState("");
  const { data: items, loading, error, reload } = useResource(
    () => api.listCounterparties(token, { company_id: companyFilter || undefined }),
    [token, companyFilter]
  );

  const [banner, setBanner] = useState("");
  const [actionError, setActionError] = useState("");
  const [syncing, setSyncing] = useState(false);

  // Компания, в контексте которой идут операции с СДВФ. При «Все компании»
  // синхронизировать нельзя: у каждой компании свой аккаунт в СДВФ.
  const sdvfCompanyId = companyFilter || (multiCompany ? "" : editableCompanies[0]?.company.id || "");

  async function runSync(createMissing) {
    if (!sdvfCompanyId) {
      setActionError("Выберите конкретную компанию — у каждой свой аккаунт в СДВФ");
      return;
    }
    setSyncing(true);
    setActionError("");
    setBanner("");
    try {
      const r = await api.syncCounterpartiesWithSdvf(token, sdvfCompanyId, createMissing);
      const parts = [
        r.linked_by_inn ? `добавлено из СДВФ: ${r.linked_by_inn}` : null,
        r.updated_from_sdvf ? `обновлено по данным СДВФ: ${r.updated_from_sdvf}` : null,
        r.created_in_sdvf ? `заведено в СДВФ: ${r.created_in_sdvf}` : null,
        r.skipped_no_inn ? `пропущено без ИНН: ${r.skipped_no_inn}` : null,
        r.failed ? `с ошибкой: ${r.failed}` : null,
      ].filter(Boolean);
      setBanner(parts.length ? `Синхронизация завершена — ${parts.join(", ")}.` : "Синхронизация завершена, изменений нет.");
      if (r.errors?.length) setActionError(r.errors.join("; "));
      reload();
    } catch (err) {
      setActionError(err.message);
    } finally {
      setSyncing(false);
    }
  }

  // --- карточка контрагента ---
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(FORM_EMPTY);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [originalCompanyId, setOriginalCompanyId] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [innLookup, setInnLookup] = useState({ loading: false, message: "", error: "" });

  function openAdd() {
    setEditing(null);
    setForm(FORM_EMPTY);
    const preselected = editableCompanies.find((m) => m.company.id === companyFilter) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setOriginalCompanyId("");
    setFormError("");
    setInnLookup({ loading: false, message: "", error: "" });
    setModalOpen(true);
  }

  function openEdit(item) {
    setEditing(item);
    setForm({
      name: item.name || "",
      type: item.type || "debtor",
      inn: item.inn || "",
      kpp: item.kpp || "",
      ogrn: item.ogrn || "",
      address: item.address || "",
      phone: item.phone || "",
      email: item.email || "",
    });
    setFormCompanyId(item.company_id || "");
    setOriginalCompanyId(item.company_id || "");
    setFormError("");
    setInnLookup({ loading: false, message: "", error: "" });
    setModalOpen(true);
  }

  const innIsValid = /^(\d{10}|\d{12})$/.test((form.inn || "").trim());

  async function fillFromInn() {
    setInnLookup({ loading: true, message: "", error: "" });
    try {
      const found = await api.findPartyByInn(token, form.inn.trim());
      setForm((p) => ({
        ...p,
        name: found.name || p.name,
        kpp: found.kpp || p.kpp,
        ogrn: found.ogrn || p.ogrn,
        address: found.address || p.address,
      }));
      setInnLookup({ loading: false, message: `Найдено: ${found.name}`, error: "" });
    } catch (err) {
      setInnLookup({ loading: false, message: "", error: err.message });
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const payload = { ...form, is_active: editing ? editing.is_active !== false : true };
      if (editing) {
        // Тем же порядком, что и в Reference.jsx: перенос компании — отдельным
        // вызовом раньше остальных правок (бэкенд блокирует его, если карточка
        // уже используется или у неё есть контактные лица).
        if (multiCompany && formCompanyId && formCompanyId !== originalCompanyId) {
          await api.moveCounterpartyCompany(token, editing.id, formCompanyId);
        }
        await api.updateCounterparty(token, editing.id, payload);
      } else {
        await api.createCounterparty(token, payload, formCompanyId || undefined);
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
      const result = await api.deleteCounterparty(token, item.id);
      if (result?.deactivated) {
        window.alert(
          `«${item.name}» уже используется в операциях, поэтому не удалён, а деактивирован — история сохранена.`
        );
      }
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function createInSdvf(item) {
    setActionError("");
    try {
      await api.createCounterpartyInSdvf(token, item.id);
      setBanner(`«${item.name}» заведён в СДВФ.`);
      reload();
    } catch (err) {
      setActionError(err.message);
    }
  }

  // --- привязка к существующей карточке СДВФ ---
  const [linkFor, setLinkFor] = useState(null);
  const [sdvfList, setSdvfList] = useState([]);
  const [sdvfSearch, setSdvfSearch] = useState("");
  const [sdvfLoading, setSdvfLoading] = useState(false);
  const [sdvfError, setSdvfError] = useState("");

  async function openLink(item) {
    setLinkFor(item);
    setSdvfSearch("");
    setSdvfError("");
    setSdvfLoading(true);
    try {
      setSdvfList(await api.listSdvfCounterparties(token, item.company_id));
    } catch (err) {
      setSdvfError(err.message);
      setSdvfList([]);
    } finally {
      setSdvfLoading(false);
    }
  }

  async function confirmLink(buyer) {
    try {
      await api.linkCounterpartyToSdvf(token, linkFor.id, buyer.id);
      setBanner(`«${linkFor.name}» привязан к карточке СДВФ «${buyer.naming}» — реквизиты подтянуты оттуда.`);
      setLinkFor(null);
      reload();
    } catch (err) {
      setSdvfError(err.message);
    }
  }

  // --- контактные лица ---
  const [contactsFor, setContactsFor] = useState(null);
  const [contactForm, setContactForm] = useState(CONTACT_EMPTY);
  const [editingContactId, setEditingContactId] = useState(null);
  const [contactError, setContactError] = useState("");

  const contactsTarget = contactsFor ? (items || []).find((i) => i.id === contactsFor.id) || contactsFor : null;

  async function saveContact(e) {
    e.preventDefault();
    setContactError("");
    try {
      if (editingContactId) {
        await api.updateContact(token, editingContactId, contactForm);
      } else {
        await api.createContact(token, contactsFor.id, contactForm);
      }
      setContactForm(CONTACT_EMPTY);
      setEditingContactId(null);
      reload();
    } catch (err) {
      setContactError(err.message);
    }
  }

  async function removeContact(contact) {
    if (!window.confirm(`Удалить контакт «${contact.full_name}»?`)) return;
    try {
      await api.deleteContact(token, contact.id);
      reload();
    } catch (err) {
      setContactError(err.message);
    }
  }

  const showCompanyColumn = multiCompany && !companyFilter;

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        {multiCompany ? (
          <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
            <option value="">Все компании</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        ) : (
          <div />
        )}
        {canEditAny && (
          <>
            <button type="button" className="fp-btn-tiny" onClick={() => runSync(false)} disabled={syncing}>
              <RefreshCw size={13} /> {syncing ? "Синхронизируем…" : "Синхронизировать с СДВФ"}
            </button>
            <button
              type="button"
              className="fp-btn-tiny"
              onClick={() => runSync(true)}
              disabled={syncing}
              title="Дополнительно заведёт в СДВФ те карточки, которых там ещё нет"
            >
              <RefreshCw size={13} /> …и создать недостающие в СДВФ
            </button>
            <button type="button" className="fp-btn-tiny" onClick={openAdd}>
              <Plus size={13} /> Добавить
            </button>
          </>
        )}
      </div>

      {error && <div className="fp-error-banner">{error}</div>}
      {actionError && <div className="fp-error-banner">{actionError}</div>}
      {banner && (
        <div className="fp-panel" style={{ padding: "10px 14px", fontSize: 13 }}>
          {banner}
        </div>
      )}

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
                <th>Контрагент</th>
                <th>ИНН</th>
                <th>Тип</th>
                <th>СДВФ</th>
                <th>Контакты</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const canEditRow = canEditReference(roleForCompany(item.company_id));
                const inSdvf = Boolean(item.sdvf_buyer_id);
                return (
                  <tr key={item.id} style={item.is_active === false ? { opacity: 0.55 } : undefined}>
                    {showCompanyColumn && (
                      <td className="fp-muted">
                        {companies.find((m) => m.company.id === item.company_id)?.company.name || "—"}
                      </td>
                    )}
                    <td>{item.name}</td>
                    <td className="fp-muted">{item.inn || "—"}</td>
                    <td>{item.type === "creditor" ? "Кредитор" : "Дебитор"}</td>
                    <td>
                      {inSdvf ? (
                        <span className="fp-status-badge ok" title={`Карточка СДВФ №${item.sdvf_buyer_id}`}>
                          <Check size={11} /> В СДВФ
                        </span>
                      ) : (
                        <span className="fp-status-badge danger" title="Карточки нет в СДВФ — документы по ней не выставить">
                          <AlertTriangle size={11} /> Нет в СДВФ
                        </span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="fp-icon-btn"
                        title="Контактные лица"
                        onClick={() => {
                          setContactsFor(item);
                          setContactForm(CONTACT_EMPTY);
                          setEditingContactId(null);
                          setContactError("");
                        }}
                      >
                        <UserPlus size={14} />
                      </button>
                      <span className="fp-muted" style={{ fontSize: 12 }}>
                        {(item.contacts || []).length || "—"}
                      </span>
                    </td>
                    <td className="fp-table-actions-col">
                      {canEditRow && (
                        <span className="fp-row-actions">
                          {!inSdvf && (
                            <>
                              <button className="fp-icon-btn" title="Привязать к карточке СДВФ" onClick={() => openLink(item)}>
                                <Link2 size={14} />
                              </button>
                              <button
                                className="fp-icon-btn"
                                title="Создать карточку в СДВФ"
                                onClick={() => createInSdvf(item)}
                              >
                                <Plus size={14} />
                              </button>
                            </>
                          )}
                          <button className="fp-icon-btn" onClick={() => openEdit(item)}>
                            <Pencil size={14} />
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
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          Реквизиты берутся из СДВФ — он первичен. Данные из amoCRM подставляются только там, где карточка ещё
          не связана с СДВФ.
        </p>
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editing ? "Карточка контрагента" : "Новый контрагент"}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
                  <select value={formCompanyId} onChange={(e) => setFormCompanyId(e.target.value)} required>
                    {editing &&
                      !editableCompanies.some((m) => m.company.id === originalCompanyId) &&
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
                  {editing && formCompanyId !== originalCompanyId && (
                    <span className="fp-muted" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                      Перенос сработает, только если у карточки нет операций и контактных лиц.
                    </span>
                  )}
                </label>
              )}
              <label>
                ИНН
                <div style={{ display: "flex", gap: 6 }}>
                  <input
                    value={form.inn}
                    inputMode="numeric"
                    onChange={(e) => {
                      setInnLookup({ loading: false, message: "", error: "" });
                      setForm((p) => ({ ...p, inn: e.target.value }));
                    }}
                    style={{ flex: 1, minWidth: 0 }}
                  />
                  <button
                    type="button"
                    className="fp-btn-ghost"
                    onClick={fillFromInn}
                    disabled={!innIsValid || innLookup.loading}
                    title={innIsValid ? "Подставить реквизиты из ЕГРЮЛ/ЕГРИП" : "Введите ИНН: 10 цифр или 12 для ИП"}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    {innLookup.loading ? "Ищем…" : "По ИНН"}
                  </button>
                </div>
              </label>
              <label>
                Тип
                <select value={form.type} onChange={(e) => setForm((p) => ({ ...p, type: e.target.value }))}>
                  <option value="debtor">Дебитор</option>
                  <option value="creditor">Кредитор</option>
                </select>
              </label>
              {innLookup.message && (
                <div className="fp-span-2 fp-muted" style={{ fontSize: 12.5 }}>
                  {innLookup.message}
                </div>
              )}
              {innLookup.error && <div className="fp-form-error fp-span-2">{innLookup.error}</div>}
              <label className="fp-span-2">
                Наименование
                <input required value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} />
              </label>
              <label>
                КПП
                <input value={form.kpp} onChange={(e) => setForm((p) => ({ ...p, kpp: e.target.value }))} />
              </label>
              <label>
                ОГРН/ОГРНИП
                <input value={form.ogrn} onChange={(e) => setForm((p) => ({ ...p, ogrn: e.target.value }))} />
              </label>
              <label className="fp-span-2">
                Адрес
                <input value={form.address} onChange={(e) => setForm((p) => ({ ...p, address: e.target.value }))} />
              </label>
              <label>
                Телефон
                <input value={form.phone} onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))} />
              </label>
              <label>
                Email
                <input value={form.email} onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} />
              </label>

              {editing && (
                <div className="fp-span-2 fp-note" style={{ margin: 0 }}>
                  {editing.sdvf_buyer_id
                    ? `Связан с карточкой СДВФ №${editing.sdvf_buyer_id} — при синхронизации реквизиты придут оттуда.`
                    : "Карточки нет в СДВФ. Привяжите к существующей или создайте новую — иначе по ней не выставить Счёт/УПД."}
                </div>
              )}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}

              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? "Сохраняем…" : editing ? "Сохранить" : "Создать"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {linkFor && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setLinkFor(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Привязать «{linkFor.name}» к карточке СДВФ</h3>
              <button className="fp-icon-btn" onClick={() => setLinkFor(null)}>
                <X size={18} />
              </button>
            </div>
            <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
              <input
                placeholder="Поиск по названию или ИНН"
                value={sdvfSearch}
                onChange={(e) => setSdvfSearch(e.target.value)}
              />
              {sdvfError && <div className="fp-form-error">{sdvfError}</div>}
              {sdvfLoading ? (
                <div className="fp-loading">Загружаем карточки из СДВФ…</div>
              ) : (
                <div style={{ maxHeight: 340, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                  {sdvfList
                    .filter((b) => {
                      const q = sdvfSearch.trim().toLowerCase();
                      if (!q) return true;
                      return `${b.naming} ${b.inn}`.toLowerCase().includes(q);
                    })
                    .map((b) => (
                      <div
                        key={b.id}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 10,
                          padding: "8px 10px",
                          border: "1px solid var(--line)",
                          borderRadius: 8,
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: 600, fontSize: 13 }}>{b.naming}</div>
                          <div className="fp-muted" style={{ fontSize: 12 }}>
                            ИНН {b.inn}
                            {b.linked_counterparty_id ? " · уже привязана" : ""}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="fp-btn-tiny"
                          disabled={Boolean(b.linked_counterparty_id)}
                          onClick={() => confirmLink(b)}
                        >
                          Привязать
                        </button>
                      </div>
                    ))}
                  {sdvfList.length === 0 && !sdvfError && <div className="fp-empty">В СДВФ карточек не найдено</div>}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {contactsTarget && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setContactsFor(null))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Контактные лица — {contactsTarget.name}</h3>
              <button className="fp-icon-btn" onClick={() => setContactsFor(null)}>
                <X size={18} />
              </button>
            </div>
            <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              {(contactsTarget.contacts || []).length === 0 ? (
                <div className="fp-empty">Контактов пока нет</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {contactsTarget.contacts.map((c) => (
                    <div
                      key={c.id}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "8px 10px",
                        border: "1px solid var(--line)",
                        borderRadius: 8,
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 13 }}>
                          {c.full_name}
                          {c.is_primary ? " · основной" : ""}
                        </div>
                        <div className="fp-muted" style={{ fontSize: 12 }}>
                          {[c.position, c.phone, c.email].filter(Boolean).join(" · ") || "—"}
                        </div>
                      </div>
                      <span className="fp-row-actions">
                        <button
                          className="fp-icon-btn"
                          onClick={() => {
                            setEditingContactId(c.id);
                            setContactForm({
                              full_name: c.full_name || "",
                              position: c.position || "",
                              phone: c.phone || "",
                              email: c.email || "",
                              is_primary: Boolean(c.is_primary),
                            });
                          }}
                        >
                          <Pencil size={14} />
                        </button>
                        <button className="fp-icon-btn" onClick={() => removeContact(c)}>
                          <Trash2 size={14} />
                        </button>
                      </span>
                    </div>
                  ))}
                </div>
              )}

              <form className="fp-form-grid" onSubmit={saveContact}>
                <label className="fp-span-2">
                  ФИО
                  <input
                    required
                    value={contactForm.full_name}
                    onChange={(e) => setContactForm((p) => ({ ...p, full_name: e.target.value }))}
                  />
                </label>
                <label>
                  Должность
                  <input
                    value={contactForm.position}
                    onChange={(e) => setContactForm((p) => ({ ...p, position: e.target.value }))}
                  />
                </label>
                <label>
                  Телефон
                  <input
                    value={contactForm.phone}
                    onChange={(e) => setContactForm((p) => ({ ...p, phone: e.target.value }))}
                  />
                </label>
                <label>
                  Email
                  <input
                    value={contactForm.email}
                    onChange={(e) => setContactForm((p) => ({ ...p, email: e.target.value }))}
                  />
                </label>
                <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={contactForm.is_primary}
                    onChange={(e) => setContactForm((p) => ({ ...p, is_primary: e.target.checked }))}
                  />
                  Основной контакт
                </label>
                {contactError && <div className="fp-form-error fp-span-2">{contactError}</div>}
                <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
                  <button type="submit" className="fp-btn-primary">
                    {editingContactId ? "Сохранить контакт" : "Добавить контакт"}
                  </button>
                  {editingContactId && (
                    <button
                      type="button"
                      className="fp-btn-ghost"
                      onClick={() => {
                        setEditingContactId(null);
                        setContactForm(CONTACT_EMPTY);
                      }}
                    >
                      Отмена
                    </button>
                  )}
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
