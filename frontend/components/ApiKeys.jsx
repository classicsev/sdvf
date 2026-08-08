"use client";

import { useState } from "react";
import { Plus, X, Trash2, Copy, Check } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";

export default function ApiKeys() {
  const { token } = useAuth();
  const { data: keys, loading, error, reload } = useResource(() => api.listApiKeys(token), [token]);
  const { data: users } = useResource(() => api.listUsers(token), [token]);
  const usersById = Object.fromEntries((users || []).map((u) => [u.id, u]));

  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({ name: "", user_id: "" });
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [createdKey, setCreatedKey] = useState(null);
  const [copied, setCopied] = useState(false);

  function openAdd() {
    setForm({ name: "", user_id: "" });
    setFormError("");
    setCreatedKey(null);
    setCopied(false);
    setModalOpen(true);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const result = await api.createApiKey(token, {
        name: form.name,
        user_id: form.user_id || null,
      });
      setCreatedKey(result.key);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(createdKey);
    setCopied(true);
  }

  async function handleRevoke(key) {
    if (!window.confirm(`Отозвать ключ «${key.name}»? Все интеграции, использующие его, перестанут работать.`)) return;
    try {
      await api.revokeApiKey(token, key.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>API-ключи</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> Новый ключ
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
                <th>Название</th>
                <th>Ключ</th>
                <th>От имени</th>
                <th className="center">Статус</th>
                <th>Создан</th>
                <th>Использован</th>
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {(keys || []).map((k) => (
                <tr key={k.id}>
                  <td>{k.name}</td>
                  <td className="fp-muted">
                    <code>{k.key_prefix}…</code>
                  </td>
                  <td className="fp-muted">{usersById[k.user_id]?.email || k.user_id}</td>
                  <td className="center">
                    <span className={`fp-status-badge ${k.is_active ? "ok" : "warn"}`}>
                      {k.is_active ? "Активен" : "Отозван"}
                    </span>
                  </td>
                  <td className="fp-muted">{fmtDate(k.created_at)}</td>
                  <td className="fp-muted">{k.last_used_at ? fmtDate(k.last_used_at) : "ещё не использован"}</td>
                  <td className="fp-table-actions-col">
                    {k.is_active && (
                      <button className="fp-icon-btn" onClick={() => handleRevoke(k)}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {(keys || []).length === 0 && (
                <tr>
                  <td colSpan={7} className="fp-empty">
                    Ключей пока нет
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          Ключ авторизует запросы заголовком <code>X-API-Key</code> с теми же правами, что и у выбранного
          пользователя. Полное значение ключа показывается только один раз — сразу после создания.
        </p>
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" onClick={() => setModalOpen(false)}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>Новый API-ключ</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            {createdKey ? (
              <div className="fp-form-grid">
                <div className="fp-note fp-span-2">
                  Сохраните ключ сейчас — второй раз он показан не будет.
                </div>
                <label className="fp-span-2">
                  Ключ
                  <div style={{ display: "flex", gap: 8 }}>
                    <input readOnly value={createdKey} style={{ fontFamily: "monospace" }} />
                    <button type="button" className="fp-btn-tiny" onClick={handleCopy}>
                      {copied ? <Check size={13} /> : <Copy size={13} />}
                      {copied ? "Скопировано" : "Копировать"}
                    </button>
                  </div>
                </label>
                <div className="fp-modal-foot fp-span-2">
                  <button type="button" className="fp-btn-primary" onClick={() => setModalOpen(false)}>
                    Готово
                  </button>
                </div>
              </div>
            ) : (
              <form className="fp-form-grid" onSubmit={handleSubmit}>
                <label className="fp-span-2">
                  Название
                  <input
                    required
                    placeholder="Например: 1С:УНФ"
                    value={form.name}
                    onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  />
                </label>
                <label className="fp-span-2">
                  От имени пользователя
                  <select
                    value={form.user_id}
                    onChange={(e) => setForm((p) => ({ ...p, user_id: e.target.value }))}
                  >
                    <option value="">— я сам —</option>
                    {(users || []).map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name} ({u.email})
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
                    {saving ? "Создаём…" : "Создать"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
