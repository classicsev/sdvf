// Русские значения по умолчанию — для мест, куда t() ещё не докинули (редко,
// в основном отладочные выводы); экраны используют roleLabel(t, role) /
// roleDescription(t, role) ниже, которые берут перевод из lib/i18n.js.
export const ROLE_LABELS = {
  admin: "Администратор",
  operator: "Оператор ввода",
  payroll_operator: "Оператор ЗП",
  project_manager: "Руководитель проекта",
  viewer: "Наблюдатель",
  warehouse_operator: "Оператор склада",
};

// Человеческие пояснения к ролям для форм выдачи доступа — держим рядом с
// ROLE_NAV/canEdit* ниже, чтобы описание и реальные права правились вместе.
export const ROLE_DESCRIPTIONS = {
  admin:
    "Полный доступ: все разделы, справочники, пользователи, API-ключи, интеграции и настройки компании.",
  operator:
    "Вводит и правит операции. Видит дашборд, операции, отчёты и справочники. Зарплата и склад недоступны.",
  payroll_operator:
    "Только зарплата: начисления и выплаты сотрудникам, плюс журнал аудита по ФОТ. Остальные разделы скрыты.",
  project_manager:
    "Дашборд, операции и отчёты в рамках закреплённого проекта. Данные других проектов не видит.",
  viewer:
    "Только просмотр — операции, зарплата, отчёты, справочники и склад. Ничего изменить не может.",
  warehouse_operator:
    "Только склад: остатки, движения, заказы и производство. Финансовые разделы недоступны.",
};

// t — из useTranslation() (lib/i18n.js). Роли — фиксированный набор (см.
// RoleEnum на бэкенде), поэтому t(`role.${role}`) всегда попадает в словарь.
export function roleLabel(t, role) {
  return t(`role.${role}`);
}

export function roleDescription(t, role) {
  return t(`roleDesc.${role}`);
}

// Видимость разделов навигации по ролям (см. таблицу прав в README).
export const ROLE_NAV = {
  admin: [
    "dashboard",
    "dashboard2",
    "transactions",
    "payroll",
    "reports",
    "automation",
    "projects",
    "reference",
    "audit",
    "users",
    "api-keys",
    "warehouse",
  ],
  operator: ["dashboard", "dashboard2", "transactions", "reports", "projects", "reference"],
  payroll_operator: ["payroll", "audit"],
  project_manager: ["dashboard", "dashboard2", "transactions", "reports"],
  viewer: ["dashboard", "dashboard2", "transactions", "payroll", "reports", "projects", "reference", "warehouse"],
  warehouse_operator: ["warehouse"],
};

// Какой оплаченный модуль компании открывает раздел навигации — чисто UX-подсказка,
// чтобы не показывать пункт меню, который всё равно ответит 403. Реальная защита —
// всегда на бэкенде (require_module в соответствующих роутерах).
export const NAV_MODULE = {
  dashboard: "finance",
  dashboard2: "finance",
  transactions: "finance",
  payroll: "finance",
  reports: "finance",
  automation: "finance",
  projects: "finance",
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

export function canEditWarehouse(role) {
  return role === "admin" || role === "warehouse_operator";
}
