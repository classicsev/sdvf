"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthProvider, useAuth } from "../../lib/auth-context";

const ERROR_MESSAGES = {
  provider_denied: "Вход отменён.",
  invalid_state: "Истекла или недействительна ссылка входа. Попробуйте снова.",
  no_access_token: "Провайдер не вернул токен доступа.",
  provider_error: "Сервис авторизации временно недоступен. Попробуйте позже.",
  account_disabled: "Учётная запись деактивирована.",
};

function Inner() {
  const { applyToken } = useAuth();
  const router = useRouter();
  const [error, setError] = useState(null);

  useEffect(() => {
    // VK/Яндекс/Sber ID редиректят сюда с backend'а: токен едет во fragment
    // (#token=...), не в query — он не должен попадать в серверные логи/Referer.
    const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
    const token = new URLSearchParams(hash).get("token");
    const queryError = new URLSearchParams(window.location.search).get("error");

    if (token) {
      applyToken(token)
        .then(() => router.replace("/"))
        .catch(() => setError("Не удалось войти. Попробуйте ещё раз."));
      return;
    }
    setError(ERROR_MESSAGES[queryError] || "Не удалось войти через выбранный сервис.");
  }, [applyToken, router]);

  return (
    <div className="fp-login-page">
      <div className="fp-login-card" style={{ textAlign: "center" }}>
        <div className="fp-brand-mark" style={{ margin: "0 auto 14px" }}>
          ₽
        </div>
        {error ? (
          <>
            <p style={{ color: "#B23A48", fontSize: 13.5, marginBottom: 14 }}>{error}</p>
            <a href="/" style={{ color: "#2F6F5E", fontSize: 12.5 }}>
              Вернуться на страницу входа
            </a>
          </>
        ) : (
          <p style={{ fontSize: 13.5, color: "#5B6472" }}>Выполняется вход…</p>
        )}
      </div>
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <AuthProvider>
      <Inner />
    </AuthProvider>
  );
}
