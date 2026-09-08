"use client";

import { Wallet, ArrowUpRight, ArrowDownRight, TrendingUp, TrendingDown } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { useTranslation } from "../lib/i18n";

// Тот же виджет "Табло" (остаток/приход/расход/чистый поток), что и на
// Дашборде (Dashboard.jsx::KpiCard) — вынесен сюда отдельным компонентом,
// чтобы показывать его же на вкладках Операций/Отчётов/Проектов (по просьбе
// пользователя, 2026-09-07), не трогая рабочий код самого Dashboard.jsx.

function formatPeriodLabel(from, to) {
  if (!from || !to) return "";
  if (from === to) return fmtDate(from);
  return `${fmtDate(from)} — ${fmtDate(to)}`;
}

function trendPct(current, prev) {
  if (!prev) return null;
  return ((current - prev) / Math.abs(prev)) * 100;
}

function TrendBadge({ pct, invert }) {
  const { t } = useTranslation();
  if (pct === null || !Number.isFinite(pct)) return null;
  const isGood = invert ? pct <= 0 : pct >= 0;
  const Icon = pct >= 0 ? TrendingUp : TrendingDown;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        fontSize: 11.5,
        fontFamily: "'IBM Plex Mono', monospace",
        color: isGood ? "var(--accent)" : "var(--expense)",
      }}
      title={t("dashboard.trendTitle")}
    >
      <Icon size={12} />
      {pct >= 0 ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

function KpiCard({ label, value, tone, icon, periodLabel, trendPctValue, invertTrend }) {
  return (
    <div className={`fp-kpi fp-kpi-${tone}`}>
      <div className="fp-kpi-top">
        <span className="fp-kpi-label">{label}</span>
        <span className="fp-kpi-icon">{icon}</span>
      </div>
      <div className="fp-kpi-value">{value}</div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
        {periodLabel && (
          <span className="fp-muted" style={{ fontSize: 11 }}>
            {periodLabel}
          </span>
        )}
        <TrendBadge pct={trendPctValue} invert={invertTrend} />
      </div>
    </div>
  );
}

// companyId — undefined/"" значит "по всем доступным компаниям" (как и в
// остальных отчётах). range — "today"|"week"|"month"|"quarter"|"year".
export default function BalanceKpiRow({ companyId, range = "month" }) {
  const { token } = useAuth();
  const { t } = useTranslation();
  const { data: summary } = useResource(
    () => api.dashboardSummary(token, { range, company_id: companyId || undefined }),
    [token, range, companyId]
  );

  if (!summary) return null;

  const netFlow = summary.net_flow_rub;
  const prevNetFlow = summary.prev_net_flow_rub;
  const periodLabel = formatPeriodLabel(summary.period_from, summary.period_to);

  return (
    <section className="fp-kpi-row">
      <KpiCard
        label={t("dashboard.kpi.totalBalance")}
        value={fmt(summary.total_balance_rub, "RUB")}
        tone="neutral"
        icon={<Wallet size={16} />}
        periodLabel={t("dashboard.kpi.asOfToday")}
      />
      <KpiCard
        label={t("dashboard.kpi.income")}
        value={fmt(summary.period_income_rub, "RUB")}
        tone="income"
        icon={<ArrowUpRight size={16} />}
        periodLabel={periodLabel}
        trendPctValue={trendPct(summary.period_income_rub, summary.prev_period_income_rub)}
      />
      <KpiCard
        label={t("dashboard.kpi.expense")}
        value={fmt(summary.period_expense_rub, "RUB")}
        tone="expense"
        icon={<ArrowDownRight size={16} />}
        periodLabel={periodLabel}
        trendPctValue={trendPct(summary.period_expense_rub, summary.prev_period_expense_rub)}
        invertTrend
      />
      <KpiCard
        label={t("dashboard.kpi.netFlow")}
        value={`${netFlow >= 0 ? "+" : ""}${fmt(netFlow, "RUB")}`}
        tone={netFlow >= 0 ? "income" : "expense"}
        icon={netFlow >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
        periodLabel={t("dashboard.kpi.netFlowSub")}
        trendPctValue={trendPct(netFlow, prevNetFlow)}
      />
    </section>
  );
}
