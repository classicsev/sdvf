"use client";

import { useMemo } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { useTranslation } from "../lib/i18n";

// Не все action/entity_type, встречающиеся в реальном логе (sync,
// order_generate_invoice, integration и т.п.), имеют перевод — для остальных
// t() вернул бы сам технический ключ ("audit.action.sync"), что хуже
// исходной строки. Переводим только известные, для прочих показываем как есть.
const ACTION_KEYS = { create: "audit.action.create", update: "audit.action.update", delete: "audit.action.delete" };
const ENTITY_KEYS = {
  transaction: "audit.entity.transaction",
  payroll_accrual: "audit.entity.payroll_accrual",
  payroll_payment: "audit.entity.payroll_payment",
};

export default function Audit() {
  const { token, user } = useAuth();
  const { t, locale } = useTranslation();
  const isAdmin = (user.companies || []).some((m) => m.role === "admin");
  const { data: log, loading, error } = useResource(() => api.listAuditLog(token), [token]);
  const { data: users } = useResource(
    () => (isAdmin ? api.listUsers(token) : Promise.resolve([])),
    [token, isAdmin]
  );
  const usersById = useMemo(() => Object.fromEntries((users || []).map((u) => [u.id, u])), [users]);

  return (
    <div className="fp-dash">
      {error && <div className="fp-error-banner">{error}</div>}
      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                <th>{t("audit.time")}</th>
                <th>{t("audit.user")}</th>
                <th>{t("audit.action")}</th>
                <th>{t("audit.object")}</th>
              </tr>
            </thead>
            <tbody>
              {(log || []).map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.created_at).toLocaleString(locale === "zh" ? "zh-CN" : "ru-RU")}</td>
                  <td>{usersById[entry.user_id]?.full_name || entry.user_id}</td>
                  <td>
                    {ACTION_KEYS[entry.action] ? t(ACTION_KEYS[entry.action]) : entry.action}{" "}
                    {ENTITY_KEYS[entry.entity_type] ? t(ENTITY_KEYS[entry.entity_type]) : entry.entity_type}
                  </td>
                  <td className="fp-muted fp-mono">{entry.entity_id}</td>
                </tr>
              ))}
              {(log || []).length === 0 && (
                <tr>
                  <td colSpan={4} className="fp-empty">
                    {t("audit.noRecords")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
