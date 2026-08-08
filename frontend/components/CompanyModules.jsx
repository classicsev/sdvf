"use client";

import { useState } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";

const MODULES = [
  {
    key: "module_finance_enabled",
    title: "Учёт",
    description: "Операции, отчёты, зарплата, автоматизация и интеграции банков/CRM.",
  },
  {
    key: "module_warehouse_enabled",
    title: "Склад",
    description: "Остатки, движения, заказы, производство.",
  },
];

const SDVF_FIELDS = [
  { key: "sdvf_org_naming", label: "Наименование организации", required: true },
  { key: "sdvf_org_inn", label: "ИНН", required: true },
  { key: "sdvf_org_kpp", label: "КПП" },
  { key: "sdvf_org_ogrn", label: "ОГРН/ОГРНИП" },
  { key: "sdvf_org_address", label: "Адрес" },
  { key: "sdvf_org_phone", label: "Телефон" },
];

export default function CompanyModules() {
  const { token, user, refreshUser } = useAuth();
  const [busyKey, setBusyKey] = useState(null);
  const [error, setError] = useState("");
  const company = user.company;

  const [sdvfForm, setSdvfForm] = useState(
    Object.fromEntries(SDVF_FIELDS.map((f) => [f.key, company[f.key] || ""]))
  );
  const [sdvfSaving, setSdvfSaving] = useState(false);
  const [sdvfSaved, setSdvfSaved] = useState(false);

  async function toggle(moduleKey, value) {
    setError("");
    setBusyKey(moduleKey);
    try {
      await api.updateCompanyModules(token, { [moduleKey]: value });
      await refreshUser();
    } catch (err) {
      setError(err.message || "Не удалось сохранить");
    } finally {
      setBusyKey(null);
    }
  }

  async function saveSdvfForm(e) {
    e.preventDefault();
    setError("");
    setSdvfSaving(true);
    setSdvfSaved(false);
    try {
      await api.updateCompanyModules(token, sdvfForm);
      await refreshUser();
      setSdvfSaved(true);
    } catch (err) {
      setError(err.message || "Не удалось сохранить");
    } finally {
      setSdvfSaving(false);
    }
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <h3 style={{ margin: 0, fontFamily: "'Fraunces', serif" }}>Модули</h3>
      </div>

      {error && <div className="fp-error-banner">{error}</div>}

      <div className="fp-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <p className="fp-note" style={{ margin: 0 }}>
          Компания «{company.name}». Оплата пока не требуется — включайте и выключайте модули
          свободно, биллинг подключим позже.
        </p>
        {MODULES.map((m) => (
          <label
            key={m.key}
            className="fp-switch"
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: 12,
              border: "1px solid var(--line)",
              borderRadius: 8,
              cursor: busyKey ? "default" : "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={Boolean(company[m.key])}
              disabled={busyKey === m.key}
              onChange={(e) => toggle(m.key, e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <div>
              <div style={{ fontWeight: 600 }}>{m.title}</div>
              <div className="fp-muted" style={{ fontSize: 12.5 }}>
                {m.description}
              </div>
            </div>
          </label>
        ))}
      </div>

      <div className="fp-panel" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <div style={{ fontWeight: 600 }}>Реквизиты для СДВФ</div>
          <p className="fp-note" style={{ margin: "4px 0 0" }}>
            Нужны для генерации Счёт/УПД из карточки заказа в Складе — заполняются один раз.
          </p>
        </div>
        <form className="fp-form-grid" onSubmit={saveSdvfForm}>
          {SDVF_FIELDS.map((f) => (
            <label key={f.key}>
              {f.label}
              <input
                required={f.required}
                value={sdvfForm[f.key]}
                onChange={(e) => {
                  setSdvfSaved(false);
                  setSdvfForm((p) => ({ ...p, [f.key]: e.target.value }));
                }}
              />
            </label>
          ))}
          <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "flex-start" }}>
            <button type="submit" className="fp-btn-primary" disabled={sdvfSaving}>
              {sdvfSaving ? "Сохраняем…" : "Сохранить"}
            </button>
            {sdvfSaved && <span className="fp-muted" style={{ fontSize: 12.5 }}>Сохранено</span>}
          </div>
        </form>
      </div>
    </div>
  );
}
