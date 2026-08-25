"use client";

import { useRef, useState } from "react";
import { Paperclip, Trash2, Upload } from "lucide-react";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmtDate } from "../lib/format";
import { useTranslation } from "../lib/i18n";

// Универсальный список вложений — монтируется в формы Заказа/Операции (см.
// HANDOVER.md, "Вложения"). entityType/entityId — полиморфная пара, как на
// бэкенде (Attachment.entity_type/entity_id). Ничего не показывает, пока нет
// entityId (черновик ещё не сохранён — вложения нужен реальный id сущности).
export default function AttachmentList({ token, entityType, entityId, canEdit = true }) {
  const { t } = useTranslation();
  const { data: attachments, loading, reload } = useResource(
    () => (entityId ? api.listAttachments(token, entityType, entityId) : Promise.resolve([])),
    [token, entityType, entityId]
  );
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  if (!entityId) return null;

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      await api.uploadAttachment(token, entityType, entityId, file);
      reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm(t("attachments.deleteConfirm"))) return;
    try {
      await api.deleteAttachment(token, id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  return (
    <div className="fp-span-2" style={{ borderTop: "1px solid var(--line)", paddingTop: 10, marginTop: 4 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ fontSize: 12, color: "var(--ink-soft)", display: "flex", alignItems: "center", gap: 5 }}>
          <Paperclip size={13} /> {t("attachments.title")}
        </div>
        {canEdit && (
          <>
            <button
              type="button"
              className="fp-btn-tiny"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Upload size={13} /> {uploading ? t("attachments.uploading") : t("attachments.upload")}
            </button>
            <input ref={fileInputRef} type="file" hidden onChange={handleFileChange} />
          </>
        )}
      </div>
      {error && <div className="fp-form-error">{error}</div>}
      {loading ? (
        <div className="fp-muted" style={{ fontSize: 12.5 }}>
          {t("common.loading")}
        </div>
      ) : !attachments?.length ? (
        <div className="fp-muted" style={{ fontSize: 12.5 }}>
          {t("attachments.empty")}
        </div>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
          {attachments.map((a) => (
            <li key={a.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
              <a href={`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}${a.url}`} target="_blank" rel="noopener noreferrer">
                {a.filename}
              </a>
              <span className="fp-muted" style={{ fontSize: 11.5 }}>
                {fmtDate(a.created_at)}
              </span>
              {canEdit && (
                <button type="button" className="fp-icon-btn" onClick={() => handleDelete(a.id)} title={t("common.delete")}>
                  <Trash2 size={13} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
