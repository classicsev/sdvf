"use client";

import { useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import OAuthButtons from "./OAuthButtons";

export default function Register({ onSwitchToLogin }) {
  const { applyToken } = useAuth();
  const [companyName, setCompanyName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pdnConsent, setPdnConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Токен уже получен, но ещё не применён к сессии — сначала показываем
  // предупреждение про папку "Спам", и только после того, как пользователь
  // его закроет, реально входим (см. applyToken в auth-context.jsx).
  const [pendingToken, setPendingToken] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { access_token } = await api.registerCompany({
        company_name: companyName,
        admin_full_name: fullName,
        admin_email: email,
        admin_password: password,
        pdn_consent: pdnConsent,
      });
      setPendingToken(access_token);
    } catch (err) {
      setError(err.message || "Не удалось зарегистрировать компанию");
    } finally {
      setBusy(false);
    }
  }

  if (pendingToken) {
    return (
      <div className="fp-login-page">
        <div className="fp-login-card fp-register-notice">
          <div className="fp-brand-mark">₽</div>
          <h2>Компания зарегистрирована</h2>
          <p>
            Мы отправили письмо для подтверждения на <b>{email}</b>.
          </p>
          <div className="fp-spam-hint">
            Письмо, скорее всего, попадёт в папку «Спам» — это обычное дело для нового
            почтового отправителя. Проверьте её и пометьте письмо как «Не спам», чтобы
            следующие письма приходили нормально.
          </div>
          <p>Подтверждать email не обязательно прямо сейчас — доступ уже открыт.</p>
          <button
            type="button"
            className="fp-btn-primary"
            style={{ justifyContent: "center", width: "100%" }}
            onClick={() => applyToken(pendingToken)}
          >
            Перейти в аккаунт
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fp-login-page">
      <div className="fp-login-card">
        <div className="fp-login-brand">
          <div className="fp-brand-mark">₽</div>
          <div>
            <div style={{ fontFamily: "'Fraunces', serif", fontWeight: 600, fontSize: 15 }}>
              Учёт Движения
            </div>
            <div style={{ fontSize: 11, color: "#5B6472" }}>регистрация компании</div>
          </div>
        </div>
        <form className="fp-login-form" onSubmit={handleSubmit}>
          <label>
            Название компании
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              required
              autoFocus
            />
          </label>
          <label>
            Ваше имя
            <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </label>
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </label>
          <label className="fp-switch" style={{ marginTop: 2 }}>
            <input
              type="checkbox"
              checked={pdnConsent}
              onChange={(e) => setPdnConsent(e.target.checked)}
            />
            <span>
              Даю согласие на обработку персональных данных в соответствии с{" "}
              <a href="/privacy" target="_blank" rel="noopener noreferrer">
                Политикой обработки персональных данных
              </a>
            </span>
          </label>
          {error && <div className="fp-form-error">{error}</div>}
          <button
            type="submit"
            className="fp-btn-primary"
            disabled={busy || !pdnConsent}
            style={{ justifyContent: "center", marginTop: 6 }}
          >
            {busy ? "Регистрируем…" : "Зарегистрировать компанию"}
          </button>
        </form>
        <OAuthButtons />
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <button
            type="button"
            onClick={onSwitchToLogin}
            style={{
              background: "none",
              border: "none",
              color: "#2F6F5E",
              fontSize: 12.5,
              cursor: "pointer",
              textDecoration: "underline",
            }}
          >
            Уже есть аккаунт? Войти
          </button>
        </div>
      </div>
    </div>
  );
}
