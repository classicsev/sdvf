export const ROLE_LABELS = {
  admin: "Администратор",
  operator: "Оператор ввода",
  payroll_operator: "Оператор ЗП",
  project_manager: "Руководитель проекта",
  viewer: "Наблюдатель",
};

// Видимость разделов навигации по ролям (см. таблицу прав в README).
export const ROLE_NAV = {
  admin: ["dashboard", "transactions", "payroll", "reports", "automation", "reference", "audit", "users"],
  operator: ["dashboard", "transactions", "reports", "reference"],
  payroll_operator: ["payroll", "audit"],
  project_manager: ["dashboard", "transactions", "reports"],
  viewer: ["dashboard", "transactions", "payroll", "reports", "reference"],
};

export function canEditTransactions(role) {
  return role === "admin" || role === "operator";
}

export function canEditReference(role) {
  return role === "admin";
}

export function canEditPayroll(role) {
  return role === "admin" || role === "payroll_operator";
}

export function canEditAutomation(role) {
  return role === "admin";
}

export function canEditPlanning(role) {
  return role === "admin";
}
