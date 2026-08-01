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
  const { data: users, loading, error, reload } = useResource(() => api.listUsers(token), [token]);
  const { data: projects } = useResource(() => api.listProjects(token), [token]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(FORM_EMPTY);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  function openAdd() {
    setEditingId(null);
    setForm(FORM_EMPTY);
    setFormError("");
    setModalOpen(true);
  }

  function openEdit(u) {
    setEditingId(u.id);
    setForm({
      email: u.email,
      full_name: u.full_name,
      password: "",
      role: u.role,
      project_id: u.project_id || "",
    });
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
        await api.updateUser(token, editingId, payload);
      } else {
        await api.createUser(token, {
          email: form.email,
          full_name: form.full_name,
          password: form.password,
          role: form.role,
          project_id: form.role === "project_manager" ? form.project_id || null : null,
        });
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
    try {
      if (u.is_active === false) {
        await api.updateUser(token, u.id, { is_active: true });
      } else {
        await api.deleteUser(token, u.id);
      }
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <div />
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
                <th>ФИО</th>
                <th>Email</th>
                <th>Роль</th>
                <th className="center">Активен</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(users || []).map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td className="fp-muted">{u.email}</td>
                  <td>{ROLE_LABELS[u.role] || u.role}</td>
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
              ))}
              {(users || []).length === 0 && (
                <tr>
                  <td colSpan={5} className="fp-empty">
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
