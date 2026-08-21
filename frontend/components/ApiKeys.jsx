"use client";

import { useState } from "react";
import { backdropClickProps } from "../lib/modalBackdrop";
import { Plus, X, Trash2, Copy, Check } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";
import { useTranslation } from "../lib/i18n";

export default function ApiKeys() {
  const { token } = useAuth();
  const { t } = useTranslation();
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
    if (!window.confirm(t("apiKeys.revokeConfirm", { name: key.name }))) return;
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
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>{t("apiKeys.title")}</h3>
        <button type="button" className="fp-btn-tiny" onClick={openAdd}>
          <Plus size={13} /> {t("apiKeys.newKey")}
        </button>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("apiKeys.col.name")}</th>
                <th>{t("apiKeys.col.key")}</th>
                <th>{t("apiKeys.col.onBehalfOf")}</th>
                <th className="center">{t("apiKeys.col.status")}</th>
                <th>{t("apiKeys.col.created")}</th>
                <th>{t("apiKeys.col.lastUsed")}</th>
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
                      {k.is_active ? t("apiKeys.active") : t("apiKeys.revoked")}
                    </span>
                  </td>
                  <td className="fp-muted">{fmtDate(k.created_at)}</td>
                  <td className="fp-muted">{k.last_used_at ? fmtDate(k.last_used_at) : t("apiKeys.neverUsed")}</td>
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
                    {t("apiKeys.noKeys")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
        <p className="fp-note" style={{ padding: "0 16px 16px" }}>
          {t("apiKeys.note")}
        </p>
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("apiKeys.newKeyTitle")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            {createdKey ? (
              <div className="fp-form-grid">
                <div className="fp-note fp-span-2">{t("apiKeys.saveNowNote")}</div>
                <label className="fp-span-2">
                  {t("apiKeys.col.key")}
                  <div style={{ display: "flex", gap: 8 }}>
                    <input readOnly value={createdKey} style={{ fontFamily: "monospace" }} />
                    <button type="button" className="fp-btn-tiny" onClick={handleCopy}>
                      {copied ? <Check size={13} /> : <Copy size={13} />}
                      {copied ? t("apiKeys.copied") : t("apiKeys.copy")}
                    </button>
                  </div>
                </label>
                <div className="fp-modal-foot fp-span-2">
                  <button type="button" className="fp-btn-primary" onClick={() => setModalOpen(false)}>
                    {t("apiKeys.done")}
                  </button>
                </div>
              </div>
            ) : (
              <form className="fp-form-grid" onSubmit={handleSubmit}>
                <label className="fp-span-2">
                  {t("apiKeys.col.name")}
                  <input
                    required
                    placeholder={t("apiKeys.namePlaceholder")}
                    value={form.name}
                    onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  />
                </label>
                <label className="fp-span-2">
                  {t("apiKeys.onBehalfOfUser")}
                  <select
                    value={form.user_id}
                    onChange={(e) => setForm((p) => ({ ...p, user_id: e.target.value }))}
                  >
                    <option value="">{t("apiKeys.myself")}</option>
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
                    {t("common.cancel")}
                  </button>
                  <button type="submit" className="fp-btn-primary" disabled={saving}>
                    {saving ? t("modules.creating") : t("modules.create")}
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
