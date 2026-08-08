"use client";

import { useState } from "react";
import {
  LayoutDashboard,
  FileText,
  Users,
  Settings,
  Landmark,
  Zap,
  History,
  LogOut,
  KeyRound,
  Warehouse as WarehouseIcon,
  ToggleLeft,
} from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { ROLE_LABELS, ROLE_NAV, NAV_MODULE, isModuleEnabled } from "../lib/roles";
import Dashboard from "./Dashboard";
import Transactions from "./Transactions";
import Payroll from "./Payroll";
import Reports from "./Reports";
import Automation from "./Automation";
import Reference from "./Reference";
import Audit from "./Audit";
import UsersView from "./UsersView";
import ApiKeys from "./ApiKeys";
import WarehouseView from "./Warehouse";
import CompanyModules from "./CompanyModules";

const NAV_ITEMS = [
  { key: "dashboard", label: "Дашборд", icon: LayoutDashboard },
  { key: "transactions", label: "Операции", icon: FileText },
  { key: "payroll", label: "Зарплата", icon: Users },
  { key: "reports", label: "Отчёты", icon: Landmark },
  { key: "automation", label: "Автоматизация", icon: Zap },
  { key: "reference", label: "Справочники", icon: Settings },
  { key: "audit", label: "Аудит", icon: History },
  { key: "users", label: "Пользователи", icon: Users },
  { key: "api-keys", label: "API-ключи", icon: KeyRound },
  { key: "warehouse", label: "Склад", icon: WarehouseIcon },
  { key: "modules", label: "Модули", icon: ToggleLeft },
];

const VIEW_META = {
  dashboard: { eyebrow: "Обзор", title: "Дашборд" },
  transactions: { eyebrow: "Оперативный учёт", title: "Операции" },
  payroll: { eyebrow: "Начислено · Выплачено · Остаток", title: "Зарплата" },
  reports: { eyebrow: "Управленческая отчётность", title: "Отчёты" },
  automation: { eyebrow: "Автоматизация ввода данных", title: "Автоматизация" },
  reference: { eyebrow: "Настройка справочников", title: "Справочники" },
  audit: { eyebrow: "Журнал действий пользователей", title: "Аудит" },
  users: { eyebrow: "Управление доступом", title: "Пользователи" },
  "api-keys": { eyebrow: "Доступ для внешних систем", title: "API-ключи" },
  warehouse: { eyebrow: "Остатки · Движения · Производство", title: "Склад" },
  modules: { eyebrow: "Тариф компании", title: "Модули" },
};

const VIEW_COMPONENTS = {
  dashboard: Dashboard,
  transactions: Transactions,
  payroll: Payroll,
  reports: Reports,
  automation: Automation,
  reference: Reference,
  audit: Audit,
  users: UsersView,
  "api-keys": ApiKeys,
  warehouse: WarehouseView,
  modules: CompanyModules,
};

// "Модули" — только admin, независимо от ROLE_NAV (управляет тарифом компании,
// должен быть доступен даже когда все продуктовые модули выключены).
const MODULES_NAV_ROLES = ["admin"];

export default function Shell() {
  const { user, token, logout } = useAuth();
  const allowed = [
    ...(ROLE_NAV[user.role] || []),
    ...(MODULES_NAV_ROLES.includes(user.role) ? ["modules"] : []),
  ].filter((key) => isModuleEnabled(user.company, NAV_MODULE[key]));
  const [view, setView] = useState(allowed[0] || "dashboard");
  const [resendState, setResendState] = useState("idle"); // idle | busy | sent

  const ActiveView = VIEW_COMPONENTS[view] || (() => null);
  const meta = VIEW_META[view] || {};

  async function handleResend() {
    setResendState("busy");
    try {
      await api.resendVerification(token);
      setResendState("sent");
    } catch {
      setResendState("idle");
    }
  }

  return (
    <>
      {/* У OAuth-пользователей без email (user.email пуст) подтверждать нечего */}
      {!user.email_verified && user.email && (
        <div className="fp-verify-banner">
          <span>Email не подтверждён. Проверьте почту (и папку «Спам»).</span>
          <button onClick={handleResend} disabled={resendState !== "idle"}>
            {resendState === "sent"
              ? "Письмо отправлено"
              : resendState === "busy"
              ? "Отправляем…"
              : "Отправить письмо повторно"}
          </button>
        </div>
      )}
      <div className="fp-root">
      <aside className="fp-sidebar">
        <div className="fp-brand">
          <div className="fp-brand-mark">₽</div>
          <div>
            <div className="fp-brand-name">Учёт&nbsp;Движения</div>
            <div className="fp-brand-sub">финансовый контур</div>
          </div>
        </div>

        <nav className="fp-nav">
          {NAV_ITEMS.filter((item) => allowed.includes(item.key)).map((item) => (
            <button
              key={item.key}
              className={`fp-nav-item ${view === item.key ? "active" : ""}`}
              onClick={() => setView(item.key)}
            >
              <item.icon size={18} strokeWidth={1.75} />
              {item.label}
            </button>
          ))}
        </nav>

        <div className="fp-sidebar-foot">
          <div className="fp-role-box">{ROLE_LABELS[user.role] || user.role}</div>
          <div className="fp-role-hint">
            {user.full_name}
            {user.email ? ` · ${user.email}` : ""}
          </div>
          <button className="fp-logout-btn" onClick={logout}>
            <LogOut size={14} /> Выйти
          </button>
        </div>
      </aside>

      <main className="fp-main">
        <header className="fp-topbar">
          <div>
            <div className="fp-eyebrow">{meta.eyebrow}</div>
            <h1>{meta.title}</h1>
          </div>
        </header>

        <ActiveView />
      </main>
      </div>
    </>
  );
}
