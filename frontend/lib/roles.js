export const ROLE_LABELS = {
  admin: "Администратор",
  operator: "Оператор ввода",
  payroll_operator: "Оператор ЗП",
  project_manager: "Руководитель проекта",
  viewer: "Наблюдатель",
  warehouse_operator: "Оператор склада",
};

// Видимость разделов навигации по ролям (см. таблицу прав в README).
export const ROLE_NAV = {
  admin: [
    "dashboard",
    "transactions",
    "payroll",
    "reports",
    "automation",
    "reference",
    "audit",
    "users",
    "api-keys",
    "warehouse",
  ],
  operator: ["dashboard", "transactions", "reports", "reference"],
  payroll_operator: ["payroll", "audit"],
  project_manager: ["dashboard", "transactions", "reports"],
  viewer: ["dashboard", "transactions", "payroll", "reports", "reference", "warehouse"],
  warehouse_operator: ["warehouse"],
};

// Какой оплаченный модуль компании открывает раздел навигации — чисто UX-подсказка,
// чтобы не показывать пункт меню, который всё равно ответит 403. Реальная защита —
// всегда на бэкенде (require_module в соответствующих роутерах).
export const NAV_MODULE = {
  dashboard: "finance",
  transactions: "finance",
  payroll: "finance",
  reports: "finance",
  automation: "finance",
  reference: "finance",
  warehouse: "warehouse",
  // audit, users, api-keys, modules — без модуль-гейта, доступны независимо от тарифа
};

export function isModuleEnabled(company, moduleKey) {
  if (!moduleKey) return true;
  if (!company) return true;
  return Boolean(company[`module_${moduleKey}_enabled`]);
}

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

export function canEditWarehouse(role) {
  return role === "admin" || role === "warehouse_operator";
}
