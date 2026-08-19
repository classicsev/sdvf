"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";

const LABELS = {
  vk: "Войти через VK ID",
  yandex: "Войти через Яндекс ID",
  sber: "Войти через Sber ID",
};

// Кнопка показывается только для провайдеров, у которых на бэкенде задан
// client_id (см. GET /auth/oauth/providers) — пока не подключён, кнопки просто нет.
export default function OAuthButtons() {
  const [providers, setProviders] = useState([]);
  const [sdvfEnabled, setSdvfEnabled] = useState(false);

  useEffect(() => {
    api
      .listOAuthProviders()
      .then((data) => setProviders(data.providers || []))
      .catch(() => {});
    api
      .sdvfLoginEnabled()
      .then((data) => setSdvfEnabled(!!data.enabled))
      .catch(() => {});
  }, []);

  if (providers.length === 0 && !sdvfEnabled) return null;

  return (
    <>
      <div className="fp-login-divider">или</div>
      <div className="fp-oauth-list">
        {providers.map((provider) => (
          <a key={provider} className="fp-oauth-btn" href={api.oauthStartUrl(provider)}>
            {LABELS[provider] || provider}
          </a>
        ))}
        {sdvfEnabled && (
          <a className="fp-oauth-btn" href={api.sdvfLoginStartUrl()}>
            Войти через СДВФ
          </a>
        )}
      </div>
    </>
  );
}
