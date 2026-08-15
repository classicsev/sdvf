"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "../../lib/api";
import { AuthProvider, useAuth } from "../../lib/auth-context";
import Login from "../../components/Login";

const CLIENT_NAMES = {
  sdvf: "СДВФ",
};

function ConsentScreen({ redirectUri, state, clientName, isLink }) {
  const { token } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [emailSentTo, setEmailSentTo] = useState("");

  async function handleContinue() {
    setBusy(true);
    setError("");
    try {
      const purpose = isLink ? "link" : "login";
      const { redirect_url, email_sent_to } = await api.ssoConsent(token, {
        redirect_uri: redirectUri,
        state,
        purpose,
      });
      if (email_sent_to) {
        // purpose=link: активной сессии в браузере недостаточно (могла остаться
        // от другого человека) — код придёт только по ссылке из письма.
        setEmailSentTo(email_sent_to);
        setBusy(false);
        return;
      }
      window.location.href = redirect_url;
    } catch (err) {
      setError(err.message || "Не удалось подтвердить вход");
      setBusy(false);
    }
  }

  if (emailSentTo) {
    return (
      <div className="fp-login-page">
        <div className="fp-login-card" style={{ textAlign: "center" }}>
          <div className="fp-brand-mark" style={{ margin: "0 auto 14px" }}>
            ₽
          </div>
          <h2 style={{ fontFamily: "'Fraunces', serif", fontSize: 18, margin: "0 0 10px" }}>
            Проверьте почту
          </h2>
          <p style={{ fontSize: 13, color: "#5B6472" }}>
            Письмо со ссылкой для подтверждения привязки отправлено на <b>{emailSentTo}</b>. Перейдите по
            ней, чтобы завершить привязку к {clientName} — ссылка действует 30 минут.
          </p>
        </div>
      </div>
    );
  }

  function handleCancel() {
    const url = new URL(redirectUri);
    url.searchParams.set("error", "access_denied");
    url.searchParams.set("state", state);
    window.location.href = url.toString();
  }

  return (
    <div className="fp-login-page">
      <div className="fp-login-card" style={{ textAlign: "center" }}>
        <div className="fp-brand-mark" style={{ margin: "0 auto 14px" }}>
          ₽
        </div>
        <h2 style={{ fontFamily: "'Fraunces', serif", fontSize: 18, margin: "0 0 10px" }}>
          {isLink ? "Привязка аккаунта СДВФ" : "Вход через Учёт Движения"}
        </h2>
        <p style={{ fontSize: 13, color: "#5B6472", marginBottom: 18 }}>
          {isLink ? (
            <>
              <b>{clientName}</b> запрашивает привязку этого аккаунта Учёта к вашему аккаунту в{" "}
              {clientName}. Мы отправим письмо на ваш подтверждённый email — привязка завершится только
              после перехода по ссылке из письма.
            </>
          ) : (
            <>
              <b>{clientName}</b> хочет получить доступ к вашему email и имени, чтобы войти под тем же
              аккаунтом.
            </>
          )}
        </p>
        {error && <div className="fp-form-error" style={{ marginBottom: 12 }}>{error}</div>}
        <button
          type="button"
          className="fp-btn-primary"
          style={{ justifyContent: "center", width: "100%", marginBottom: 8 }}
          disabled={busy}
          onClick={handleContinue}
        >
          {busy ? "Входим…" : "Продолжить"}
        </button>
        <button
          type="button"
          onClick={handleCancel}
          disabled={busy}
          style={{ background: "none", border: "none", color: "#5B6472", fontSize: 12.5, cursor: "pointer" }}
        >
          Отмена
        </button>
      </div>
    </div>
  );
}

function SsoConsentInner() {
  const { user, loading } = useAuth();
  const searchParams = useSearchParams();
  const redirectUri = searchParams.get("redirect_uri");
  const state = searchParams.get("state");
  const clientKey = searchParams.get("client");
  const isLink = searchParams.get("purpose") === "link";

  if (!redirectUri || !state) {
    return (
      <div className="fp-login-page">
        <div className="fp-login-card" style={{ textAlign: "center" }}>
          <p style={{ color: "#B23A48", fontSize: 13.5 }}>Некорректная ссылка входа.</p>
        </div>
      </div>
    );
  }

  if (loading) return <div className="fp-login-page">Загрузка…</div>;
  if (!user) return <Login />;

  return (
    <ConsentScreen
      redirectUri={redirectUri}
      state={state}
      clientName={CLIENT_NAMES[clientKey] || "Внешний сервис"}
      isLink={isLink}
    />
  );
}

export default function SsoConsentPage() {
  return (
    <AuthProvider>
      <Suspense fallback={<div className="fp-login-page">Загрузка…</div>}>
        <SsoConsentInner />
      </Suspense>
    </AuthProvider>
  );
}
