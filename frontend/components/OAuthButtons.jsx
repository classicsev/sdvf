"use client";

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useTranslation } from "../lib/i18n";

const LABEL_KEYS = {
  vk: "auth.oauth.vk",
  yandex: "auth.oauth.yandex",
  sber: "auth.oauth.sber",
};

// Кнопка показывается только для провайдеров, у которых на бэкенде задан
// client_id (см. GET /auth/oauth/providers) — пока не подключён, кнопки просто нет.
export default function OAuthButtons() {
  const { t } = useTranslation();
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
      <div className="fp-login-divider">{t("auth.or")}</div>
      <div className="fp-oauth-list">
        {providers.map((provider) => (
          <a key={provider} className="fp-oauth-btn" href={api.oauthStartUrl(provider)}>
            {LABEL_KEYS[provider] ? t(LABEL_KEYS[provider]) : provider}
          </a>
        ))}
        {sdvfEnabled && (
          <a className="fp-oauth-btn" href={api.sdvfLoginStartUrl()}>
            {t("auth.oauth.sdvf")}
          </a>
        )}
      </div>
    </>
  );
}
