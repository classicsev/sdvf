import React, { useState, useMemo } from "react";
import * as XLSX from "xlsx";
import {
  LayoutDashboard,
  FileText,
  Users,
  Settings,
  Plus,
  ArrowUpRight,
  ArrowDownRight,
  Wallet,
  X,
  ChevronDown,
  Lock,
  Landmark,
  AlertTriangle,
  CalendarClock,
  Tag,
  Building2,
  Contact,
  Pencil,
  CheckCircle2,
  History,
  Zap,
  Plug,
  KeyRound,
  TrendingUp,
  Package,
  HardDrive,
  Download,
  Check,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

/* ---------------------------------------------------------------------- */
/*  СПРАВОЧНЫЕ ДАННЫЕ (демо-данные на основе реальной структуры файлов)   */
/* ---------------------------------------------------------------------- */

const DEFAULT_ACCOUNTS = [
  { id: "acc1", name: "Альфа счет ТДЩ", currency: "RUB", balance: 96013 },
  { id: "acc2", name: "Т-б счет ТДЩ", currency: "RUB", balance: 17833.02 },
  { id: "acc3", name: "ИП ЩЭО Альфа", currency: "RUB", balance: 128479.19 },
  { id: "acc4", name: "ИП ЩЭО ТБ счет", currency: "RUB", balance: -8866.68 },
  { id: "acc5", name: "ТОФ Т-Б", currency: "RUB", balance: 12169.96 },
  { id: "acc6", name: "ИП ЩЛИ Альфа", currency: "RUB", balance: 4876.46 },
  { id: "acc7", name: "Юани наличка", currency: "CNY", balance: 4514 },
  { id: "acc8", name: "Юани Алипэй", currency: "CNY", balance: 27126 },
];

const RATES = { RUB: 1, CNY: 12.6 };

const DEFAULT_CATEGORIES = [
  { id: "c1", name: "Поступления от покупателей", type: "income", group: "Выручка" },
  { id: "c2", name: "Поступления от партнеров", type: "income", group: "Выручка" },
  { id: "c3", name: "Перенос остатков денег", type: "income", group: "Активы" },
  { id: "c4", name: "ЗП чистка Артём", type: "expense", group: "Расходы на обработку" },
  { id: "c5", name: "Комиссии банка", type: "expense", group: "Банковское обслуживание" },
  { id: "c6", name: "Реклама Facebook", type: "expense", group: "Рекламные расходы" },
  { id: "c7", name: "Озон для Бизнеса", type: "expense", group: "Коммерческие расходы" },
  { id: "c8", name: "АЗС рабочая заправка", type: "expense", group: "Коммерческие расходы" },
  { id: "c9", name: "услуги Ветслужбы (ветврачи)", type: "expense", group: "Другие расходы" },
  { id: "c10", name: "Возвраты клиентам", type: "expense", group: "Возвраты" },
  { id: "c11", name: "Расх. на строит/рем базы", type: "expense", group: "Другие расходы" },
];

const DEFAULT_PROJECTS = [
  { id: "p1", name: "Проект A" },
  { id: "p2", name: "Проект B" },
  { id: "p3", name: "Проект C" },
  { id: "p4", name: "Проект D" },
  { id: "p5", name: "Проект E" },
  { id: "p6", name: "Амбер" },
];

const SEED_TRANSACTIONS = [
  { id: 1, dateODDS: "2026-06-01", accountId: "acc3", categoryId: "c1", project: "Амбер", amount: 24542, type: "income", counterparty: "ИП Новоселецкий Амбер", commission: 0, comment: "" },
  { id: 2, dateODDS: "2026-06-01", accountId: "acc4", categoryId: "c1", project: "Проект A", amount: 31500, type: "income", counterparty: "ИП Мальшин", commission: 0, comment: "ТД-620 от 26.05" },
  { id: 3, dateODDS: "2026-06-01", accountId: "acc2", categoryId: "c4", project: null, amount: 46259.01, type: "expense", counterparty: "", commission: 458.01, comment: "Антон за май" },
  { id: 4, dateODDS: "2026-06-01", accountId: "acc4", categoryId: "c4", project: null, amount: 59571.82, type: "expense", counterparty: "", commission: 589.82, comment: "Таня часть за май" },
  { id: 5, dateODDS: "2026-06-01", accountId: "acc4", categoryId: "c4", project: null, amount: 70146.52, type: "expense", counterparty: "", commission: 694.52, comment: "Виталя за май" },
  { id: 6, dateODDS: "2026-06-01", accountId: "acc3", categoryId: "c11", project: null, amount: 4973, type: "expense", counterparty: "", commission: 0, comment: "леруа (крыша на бытовке)" },
  { id: 7, dateODDS: "2026-06-01", accountId: "acc3", categoryId: "c8", project: null, amount: 2134.5, type: "expense", counterparty: "", commission: 0, comment: "с 05.2026" },
  { id: 8, dateODDS: "2026-06-01", accountId: "acc3", categoryId: "c7", project: null, amount: 25179, type: "expense", counterparty: "", commission: 0, comment: "закупка на Озон" },
  { id: 9, dateODDS: "2026-06-01", accountId: "acc3", categoryId: "c9", project: null, amount: 10760, type: "expense", counterparty: "", commission: 0, comment: "Ветврач ВДК (Варвара) ежемесяч на ИП" },
  { id: 10, dateODDS: "2026-06-01", accountId: "acc1", categoryId: "c5", project: null, amount: 4990, type: "expense", counterparty: "", commission: 0, comment: "Комиссия за Пакет переводов «Альфа-платежи»" },
];

const MONTHLY_DEMO = [
  { month: "Янв", income: 0, expense: 0 },
  { month: "Фев", income: 0, expense: 0 },
  { month: "Мар", income: 0, expense: 0 },
  { month: "Апр", income: 0, expense: 0 },
  { month: "Май", income: 0, expense: 0 },
  { month: "Июн", income: 56042, expense: 225756.2 },
];

const ROLE_LABELS = {
  admin: "Администратор",
  operator: "Оператор ввода",
  payroll_operator: "Оператор ЗП",
  project_manager: "Руководитель проекта",
  viewer: "Только просмотр",
};

const ROLE_ACCESS = {
  admin: { views: ["dashboard", "transactions", "payroll", "reports", "automation", "reference", "audit"], editTransactions: true, editPayroll: true },
  operator: { views: ["dashboard", "transactions", "reports", "reference"], editTransactions: true, editPayroll: false },
  payroll_operator: { views: ["payroll"], editTransactions: false, editPayroll: true },
  project_manager: { views: ["dashboard", "transactions", "reports"], editTransactions: false, editPayroll: false, ownProjectOnly: "Проект A" },
  viewer: { views: ["dashboard", "transactions", "payroll", "reports", "reference"], editTransactions: false, editPayroll: false },
};

const DEFAULT_EMPLOYEES = [
  { id: "e1", name: "Иванова Мария", dept: "Чистка/Упаковка", type: "Самозанятый", accrued: 46259.01, paid: 46259.01 },
  { id: "e2", name: "Соколов Антон", dept: "Технический отдел", type: "ИП", accrued: 89500, paid: 70000 },
  { id: "e3", name: "Петрова Дарья", dept: "Отдел Контента", type: "Самозанятый", accrued: 52000, paid: 52000 },
  { id: "e4", name: "Кузнецов Виталий", dept: "Клиентский сервис", type: "Самозанятый", accrued: 70146.52, paid: 40000 },
  { id: "e5", name: "Разина Татьяна", dept: "Бухгалтерия", type: "ИП", accrued: 59571.82, paid: 59571.82 },
  { id: "e6", name: "Морозова Елена", dept: "HR", type: "Самозанятый", accrued: 38000, paid: 20000 },
  { id: "e7", name: "Волков Игорь", dept: "Отдел продаж", type: "ИП", accrued: 64000, paid: 64000 },
  { id: "e8", name: "Никитина Анна", dept: "Отдел маркетинга", type: "Самозанятый", accrued: 47500, paid: 30000 },
];

const DEFAULT_COUNTERPARTIES = [
  { id: "cp1", name: "ИП Новоселецкий Амбер", type: "Дебитор", amount: 0, status: "Погашено" },
  { id: "cp2", name: "ИП Мальшин", type: "Дебитор", amount: 12400, status: "Просрочено" },
  { id: "cp3", name: "Рекламное агентство «Норд»", type: "Кредитор", amount: 18500, status: "В срок" },
  { id: "cp4", name: "ООО «Логистик Плюс»", type: "Кредитор", amount: 0, status: "Погашено" },
  { id: "cp5", name: "Ветслужба ВДК", type: "Кредитор", amount: 10760, status: "В срок" },
];

const CALENDAR_ROWS = [
  { category: "Выручка", q: [{ plan: 850000, fact: 792000 }, { plan: 900000, fact: 911000 }, { plan: 950000, fact: 0 }, { plan: 1000000, fact: 0 }] },
  { category: "ФОТ (зарплата)", q: [{ plan: -420000, fact: -398000 }, { plan: -430000, fact: -441000 }, { plan: -440000, fact: 0 }, { plan: -450000, fact: 0 }] },
  { category: "Маркетинг", q: [{ plan: -120000, fact: -134000 }, { plan: -130000, fact: -119000 }, { plan: -140000, fact: 0 }, { plan: -140000, fact: 0 }] },
  { category: "Аренда и коммерч. расходы", q: [{ plan: -85000, fact: -83500 }, { plan: -85000, fact: -87200 }, { plan: -90000, fact: 0 }, { plan: -90000, fact: 0 }] },
  { category: "Налоги", q: [{ plan: -64000, fact: -64000 }, { plan: -68000, fact: -70500 }, { plan: -70000, fact: 0 }, { plan: -72000, fact: 0 }] },
];

const REFERENCE_TABS = {
  categories: { label: "Статьи", icon: "tag" },
  projects: { label: "Проекты", icon: "layout" },
  accounts: { label: "Счета", icon: "building" },
  counterparties: { label: "Контрагенты", icon: "contact" },
};

const PNL = {
  revenue: [
    { name: "Поступления от покупателей", amount: 780000 },
    { name: "Поступления от партнёров", amount: 132000 },
  ],
  cogs: [
    { name: "Себестоимость закупки (Озон/маркетплейсы)", amount: 210000 },
    { name: "Комиссии эквайринга и банков", amount: 18500 },
  ],
  opex: [
    { name: "ФОТ (зарплата и подрядчики)", amount: 398000 },
    { name: "Реклама и маркетинг", amount: 134000 },
    { name: "Аренда и коммерческие расходы", amount: 83500 },
    { name: "Прочие расходы", amount: 26800 },
  ],
};

const PROFITABILITY = [
  { project: "Проект A", revenue: 312000, directCosts: 168000 },
  { project: "Проект B", revenue: 198000, directCosts: 141000 },
  { project: "Проект C", revenue: 145000, directCosts: 52000 },
  { project: "Проект D", revenue: 96000, directCosts: 88000 },
  { project: "Амбер", revenue: 161000, directCosts: 61000 },
];

const AUTOMATION_RULES = [
  { id: "r1", condition: "Контрагент содержит «Wildberries»", action: "Статья → «Поступления от покупателей», Проект → «Проект A»", active: true },
  { id: "r2", condition: "Плательщик = ИП ЩЭО, комментарий содержит «АЗС»", action: "Статья → «АЗС рабочая заправка»", active: true },
  { id: "r3", condition: "Сумма < 500 ₽ и статья не задана", action: "Статья → «Комиссии банка»", active: true },
  { id: "r4", condition: "Контрагент содержит «Ozon»", action: "Статья → «Поступления от покупателей», Проект → «Проект B»", active: false },
  { id: "r5", condition: "Комментарий содержит «Ветслужба»", action: "Статья → «услуги Ветслужбы (ветврачи)»", active: true },
];

const INTEGRATIONS = [
  { id: "i1", name: "Т-Банк", type: "Банк", connected: true },
  { id: "i2", name: "Альфа-Банк", type: "Банк", connected: true },
  { id: "i3", name: "Wildberries", type: "Маркетплейс", connected: false },
  { id: "i4", name: "Ozon", type: "Маркетплейс", connected: true },
  { id: "i5", name: "ЮKassa", type: "Эквайринг", connected: false },
  { id: "i6", name: "amoCRM", type: "CRM", connected: false },
  { id: "i7", name: "1С:УНФ", type: "Учётная система", connected: false },
];

const AUDIT_LOG = [
  { id: "a1", time: "01.06.2026 18:42", user: "Соколов Антон", role: "Администратор", action: "Изменил статью «Реклама Facebook» в справочнике" },
  { id: "a2", time: "01.06.2026 16:10", user: "Иванова Мария", role: "Оператор ввода", action: "Добавила операцию «Комиссии банка», 4 990 ₽" },
  { id: "a3", time: "01.06.2026 14:55", user: "Разина Татьяна", role: "Оператор ввода", action: "Внесла выплату «Таня часть за май», 59 571.82 ₽" },
  { id: "a4", time: "31.05.2026 11:20", user: "Соколов Антон", role: "Администратор", action: "Подключил интеграцию «Ozon»" },
  { id: "a5", time: "30.05.2026 09:07", user: "Морозова Елена", role: "Оператор ввода", action: "Изменила остаток по счёту «Юани Алипэй»" },
  { id: "a6", time: "29.05.2026 17:33", user: "Соколов Антон", role: "Администратор", action: "Создал правило автоматизации «Wildberries → Проект A»" },
];

const FIXED_ASSETS = [
  { id: "fa1", name: "Ноутбуки сотрудников (5 шт.)", value: 425000, monthlyDepreciation: 8850 },
  { id: "fa2", name: "Офисная мебель и оборудование", value: 180000, monthlyDepreciation: 3600 },
  { id: "fa3", name: "Серверное оборудование", value: 96000, monthlyDepreciation: 2400 },
];

const INVENTORY_VALUE = { warehouseValue: 214000, unitsInStock: 1380, avgCost: 155 };

/* ---------------------------------------------------------------------- */
/*  ПОЛЯ ФОРМ ДЛЯ СПРАВОЧНИКОВ (add/edit)                                 */
/* ---------------------------------------------------------------------- */

const CATEGORY_FIELDS = [
  { key: "name", label: "Название статьи", type: "text", required: true },
  { key: "group", label: "Группа", type: "text" },
  {
    key: "type",
    label: "Тип",
    type: "select",
    options: [
      { value: "income", label: "Приход" },
      { value: "expense", label: "Расход" },
    ],
  },
];

const PROJECT_FIELDS = [{ key: "name", label: "Название проекта", type: "text", required: true }];

const ACCOUNT_FIELDS = [
  { key: "name", label: "Название счёта", type: "text", required: true },
  {
    key: "currency",
    label: "Валюта",
    type: "select",
    options: [
      { value: "RUB", label: "RUB" },
      { value: "CNY", label: "CNY" },
    ],
  },
  { key: "balance", label: "Остаток", type: "number" },
];

const COUNTERPARTY_FIELDS = [
  { key: "name", label: "Название контрагента", type: "text", required: true },
  {
    key: "type",
    label: "Тип",
    type: "select",
    options: [
      { value: "Дебитор", label: "Дебитор" },
      { value: "Кредитор", label: "Кредитор" },
    ],
  },
];

const EMPLOYEE_FIELDS = [
  { key: "name", label: "ФИО", type: "text", required: true },
  { key: "dept", label: "Отдел", type: "text" },
  {
    key: "type",
    label: "Тип занятости",
    type: "select",
    options: [
      { value: "Самозанятый", label: "Самозанятый" },
      { value: "ИП", label: "ИП" },
    ],
  },
];

/* ---------------------------------------------------------------------- */
/*  УНИВЕРСАЛЬНЫЙ ХУК ДЛЯ CRUD-СПИСКОВ (справочники, сотрудники)          */
/* ---------------------------------------------------------------------- */

function genId() {
  return `id_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function useCrudList(initial) {
  const [items, setItems] = useState(initial);

  function add(data) {
    setItems((prev) => [...prev, { id: genId(), ...data }]);
  }
  function update(id, data) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...data } : it)));
  }
  function remove(id) {
    setItems((prev) => prev.filter((it) => it.id !== id));
  }

  return [items, { add, update, remove }];
}

/* ---------------------------------------------------------------------- */
/*  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ                                               */
/* ---------------------------------------------------------------------- */

function fmt(amount, currency = "RUB") {
  const sym = currency === "CNY" ? "¥" : "₽";
  const v = Number(amount).toLocaleString("ru-RU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${v} ${sym}`;
}

function toRub(amount, currency) {
  return amount * (RATES[currency] || 1);
}

const VIEW_META = {
  dashboard: { eyebrow: "Обзор", title: "Дашборд" },
  transactions: { eyebrow: "Оперативный учёт", title: "Операции" },
  payroll: { eyebrow: "Начислено · Выплачено · Остаток", title: "Зарплата" },
  reports: { eyebrow: "Управленческая отчётность", title: "Отчёты" },
  automation: { eyebrow: "Автоматизация ввода данных", title: "Автоматизация" },
  reference: { eyebrow: "Настройка справочников", title: "Справочники" },
  audit: { eyebrow: "Журнал действий пользователей", title: "Аудит" },
};

const NAV_ITEMS = [
  { key: "dashboard", label: "Дашборд", icon: LayoutDashboard },
  { key: "transactions", label: "Операции", icon: FileText },
  { key: "payroll", label: "Зарплата", icon: Users },
  { key: "reports", label: "Отчёты", icon: Landmark },
  { key: "automation", label: "Автоматизация", icon: Zap },
  { key: "reference", label: "Справочники", icon: Settings },
  { key: "audit", label: "Аудит", icon: History },
];

/* ---------------------------------------------------------------------- */
/*  ГЛАВНЫЙ КОМПОНЕНТ                                                     */
/* ---------------------------------------------------------------------- */

export default function App() {
  const [view, setView] = useState("dashboard");
  const [role, setRole] = useState("admin");
  const [showRub, setShowRub] = useState(true);
  const [transactions, setTransactions] = useState(SEED_TRANSACTIONS);
  const [showForm, setShowForm] = useState(false);
  const [projectFilter, setProjectFilter] = useState("Все проекты");
  const [reportTab, setReportTab] = useState("calendar");
  const [refTab, setRefTab] = useState("categories");
  const [automationTab, setAutomationTab] = useState("rules");
  const [rules, setRules] = useState(AUTOMATION_RULES);
  const [integrations, setIntegrations] = useState(INTEGRATIONS);

  const [accounts, accountsCrud] = useCrudList(DEFAULT_ACCOUNTS);
  const [categories, categoriesCrud] = useCrudList(DEFAULT_CATEGORIES);
  const [projects, projectsCrud] = useCrudList(DEFAULT_PROJECTS);
  const [counterparties, counterpartiesCrud] = useCrudList(DEFAULT_COUNTERPARTIES);
  const [employees, employeesCrud] = useCrudList(DEFAULT_EMPLOYEES);

  const access = ROLE_ACCESS[role];
  const canEditTransactions = access.editTransactions;
  const canEditPayroll = access.editPayroll;

  function handleRoleChange(newRole) {
    setRole(newRole);
    const newAccess = ROLE_ACCESS[newRole];
    if (!newAccess.views.includes(view)) {
      setView(newAccess.views[0]);
    }
    if (newAccess.ownProjectOnly) {
      setProjectFilter(newAccess.ownProjectOnly);
    } else {
      setProjectFilter("Все проекты");
    }
  }

  const accountsById = useMemo(() => {
    const map = {};
    accounts.forEach((a) => (map[a.id] = a));
    return map;
  }, [accounts]);
  const categoriesById = useMemo(() => {
    const map = {};
    categories.forEach((c) => (map[c.id] = c));
    return map;
  }, [categories]);

  const filteredTransactions =
    projectFilter === "Все проекты"
      ? transactions
      : transactions.filter((t) => t.project === projectFilter);

  const totalBalanceRub = accounts.reduce(
    (sum, a) => sum + toRub(a.balance, a.currency),
    0
  );
  const periodIncome = transactions
    .filter((t) => t.type === "income")
    .reduce((s, t) => s + toRub(t.amount, accountsById[t.accountId].currency), 0);
  const periodExpense = transactions
    .filter((t) => t.type === "expense")
    .reduce((s, t) => s + toRub(t.amount, accountsById[t.accountId].currency), 0);
  const netFlow = periodIncome - periodExpense;

  function handleAddTransaction(tx) {
    setTransactions((prev) => [{ ...tx, id: prev.length + 1 }, ...prev]);
    setShowForm(false);
  }

  function handleExport() {
    const rows = filteredTransactions.map((t) => {
      const acc = accountsById[t.accountId];
      const cat = categoriesById[t.categoryId];
      return {
        "Дата ОДДС": t.dateODDS,
        "Счёт": acc.name,
        "Валюта": acc.currency,
        "Статья": cat.name,
        "Тип": t.type === "income" ? "Приход" : "Расход",
        "Проект": t.project || "",
        "Контрагент": t.counterparty || "",
        "Комментарий": t.comment || "",
        "Комиссия": t.commission || 0,
        "Сумма": t.amount,
        "Сумма, ₽": Math.round(toRub(t.amount, acc.currency) * 100) / 100,
      };
    });
    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Операции");
    XLSX.writeFile(wb, "operatsii_export.xlsx");
  }

  function toggleRule(id) {
    setRules((prev) => prev.map((r) => (r.id === id ? { ...r, active: !r.active } : r)));
  }

  function toggleIntegration(id) {
    setIntegrations((prev) =>
      prev.map((i) => (i.id === id ? { ...i, connected: !i.connected } : i))
    );
  }

  return (
    <div className="fp-root">
      <style>{CSS}</style>

      <aside className="fp-sidebar">
        <div className="fp-brand">
          <div className="fp-brand-mark">₽</div>
          <div>
            <div className="fp-brand-name">Учёт&nbsp;Движения</div>
            <div className="fp-brand-sub">финансовый контур</div>
          </div>
        </div>

        <div className="fp-stamp">ПРОТОТИП · ЭКРАН 1 из N</div>

        <nav className="fp-nav">
          {NAV_ITEMS.filter((item) => access.views.includes(item.key)).map((item) => (
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
          <div className="fp-role-box">
            <Lock size={13} />
            <select value={role} onChange={(e) => handleRoleChange(e.target.value)}>
              {Object.entries(ROLE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div className="fp-role-hint">
            {role === "payroll_operator" && "Видит только раздел «Зарплата»"}
            {role === "project_manager" && `Доступ только к «${access.ownProjectOnly}»`}
            {(role === "admin" || role === "operator" || role === "viewer") && "демо-переключатель роли"}
          </div>
        </div>
      </aside>

      <main className="fp-main">
        <header className="fp-topbar">
          <div>
            <div className="fp-eyebrow">{VIEW_META[view].eyebrow}</div>
            <h1>{VIEW_META[view].title}</h1>
          </div>

          <div className="fp-topbar-controls">
            <label className="fp-switch">
              <input
                type="checkbox"
                checked={showRub}
                onChange={(e) => setShowRub(e.target.checked)}
              />
              <span>Показывать в рублях (пересчёт по курсу)</span>
            </label>

            {view === "transactions" && (
              <div className="fp-select-wrap">
                <select
                  value={projectFilter}
                  onChange={(e) => setProjectFilter(e.target.value)}
                  disabled={!!access.ownProjectOnly}
                >
                  <option>Все проекты</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.name}>{p.name}</option>
                  ))}
                </select>
                <ChevronDown size={14} />
              </div>
            )}

            {view === "transactions" && (
              <button className="fp-btn-ghost" onClick={handleExport}>
                <Download size={15} /> Экспорт в Excel
              </button>
            )}

            {view === "transactions" && canEditTransactions && (
              <button className="fp-btn-primary" onClick={() => setShowForm(true)}>
                <Plus size={16} /> Новая операция
              </button>
            )}
          </div>
        </header>

        {view === "dashboard" && (
          <Dashboard
            accounts={accounts}
            totalBalanceRub={totalBalanceRub}
            periodIncome={periodIncome}
            periodExpense={periodExpense}
            netFlow={netFlow}
            showRub={showRub}
          />
        )}
        {view === "transactions" && (
          <TransactionsView
            transactions={filteredTransactions}
            accountsById={accountsById}
            categoriesById={categoriesById}
            canEdit={canEditTransactions}
            showRub={showRub}
          />
        )}
        {view === "payroll" && (
          <PayrollView canEdit={canEditPayroll} employees={employees} employeesCrud={employeesCrud} />
        )}
        {view === "reports" && (
          <ReportsView
            reportTab={reportTab}
            setReportTab={setReportTab}
            accounts={accounts}
            employees={employees}
            counterparties={counterparties}
          />
        )}
        {view === "automation" && (
          <AutomationView
            automationTab={automationTab}
            setAutomationTab={setAutomationTab}
            rules={rules}
            toggleRule={toggleRule}
            integrations={integrations}
            toggleIntegration={toggleIntegration}
            canEdit={role === "admin"}
          />
        )}
        {view === "reference" && (
          <ReferenceView
            refTab={refTab}
            setRefTab={setRefTab}
            canEdit={role === "admin"}
            categories={categories}
            projects={projects}
            accounts={accounts}
            counterparties={counterparties}
            categoriesCrud={categoriesCrud}
            projectsCrud={projectsCrud}
            accountsCrud={accountsCrud}
            counterpartiesCrud={counterpartiesCrud}
          />
        )}
        {view === "audit" && <AuditView />}
      </main>

      {showForm && (
        <TransactionForm
          accounts={accounts}
          categories={categories}
          projects={projects}
          onClose={() => setShowForm(false)}
          onSubmit={handleAddTransaction}
        />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ДАШБОРД                                                               */
/* ---------------------------------------------------------------------- */

function Dashboard({ accounts, totalBalanceRub, periodIncome, periodExpense, netFlow, showRub }) {
  return (
    <div className="fp-dash">
      <section className="fp-kpi-row">
        <KpiCard
          label="Общий остаток"
          value={fmt(totalBalanceRub, "RUB")}
          tone="neutral"
          icon={<Wallet size={16} />}
        />
        <KpiCard
          label="Приход за июнь"
          value={fmt(periodIncome, "RUB")}
          tone="income"
          icon={<ArrowUpRight size={16} />}
        />
        <KpiCard
          label="Расход за июнь"
          value={fmt(periodExpense, "RUB")}
          tone="expense"
          icon={<ArrowDownRight size={16} />}
        />
        <KpiCard
          label="Чистый поток"
          value={`${netFlow >= 0 ? "+" : ""}${fmt(netFlow, "RUB")}`}
          tone={netFlow >= 0 ? "income" : "expense"}
          icon={netFlow >= 0 ? <ArrowUpRight size={16} /> : <ArrowDownRight size={16} />}
        />
      </section>

      <section className="fp-grid-2">
        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>Движение денег, 2026 (демо-данные)</h3>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={MONTHLY_DEMO} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#E7E1D3" vertical={false} />
              <XAxis
                dataKey="month"
                tick={{ fontFamily: "IBM Plex Sans", fontSize: 12, fill: "#5B6472" }}
                axisLine={{ stroke: "#E7E1D3" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontFamily: "IBM Plex Mono", fontSize: 11, fill: "#5B6472" }}
                axisLine={false}
                tickLine={false}
                width={70}
                tickFormatter={(v) => v.toLocaleString("ru-RU")}
              />
              <Tooltip
                formatter={(v) => fmt(v, "RUB")}
                contentStyle={{
                  fontFamily: "IBM Plex Sans",
                  fontSize: 13,
                  border: "1px solid #E7E1D3",
                  borderRadius: 6,
                }}
              />
              <Area type="monotone" dataKey="income" name="Приход" stroke="#2F6F5E" fill="#DCEAE4" strokeWidth={2} />
              <Bar dataKey="expense" name="Расход" fill="#A8503F" radius={[3, 3, 0, 0]} barSize={22} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>Остатки по счетам</h3>
          </div>
          <div className="fp-ledger">
            {accounts.map((a) => (
              <div className="ledger-row" key={a.id}>
                <span className="label">
                  {a.name}
                  <span className={`fp-currency-badge ${a.currency}`}>{a.currency}</span>
                </span>
                <span className="fill" />
                <span
                  className="value"
                  style={{ color: a.balance < 0 ? "#A8503F" : "#1B2430" }}
                >
                  {fmt(a.balance, a.currency)}
                  {showRub && a.currency !== "RUB" && (
                    <span className="fp-sub-value"> ≈ {fmt(toRub(a.balance, a.currency), "RUB")}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function KpiCard({ label, value, tone, icon }) {
  return (
    <div className={`fp-kpi fp-kpi-${tone}`}>
      <div className="fp-kpi-top">
        <span className="fp-kpi-label">{label}</span>
        <span className="fp-kpi-icon">{icon}</span>
      </div>
      <div className="fp-kpi-value">{value}</div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ОПЕРАЦИИ (ТАБЛИЦА)                                                    */
/* ---------------------------------------------------------------------- */

function TransactionsView({ transactions, accountsById, categoriesById, canEdit, showRub }) {
  return (
    <div className="fp-panel fp-table-panel">
      <table className="fp-table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Счёт</th>
            <th>Статья</th>
            <th>Проект</th>
            <th>Контрагент</th>
            <th>Комментарий</th>
            <th className="right">Комиссия</th>
            <th className="right">Сумма</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => {
            const acc = accountsById[t.accountId];
            const cat = categoriesById[t.categoryId];
            return (
              <tr key={t.id}>
                <td>{new Date(t.dateODDS).toLocaleDateString("ru-RU")}</td>
                <td>
                  {acc.name}
                  <span className={`fp-currency-badge ${acc.currency}`}>{acc.currency}</span>
                </td>
                <td>
                  <span className={`fp-cat-dot ${t.type}`} />
                  {cat.name}
                </td>
                <td>{t.project || <span className="fp-muted">—</span>}</td>
                <td>{t.counterparty || <span className="fp-muted">—</span>}</td>
                <td className="fp-muted">{t.comment || "—"}</td>
                <td className="right fp-mono">{t.commission ? fmt(t.commission, acc.currency) : "—"}</td>
                <td className={`right fp-mono fp-amount-${t.type}`}>
                  {t.type === "expense" ? "-" : "+"}
                  {fmt(t.amount, acc.currency)}
                  {showRub && acc.currency !== "RUB" && (
                    <div className="fp-sub-value">≈ {fmt(toRub(t.amount, acc.currency), "RUB")}</div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!canEdit && (
        <div className="fp-viewer-note">
          <Lock size={13} /> Режим «Только просмотр» — добавление и редактирование операций недоступно
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ЗАРПЛАТА                                                              */
/* ---------------------------------------------------------------------- */

function PayrollView({ canEdit, employees, employeesCrud }) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);

  const totalAccrued = employees.reduce((s, e) => s + e.accrued, 0);
  const totalPaid = employees.reduce((s, e) => s + e.paid, 0);
  const totalRemaining = totalAccrued - totalPaid;

  const byDept = useMemo(() => {
    const map = {};
    employees.forEach((e) => {
      if (!map[e.dept]) map[e.dept] = { accrued: 0, paid: 0 };
      map[e.dept].accrued += e.accrued;
      map[e.dept].paid += e.paid;
    });
    return map;
  }, [employees]);

  function openAdd() {
    setEditingId(null);
    setModalOpen(true);
  }
  function openEdit(id) {
    setEditingId(id);
    setModalOpen(true);
  }
  function handleSave(data) {
    if (editingId) employeesCrud.update(editingId, data);
    else employeesCrud.add({ ...data, accrued: 0, paid: 0 });
    setModalOpen(false);
  }

  const editingEmployee = editingId ? employees.find((e) => e.id === editingId) : null;

  return (
    <div className="fp-dash">
      <section className="fp-kpi-row" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <KpiCard label="Начислено за месяц" value={fmt(totalAccrued)} tone="neutral" icon={<Wallet size={16} />} />
        <KpiCard label="Выплачено" value={fmt(totalPaid)} tone="income" icon={<ArrowUpRight size={16} />} />
        <KpiCard
          label="Остаток к выплате"
          value={fmt(totalRemaining)}
          tone={totalRemaining > 0 ? "expense" : "income"}
          icon={<AlertTriangle size={16} />}
        />
      </section>

      <section className="fp-grid-2">
        <div className="fp-panel fp-table-panel">
          <div className="fp-panel-head fp-panel-head-row" style={{ padding: "18px 18px 0" }}>
            <h3>Сотрудники</h3>
            {canEdit && (
              <button type="button" className="fp-btn-tiny" onClick={openAdd}>
                <Plus size={13} /> Добавить сотрудника
              </button>
            )}
          </div>
          <table className="fp-table">
            <thead>
              <tr>
                <th>ФИО</th>
                <th>Отдел</th>
                <th>Тип занятости</th>
                <th className="right">Начислено</th>
                <th className="right">Выплачено</th>
                <th className="right">Остаток</th>
                {canEdit && <th></th>}
              </tr>
            </thead>
            <tbody>
              {employees.map((e) => {
                const remaining = e.accrued - e.paid;
                return (
                  <tr key={e.id}>
                    <td>{e.name}</td>
                    <td className="fp-muted">{e.dept}</td>
                    <td className="fp-muted">{e.type}</td>
                    <td className="right fp-mono">{fmt(e.accrued)}</td>
                    <td className="right fp-mono">{fmt(e.paid)}</td>
                    <td className={`right fp-mono ${remaining > 0 ? "fp-amount-expense" : "fp-amount-income"}`}>
                      {remaining > 0 ? fmt(remaining) : <CheckCircle2 size={14} />}
                    </td>
                    {canEdit && (
                      <td className="right">
                        <RowActions onEdit={() => openEdit(e.id)} onDelete={() => employeesCrud.remove(e.id)} />
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="fp-panel">
          <div className="fp-panel-head">
            <h3>По отделам</h3>
          </div>
          <div className="fp-ledger">
            {Object.entries(byDept).map(([dept, v]) => (
              <div className="ledger-row" key={dept}>
                <span className="label">{dept}</span>
                <span className="fill" />
                <span className="value">{fmt(v.paid)} / {fmt(v.accrued)}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {modalOpen && (
        <EntityFormModal
          title={editingId ? "Изменить сотрудника" : "Добавить сотрудника"}
          fields={EMPLOYEE_FIELDS}
          initialValues={editingEmployee}
          onSave={handleSave}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ОТЧЁТЫ: БАЛАНС / ЗАДОЛЖЕННОСТЬ / ПЛАТЁЖНЫЙ КАЛЕНДАРЬ                  */
/* ---------------------------------------------------------------------- */

function ReportsView({ reportTab, setReportTab, accounts, employees, counterparties }) {
  return (
    <div className="fp-dash">
      <div className="fp-tabs">
        <button className={reportTab === "calendar" ? "active" : ""} onClick={() => setReportTab("calendar")}>
          <CalendarClock size={14} /> Платёжный календарь
        </button>
        <button className={reportTab === "pnl" ? "active" : ""} onClick={() => setReportTab("pnl")}>
          <FileText size={14} /> ОПУ
        </button>
        <button className={reportTab === "balance" ? "active" : ""} onClick={() => setReportTab("balance")}>
          <Landmark size={14} /> Баланс
        </button>
        <button className={reportTab === "debt" ? "active" : ""} onClick={() => setReportTab("debt")}>
          <AlertTriangle size={14} /> Задолженность
        </button>
        <button className={reportTab === "profitability" ? "active" : ""} onClick={() => setReportTab("profitability")}>
          <TrendingUp size={14} /> Рентабельность
        </button>
        <button className={reportTab === "other" ? "active" : ""} onClick={() => setReportTab("other")}>
          <HardDrive size={14} /> ОС и запасы
        </button>
      </div>

      {reportTab === "calendar" && <CalendarReport />}
      {reportTab === "pnl" && <PnLReport />}
      {reportTab === "balance" && <BalanceReport accounts={accounts} employees={employees} />}
      {reportTab === "debt" && <DebtReport counterparties={counterparties} />}
      {reportTab === "profitability" && <ProfitabilityReport />}
      {reportTab === "other" && <OtherAssetsReport />}
    </div>
  );
}

function PnLReport() {
  const revenue = PNL.revenue.reduce((s, r) => s + r.amount, 0);
  const cogs = PNL.cogs.reduce((s, r) => s + r.amount, 0);
  const grossProfit = revenue - cogs;
  const opex = PNL.opex.reduce((s, r) => s + r.amount, 0);
  const netProfit = grossProfit - opex;
  const margin = ((netProfit / revenue) * 100).toFixed(1);

  return (
    <div className="fp-grid-2">
      <div className="fp-panel">
        <div className="fp-panel-head"><h3>Выручка и себестоимость</h3></div>
        <div className="fp-ledger">
          {PNL.revenue.map((r) => (
            <div className="ledger-row" key={r.name}><span className="label">{r.name}</span><span className="fill" /><span className="value fp-amount-income">{fmt(r.amount)}</span></div>
          ))}
          <div className="ledger-row fp-ledger-total"><span className="label">Итого выручка</span><span className="fill" /><span className="value">{fmt(revenue)}</span></div>
          {PNL.cogs.map((r) => (
            <div className="ledger-row" key={r.name}><span className="label">{r.name}</span><span className="fill" /><span className="value fp-amount-expense">-{fmt(r.amount)}</span></div>
          ))}
          <div className="ledger-row fp-ledger-total"><span className="label">Валовая прибыль</span><span className="fill" /><span className="value">{fmt(grossProfit)}</span></div>
        </div>
      </div>
      <div className="fp-panel">
        <div className="fp-panel-head"><h3>Операционные расходы и итог</h3></div>
        <div className="fp-ledger">
          {PNL.opex.map((r) => (
            <div className="ledger-row" key={r.name}><span className="label">{r.name}</span><span className="fill" /><span className="value fp-amount-expense">-{fmt(r.amount)}</span></div>
          ))}
          <div className="ledger-row fp-ledger-total"><span className="label">Итого операционные расходы</span><span className="fill" /><span className="value">{fmt(opex)}</span></div>
          <div className="ledger-row fp-ledger-total"><span className="label">Чистая прибыль</span><span className="fill" /><span className={`value ${netProfit >= 0 ? "fp-amount-income" : "fp-amount-expense"}`}>{fmt(netProfit)}</span></div>
          <div className="ledger-row"><span className="label">Рентабельность по чистой прибыли</span><span className="fill" /><span className="value">{margin}%</span></div>
        </div>
      </div>
    </div>
  );
}

function ProfitabilityReport() {
  return (
    <div className="fp-panel fp-table-panel">
      <table className="fp-table">
        <thead>
          <tr><th>Проект</th><th className="right">Выручка</th><th className="right">Прямые расходы</th><th className="right">Прибыль</th><th className="right">Рентаб., %</th></tr>
        </thead>
        <tbody>
          {PROFITABILITY.map((p) => {
            const profit = p.revenue - p.directCosts;
            const margin = ((profit / p.revenue) * 100).toFixed(1);
            return (
              <tr key={p.project}>
                <td>{p.project}</td>
                <td className="right fp-mono">{fmt(p.revenue)}</td>
                <td className="right fp-mono fp-amount-expense">-{fmt(p.directCosts)}</td>
                <td className={`right fp-mono ${profit >= 0 ? "fp-amount-income" : "fp-amount-expense"}`}>{fmt(profit)}</td>
                <td className="right fp-mono">
                  <span className={`fp-status-badge ${margin >= 30 ? "ok" : margin >= 10 ? "warn" : "danger"}`}>{margin}%</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OtherAssetsReport() {
  const totalValue = FIXED_ASSETS.reduce((s, a) => s + a.value, 0);
  const totalDepreciation = FIXED_ASSETS.reduce((s, a) => s + a.monthlyDepreciation, 0);
  return (
    <div className="fp-grid-2">
      <div className="fp-panel">
        <div className="fp-panel-head"><h3>Основные средства и амортизация</h3></div>
        <div className="fp-ledger">
          {FIXED_ASSETS.map((a) => (
            <div className="ledger-row" key={a.id}>
              <span className="label">{a.name}</span>
              <span className="fill" />
              <span className="value">{fmt(a.value)} <span className="fp-sub-value">/ -{fmt(a.monthlyDepreciation)} мес.</span></span>
            </div>
          ))}
          <div className="ledger-row fp-ledger-total"><span className="label">Итого / амортизация в месяц</span><span className="fill" /><span className="value">{fmt(totalValue)} / -{fmt(totalDepreciation)}</span></div>
        </div>
        <p className="fp-note">Судя по структуре ваших файлов, для текущей модели бизнеса (услуги/инфопродукты) это, вероятно, не приоритет — раздел добавлен для полноты сравнения с ПланФакт.</p>
      </div>
      <div className="fp-panel">
        <div className="fp-panel-head"><h3>Запасы в деньгах</h3></div>
        <div className="fp-ledger">
          <div className="ledger-row"><span className="label">Стоимость запасов на складе</span><span className="fill" /><span className="value">{fmt(INVENTORY_VALUE.warehouseValue)}</span></div>
          <div className="ledger-row"><span className="label">Единиц на складе</span><span className="fill" /><span className="value">{INVENTORY_VALUE.unitsInStock.toLocaleString("ru-RU")} шт.</span></div>
          <div className="ledger-row"><span className="label">Средняя себестоимость единицы</span><span className="fill" /><span className="value">{fmt(INVENTORY_VALUE.avgCost)}</span></div>
        </div>
        <p className="fp-note">Актуально, только если у вас есть физический товарный запас — уточним при проектировании БД, нужен ли этот раздел вообще.</p>
      </div>
    </div>
  );
}

function CalendarReport() {
  return (
    <div className="fp-panel fp-table-panel">
      <table className="fp-table fp-calendar-table">
        <thead>
          <tr>
            <th>Статья</th>
            {["I кв.", "II кв.", "III кв.", "IV кв."].map((q) => (
              <th key={q} colSpan={3} className="center">{q}</th>
            ))}
          </tr>
          <tr>
            <th></th>
            {[0, 1, 2, 3].map((i) => (
              <React.Fragment key={i}>
                <th className="right">План</th>
                <th className="right">Факт</th>
                <th className="right">Откл.</th>
              </React.Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {CALENDAR_ROWS.map((row) => (
            <tr key={row.category}>
              <td>{row.category}</td>
              {row.q.map((cell, i) => {
                const dev = cell.fact - cell.plan;
                const empty = cell.fact === 0;
                return (
                  <React.Fragment key={i}>
                    <td className="right fp-mono fp-muted">{fmt(cell.plan)}</td>
                    <td className="right fp-mono">{empty ? "—" : fmt(cell.fact)}</td>
                    <td className={`right fp-mono ${empty ? "fp-muted" : dev >= 0 ? "fp-amount-income" : "fp-amount-expense"}`}>
                      {empty ? "—" : `${dev >= 0 ? "+" : ""}${fmt(dev)}`}
                    </td>
                  </React.Fragment>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BalanceReport({ accounts, employees }) {
  const cash = accounts.reduce((s, a) => s + toRub(a.balance, a.currency), 0);
  const receivables = 12400;
  const prepaid = 6200;
  const assets = cash + receivables + prepaid;

  const payableToStaff = employees.reduce((s, e) => s + (e.accrued - e.paid), 0);
  const payables = 18500 + 10760;
  const retainedEarnings = assets - payableToStaff - payables;

  return (
    <div className="fp-grid-2">
      <div className="fp-panel">
        <div className="fp-panel-head"><h3>Активы</h3></div>
        <div className="fp-ledger">
          <div className="ledger-row"><span className="label">Денежные средства</span><span className="fill" /><span className="value">{fmt(cash)}</span></div>
          <div className="ledger-row"><span className="label">Дебиторская задолженность</span><span className="fill" /><span className="value">{fmt(receivables)}</span></div>
          <div className="ledger-row"><span className="label">Расходы будущих периодов</span><span className="fill" /><span className="value">{fmt(prepaid)}</span></div>
          <div className="ledger-row fp-ledger-total"><span className="label">Итого активы</span><span className="fill" /><span className="value">{fmt(assets)}</span></div>
        </div>
      </div>
      <div className="fp-panel">
        <div className="fp-panel-head"><h3>Пассивы</h3></div>
        <div className="fp-ledger">
          <div className="ledger-row"><span className="label">Задолженность перед сотрудниками</span><span className="fill" /><span className="value">{fmt(payableToStaff)}</span></div>
          <div className="ledger-row"><span className="label">Кредиторская задолженность</span><span className="fill" /><span className="value">{fmt(payables)}</span></div>
          <div className="ledger-row"><span className="label">Нераспределённая прибыль</span><span className="fill" /><span className="value">{fmt(retainedEarnings)}</span></div>
          <div className="ledger-row fp-ledger-total"><span className="label">Итого пассивы</span><span className="fill" /><span className="value">{fmt(payableToStaff + payables + retainedEarnings)}</span></div>
        </div>
      </div>
    </div>
  );
}

function DebtReport({ counterparties }) {
  return (
    <div className="fp-panel fp-table-panel">
      <table className="fp-table">
        <thead>
          <tr>
            <th>Контрагент</th>
            <th>Тип</th>
            <th className="right">Сумма</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {counterparties.map((c) => (
            <tr key={c.id}>
              <td>{c.name}</td>
              <td className="fp-muted">{c.type}</td>
              <td className="right fp-mono">{c.amount ? fmt(c.amount) : "—"}</td>
              <td>
                <span className={`fp-status-badge ${c.status === "Просрочено" ? "danger" : c.status === "В срок" ? "warn" : "ok"}`}>
                  {c.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  СПРАВОЧНИКИ                                                           */
/* ---------------------------------------------------------------------- */

function ReferenceView({
  refTab,
  setRefTab,
  canEdit,
  categories,
  projects,
  accounts,
  counterparties,
  categoriesCrud,
  projectsCrud,
  accountsCrud,
  counterpartiesCrud,
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);

  const CONFIGS = {
    categories: { noun: "статью", fields: CATEGORY_FIELDS, list: categories, crud: categoriesCrud, extra: {} },
    projects: { noun: "проект", fields: PROJECT_FIELDS, list: projects, crud: projectsCrud, extra: {} },
    accounts: { noun: "счёт", fields: ACCOUNT_FIELDS, list: accounts, crud: accountsCrud, extra: {} },
    counterparties: {
      noun: "контрагента",
      fields: COUNTERPARTY_FIELDS,
      list: counterparties,
      crud: counterpartiesCrud,
      extra: { amount: 0, status: "Погашено" },
    },
  };
  const active = CONFIGS[refTab];

  function openAdd() {
    setEditingId(null);
    setModalOpen(true);
  }
  function openEdit(id) {
    setEditingId(id);
    setModalOpen(true);
  }
  function handleSave(data) {
    if (editingId) active.crud.update(editingId, data);
    else active.crud.add({ ...active.extra, ...data });
    setModalOpen(false);
  }

  const editingItem = editingId ? active.list.find((it) => it.id === editingId) : null;

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        <div className="fp-tabs">
          {Object.entries(REFERENCE_TABS).map(([key, meta]) => (
            <button key={key} className={refTab === key ? "active" : ""} onClick={() => setRefTab(key)}>
              {meta.icon === "tag" && <Tag size={14} />}
              {meta.icon === "layout" && <LayoutDashboard size={14} />}
              {meta.icon === "building" && <Building2 size={14} />}
              {meta.icon === "contact" && <Contact size={14} />}
              {meta.label}
            </button>
          ))}
        </div>
        {canEdit && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> Добавить
          </button>
        )}
      </div>

      <div className="fp-panel fp-table-panel">
        {refTab === "categories" && (
          <table className="fp-table">
            <thead><tr><th>Статья</th><th>Группа</th><th>Тип</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.id}>
                  <td><span className={`fp-cat-dot ${c.type}`} />{c.name}</td>
                  <td className="fp-muted">{c.group}</td>
                  <td className="fp-muted">{c.type === "income" ? "Приход" : "Расход"}</td>
                  {canEdit && (
                    <td className="right">
                      <RowActions onEdit={() => openEdit(c.id)} onDelete={() => categoriesCrud.remove(c.id)} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {refTab === "projects" && (
          <table className="fp-table">
            <thead><tr><th>Проект</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  {canEdit && (
                    <td className="right">
                      <RowActions onEdit={() => openEdit(p.id)} onDelete={() => projectsCrud.remove(p.id)} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {refTab === "accounts" && (
          <table className="fp-table">
            <thead><tr><th>Счёт</th><th>Валюта</th><th className="right">Остаток</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td><span className={`fp-currency-badge ${a.currency}`}>{a.currency}</span></td>
                  <td className="right fp-mono">{fmt(a.balance, a.currency)}</td>
                  {canEdit && (
                    <td className="right">
                      <RowActions onEdit={() => openEdit(a.id)} onDelete={() => accountsCrud.remove(a.id)} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {refTab === "counterparties" && (
          <table className="fp-table">
            <thead><tr><th>Контрагент</th><th>Тип</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {counterparties.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td className="fp-muted">{c.type}</td>
                  {canEdit && (
                    <td className="right">
                      <RowActions onEdit={() => openEdit(c.id)} onDelete={() => counterpartiesCrud.remove(c.id)} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {modalOpen && (
        <EntityFormModal
          title={`${editingId ? "Изменить" : "Добавить"} ${active.noun}`}
          fields={active.fields}
          initialValues={editingItem}
          onSave={handleSave}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ПЕРЕИСПОЛЬЗУЕМЫЕ: ДЕЙСТВИЯ В СТРОКЕ (ред./удал.) И МОДАЛКА ФОРМЫ      */
/* ---------------------------------------------------------------------- */

function RowActions({ onEdit, onDelete }) {
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <span className="fp-row-actions">
        <button type="button" className="fp-btn-tiny fp-btn-danger" onClick={onDelete}>
          Удалить
        </button>
        <button type="button" className="fp-btn-tiny" onClick={() => setConfirming(false)}>
          Отмена
        </button>
      </span>
    );
  }

  return (
    <span className="fp-row-actions">
      <button type="button" className="fp-icon-btn" onClick={onEdit} aria-label="Редактировать">
        <Pencil size={13} />
      </button>
      <button type="button" className="fp-icon-btn" onClick={() => setConfirming(true)} aria-label="Удалить">
        <Trash2 size={13} />
      </button>
    </span>
  );
}

function EntityFormModal({ title, fields, initialValues, onSave, onClose }) {
  const [values, setValues] = useState(() => {
    const v = {};
    fields.forEach((f) => {
      v[f.key] = initialValues?.[f.key] ?? (f.type === "number" ? 0 : f.options ? f.options[0].value : "");
    });
    return v;
  });

  function submit(e) {
    e.preventDefault();
    if (fields.some((f) => f.required && !String(values[f.key]).trim())) return;
    const payload = { ...values };
    fields.forEach((f) => {
      if (f.type === "number") payload[f.key] = parseFloat(payload[f.key]) || 0;
    });
    onSave(payload);
  }

  return (
    <div className="fp-modal-backdrop" onClick={onClose}>
      <form className="fp-modal" style={{ width: 400 }} onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="fp-modal-head">
          <h3>{title}</h3>
          <button type="button" className="fp-icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="fp-form-grid" style={{ gridTemplateColumns: "1fr" }}>
          {fields.map((f) => (
            <label key={f.key}>
              {f.label}
              {f.type === "select" ? (
                <select
                  value={values[f.key]}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                >
                  {f.options.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={f.type === "number" ? "number" : "text"}
                  step={f.type === "number" ? "0.01" : undefined}
                  value={values[f.key]}
                  onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                />
              )}
            </label>
          ))}
        </div>

        <div className="fp-modal-foot">
          <button type="button" className="fp-btn-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="fp-btn-primary">
            Сохранить
          </button>
        </div>
      </form>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  АВТОМАТИЗАЦИЯ: ПРАВИЛА / ИНТЕГРАЦИИ / API                            */
/* ---------------------------------------------------------------------- */

function AutomationView({ automationTab, setAutomationTab, rules, toggleRule, integrations, toggleIntegration, canEdit }) {
  return (
    <div className="fp-dash">
      <div className="fp-tabs">
        <button className={automationTab === "rules" ? "active" : ""} onClick={() => setAutomationTab("rules")}>
          <Zap size={14} /> Правила обработки
        </button>
        <button className={automationTab === "integrations" ? "active" : ""} onClick={() => setAutomationTab("integrations")}>
          <Plug size={14} /> Интеграции
        </button>
        <button className={automationTab === "api" ? "active" : ""} onClick={() => setAutomationTab("api")}>
          <KeyRound size={14} /> API
        </button>
      </div>

      {automationTab === "rules" && (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead><tr><th>Условие</th><th>Действие</th><th>Статус</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.condition}</td>
                  <td className="fp-muted">{r.action}</td>
                  <td>
                    <span className={`fp-status-badge ${r.active ? "ok" : "warn"}`}>
                      {r.active ? "Активно" : "Отключено"}
                    </span>
                  </td>
                  {canEdit && (
                    <td className="right">
                      <label className="fp-mini-switch">
                        <input type="checkbox" checked={r.active} onChange={() => toggleRule(r.id)} />
                        <span />
                      </label>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {canEdit && (
            <div className="fp-viewer-note">
              <Zap size={13} /> Правила применяются автоматически при поступлении новой операции — статья, проект и контрагент подставляются без ручного ввода
            </div>
          )}
        </div>
      )}

      {automationTab === "integrations" && (
        <div className="fp-panel fp-table-panel">
          <table className="fp-table">
            <thead><tr><th>Сервис</th><th>Тип</th><th>Статус</th>{canEdit && <th></th>}</tr></thead>
            <tbody>
              {integrations.map((i) => (
                <tr key={i.id}>
                  <td>{i.name}</td>
                  <td className="fp-muted">{i.type}</td>
                  <td>
                    <span className={`fp-status-badge ${i.connected ? "ok" : "warn"}`}>
                      {i.connected ? "Подключено" : "Не подключено"}
                    </span>
                  </td>
                  {canEdit && (
                    <td className="right">
                      <button className="fp-btn-tiny" onClick={() => toggleIntegration(i.id)}>
                        {i.connected ? "Отключить" : "Подключить"}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="fp-viewer-note">
            <Plug size={13} /> Подключение банков перенесёт операции по выпискам автоматически — без ручного дублирования между «Внесением» и «Архивом»
          </div>
        </div>
      )}

      {automationTab === "api" && (
        <div className="fp-panel" style={{ maxWidth: 520 }}>
          <div className="fp-panel-head"><h3>Доступ к API</h3></div>
          <div className="fp-api-key">
            <code>pf_live_••••••••••••••••7a41</code>
            <button className="fp-btn-tiny"><RefreshCw size={13} /> Обновить ключ</button>
          </div>
          <p className="fp-note">
            Открытый REST API для собственных интеграций (например, с вашей CRM или сайтом продаж) —
            позволяет создавать операции и читать отчёты без входа в интерфейс.
          </p>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  АУДИТ — ЖУРНАЛ ДЕЙСТВИЙ                                               */
/* ---------------------------------------------------------------------- */

function AuditView() {
  return (
    <div className="fp-panel fp-table-panel">
      <table className="fp-table">
        <thead><tr><th>Время</th><th>Пользователь</th><th>Роль</th><th>Действие</th></tr></thead>
        <tbody>
          {AUDIT_LOG.map((a) => (
            <tr key={a.id}>
              <td className="fp-mono fp-muted">{a.time}</td>
              <td>{a.user}</td>
              <td className="fp-muted">{a.role}</td>
              <td>{a.action}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="fp-viewer-note">
        <History size={13} /> Полная история изменений — кто и когда вносил, редактировал или удалял записи. Недоступно для роли «Только просмотр»
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  ФОРМА ДОБАВЛЕНИЯ ОПЕРАЦИИ                                             */
/* ---------------------------------------------------------------------- */

function TransactionForm({ accounts, categories, projects, onClose, onSubmit }) {
  const [type, setType] = useState("income");
  const [accountId, setAccountId] = useState(accounts[0].id);
  const [categoryId, setCategoryId] = useState(
    categories.find((c) => c.type === "income").id
  );
  const [project, setProject] = useState(projects[0]?.name || "");
  const [amount, setAmount] = useState("");
  const [commission, setCommission] = useState("");
  const [counterparty, setCounterparty] = useState("");
  const [comment, setComment] = useState("");
  const [date, setDate] = useState("2026-06-01");

  const relevantCategories = categories.filter((c) => c.type === type);

  function submit(e) {
    e.preventDefault();
    if (!amount) return;
    onSubmit({
      dateODDS: date,
      accountId,
      categoryId,
      project,
      amount: parseFloat(amount),
      commission: commission ? parseFloat(commission) : 0,
      counterparty,
      comment,
      type,
    });
  }

  return (
    <div className="fp-modal-backdrop" onClick={onClose}>
      <form className="fp-modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <div className="fp-modal-head">
          <h3>Новая операция</h3>
          <button type="button" className="fp-icon-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="fp-type-toggle">
          <button
            type="button"
            className={type === "income" ? "active income" : "income"}
            onClick={() => {
              setType("income");
              setCategoryId(categories.find((c) => c.type === "income").id);
            }}
          >
            <ArrowUpRight size={15} /> Приход
          </button>
          <button
            type="button"
            className={type === "expense" ? "active expense" : "expense"}
            onClick={() => {
              setType("expense");
              setCategoryId(categories.find((c) => c.type === "expense").id);
            }}
          >
            <ArrowDownRight size={15} /> Расход
          </button>
        </div>

        <div className="fp-form-grid">
          <label>
            Дата ОДДС
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>
            Счёт
            <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.currency})
                </option>
              ))}
            </select>
          </label>
          <label>
            Статья
            <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
              {relevantCategories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Проект
            <select value={project} onChange={(e) => setProject(e.target.value)}>
              {projects.map((p) => (
                <option key={p.id} value={p.name}>{p.name}</option>
              ))}
            </select>
          </label>
          <label>
            Сумма
            <input
              type="number"
              step="0.01"
              placeholder="0.00"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </label>
          <label>
            Сумма комиссии
            <input
              type="number"
              step="0.01"
              placeholder="0.00"
              value={commission}
              onChange={(e) => setCommission(e.target.value)}
            />
          </label>
          <label className="fp-span-2">
            Контрагент
            <input
              type="text"
              value={counterparty}
              onChange={(e) => setCounterparty(e.target.value)}
              placeholder="Название контрагента"
            />
          </label>
          <label className="fp-span-2">
            Примечание / комментарий
            <input
              type="text"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </label>
        </div>

        <div className="fp-modal-foot">
          <button type="button" className="fp-btn-ghost" onClick={onClose}>
            Отмена
          </button>
          <button type="submit" className="fp-btn-primary">
            Сохранить операцию
          </button>
        </div>
      </form>
    </div>
  );
}

/* ---------------------------------------------------------------------- */
/*  СТИЛИ                                                                 */
/* ---------------------------------------------------------------------- */

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

.fp-root {
  --bg: #F5F2EC;
  --surface: #FFFFFF;
  --ink: #1B2430;
  --ink-soft: #5B6472;
  --sidebar: #12172A;
  --sidebar-soft: #8C93A6;
  --line: #E7E1D3;
  --accent: #2F6F5E;
  --accent-soft: #DCEAE4;
  --expense: #A8503F;
  --expense-soft: #F3E1DC;
  --gold: #C9A227;

  display: flex;
  min-height: 640px;
  width: 100%;
  background: var(--bg);
  color: var(--ink);
  font-family: 'IBM Plex Sans', sans-serif;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--line);
}

.fp-root * { box-sizing: border-box; }

/* ---------- Sidebar ---------- */
.fp-sidebar {
  width: 232px;
  flex-shrink: 0;
  background: var(--sidebar);
  color: #E7E9EF;
  display: flex;
  flex-direction: column;
  padding: 20px 16px;
}
.fp-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
.fp-brand-mark {
  width: 34px; height: 34px; border-radius: 8px;
  background: var(--accent);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Fraunces', serif; font-weight: 600; font-size: 17px;
}
.fp-brand-name { font-family: 'Fraunces', serif; font-weight: 600; font-size: 15px; line-height: 1.2; }
.fp-brand-sub { font-size: 11px; color: var(--sidebar-soft); letter-spacing: 0.03em; }

.fp-stamp {
  align-self: flex-start;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9.5px;
  letter-spacing: 0.08em;
  color: var(--gold);
  border: 1px dashed var(--gold);
  padding: 3px 8px;
  border-radius: 3px;
  transform: rotate(-2deg);
  margin-bottom: 22px;
}

.fp-nav { display: flex; flex-direction: column; gap: 2px; flex: 1; }
.fp-nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 10px;
  border-radius: 7px;
  background: transparent; border: none;
  color: #C3C8D4;
  font-family: 'IBM Plex Sans', sans-serif;
  font-size: 13.5px;
  cursor: pointer;
  text-align: left;
  position: relative;
}
.fp-nav-item:hover:not(.disabled) { background: rgba(255,255,255,0.06); color: #fff; }
.fp-nav-item.active { background: var(--accent); color: #fff; }
.fp-nav-item.disabled { color: #565E70; cursor: default; }
.fp-soon {
  margin-left: auto;
  font-size: 9px;
  font-family: 'IBM Plex Mono', monospace;
  background: rgba(255,255,255,0.08);
  padding: 2px 6px;
  border-radius: 10px;
}

.fp-sidebar-foot { border-top: 1px solid rgba(255,255,255,0.09); padding-top: 14px; margin-top: 10px; }
.fp-role-box {
  display: flex; align-items: center; gap: 8px;
  background: rgba(255,255,255,0.06);
  padding: 7px 10px; border-radius: 7px;
  color: #C3C8D4;
}
.fp-role-box select {
  background: transparent; border: none; color: #fff;
  font-family: 'IBM Plex Sans', sans-serif; font-size: 12.5px;
  flex: 1; cursor: pointer;
}
.fp-role-box select option { color: #1B2430; }
.fp-role-hint { font-size: 10.5px; color: #565E70; margin-top: 5px; padding-left: 2px; }

/* ---------- Main ---------- */
.fp-main { flex: 1; padding: 26px 30px; overflow-y: auto; min-width: 0; }

.fp-topbar {
  display: flex; align-items: flex-end; justify-content: space-between;
  margin-bottom: 22px; flex-wrap: wrap; gap: 14px;
}
.fp-eyebrow { font-size: 11px; letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-soft); margin-bottom: 3px; }
.fp-topbar h1 { font-family: 'Fraunces', serif; font-size: 26px; font-weight: 600; margin: 0; }

.fp-topbar-controls { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.fp-switch { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--ink-soft); cursor: pointer; }
.fp-switch input { accent-color: var(--accent); }

.fp-select-wrap { position: relative; display: flex; align-items: center; }
.fp-select-wrap select {
  appearance: none;
  font-family: 'IBM Plex Sans', sans-serif;
  font-size: 13px;
  padding: 8px 28px 8px 12px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--surface);
  color: var(--ink);
}
.fp-select-wrap svg { position: absolute; right: 9px; pointer-events: none; color: var(--ink-soft); }

.fp-btn-primary {
  display: flex; align-items: center; gap: 6px;
  background: var(--ink); color: #fff;
  border: none; padding: 9px 16px; border-radius: 7px;
  font-size: 13.5px; font-weight: 500; cursor: pointer;
}
.fp-btn-primary:hover { background: #2A3446; }
.fp-btn-ghost {
  background: transparent; border: 1px solid var(--line);
  padding: 9px 16px; border-radius: 7px; font-size: 13.5px; cursor: pointer; color: var(--ink-soft);
}

/* ---------- KPI cards ---------- */
.fp-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.fp-kpi {
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  padding: 15px 16px;
}
.fp-kpi-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.fp-kpi-label { font-size: 12px; color: var(--ink-soft); }
.fp-kpi-icon { color: var(--ink-soft); }
.fp-kpi-income .fp-kpi-icon { color: var(--accent); }
.fp-kpi-expense .fp-kpi-icon { color: var(--expense); }
.fp-kpi-value { font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-variant-numeric: tabular-nums; }
.fp-kpi-income .fp-kpi-value { color: var(--accent); }
.fp-kpi-expense .fp-kpi-value { color: var(--expense); }

/* ---------- Panels ---------- */
.fp-grid-2 { display: grid; grid-template-columns: 1.3fr 1fr; gap: 16px; }
.fp-panel { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 18px; }
.fp-panel-head h3 { font-family: 'Fraunces', serif; font-size: 15.5px; font-weight: 600; margin: 0 0 12px; }

.fp-ledger { display: flex; flex-direction: column; gap: 11px; margin-top: 4px; }
.ledger-row { display: flex; align-items: baseline; gap: 8px; }
.ledger-row .label { white-space: nowrap; font-size: 13px; display: flex; align-items: center; gap: 6px; }
.ledger-row .fill { flex: 1; border-bottom: 1px dotted #D8D2C2; position: relative; top: -4px; }
.ledger-row .value {
  white-space: nowrap; font-family: 'IBM Plex Mono', monospace; font-size: 13px;
  font-variant-numeric: tabular-nums; text-align: right;
}
.fp-sub-value { font-size: 11px; color: var(--ink-soft); }

.fp-currency-badge {
  font-size: 9.5px; font-family: 'IBM Plex Mono', monospace;
  padding: 1px 5px; border-radius: 4px; margin-left: 6px;
  background: var(--accent-soft); color: var(--accent);
}
.fp-currency-badge.CNY { background: #F3E9D2; color: #8A6A16; }

/* ---------- Table ---------- */
.fp-table-panel { padding: 0; overflow-x: auto; }
.fp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.fp-table th {
  text-align: left; font-weight: 500; color: var(--ink-soft);
  font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.04em;
  padding: 12px 16px; border-bottom: 1px solid var(--line); white-space: nowrap;
}
.fp-table td { padding: 11px 16px; border-bottom: 1px solid #F0ECE1; white-space: nowrap; }
.fp-table tr:last-child td { border-bottom: none; }
.fp-table .right { text-align: right; }
.fp-mono { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; }
.fp-amount-income { color: var(--accent); }
.fp-amount-expense { color: var(--expense); }
.fp-muted { color: var(--ink-soft); }
.fp-cat-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 7px;
}
.fp-cat-dot.income { background: var(--accent); }
.fp-cat-dot.expense { background: var(--expense); }

.fp-viewer-note {
  display: flex; align-items: center; gap: 7px;
  padding: 12px 16px; font-size: 12.5px; color: var(--ink-soft);
  border-top: 1px solid var(--line); background: #FBFAF6;
}

/* ---------- Modal / form ---------- */
.fp-modal-backdrop {
  position: absolute; inset: 0; background: rgba(18,23,42,0.45);
  display: flex; align-items: center; justify-content: center; z-index: 10;
  border-radius: 12px;
}
.fp-modal {
  background: var(--surface); border-radius: 12px; padding: 22px;
  width: 480px; max-width: 92%; max-height: 86%; overflow-y: auto;
  box-shadow: 0 20px 50px rgba(18,23,42,0.25);
}
.fp-modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.fp-modal-head h3 { font-family: 'Fraunces', serif; font-size: 17px; margin: 0; }
.fp-icon-btn { background: none; border: none; cursor: pointer; color: var(--ink-soft); }

.fp-type-toggle { display: flex; gap: 8px; margin-bottom: 16px; }
.fp-type-toggle button {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 9px; border-radius: 7px; border: 1px solid var(--line);
  background: var(--surface); font-size: 13px; cursor: pointer; color: var(--ink-soft);
}
.fp-type-toggle button.active.income { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.fp-type-toggle button.active.expense { background: var(--expense-soft); border-color: var(--expense); color: var(--expense); }

.fp-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.fp-form-grid label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--ink-soft); }
.fp-form-grid .fp-span-2 { grid-column: span 2; }
.fp-form-grid input, .fp-form-grid select {
  font-family: 'IBM Plex Sans', sans-serif; font-size: 13.5px; color: var(--ink);
  padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface);
}

.fp-modal-foot { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }

.fp-tabs { display: flex; gap: 6px; margin-bottom: 16px; }
.fp-tabs-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.fp-tabs-row .fp-tabs { margin-bottom: 0; }
.fp-panel-head-row { display: flex; align-items: center; justify-content: space-between; }
.fp-row-actions { display: inline-flex; align-items: center; gap: 6px; }
.fp-btn-danger { background: var(--expense-soft); color: var(--expense); border-color: var(--expense); }
.fp-btn-danger:hover { background: var(--expense); color: #fff; }
.fp-tabs button {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 7px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink-soft); font-size: 13px; cursor: pointer;
}
.fp-tabs button.active { background: var(--ink); color: #fff; border-color: var(--ink); }

.fp-ledger-total { margin-top: 6px; padding-top: 10px; border-top: 1px solid var(--line); font-weight: 600; }
.fp-ledger-total .value { font-size: 14px; }

.fp-status-badge {
  font-size: 11.5px; padding: 3px 9px; border-radius: 20px; font-weight: 500;
}
.fp-status-badge.ok { background: var(--accent-soft); color: var(--accent); }
.fp-status-badge.warn { background: #F3E9D2; color: #8A6A16; }
.fp-status-badge.danger { background: var(--expense-soft); color: var(--expense); }

.fp-table th.center { text-align: center; }
.fp-calendar-table th, .fp-calendar-table td { padding: 9px 12px; }

.fp-mini-switch { position: relative; display: inline-block; width: 34px; height: 19px; }
.fp-mini-switch input { opacity: 0; width: 0; height: 0; }
.fp-mini-switch span {
  position: absolute; inset: 0; background: #DDD7C8; border-radius: 20px; cursor: pointer; transition: 0.15s;
}
.fp-mini-switch span::before {
  content: ""; position: absolute; width: 14px; height: 14px; left: 3px; top: 2.5px;
  background: #fff; border-radius: 50%; transition: 0.15s;
}
.fp-mini-switch input:checked + span { background: var(--accent); }
.fp-mini-switch input:checked + span::before { transform: translateX(15px); }

.fp-btn-tiny {
  font-size: 12px; padding: 5px 11px; border-radius: 6px; border: 1px solid var(--line);
  background: var(--surface); color: var(--ink); cursor: pointer;
}
.fp-btn-tiny:hover { background: #F3F0E8; }

.fp-api-key {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  background: #F3F0E8; border: 1px solid var(--line); border-radius: 7px;
  padding: 10px 14px; margin-bottom: 12px;
}
.fp-api-key code { font-family: 'IBM Plex Mono', monospace; font-size: 13px; }

.fp-note { font-size: 12px; color: var(--ink-soft); line-height: 1.5; margin-top: 12px; }

@media (max-width: 860px) {
  .fp-root { flex-direction: column; }
  .fp-sidebar { width: 100%; flex-direction: row; align-items: center; padding: 12px 16px; }
  .fp-nav { flex-direction: row; }
  .fp-stamp, .fp-sidebar-foot, .fp-brand-sub { display: none; }
  .fp-kpi-row { grid-template-columns: repeat(2, 1fr); }
  .fp-grid-2 { grid-template-columns: 1fr; }
}
`;
