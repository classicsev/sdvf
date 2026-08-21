"use client";

import { useState } from "react";
import { Languages } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { useTranslation } from "../lib/i18n";
import OAuthButtons from "./OAuthButtons";

export default function Login({ onSwitchToRegister }) {
  const { login } = useAuth();
  const { t, locale, setLocale } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message || t("auth.loginFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fp-login-page">
      <div className="fp-login-card">
        <div className="fp-login-brand" style={{ justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div className="fp-brand-mark">₽</div>
            <div>
              <div style={{ fontFamily: "'Fraunces', serif", fontWeight: 600, fontSize: 15 }}>
                {t("shell.brandName")}
              </div>
              <div style={{ fontSize: 11, color: "#5B6472" }}>{t("auth.brandSubLogin")}</div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setLocale(locale === "ru" ? "zh" : "ru")}
            title="RU / 中文"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              background: "none",
              border: "1px solid #E7E1D3",
              borderRadius: 6,
              padding: "4px 8px",
              cursor: "pointer",
              fontSize: 12,
              color: "#5B6472",
            }}
          >
            <Languages size={13} /> {t("shell.languageToggle")}
          </button>
        </div>
        <form className="fp-login-form" onSubmit={handleSubmit}>
          <label>
            {t("modules.email")}
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </label>
          <label>
            {t("auth.password")}
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <div className="fp-form-error">{error}</div>}
          <button
            type="submit"
            className="fp-btn-primary"
            disabled={busy}
            style={{ justifyContent: "center", marginTop: 6 }}
          >
            {busy ? t("auth.loggingIn") : t("auth.login")}
          </button>
        </form>
        <OAuthButtons />
        {onSwitchToRegister && (
          <div style={{ marginTop: 16, textAlign: "center" }}>
            <button
              type="button"
              onClick={onSwitchToRegister}
              style={{
                background: "none",
                border: "none",
                color: "#2F6F5E",
                fontSize: 12.5,
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              {t("auth.newCompanyRegister")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
