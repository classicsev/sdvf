"use client";

import { useState } from "react";
import { Plus, X, Pencil, Ban, RotateCcw } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { ROLE_LABELS } from "../lib/roles";

const FORM_EMPTY = { email: "", full_name: "", password: "", role: "viewer", project_id: "" };

export default function UsersView() {
  const { token, user: currentUser } = useAuth();
  const myCompanies = currentUser.companies || [];
  const multiCompany = myCompanies.length > 1;
  const editableCompanies = myCompanies.filter((m) => m.role === "admin");

  const [companyFilter, setCompanyFilter] = useState("");
  const { data: users, loading, error, reload } = useResource(
    () => api.listUsers(token, { company_id: companyFilter || undefined }),
    [token, companyFilter]
  );
  const { data: projects } = useResource(() => api.listProjects(token), [token]);

  // Роль пользователя в компании, которую сейчас показываем в таблице — при
  // просмотре "Все компании" берём первую компанию из списка пользователя,
  // при фильтре по конкретной — роль именно в ней.
  function firstMembershipRole(u) {
    return u.companies?.[0]?.role || u.role;
  }
  function roleInContext(u) {
    if (companyFilter) return u.companies?.find((c) => c.company.id === companyFilter)?.role || firstMembershipRole(u);
    return firstMembershipRole(u);
  }
  function targetCompanyFor(u) {
    return companyFilter || u.companies?.[0]?.company.id || u.company_id;
  }

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editingCompanyId, setEditingCompanyId] = useState(null);
  const [form, setForm] = useState(FORM_EMPTY);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  function openAdd() {
    setEditingId(null);
    setEditingCompanyId(null);
    setForm(FORM_EMPTY);
    const preselected = editableCompanies.find((m) => m.company.id === companyFilter) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setFormError("");
    setModalOpen(true);
  }

  function openEdit(u) {
    const companyId = targetCompanyFor(u);
    setEditingId(u.id);
    setEditingCompanyId(companyId);
    setForm({
      email: u.email,
      full_name: u.full_name,
      password: "",
      role: roleInContext(u),
      project_id: u.companies?.find((c) => c.company.id === companyId)?.project_id || "",
    });
    setFormCompanyId(companyId);
    setFormError("");
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      if (editingId) {
        const payload = {
          full_name: form.full_name,
          role: form.role,
          project_id: form.role === "project_manager" ? form.project_id || null : null,
        };
        if (form.password) payload.password = form.password;
        await api.updateUser(token, editingId, payload, editingCompanyId || undefined);
      } else {
        await api.createUser(
          token,
          {
            email: form.email,
            full_name: form.full_name,
            password: form.password,
            role: form.role,
            project_id: form.role === "project_manager" ? form.project_id || null : null,
          },
          formCompanyId || undefined
        );
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(u) {
    const action = u.is_active === false ? "восстановить" : "деактивировать";
    if (!window.confirm(`Точно ${action} пользователя «${u.full_name}»?`)) return;
    const companyId = targetCompanyFor(u) || undefined;
    try {
      if (u.is_active === false) {
        await api.updateUser(token, u.id, { is_active: true }, companyId);
      } else {
        await api.deleteUser(token, u.id, companyId);
      }
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        {multiCompany ? (
          <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
            <option value="">Все компании</option>
            {myCompanies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        ) : (
          <div />
        )}
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Новый пользователь
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
                {multiCompany && <th>Компания</th>}
                <th>ФИО</th>
                <th>Email</th>
                <th>Роль</th>
                <th className="center">Активен</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(users || []).map((u) => {
                const role = roleInContext(u);
                return (
                <tr key={u.id}>
                  {multiCompany && (
                    <td className="fp-muted">
                      {companyFilter
                        ? myCompanies.find((m) => m.company.id === companyFilter)?.company.name || "—"
                        : (u.companies || []).map((c) => c.company.name).join(", ") || "—"}
                    </td>
                  )}
                  <td>{u.full_name}</td>
                  <td className="fp-muted">{u.email}</td>
                  <td>{ROLE_LABELS[role] || role}</td>
                  <td className="center">
                    <span className={`fp-status-badge ${u.is_active === false ? "danger" : "ok"}`}>
                      {u.is_active === false ? "Нет" : "Да"}
                    </span>
                  </td>
                  <td className="fp-table-actions-col">
                    <span className="fp-row-actions">
                      <button className="fp-icon-btn" onClick={() => openEdit(u)}>
                        <Pencil size={14} />
                      </button>
                      {u.id !== currentUser.id && (
                        <button className="fp-icon-btn" onClick={() => toggleActive(u)} title={u.is_active === false ? "Восстановить" : "Деактивировать"}>
                          {u.is_active === false ? <RotateCcw size={14} /> : <Ban size={14} />}
                        </button>
                      )}
                    </span>
                  </td>
                </tr>
                );
              })}
              {(users || []).length === 0 && (
                <tr>
                  <td colSpan={multiCompany ? 6 : 5} className="fp-empty">
                    Пользователей пока нет
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          «Удаление» деактивирует пользователя (блокирует вход), а не удаляет физически — на него уже могут
          ссылаться операции и записи аудита.
        </p>
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editingId ? "Редактировать пользователя" : "Новый пользователь"}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  Компания
                  {editingId ? (
                    <input
                      type="text"
                      disabled
                      value={myCompanies.find((m) => m.company.id === editingCompanyId)?.company.name || ""}
                    />
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
              <label className="fp-span-2">
                ФИО
                <input
                  required
                  value={form.full_name}
                  onChange={(e) => setForm((p) => ({ ...p, full_name: e.target.value }))}
                />
              </label>
              <label className="fp-span-2">
                Email
                <input type="email" required disabled={!!editingId} value={form.email} onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} />
              </label>
              <label className="fp-span-2">
                {editingId ? "Новый пароль (оставьте пустым, чтобы не менять)" : "Пароль"}
                <input
                  type="password"
                  required={!editingId}
                  value={form.password}
                  onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
                />
              </label>
              <label>
                Роль
                <select
                  disabled={editingId === currentUser.id}
                  value={form.role}
                  onChange={(e) => setForm((p) => ({ ...p, role: e.target.value }))}
                >
                  {Object.entries(ROLE_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {form.role === "project_manager" && (
                <label>
                  Проект
                  <select
                    value={form.project_id}
                    onChange={(e) => setForm((p) => ({ ...p, project_id: e.target.value }))}
                  >
                    <option value="">— не указан —</option>
                    {(projects || []).map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}

              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  Отмена
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? "Сохраняем…" : editingId ? "Сохранить" : "Создать"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
