"use client";

import { Fragment, useState } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt } from "../lib/format";
import { useTranslation } from "../lib/i18n";

const TAB_KEYS = ["cashflow", "pnl", "balance", "debt", "profitability", "calendar"];

// Селектор компании для отчётов — общий для всех вкладок (см. план "Мульти-компании").
// Пусто по умолчанию = сводно по всем доступным компаниям.
function CompanyFilter({ companyId, onChange }) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  if (companies.length <= 1) return null;
  return (
    <select value={companyId} onChange={(e) => onChange(e.target.value)} style={{ marginRight: 8 }}>
      <option value="">{t("dashboard.allCompanies")}</option>
      {companies.map((m) => (
        <option key={m.company.id} value={m.company.id}>
          {m.company.name}
        </option>
      ))}
    </select>
  );
}

function CashflowTab({ token }) {
  const { t } = useTranslation();
  const [period, setPeriod] = useState("");
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.cashflowReport(token, { period: period || undefined, company_id: companyId || undefined }),
    [token, period, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} />
        {period && (
          <button className="fp-btn-tiny" style={{ marginLeft: 8 }} onClick={() => setPeriod("")}>
            {t("reports.resetMonthly")}
          </button>
        )}
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{period ? t("reports.col.category") : t("reports.col.period")}</th>
                <th className="right">{t("dashboard.table.income")}</th>
                <th className="right">{t("dashboard.table.expense")}</th>
                <th className="right">{t("dashboard.table.netFlow")}</th>
              </tr>
            </thead>
            <tbody>
              {(period ? data?.by_category : data?.by_month || []).map((row) => (
                <tr key={row.category_id || row.period}>
                  <td>{row.category || row.period}</td>
                  <td className="right fp-mono fp-amount-income">{fmt(row.income, "RUB")}</td>
                  <td className="right fp-mono fp-amount-expense">{fmt(row.expense, "RUB")}</td>
                  <td className="right fp-mono">{fmt(row.net, "RUB")}</td>
                </tr>
              ))}
              {(period ? data?.by_category : data?.by_month || [])?.length === 0 && (
                <tr>
                  <td colSpan={4} className="fp-empty">
                    {t("reports.noData")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PnlTab({ token }) {
  const { t } = useTranslation();
  const [period, setPeriod] = useState("");
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.pnlReport(token, { period: period || undefined, company_id: companyId || undefined }),
    [token, period, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input
          type="month"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          placeholder={t("reports.currentMonth")}
        />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        data && (
          <div className="fp-panel">
            <div className="fp-panel-head">
              <h3>
                {t("reports.pnlTitle")} · {data.period_from} — {data.period_to}
              </h3>
            </div>
            <div className="fp-ledger">
              <div className="ledger-row">
                <span className="label">{t("reports.revenue")}</span>
                <span className="fill" />
                <span className="value fp-amount-income">{fmt(data.revenue, "RUB")}</span>
              </div>
              {data.expenses.map((row) => (
                <div className="ledger-row" key={row.group}>
                  <span className="label">{row.group}</span>
                  <span className="fill" />
                  <span className="value">{fmt(row.amount, "RUB")}</span>
                </div>
              ))}
              <div className="ledger-row">
                <span className="label">{t("reports.totalExpenses")}</span>
                <span className="fill" />
                <span className="value fp-amount-expense">{fmt(data.total_expense, "RUB")}</span>
              </div>
              <div className="ledger-row fp-ledger-total">
                <span className="label">{t("reports.netProfit")}</span>
                <span className="fill" />
                <span className="value">{fmt(data.net_profit, "RUB")}</span>
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function BalanceTab({ token }) {
  const { t } = useTranslation();
  const [asOf, setAsOf] = useState("");
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.balanceReport(token, { as_of: asOf || undefined, company_id: companyId || undefined }),
    [token, asOf, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder={t("reports.today")} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        data && (
          <div className="fp-grid-2">
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>{t("reports.assetsAsOf", { date: data.as_of })}</h3>
              </div>
              <div className="fp-ledger">
                <div className="ledger-row">
                  <span className="label">{t("reports.cash")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.cash_rub, "RUB")}</span>
                </div>
                <div className="ledger-row fp-ledger-total">
                  <span className="label">{t("reports.totalAssets")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.assets.total_rub, "RUB")}</span>
                </div>
              </div>
            </div>
            <div className="fp-panel">
              <div className="fp-panel-head">
                <h3>{t("reports.liabilities")}</h3>
              </div>
              <div className="fp-ledger">
                <div className="ledger-row">
                  <span className="label">{t("reports.payableToStaff")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.payable_to_staff_rub, "RUB")}</span>
                </div>
                <div className="ledger-row fp-ledger-total">
                  <span className="label">{t("reports.totalLiabilities")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.liabilities.total_rub, "RUB")}</span>
                </div>
                <div className="ledger-row">
                  <span className="label">{t("reports.retainedEarnings")}</span>
                  <span className="fill" />
                  <span className="value">{fmt(data.retained_earnings_rub, "RUB")}</span>
                </div>
              </div>
            </div>
          </div>
        )
      )}
      <p className="fp-note">{t("reports.balanceNote")}</p>
    </div>
  );
}

function DebtTab({ token }) {
  const { t } = useTranslation();
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.debtReport(token, { company_id: companyId || undefined }),
    [token, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("reports.counterparty")}</th>
                <th>{t("reports.type")}</th>
                <th className="right">{t("reports.netTurnover")}</th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((row) => (
                <tr key={row.counterparty_id}>
                  <td>{row.name}</td>
                  <td className="fp-muted">{row.type === "debtor" ? t("reports.debtor") : t("reports.creditor")}</td>
                  <td className="right fp-mono">{fmt(row.net_amount_rub, "RUB")}</td>
                </tr>
              ))}
              {(data || []).length === 0 && (
                <tr>
                  <td colSpan={3} className="fp-empty">
                    {t("reports.noCounterpartyOps")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ProfitabilityTab({ token }) {
  const { t } = useTranslation();
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.profitabilityReport(token, { company_id: companyId || undefined }),
    [token, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("reports.project")}</th>
                <th className="right">{t("reports.revenue")}</th>
                <th className="right">{t("dashboard.table.expense")}</th>
                <th className="right">{t("reports.profit")}</th>
                <th className="right">{t("reports.margin")}</th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((row) => (
                <tr key={row.project_id || "unallocated"}>
                  <td>{row.project}</td>
                  <td className="right fp-mono fp-amount-income">{fmt(row.revenue, "RUB")}</td>
                  <td className="right fp-mono fp-amount-expense">{fmt(row.expense, "RUB")}</td>
                  <td className="right fp-mono">{fmt(row.profit, "RUB")}</td>
                  <td className="right fp-mono">{row.margin === null ? "—" : `${(row.margin * 100).toFixed(1)}%`}</td>
                </tr>
              ))}
              {(data || []).length === 0 && (
                <tr>
                  <td colSpan={5} className="fp-empty">
                    {t("reports.noProjectOps")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CalendarTab({ token }) {
  const { t } = useTranslation();
  const [year, setYear] = useState(new Date().getFullYear());
  const [companyId, setCompanyId] = useState("");
  const { data, loading, error } = useResource(
    () => api.paymentCalendar(token, { quarter: String(year), company_id: companyId || undefined }),
    [token, year, companyId]
  );

  return (
    <div>
      <div style={{ marginBottom: 14 }}>
        <CompanyFilter companyId={companyId} onChange={setCompanyId} />
        <input type="number" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 100 }} />
      </div>
      <p className="fp-note" style={{ marginBottom: 14 }}>
        {t("reports.planningHint")}
      </p>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table fp-calendar-table">
            <thead>
              <tr>
                <th>{t("reports.col.category")}</th>
                {[1, 2, 3, 4].map((q) => (
                  <th key={q} className="center" colSpan={2}>
                    Q{q}
                  </th>
                ))}
              </tr>
              <tr>
                <th></th>
                {[1, 2, 3, 4].map((q) => (
                  <Fragment key={q}>
                    <th className="right">{t("reports.plan")}</th>
                    <th className="right">{t("reports.fact")}</th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data?.rows || []).map((row) => (
                <tr key={row.category_id}>
                  <td>{row.category}</td>
                  {row.quarters.map((q) => (
                    <Fragment key={q.quarter}>
                      <td className="right fp-mono fp-muted">{fmt(q.plan, "RUB")}</td>
                      <td className={`right fp-mono ${q.deviation < 0 ? "fp-amount-expense" : "fp-amount-income"}`}>
                        {fmt(q.fact, "RUB")}
                      </td>
                    </Fragment>
                  ))}
                </tr>
              ))}
              {(data?.rows || []).length === 0 && (
                <tr>
                  <td colSpan={9} className="fp-empty">
                    {t("reports.noCalendarData", { year })}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const TAB_COMPONENTS = {
  cashflow: CashflowTab,
  pnl: PnlTab,
  balance: BalanceTab,
  debt: DebtTab,
  profitability: ProfitabilityTab,
  calendar: CalendarTab,
};

export default function Reports() {
  const { token } = useAuth();
  const { t } = useTranslation();
  const [tab, setTab] = useState("cashflow");
  const ActiveTab = TAB_COMPONENTS[tab];

  return (
    <div className="fp-dash">
      <div className="fp-tabs">
        {TAB_KEYS.map((key) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {t(`reports.tab.${key}`)}
          </button>
        ))}
      </div>
      <ActiveTab token={token} />
    </div>
  );
}
