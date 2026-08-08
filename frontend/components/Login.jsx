"use client";

import { useState } from "react";
import { useAuth } from "../lib/auth-context";
import OAuthButtons from "./OAuthButtons";

export default function Login({ onSwitchToRegister }) {
  const { login } = useAuth();
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
      setError(err.message || "Не удалось войти");
    } finally {
      setBusy(false);
    }
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
            <div style={{ fontSize: 11, color: "#5B6472" }}>финансовый контур</div>
          </div>
        </div>
        <form className="fp-login-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </label>
          <label>
            Пароль
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
            {busy ? "Входим…" : "Войти"}
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
              Новая компания? Зарегистрироваться
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
