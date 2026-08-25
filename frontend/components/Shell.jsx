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
  UserCircle,
  Languages,
  Briefcase,
} from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth-context";
import { useTranslation } from "../lib/i18n";
import { ROLE_NAV, NAV_MODULE, isModuleEnabled, roleLabel } from "../lib/roles";
import ProfileModal from "./ProfileModal";
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
  { key: "dashboard", icon: LayoutDashboard },
  { key: "transactions", icon: FileText },
  { key: "payroll", icon: Users },
  { key: "reports", icon: Landmark },
  { key: "automation", icon: Zap },
  { key: "projects", icon: Briefcase },
  { key: "reference", icon: Settings },
  { key: "audit", icon: History },
  { key: "users", icon: Users },
  { key: "api-keys", icon: KeyRound },
  { key: "warehouse", icon: WarehouseIcon },
  { key: "modules", icon: ToggleLeft },
];

// Тот же компонент, что вкладка "Проекты" в Справочниках — отдельная точка
// входа слева продублирует её (см. решение пользователя 2026-08-25: не
// убирать из Справочников, просто добавить второй вход), не отдельная
// реализация.
function ProjectsView() {
  return <Reference initialTab="projects" />;
}

const VIEW_COMPONENTS = {
  dashboard: Dashboard,
  transactions: Transactions,
  payroll: Payroll,
  reports: Reports,
  automation: Automation,
  projects: ProjectsView,
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
  const { locale, setLocale, t } = useTranslation();
  const companies = user.companies || [];
  const userRoles = [...new Set(companies.map((m) => m.role))];
  const allowed = [
    ...new Set(userRoles.flatMap((role) => ROLE_NAV[role] || [])),
    ...(userRoles.some((role) => MODULES_NAV_ROLES.includes(role)) ? ["modules"] : []),
  ].filter((key) =>
    companies.some((membership) => isModuleEnabled(membership.company, NAV_MODULE[key]))
  );
  const [view, setView] = useState(allowed[0] || "dashboard");
  const [resendState, setResendState] = useState("idle"); // idle | busy | sent
  const [profileOpen, setProfileOpen] = useState(false);

  const ActiveView = VIEW_COMPONENTS[view] || (() => null);
  const meta = { eyebrow: t(`view.${view}.eyebrow`), title: t(`view.${view}.title`) };

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
          <span>{t("shell.verifyBanner")}</span>
          <button onClick={handleResend} disabled={resendState !== "idle"}>
            {resendState === "sent"
              ? t("shell.resendSent")
              : resendState === "busy"
              ? t("shell.resendBusy")
              : t("shell.resendIdle")}
          </button>
        </div>
      )}
      <div className="fp-root">
      <aside className="fp-sidebar">
        <div className="fp-brand">
          <div className="fp-brand-mark">₽</div>
          <div>
            <div className="fp-brand-name">{t("shell.brandName")}</div>
            <div className="fp-brand-sub">{t("shell.brandSub")}</div>
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
              {t(`nav.${item.key}`)}
            </button>
          ))}
        </nav>

        <div className="fp-sidebar-foot">
          <button
            type="button"
            className="fp-logout-btn"
            onClick={() => setLocale(locale === "ru" ? "zh" : "ru")}
            title="RU / 中文"
          >
            <Languages size={14} /> {t("shell.languageToggle")}
          </button>
          <div className="fp-role-box">{user.role ? roleLabel(t, user.role) : ""}</div>
          <div className="fp-role-hint">
            {user.full_name}
            {user.email ? ` · ${user.email}` : ""}
          </div>
          <button className="fp-logout-btn" onClick={() => setProfileOpen(true)}>
            <UserCircle size={14} /> {t("shell.profile")}
          </button>
          <button className="fp-logout-btn" onClick={logout}>
            <LogOut size={14} /> {t("shell.logout")}
          </button>
        </div>
      </aside>

      {profileOpen && <ProfileModal onClose={() => setProfileOpen(false)} />}

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
