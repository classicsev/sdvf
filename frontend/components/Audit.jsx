"use client";

import { useMemo } from "react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";

const ENTITY_LABELS = {
  transaction: "Операция",
  payroll_accrual: "Начисление ЗП",
  payroll_payment: "Выплата ЗП",
};

const ACTION_LABELS = {
  create: "создал(а)",
  update: "изменил(а)",
  delete: "удалил(а)",
};

export default function Audit() {
  const { token, user } = useAuth();
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
          <div className="fp-loading">Загрузка…</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Пользователь</th>
                <th>Действие</th>
                <th>Объект</th>
              </tr>
            </thead>
            <tbody>
              {(log || []).map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.created_at).toLocaleString("ru-RU")}</td>
                  <td>{usersById[entry.user_id]?.full_name || entry.user_id}</td>
                  <td>
                    {ACTION_LABELS[entry.action] || entry.action} {ENTITY_LABELS[entry.entity_type] || entry.entity_type}
                  </td>
                  <td className="fp-muted fp-mono">{entry.entity_id}</td>
                </tr>
              ))}
              {(log || []).length === 0 && (
                <tr>
                  <td colSpan={4} className="fp-empty">
                    Записей пока нет
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
