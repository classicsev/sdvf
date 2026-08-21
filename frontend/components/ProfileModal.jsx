"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { backdropClickProps } from "../lib/modalBackdrop";
import { useTranslation } from "../lib/i18n";

export default function ProfileModal({ onClose }) {
  const { token, user, refreshUser } = useAuth();
  const { t } = useTranslation();
  const [fullName, setFullName] = useState(user.full_name || "");
  const [gender, setGender] = useState(user.gender || "");
  const [phone, setPhone] = useState(user.phone || "");
  const [telegram, setTelegram] = useState(user.telegram || "");
  const [maxMessenger, setMaxMessenger] = useState(user.max_messenger || "");
  const [avatarFile, setAvatarFile] = useState(null);
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const avatarSrc = avatarPreview || (user.avatar_url ? `${API_BASE()}${user.avatar_url}` : null);

  function API_BASE() {
    return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  }

  function handleAvatarChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setAvatarFile(file);
    setAvatarPreview(URL.createObjectURL(file));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      if (avatarFile) {
        await api.uploadMyAvatar(token, avatarFile);
      }
      await api.updateMyProfile(token, {
        full_name: fullName,
        gender: gender || "",
        phone,
        telegram,
        max_messenger: maxMessenger,
      });
      await refreshUser();
      onClose();
    } catch (err) {
      setError(err.message || t("profile.saveFailed"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fp-modal-backdrop" {...backdropClickProps(onClose)}>
      <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="fp-modal-head">
          <h3>{t("profile.title")}</h3>
          <button className="fp-icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form className="fp-form-grid" onSubmit={handleSubmit}>
          <div className="fp-span-2" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: "50%",
                overflow: "hidden",
                background: "var(--surface-soft, #eee)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {avatarSrc ? (
                <img src={avatarSrc} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <span style={{ fontSize: 24 }}>{(user.full_name || "?").charAt(0).toUpperCase()}</span>
              )}
            </div>
            <label style={{ fontSize: 12 }}>
              {t("profile.photo")}
              <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handleAvatarChange} />
            </label>
          </div>

          <label>
            {t("profile.name")}
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </label>

          <label>
            {t("profile.gender")}
            <select value={gender} onChange={(e) => setGender(e.target.value)}>
              <option value="">{t("profile.genderNotSpecified")}</option>
              <option value="M">{t("profile.gender.M")}</option>
              <option value="F">{t("profile.gender.F")}</option>
            </select>
          </label>

          <label>
            {t("profile.phone")}
            <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+7 900 000-00-00" />
          </label>

          <label>
            Telegram
            <input value={telegram} onChange={(e) => setTelegram(e.target.value)} placeholder="@username" />
          </label>

          <label className="fp-span-2">
            MAX
            <input
              value={maxMessenger}
              onChange={(e) => setMaxMessenger(e.target.value)}
              placeholder={t("profile.maxLoginPlaceholder")}
            />
          </label>

          {error && <div className="fp-form-error fp-span-2">{error}</div>}

          <div className="fp-modal-foot fp-span-2">
            <button type="button" className="fp-btn-ghost" onClick={onClose}>
              {t("common.cancel")}
            </button>
            <button type="submit" className="fp-btn-primary" disabled={saving}>
              {saving ? t("profile.saving") : t("common.save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
