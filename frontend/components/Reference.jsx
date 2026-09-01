"use client";

import { useState, useEffect, useRef } from "react";
import { Plus, X, Pencil, Trash2, Tag, LayoutDashboard, Building2, Contact, Ban, RotateCcw, RefreshCw, Upload, Download, ChevronDown, Archive } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditReference } from "../lib/roles";
import { backdropClickProps } from "../lib/modalBackdrop";
import Counterparties from "./Counterparties";
import ProjectCard from "./ProjectCard";
import AmountInput from "./AmountInput";
import { useTranslation } from "../lib/i18n";

// Вычисляемый статус проекта (planned/in_progress/closed — см.
// backend/app/routers/reports.py::_project_statuses) — не путать со
// STATUS_COLUMN ниже (обычный вкл/выкл is_active, общий для всех вкладок).
function renderProjectStatus(status, t) {
  if (!status) return "—";
  const variant = status === "in_progress" ? "ok" : status === "closed" ? "neutral" : "warn";
  return <span className={`fp-status-badge ${variant}`}>{t(`reference.projects.status.${status}`)}</span>;
}

const STATUS_COLUMN = {
  key: "is_active",
  labelKey: "reference.status",
  render: (v, row, t) => (
    <span className={`fp-status-badge ${v === false ? "warn" : "ok"}`}>
      {v === false ? t("reference.status.inactive") : t("reference.status.active")}
    </span>
  ),
};

const BANK_LABELS = {
  tbank: "Т-Банк",
  sberbank: "Сбербанк",
  alfabank: "Альфа-Банк",
  alfabank_business: "Альфа-Бизнес",
  vtb: "ВТБ",
  client_bank_1c: "1С:Клиент-Банк",
};

// Тот же провайдер, что Automation.jsx::PROVIDER_LABELS — для баннера
// ошибок синка здесь, отдельно от справочника интеграций.
const SYNC_PROVIDER_LABELS = {
  tinkoff: "Т-Банк",
  alfa: "Альфа-Банк",
  amocrm: "amoCRM",
  jump: "Jump.Finance",
};

const TABS = {
  categories: {
    labelKey: "reference.tab.categories",
    icon: Tag,
    list: (token, filter) =>
      api.listCategories(token, { company_ids: filter.companyIds, own_only: filter.ownOnly, match: filter.match }),
    create: (token, payload, companyId) => api.createCategory(token, payload, companyId),
    update: (token, id, payload) => api.updateCategory(token, id, payload),
    remove: (token, id) => api.deleteCategory(token, id),
    moveCompany: (token, id, companyId) => api.moveCategoryCompany(token, id, companyId),
    bulkVisibility: (token, ids, companyIds, isGlobal) => api.bulkVisibilityCategories(token, ids, companyIds, isGlobal),
    fields: [
      { key: "name", labelKey: "reference.categories.name", type: "text", required: true },
      { key: "group_name", labelKey: "reference.categories.group", type: "text" },
      {
        key: "type",
        labelKey: "reference.categories.type",
        type: "select",
        options: [
          { value: "income", labelKey: "tx.income" },
          { value: "expense", labelKey: "tx.expense" },
        ],
      },
    ],
    columns: [
      { key: "name", labelKey: "tx.col.category" },
      { key: "group_name", labelKey: "reference.categories.group" },
      { key: "type", labelKey: "reference.categories.type", render: (v, row, t) => (v === "income" ? t("tx.income") : t("tx.expense")) },
      STATUS_COLUMN,
    ],
  },
  projects: {
    labelKey: "reference.tab.projects",
    icon: LayoutDashboard,
    list: (token, filter) =>
      api.listProjects(token, { company_ids: filter.companyIds, own_only: filter.ownOnly, match: filter.match }),
    create: (token, payload, companyId) => api.createProject(token, payload, companyId),
    update: (token, id, payload) => api.updateProject(token, id, payload),
    remove: (token, id) => api.deleteProject(token, id),
    moveCompany: (token, id, companyId) => api.moveProjectCompany(token, id, companyId),
    bulkVisibility: (token, ids, companyIds, isGlobal) => api.bulkVisibilityProjects(token, ids, companyIds, isGlobal),
    fields: [
      { key: "name", labelKey: "reference.projects.name", type: "text", required: true },
      { key: "group_id", labelKey: "reference.projects.group", type: "select", optionsFrom: "projectGroups", allowEmpty: true },
    ],
    columns: [
      { key: "name", labelKey: "reports.project" },
      {
        key: "status",
        labelKey: "reference.projects.projectStatus",
        render: (v, row, t) => renderProjectStatus(v, t),
      },
      { key: "revenue", labelKey: "reports.revenue", render: (v) => (v == null ? "—" : fmt(v, "RUB")) },
      { key: "expense", labelKey: "dashboard.table.expense", render: (v) => (v == null ? "—" : fmt(v, "RUB")) },
      { key: "profit", labelKey: "reports.profit", render: (v) => (v == null ? "—" : fmt(v, "RUB")) },
      {
        key: "margin",
        labelKey: "reports.margin",
        render: (v) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`),
      },
      {
        key: "is_active",
        labelKey: "reference.status",
        render: (v, row, t) => (
          <span
            className={`fp-status-badge ${v === false ? "warn" : "ok"}`}
            title={v === false ? t("reference.projects.archivedHint") : undefined}
          >
            {v === false ? t("reference.status.inactive") : t("reference.status.active")}
          </span>
        ),
      },
    ],
  },
  projectGroups: {
    labelKey: "reference.tab.projectGroups",
    icon: LayoutDashboard,
    list: (token, filter) =>
      api.listProjectGroups(token, { company_ids: filter.companyIds, own_only: filter.ownOnly, match: filter.match }),
    create: (token, payload, companyId) => api.createProjectGroup(token, payload, companyId),
    update: (token, id, payload) => api.updateProjectGroup(token, id, payload),
    remove: (token, id) => api.deleteProjectGroup(token, id),
    moveCompany: (token, id, companyId) => api.moveProjectGroupCompany(token, id, companyId),
    bulkVisibility: (token, ids, companyIds, isGlobal) =>
      api.bulkVisibilityProjectGroups(token, ids, companyIds, isGlobal),
    fields: [{ key: "name", labelKey: "reference.projectGroups.name", type: "text", required: true }],
    columns: [{ key: "name", labelKey: "reference.projectGroups.name" }, STATUS_COLUMN],
  },
  accounts: {
    labelKey: "reference.tab.accounts",
    icon: Building2,
    list: (token, companyId) => api.listAccounts(token, { company_id: companyId }),
    create: (token, payload, companyId) => api.createAccount(token, payload, companyId),
    update: (token, id, payload) => api.updateAccount(token, id, payload),
    remove: (token, id) => api.deleteAccount(token, id),
    moveCompany: (token, id, companyId) => api.moveAccountCompany(token, id, companyId),
    fields: [
      { key: "name", labelKey: "reference.accounts.name", type: "text", required: true },
      {
        key: "currency",
        labelKey: "tx.form.currency",
        type: "select",
        options: [
          { value: "RUB", labelKey: null },
          { value: "USD", labelKey: null },
          { value: "EUR", labelKey: null },
          { value: "CNY", labelKey: null },
        ],
      },
      { key: "opening_balance", labelKey: "reference.accounts.openingBalance", type: "number" },
      { key: "account_number", labelKey: "reference.accounts.accountNumber", type: "text" },
    ],
    columns: [
      { key: "name", labelKey: "tx.col.account" },
      { key: "currency", labelKey: "tx.form.currency" },
      { key: "opening_balance", labelKey: "reference.accounts.openingBalance", render: (v, row) => fmt(v, row.currency) },
      { key: "account_number", labelKey: "reference.col.accountNumber", render: (v) => v || "—" },
      STATUS_COLUMN,
    ],
  },
  fixedAssets: {
    labelKey: "reference.tab.fixedAssets",
    icon: Archive,
    list: (token, companyId) => api.listFixedAssets(token, { company_id: companyId }),
    create: (token, payload, companyId) => api.createFixedAsset(token, payload, companyId),
    update: (token, id, payload) => api.updateFixedAsset(token, id, payload),
    remove: (token, id) => api.deleteFixedAsset(token, id),
    fields: [
      { key: "name", labelKey: "reference.fixedAssets.name", type: "text", required: true },
      { key: "purchase_date", labelKey: "reference.fixedAssets.purchaseDate", type: "date", required: true },
      { key: "purchase_cost_rub", labelKey: "reference.fixedAssets.purchaseCost", type: "number", required: true },
      { key: "useful_life_months", labelKey: "reference.fixedAssets.usefulLife", type: "number", required: true },
    ],
    columns: [
      { key: "name", labelKey: "reference.fixedAssets.name" },
      { key: "purchase_date", labelKey: "reference.fixedAssets.purchaseDate", render: (v) => fmtDate(v) },
      { key: "purchase_cost_rub", labelKey: "reference.fixedAssets.purchaseCost", render: (v) => fmt(v, "RUB") },
      { key: "book_value_rub", labelKey: "reference.fixedAssets.bookValue", render: (v) => fmt(v, "RUB") },
      STATUS_COLUMN,
    ],
  },
};

// Контрагенты живут в отдельном компоненте: карточка организации с реквизитами,
// контактными лицами и связью с СДВФ уже не укладывается в generic-таблицу выше.
const COUNTERPARTIES_TAB = "counterparties";
const TAB_BUTTONS = [
  ...Object.entries(TABS).map(([key, meta]) => ({ key, labelKey: meta.labelKey, icon: meta.icon })),
  { key: COUNTERPARTIES_TAB, labelKey: "reference.tab.counterparties", icon: Contact },
];

function defaultFormFor(fields) {
  const form = {};
  fields.forEach((f) => {
    form[f.key] = f.type === "number" ? "0" : f.options && !f.allowEmpty ? f.options[0].value : "";
  });
  return form;
}

export default function Reference({ initialTab = "categories" }) {
  const { token, user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const canEditAny = companies.some((m) => canEditReference(m.role));

  const [tab, setTab] = useState(initialTab);
  // Для вкладки контрагентов generic-конфига нет — она рендерится отдельным
  // компонентом ниже; TABS.categories тут только чтобы хуки ниже не падали.
  const config = TABS[tab] || TABS.categories;
  const isCounterparties = tab === COUNTERPARTIES_TAB;
  const supportsCompanyScope = tab === "categories" || tab === "projects" || tab === "projectGroups";

  // Счета/Контрагенты: нет межкомпанийной видимости, простой фильтр на одну
  // компанию ("" = все доступные). Статьи/Проекты — свой, более гибкий
  // фильтр ниже (companyFilterIds/ownOnly/matchMode), т.к. у них есть
  // is_global/visible_company_ids.
  const [companyFilter, setCompanyFilter] = useState("");

  // Фильтр Статей/Проектов по нескольким компаниям сразу: [] = все доступные.
  // ownOnly — исключить записи, которые видны здесь только потому, что
  // расшарены из другой компании (убрать пересечения). matchMode актуален
  // только когда выбрано >1 компании: "union" — видна хотя бы в одной из
  // них, "intersection" — расшарена именно между всеми выбранными сразу.
  const [companyFilterIds, setCompanyFilterIds] = useState([]);
  const [ownOnly, setOwnOnly] = useState(false);
  const [matchMode, setMatchMode] = useState("union");
  const [companyPopoverOpen, setCompanyPopoverOpen] = useState(false);
  const companyPopoverRef = useRef(null);

  // Фильтр по статусу проекта (planned/in_progress/closed, см.
  // renderProjectStatus) — только для вкладки "Проекты", по умолчанию все
  // три статуса включены (не сужает список, пока пользователь сам не снимет
  // галочку).
  const [statusFilter, setStatusFilter] = useState(["planned", "in_progress", "closed"]);
  const [statusPopoverOpen, setStatusPopoverOpen] = useState(false);
  const statusPopoverRef = useRef(null);
  function toggleStatusFilter(status) {
    setStatusFilter((prev) => (prev.includes(status) ? prev.filter((x) => x !== status) : [...prev, status]));
  }

  // Клик по названию группы во вкладке "Группы проектов" переключает на
  // вкладку "Проекты", отфильтрованную этой группой — НЕ открывает
  // редактирование самой группы (для этого отдельная кнопка-карандаш).
  // Сбрасывается при ручном переключении вкладок через switchTab().
  const [groupFilter, setGroupFilter] = useState("");
  function openProjectsForGroup(group) {
    setGroupFilter(group.id);
    setTab("projects");
  }

  // Клик по названию проекта открывает карточку проекта (см. ProjectCard.jsx)
  // ВМЕСТО остального содержимого вкладки — как view: "operations"|"balances"
  // в Transactions.jsx, не модалка (карточка с графиком/бюджетом/списком
  // операций физически не влезает в .fp-modal, тот капнут на 480px).
  // Сбрасывается при ручном переключении вкладок, как groupFilter.
  const [projectCardId, setProjectCardId] = useState(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (companyPopoverRef.current && !companyPopoverRef.current.contains(e.target)) {
        setCompanyPopoverOpen(false);
      }
    }
    if (companyPopoverOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [companyPopoverOpen]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (statusPopoverRef.current && !statusPopoverRef.current.contains(e.target)) {
        setStatusPopoverOpen(false);
      }
    }
    if (statusPopoverOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [statusPopoverOpen]);

  function toggleCompanyFilterId(id) {
    setCompanyFilterIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const { data: items, loading, error, reload } = useResource(
    () =>
      isCounterparties
        ? Promise.resolve([])
        : supportsCompanyScope
        ? config.list(token, { companyIds: companyFilterIds, ownOnly, match: matchMode })
        : config.list(token, companyFilter || undefined),
    [token, tab, companyFilter, companyFilterIds.join(","), ownOnly, matchMode]
  );

  // Группы проектов — нужны как опции в форме проекта (см. TABS.projects.fields
  // group_id/optionsFrom), загружаются один раз независимо от текущей вкладки,
  // а не только когда открыта сама вкладка "Группы проектов".
  const { data: projectGroups } = useResource(() => api.listProjectGroups(token, {}), [token]);
  const dynamicOptions = { projectGroups: projectGroups || [] };

  // Список проектов, отфильтрованный кликом по группе (см. openProjectsForGroup) —
  // фильтрация на клиенте, без отдельного запроса к бэкенду.
  const activeGroupName = groupFilter ? (projectGroups || []).find((g) => g.id === groupFilter)?.name : null;

  // Доходы/Расходы/Прибыль/Рентабельность/Статус на саму вкладку "Проекты" —
  // отдельный запрос к уже существующему /reports/profitability, склеенный
  // по project_id на клиенте (не раздувать сам /projects агрегацией, которая
  // ему не свойственна). Статус — вычисляемый на бэкенде (см. HANDOVER.md,
  // "Карточка проекта"): planned/in_progress/closed.
  const { data: projectProfitability } = useResource(
    () => (tab === "projects" ? api.profitabilityReport(token, {}) : Promise.resolve([])),
    [token, tab]
  );
  const profitabilityByProject = Object.fromEntries(
    (projectProfitability || []).filter((r) => r.project_id).map((r) => [r.project_id, r])
  );

  const groupFilteredItems =
    tab === "projects" && groupFilter ? (items || []).filter((p) => p.group_id === groupFilter) : items;
  const displayedItems =
    tab === "projects"
      ? (groupFilteredItems || [])
          .map((p) => ({ ...p, ...profitabilityByProject[p.id] }))
          .filter((p) => statusFilter.includes(p.status))
          .sort((a, b) => a.name.localeCompare(b.name, "ru"))
      : groupFilteredItems;

  // Автосинк банковских интеграций — только на вкладке Счетов, только для тех,
  // кто вообще может ими управлять. Бэкенд сам решает, не рано ли реально идти
  // в банк (integration.autosync_interval_minutes) — большинство таких вызовов
  // при обычной навигации мгновенно возвращают "пропущено по таймеру".
  const [syncBanner, setSyncBanner] = useState("");
  const [syncErrors, setSyncErrors] = useState([]);
  const [syncing, setSyncing] = useState(false);

  async function runIntegrationSync(force) {
    setSyncing(true);
    if (force) {
      setSyncBanner("");
      setSyncErrors([]);
    }
    try {
      const r = await api.syncAllIntegrations(token, companyFilter || undefined, force);
      if (force || r.processed > 0) setSyncBanner(r.message);
      setSyncErrors(r.errors_detail || []);
      if (r.processed > 0) reload();
    } catch (err) {
      if (force) setSyncBanner(err.message);
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    if (tab === "accounts" && canEditAny) {
      runIntegrationSync(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, companyFilter, canEditAny]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(defaultFormFor(config.fields));
  const [formCompanyId, setFormCompanyId] = useState("");
  const [originalCompanyId, setOriginalCompanyId] = useState("");
  const [formIsActive, setFormIsActive] = useState(true);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  // Счета: вместо поиска исторического остатка на дату первой синхронизированной
  // операции — вводим то, что видно в банке сейчас, бэкенд сам пересчитывает
  // "Начальный остаток" (см. AccountSetCurrentBalanceIn на бэкенде).
  const [currentBalanceInput, setCurrentBalanceInput] = useState("");
  const [settingBalance, setSettingBalance] = useState(false);
  const [balanceMessage, setBalanceMessage] = useState("");

  async function handleSetCurrentBalance() {
    setSettingBalance(true);
    setBalanceMessage("");
    try {
      const updated = await api.setAccountCurrentBalance(token, editingId, Number(currentBalanceInput));
      setForm((p) => ({ ...p, opening_balance: String(updated.opening_balance) }));
      setBalanceMessage(t("reference.balanceRecalculated"));
      setCurrentBalanceInput("");
      reload();
    } catch (err) {
      setBalanceMessage(err.message);
    } finally {
      setSettingBalance(false);
    }
  }

  // Импорт PDF-справки/выписки для счетов физлиц без банковского API (Т-Банк,
  // Сбербанк, Альфа-Банк, ВТБ) — банк определяется бэкендом по содержимому файла.
  // Сначала dry-run-предпросмотр (ничего не пишет в БД), затем подтверждение.
  const [statementFile, setStatementFile] = useState(null);
  const [statementPreview, setStatementPreview] = useState(null);
  const [statementResult, setStatementResult] = useState(null);
  const [statementBusy, setStatementBusy] = useState(false);
  const [statementError, setStatementError] = useState("");

  function resetStatementImport() {
    setStatementFile(null);
    setStatementPreview(null);
    setStatementResult(null);
    setStatementError("");
  }

  // Если файл выбран ещё до сохранения счёта (создание "с нуля"), сначала тихо
  // создаём счёт текущими значениями формы — иначе пришлось бы сначала жать
  // "Сохранить", а потом снова открывать счёт на редактирование ради импорта.
  // Дальше модалка ведёт себя как обычное редактирование уже созданного счёта.
  async function ensureAccountIdForStatement() {
    if (editingId) return editingId;
    if (!form.name?.trim()) {
      throw new Error(t("reference.nameRequiredError"));
    }
    const payload = { ...form, is_active: true };
    config.fields.forEach((f) => {
      if (f.type === "number") payload[f.key] = Number(payload[f.key] || 0);
    });
    const created = await config.create(token, payload, formCompanyId || undefined);
    setEditingId(created.id);
    setOriginalCompanyId(created.company_id);
    reload();
    return created.id;
  }

  async function handleStatementFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setStatementFile(file);
    setStatementResult(null);
    setStatementPreview(null);
    setStatementError("");
    setStatementBusy(true);
    try {
      const accountId = await ensureAccountIdForStatement();
      const preview = await api.importStatement(token, accountId, file, true);
      setStatementPreview(preview);
    } catch (err) {
      setStatementError(err.message);
    } finally {
      setStatementBusy(false);
    }
  }

  async function handleConfirmStatementImport() {
    if (!statementFile) return;
    setStatementBusy(true);
    setStatementError("");
    try {
      const accountId = await ensureAccountIdForStatement();
      // Остаток из справки применяется на бэкенде — тем же запросом и тем же
      // коммитом, что и сам импорт операций (см. routers/statements.py), а не
      // отдельным вызовом отсюда: раньше это было два шага, и порядок/сам факт
      // второго шага ничем не гарантировался.
      const result = await api.importStatement(token, accountId, statementFile, false);
      // Критично: синхронизируем поле формы с реальным значением из БД. Иначе
      // форма продолжает показывать старое "Начальный остаток", и если после
      // этого нажать общую кнопку "Сохранить", она отправит устаревшее число и
      // затрёт только что применённый остаток обратно — именно это и произошло
      // на реальных счетах пользователя.
      if (result.account_opening_balance != null) {
        setForm((p) => ({ ...p, opening_balance: String(result.account_opening_balance) }));
      }
      setStatementResult(result);
      setStatementPreview(null);
      setStatementFile(null);
      reload();
    } catch (err) {
      setStatementError(err.message);
    } finally {
      setStatementBusy(false);
    }
  }

  // Область видимости статьи/проекта по компаниям холдинга — отдельно от
  // generic form (у Account/Counterparty таких полей нет вовсе, схема бы не
  // приняла is_global/visible_company_ids). См. TABS.categories/projects.
  const [formIsGlobal, setFormIsGlobal] = useState(false);
  const [formVisibleCompanyIds, setFormVisibleCompanyIds] = useState([]);
  // Выбор строк чекбоксами + массовое удаление доступны на всех вкладках
  // generic-таблицы (Статьи/Проекты/Счета), не только при нескольких
  // компаниях. "Распределить по компаниям" — отдельно, только там, где это
  // вообще имеет смысл (межкомпанийная видимость + больше одной компании).
  const supportsSelection = !isCounterparties;
  const supportsBulkDistribute = supportsCompanyScope && multiCompany;

  // Массовое распределение выбранных статей/проектов по компаниям — в отличие
  // от "Видимость по компаниям" в форме одной записи (которая заменяет список
  // целиком), тут ДОБАВЛЯЕМ компании сразу нескольким выбранным записям, и
  // бэкенд сам сливает дубли с тем же названием, если они уже есть в целевой
  // компании (см. reference.py::_bulk_distribute).
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkCompanyIds, setBulkCompanyIds] = useState([]);
  const [bulkIsGlobal, setBulkIsGlobal] = useState(false);
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkError, setBulkError] = useState("");
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // Массовый перенос выбранных проектов в другую группу (или без группы) —
  // тот же паттерн выбора строк, что и распределение по компаниям выше,
  // просто целевое поле не company_id, а group_id.
  const [bulkGroupModalOpen, setBulkGroupModalOpen] = useState(false);
  const [bulkGroupTargetId, setBulkGroupTargetId] = useState("");
  const [bulkGroupSaving, setBulkGroupSaving] = useState(false);
  const [bulkGroupError, setBulkGroupError] = useState("");

  // Экспорт списка проектов в Excel (см. HANDOVER.md — пробел из сравнения
  // с ПланФактом) — переиспользует текущий фильтр по группе/компаниям.
  const [exportingProjects, setExportingProjects] = useState(false);
  async function handleExportProjects() {
    setExportingProjects(true);
    try {
      await api.exportProfitability(token, {
        company_id: companyFilterIds.length === 1 ? companyFilterIds[0] : undefined,
      });
    } catch (err) {
      window.alert(err.message);
    } finally {
      setExportingProjects(false);
    }
  }

  useEffect(() => {
    setSelectedIds(new Set());
  }, [tab, companyFilter, companyFilterIds.join(","), ownOnly, matchMode]);

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    const selectableIds = (displayedItems || [])
      .filter((i) => canEditReference(roleForCompany(i.company_id)))
      .map((i) => i.id);
    setSelectedIds((prev) => (prev.size === selectableIds.length ? new Set() : new Set(selectableIds)));
  }

  function openBulkModal() {
    setBulkCompanyIds([]);
    setBulkIsGlobal(false);
    setBulkError("");
    setBulkModalOpen(true);
  }

  async function handleBulkApply() {
    setBulkSaving(true);
    setBulkError("");
    try {
      const result = await config.bulkVisibility(
        token,
        Array.from(selectedIds),
        bulkIsGlobal ? [] : bulkCompanyIds,
        bulkIsGlobal
      );
      setBulkModalOpen(false);
      setSelectedIds(new Set());
      reload();
      if (result?.merged_names?.length > 0) {
        window.alert(
          t("reference.bulkMergedAlert", { updated: result.updated, names: result.merged_names.join(", ") })
        );
      }
    } catch (err) {
      setBulkError(err.message);
    } finally {
      setBulkSaving(false);
    }
  }

  function openBulkGroupModal() {
    setBulkGroupTargetId("");
    setBulkGroupError("");
    setBulkGroupModalOpen(true);
  }

  async function handleBulkGroupApply() {
    setBulkGroupSaving(true);
    setBulkGroupError("");
    try {
      const ids = Array.from(selectedIds);
      const results = await Promise.allSettled(
        ids.map((id) => {
          const item = items.find((i) => i.id === id);
          const payload = Object.fromEntries(config.fields.map((f) => [f.key, item[f.key]]));
          payload.group_id = bulkGroupTargetId || "";
          return config.update(token, id, payload);
        })
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      setBulkGroupModalOpen(false);
      setSelectedIds(new Set());
      reload();
      if (failed > 0) {
        window.alert(t("reference.bulkGroupFailedPart", { count: failed }));
      }
    } catch (err) {
      setBulkGroupError(err.message);
    } finally {
      setBulkGroupSaving(false);
    }
  }

  function openAdd() {
    setEditingId(null);
    setForm(defaultFormFor(config.fields));
    const editableCompanies = companies.filter((m) => canEditReference(m.role));
    const currentFilterCompanyId = supportsCompanyScope
      ? companyFilterIds.length === 1
        ? companyFilterIds[0]
        : ""
      : companyFilter;
    const preselected = editableCompanies.find((m) => m.company.id === currentFilterCompanyId) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setOriginalCompanyId("");
    setFormIsActive(true);
    setFormIsGlobal(false);
    setFormVisibleCompanyIds([]);
    setFormError("");
    setCurrentBalanceInput("");
    setBalanceMessage("");
    resetStatementImport();
    setModalOpen(true);
  }

  function openEdit(item) {
    setEditingId(item.id);
    const next = {};
    config.fields.forEach((f) => (next[f.key] = item[f.key] ?? ""));
    setForm(next);
    setFormCompanyId(item.company_id || "");
    setOriginalCompanyId(item.company_id || "");
    setFormIsActive(item.is_active !== false);
    setFormIsGlobal(!!item.is_global);
    setFormVisibleCompanyIds(item.visible_company_ids || []);
    setFormError("");
    setCurrentBalanceInput("");
    setBalanceMessage("");
    resetStatementImport();
    setModalOpen(true);
  }

  function switchTab(key) {
    setGroupFilter("");
    setProjectCardId(null);
    setTab(key);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const payload = { ...form, is_active: formIsActive };
      config.fields.forEach((f) => {
        if (f.type === "number") payload[f.key] = Number(payload[f.key] || 0);
        if (f.allowEmpty && payload[f.key] === "") payload[f.key] = null;
      });
      if (supportsCompanyScope) {
        payload.is_global = formIsGlobal;
        payload.visible_company_ids = formIsGlobal ? [] : formVisibleCompanyIds;
      }
      if (editingId) {
        // Перенос в другую компанию — отдельным вызовом (бэкенд блокирует его,
        // если запись уже где-то используется, см. move_to_company) и раньше
        // остальных правок, чтобы не сохранить их в исходной компании, если
        // перенос не удался. Часть вкладок (напр. Группы проектов) перенос
        // между компаниями вообще не поддерживают — select компании для них
        // задизейблен при редактировании, но проверяем и здесь на всякий случай.
        if (multiCompany && formCompanyId && formCompanyId !== originalCompanyId && config.moveCompany) {
          await config.moveCompany(token, editingId, formCompanyId);
        }
        await config.update(token, editingId, payload);
      } else {
        await config.create(token, payload, formCompanyId || undefined);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(t("reference.deleteConfirm", { name: item.name }))) return;
    try {
      const result = await config.remove(token, item.id);
      if (result?.deactivated) {
        window.alert(t("reference.deactivatedAlert", { name: item.name }));
      }
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  async function handleBulkDelete() {
    const ids = Array.from(selectedIds);
    if (!window.confirm(t("reference.bulkDeleteConfirm", { count: ids.length }))) return;
    setBulkDeleting(true);
    // Как и у одиночного удаления — запись, которая уже используется в
    // операциях, не стирается, а деактивируется (config.remove сам это решает
    // на бэкенде). Promise.allSettled, а не Promise.all — одна проблемная
    // запись (например, гонка с параллельным удалением) не должна прерывать
    // удаление остальных выбранных.
    const results = await Promise.allSettled(ids.map((id) => config.remove(token, id)));
    const deleted = results.filter((r) => r.status === "fulfilled" && !r.value?.deactivated).length;
    const deactivated = results.filter((r) => r.status === "fulfilled" && r.value?.deactivated).length;
    const failed = results.length - deleted - deactivated;
    setSelectedIds(new Set());
    setBulkDeleting(false);
    reload();
    if (deactivated > 0 || failed > 0) {
      window.alert(
        t("reference.bulkDeletedPart", { count: deleted }) +
          (deactivated > 0 ? t("reference.bulkDeactivatedPart", { count: deactivated }) : "") +
          (failed > 0 ? t("reference.bulkFailedPart", { count: failed }) : "")
      );
    }
  }

  async function handleToggleActive(item) {
    const payload = Object.fromEntries(config.fields.map((f) => [f.key, item[f.key]]));
    payload.is_active = item.is_active === false;
    try {
      await config.update(token, item.id, payload);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  const showCompanyColumn = supportsCompanyScope
    ? multiCompany && (companyFilterIds.length !== 1 || !ownOnly)
    : multiCompany && !companyFilter;
  const editableCompanies = companies.filter((m) => canEditReference(m.role));

  const tabsRow = (
    <div className="fp-tabs">
      {TAB_BUTTONS.map((meta) => (
        <button key={meta.key} className={tab === meta.key ? "active" : ""} onClick={() => switchTab(meta.key)}>
          <meta.icon size={14} />
          {t(meta.labelKey)}
        </button>
      ))}
    </div>
  );

  if (isCounterparties) {
    return (
      <div className="fp-dash">
        <div className="fp-tabs-row">{tabsRow}</div>
        <Counterparties />
      </div>
    );
  }

  if (tab === "projects" && projectCardId) {
    return (
      <div className="fp-dash">
        <div className="fp-tabs-row">{tabsRow}</div>
        <ProjectCard
          token={token}
          projectId={projectCardId}
          onBack={() => setProjectCardId(null)}
          canEdit={canEditAny}
        />
      </div>
    );
  }

  return (
    <div className="fp-dash">
      <div className="fp-tabs-row">
        {tabsRow}
        {tab === "projects" && (
          <select value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)}>
            <option value="">{t("reference.projects.allGroups")}</option>
            {(projectGroups || []).map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        )}
        {tab === "projects" && (
          <div style={{ position: "relative" }} ref={statusPopoverRef}>
            <button type="button" className="fp-btn-tiny" onClick={() => setStatusPopoverOpen((v) => !v)}>
              {statusFilter.length === 3
                ? t("reference.projects.allStatuses")
                : statusFilter.length === 0
                ? t("reference.projects.noStatuses")
                : statusFilter.map((s) => t(`reference.projects.status.${s}`)).join(", ")}
              <ChevronDown size={13} className={`fp-combobox-chevron ${statusPopoverOpen ? "rotated" : ""}`} />
            </button>
            {statusPopoverOpen && (
              <div className="fp-combobox-popup" style={{ width: 200, padding: "6px 0" }}>
                {["planned", "in_progress", "closed"].map((s) => (
                  <label key={s} className="fp-checkbox-row">
                    <input
                      type="checkbox"
                      checked={statusFilter.includes(s)}
                      onChange={() => toggleStatusFilter(s)}
                    />
                    {t(`reference.projects.status.${s}`)}
                  </label>
                ))}
              </div>
            )}
          </div>
        )}
        {multiCompany && !supportsCompanyScope && (
          <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
            <option value="">{t("dashboard.allCompanies")}</option>
            {companies.map((m) => (
              <option key={m.company.id} value={m.company.id}>
                {m.company.name}
              </option>
            ))}
          </select>
        )}
        {multiCompany && supportsCompanyScope && (
          <div style={{ position: "relative" }} ref={companyPopoverRef}>
            <button
              type="button"
              className="fp-btn-tiny"
              onClick={() => setCompanyPopoverOpen((v) => !v)}
            >
              <Building2 size={13} />
              {companyFilterIds.length === 0
                ? t("dashboard.allCompanies")
                : companyFilterIds.length === 1
                ? companies.find((m) => m.company.id === companyFilterIds[0])?.company.name || t("reference.oneCompany")
                : t("reference.companiesCount", { count: companyFilterIds.length })}
              {ownOnly && companyFilterIds.length > 0 && t("reference.onlyOwnSuffix")}
              <ChevronDown size={13} className={`fp-combobox-chevron ${companyPopoverOpen ? "rotated" : ""}`} />
            </button>
            {companyPopoverOpen && (
              <div className="fp-combobox-popup" style={{ width: 280, padding: "6px 0" }}>
                <label
                  className="fp-checkbox-row"
                  style={{ fontWeight: companyFilterIds.length === 0 ? 600 : 400 }}
                >
                  <input type="checkbox" checked={companyFilterIds.length === 0} onChange={() => setCompanyFilterIds([])} />
                  {t("dashboard.allCompanies")}
                </label>
                <div style={{ borderTop: "1px solid var(--line)", margin: "4px 0" }} />
                {companies.map((m) => (
                  <label key={m.company.id} className="fp-checkbox-row">
                    <input
                      type="checkbox"
                      checked={companyFilterIds.includes(m.company.id)}
                      onChange={() => toggleCompanyFilterId(m.company.id)}
                    />
                    {m.company.name}
                  </label>
                ))}
                <div style={{ borderTop: "1px solid var(--line)", margin: "4px 0" }} />
                <label className="fp-checkbox-row">
                  <input type="checkbox" checked={ownOnly} onChange={(e) => setOwnOnly(e.target.checked)} />
                  {t("reference.onlyOwnCheckbox")}
                </label>
                {companyFilterIds.length > 1 && !ownOnly && (
                  <div style={{ padding: "4px 12px 2px" }}>
                    <div className="fp-note" style={{ margin: "2px 0 4px" }}>
                      {t("reference.multipleCompaniesHint")}
                    </div>
                    <label className="fp-checkbox-row" style={{ padding: "4px 0" }}>
                      <input
                        type="radio"
                        name="companyFilterMatch"
                        checked={matchMode === "union"}
                        onChange={() => setMatchMode("union")}
                      />
                      {t("reference.matchUnion")}
                    </label>
                    <label className="fp-checkbox-row" style={{ padding: "4px 0" }}>
                      <input
                        type="radio"
                        name="companyFilterMatch"
                        checked={matchMode === "intersection"}
                        onChange={() => setMatchMode("intersection")}
                      />
                      {t("reference.matchIntersection")}
                    </label>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        {tab === "accounts" && canEditAny && (
          <button type="button" className="fp-btn-tiny" onClick={() => runIntegrationSync(true)} disabled={syncing}>
            <RefreshCw size={13} /> {syncing ? t("dashboard.syncing") : t("dashboard.sync")}
          </button>
        )}
        {supportsBulkDistribute && canEditAny && selectedIds.size > 0 && (
          <button type="button" className="fp-btn-tiny" onClick={openBulkModal}>
            <Building2 size={13} /> {t("reference.distributeByCompanies", { count: selectedIds.size })}
          </button>
        )}
        {tab === "projects" && canEditAny && selectedIds.size > 0 && (
          <button type="button" className="fp-btn-tiny" onClick={openBulkGroupModal}>
            <LayoutDashboard size={13} /> {t("reference.moveToGroup", { count: selectedIds.size })}
          </button>
        )}
        {tab === "projects" && (
          <button type="button" className="fp-btn-tiny" onClick={handleExportProjects} disabled={exportingProjects}>
            <Download size={13} />{" "}
            {exportingProjects ? t("reference.exporting") : t("reference.exportProjects")}
          </button>
        )}
        {supportsSelection && canEditAny && selectedIds.size > 0 && (
          <button type="button" className="fp-btn-tiny" onClick={handleBulkDelete} disabled={bulkDeleting}>
            <Trash2 size={13} />{" "}
            {bulkDeleting ? t("tx.deleting") : t("reference.deleteSelected", { count: selectedIds.size })}
          </button>
        )}
        {canEditAny && (
          <button type="button" className="fp-btn-tiny" onClick={openAdd}>
            <Plus size={13} /> {t("common.add")}
          </button>
        )}
      </div>

      {tab === "accounts" && syncBanner && (
        <div className="fp-panel" style={{ padding: "10px 14px", fontSize: 13 }}>
          {syncBanner}
          {syncErrors.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18, color: "var(--rust, #a8503f)" }}>
              {syncErrors.map((e, i) => (
                <li key={i}>
                  {SYNC_PROVIDER_LABELS[e.provider] || e.provider}
                  {e.account_name ? ` — ${t("tx.col.account")} «${e.account_name}»` : ""}: {e.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {error && <div className="fp-error-banner">{error}</div>}

      {tab === "projects" && groupFilter && (
        <div className="fp-panel" style={{ padding: "10px 14px", fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
          {t("reference.projects.filteredByGroup", { name: activeGroupName || "" })}
          <button type="button" className="fp-btn-tiny" onClick={() => setGroupFilter("")}>
            <X size={12} /> {t("reference.projects.clearGroupFilter")}
          </button>
        </div>
      )}

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (displayedItems || []).length === 0 ? (
          <div className="fp-empty">{t("reference.listEmpty")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {supportsSelection && canEditAny && (
                  <th style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={
                        selectedIds.size > 0 &&
                        selectedIds.size ===
                          (displayedItems || []).filter((i) => canEditReference(roleForCompany(i.company_id))).length
                      }
                      onChange={toggleSelectAll}
                    />
                  </th>
                )}
                {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                {config.columns.map((c) => (
                  <th key={c.key}>{t(c.labelKey)}</th>
                ))}
                <th className="fp-table-actions-col"></th>
              </tr>
            </thead>
            <tbody>
              {displayedItems.map((item) => {
                const canEditRow = canEditReference(roleForCompany(item.company_id));
                return (
                  <tr key={item.id}>
                    {supportsSelection && canEditAny && (
                      <td>
                        {canEditRow && (
                          <input
                            type="checkbox"
                            checked={selectedIds.has(item.id)}
                            onChange={() => toggleSelect(item.id)}
                          />
                        )}
                      </td>
                    )}
                    {showCompanyColumn && (
                      <td>
                        {item.is_global ? (
                          <span className="fp-status-badge ok">{t("reference.allCompaniesTag")}</span>
                        ) : (
                          <>
                            {companies.find((m) => m.company.id === item.company_id)?.company.name || "—"}
                            {item.visible_company_ids?.length > 0 && (
                              <span className="fp-muted" style={{ marginLeft: 6, fontSize: 11.5 }}>
                                +{item.visible_company_ids.length}
                              </span>
                            )}
                          </>
                        )}
                      </td>
                    )}
                    {config.columns.map((c) =>
                      tab === "projectGroups" && c.key === "name" ? (
                        <td key={c.key}>
                          <button
                            type="button"
                            className="fp-link-button"
                            onClick={() => openProjectsForGroup(item)}
                            title={t("reference.projectGroups.openProjects")}
                          >
                            {item.name}
                          </button>
                        </td>
                      ) : tab === "projects" && c.key === "name" ? (
                        <td key={c.key}>
                          <button
                            type="button"
                            className="fp-link-button"
                            onClick={() => setProjectCardId(item.id)}
                            title={t("reference.projects.openCard")}
                          >
                            {item.name}
                          </button>
                        </td>
                      ) : (
                        <td key={c.key}>{c.render ? c.render(item[c.key], item, t) : item[c.key] || "—"}</td>
                      )
                    )}
                    <td className="fp-table-actions-col">
                      {canEditRow && (
                        <span className="fp-row-actions">
                          <button className="fp-icon-btn" onClick={() => openEdit(item)}>
                            <Pencil size={14} />
                          </button>
                          <button
                            className="fp-icon-btn"
                            onClick={() => handleToggleActive(item)}
                            title={item.is_active === false ? t("payroll.restore") : t("reference.deactivate")}
                          >
                            {item.is_active === false ? <RotateCcw size={14} /> : <Ban size={14} />}
                          </button>
                          <button className="fp-icon-btn" onClick={() => handleDelete(item)}>
                            <Trash2 size={14} />
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {tab === "projects" && (displayedItems || []).length > 0 && (
          <div className="fp-table-totals-row">
            <span>{t("reference.projects.totalsLabel", { count: displayedItems.length })}</span>
            <span>
              {t("reports.revenue")}: {fmt(displayedItems.reduce((s, p) => s + (p.revenue || 0), 0), "RUB")}
            </span>
            <span>
              {t("dashboard.table.expense")}: {fmt(displayedItems.reduce((s, p) => s + (p.expense || 0), 0), "RUB")}
            </span>
            <span>
              {t("reports.profit")}: {fmt(displayedItems.reduce((s, p) => s + (p.profit || 0), 0), "RUB")}
            </span>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t(editingId ? `reference.editTitle.${tab}` : `reference.newTitle.${tab}`)}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && (
                <label className="fp-span-2">
                  {t("tx.form.company")}
                  <select
                    value={formCompanyId}
                    onChange={(e) => setFormCompanyId(e.target.value)}
                    disabled={!!editingId && !config.moveCompany}
                    required
                  >
                    {/* Текущая компания записи может быть уже недоступна для
                        переноса (не admin) — всё равно показываем её в списке,
                        иначе выбранное значение "потеряется" при открытии формы. */}
                    {!editableCompanies.some((m) => m.company.id === originalCompanyId) &&
                      originalCompanyId &&
                      companies
                        .filter((m) => m.company.id === originalCompanyId)
                        .map((m) => (
                          <option key={m.company.id} value={m.company.id}>
                            {m.company.name}
                          </option>
                        ))}
                    {editableCompanies.map((m) => (
                      <option key={m.company.id} value={m.company.id}>
                        {m.company.name}
                      </option>
                    ))}
                  </select>
                  {editingId && formCompanyId !== originalCompanyId && (
                    <span className="fp-muted" style={{ fontSize: 12, display: "block", marginTop: 4 }}>
                      {t("reference.moveNote")}
                    </span>
                  )}
                </label>
              )}
              {config.fields.map((f) => (
                <label key={f.key} className={f.type === "text" && f.key === "name" ? "fp-span-2" : ""}>
                  {t(f.labelKey)}
                  {f.type === "select" && f.optionsFrom ? (
                    <select value={form[f.key]} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}>
                      {f.allowEmpty && <option value="">{t("reference.noGroup")}</option>}
                      {(dynamicOptions[f.optionsFrom] || [])
                        .filter((o) => !formCompanyId || o.company_id === formCompanyId)
                        .map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name}
                          </option>
                        ))}
                    </select>
                  ) : f.type === "select" ? (
                    <select value={form[f.key]} onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}>
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.labelKey ? t(o.labelKey) : o.value}
                        </option>
                      ))}
                    </select>
                  ) : f.type === "number" ? (
                    <AmountInput
                      required={f.required}
                      value={form[f.key]}
                      onChange={(v) => {
                        setForm((p) => ({ ...p, [f.key]: v }));
                        if (f.key === "opening_balance") setStatementResult(null);
                      }}
                    />
                  ) : f.type === "date" ? (
                    <input
                      type="date"
                      required={f.required}
                      value={form[f.key]}
                      onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    />
                  ) : (
                    <input
                      type="text"
                      required={f.required}
                      value={form[f.key]}
                      onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                    />
                  )}
                  {f.key === "opening_balance" && statementResult?.account_opening_balance != null && (
                    <span style={{ color: "var(--expense)", fontSize: 11.5, display: "block", marginTop: 3 }}>
                      {t("reference.matchesBank")}
                    </span>
                  )}
                </label>
              ))}

              {supportsCompanyScope && multiCompany && (
                <div
                  className="fp-span-2"
                  style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{t("reference.visibilityTitle")}</div>
                  <label className="fp-checkbox-row">
                    <input
                      type="checkbox"
                      checked={formIsGlobal}
                      onChange={(e) => setFormIsGlobal(e.target.checked)}
                    />
                    {t("reference.allCompaniesFuture")}
                  </label>
                  {!formIsGlobal && (
                    <>
                      <p className="fp-note" style={{ margin: "6px 0 2px" }}>
                        {t(`reference.visibilityHint.${tab}`)}
                      </p>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {companies
                          .filter((m) => canEditReference(m.role) && m.company.id !== formCompanyId)
                          .map((m) => (
                            <label key={m.company.id} className="fp-checkbox-row">
                              <input
                                type="checkbox"
                                checked={formVisibleCompanyIds.includes(m.company.id)}
                                onChange={(e) =>
                                  setFormVisibleCompanyIds((prev) =>
                                    e.target.checked
                                      ? [...prev, m.company.id]
                                      : prev.filter((id) => id !== m.company.id)
                                  )
                                }
                              />
                              {m.company.name}
                            </label>
                          ))}
                      </div>
                    </>
                  )}
                </div>
              )}

              {tab === "accounts" && editingId && (
                <div
                  className="fp-span-2"
                  style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{t("reference.balanceMismatchTitle")}</div>
                  <p className="fp-note" style={{ margin: "0 0 8px" }}>
                    {t("reference.balanceMismatchNote")}
                  </p>
                  <div style={{ display: "flex", gap: 6 }}>
                    <AmountInput
                      placeholder={t("reference.balanceToday")}
                      value={currentBalanceInput}
                      onChange={(v) => {
                        setBalanceMessage("");
                        setCurrentBalanceInput(v);
                      }}
                      style={{ flex: 1, minWidth: 0 }}
                    />
                    <button
                      type="button"
                      className="fp-btn-ghost"
                      onClick={handleSetCurrentBalance}
                      disabled={!currentBalanceInput || settingBalance}
                      style={{ whiteSpace: "nowrap" }}
                    >
                      {settingBalance ? t("reference.calculating") : t("reference.specify")}
                    </button>
                  </div>
                  {balanceMessage && (
                    <div className="fp-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                      {balanceMessage}
                    </div>
                  )}
                </div>
              )}

              {tab === "accounts" && (
                <div
                  className="fp-span-2"
                  style={{ border: "1px solid var(--line)", borderRadius: 8, padding: 12, marginTop: 4 }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                    {t("reference.importTitle")}
                  </div>
                  <p className="fp-note" style={{ margin: "0 0 8px" }}>
                    {t("reference.importNote")}
                    {!editingId && t("reference.importAutoSaveNote")}
                  </p>
                  <label className="fp-btn-ghost" style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                    <Upload size={14} />
                    {statementFile ? statementFile.name : t("reference.chooseFile")}
                    <input
                      type="file"
                      accept="application/pdf,.pdf,.txt,text/plain"
                      onChange={handleStatementFileChange}
                      disabled={statementBusy}
                      style={{ display: "none" }}
                    />
                  </label>
                  {statementBusy && (
                    <div className="fp-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                      {t("reference.parsingFile")}
                    </div>
                  )}
                  {statementError && (
                    <div className="fp-form-error" style={{ marginTop: 6 }}>
                      {statementError}
                    </div>
                  )}
                  {statementPreview && (
                    <div style={{ marginTop: 8, fontSize: 12.5 }}>
                      <div>
                        {t("reference.bank")}: <b>{BANK_LABELS[statementPreview.bank] || statementPreview.bank}</b>
                        {statementPreview.period_from && statementPreview.period_to && (
                          <>
                            {" "}
                            · {t("payroll.col.period")} {fmtDate(statementPreview.period_from)} — {fmtDate(statementPreview.period_to)}
                          </>
                        )}
                      </div>
                      <div style={{ marginTop: 4 }}>
                        {t("reference.newOps")}: <b>{statementPreview.created}</b>
                        {statementPreview.skipped_duplicate > 0 && (
                          <> · {t("reference.alreadyInSystem")}: {statementPreview.skipped_duplicate}</>
                        )}
                        {statementPreview.skipped_no_fx_rate > 0 && (
                          <> · {t("reference.noRateOnDate")}: {statementPreview.skipped_no_fx_rate}</>
                        )}
                      </div>
                      {statementPreview.closing_balance != null && (
                        <div style={{ marginTop: 6 }}>
                          {t("reference.balanceAsOf", { date: fmtDate(statementPreview.closing_balance_date) })}:{" "}
                          <b>{fmt(statementPreview.closing_balance, form.currency)}</b>
                          {t("reference.willApplyAuto")}
                          {statementPreview.created > 0 ? t("reference.afterImport") : "."}
                        </div>
                      )}
                      <div style={{ marginTop: 8 }}>
                        <button
                          type="button"
                          className="fp-btn-primary"
                          onClick={handleConfirmStatementImport}
                          disabled={statementBusy || (statementPreview.created === 0 && statementPreview.closing_balance == null)}
                        >
                          {statementBusy
                            ? t("reference.processing")
                            : statementPreview.created > 0
                            ? t("reference.importNOps", { count: statementPreview.created })
                            : t("reference.applyBalanceFromStatement")}
                        </button>
                      </div>
                    </div>
                  )}
                  {statementResult && (
                    <div className="fp-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                      {t("reference.importedNOps", { count: statementResult.created })}
                      {statementResult.skipped_duplicate > 0
                        ? t("reference.skippedDuplicates", { count: statementResult.skipped_duplicate })
                        : ""}
                      {statementResult.closing_balance != null ? t("reference.openingBalanceRecalculated") : "."}
                    </div>
                  )}
                </div>
              )}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}

              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setModalOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button type="submit" className="fp-btn-primary" disabled={saving}>
                  {saving ? t("common.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {bulkModalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setBulkModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("reference.distributeTitle", { count: selectedIds.size })}</h3>
              <button className="fp-icon-btn" onClick={() => setBulkModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <p className="fp-note" style={{ margin: "0 0 10px" }}>
              {t("reference.distributeNote", { noun: t(`reference.pluralNoun.${tab}`) })}
            </p>
            <label className="fp-checkbox-row">
              <input type="checkbox" checked={bulkIsGlobal} onChange={(e) => setBulkIsGlobal(e.target.checked)} />
              {t("reference.allCompaniesFuture")}
            </label>
            {!bulkIsGlobal && (
              <div style={{ display: "flex", flexDirection: "column", marginTop: 4 }}>
                {editableCompanies.map((m) => (
                  <label key={m.company.id} className="fp-checkbox-row">
                    <input
                      type="checkbox"
                      checked={bulkCompanyIds.includes(m.company.id)}
                      onChange={(e) =>
                        setBulkCompanyIds((prev) =>
                          e.target.checked ? [...prev, m.company.id] : prev.filter((id) => id !== m.company.id)
                        )
                      }
                    />
                    {m.company.name}
                  </label>
                ))}
              </div>
            )}
            {bulkError && <div className="fp-form-error" style={{ marginTop: 10 }}>{bulkError}</div>}
            <div className="fp-modal-foot">
              <button type="button" className="fp-btn-ghost" onClick={() => setBulkModalOpen(false)}>
                {t("common.cancel")}
              </button>
              <button
                type="button"
                className="fp-btn-primary"
                onClick={handleBulkApply}
                disabled={bulkSaving || (!bulkIsGlobal && bulkCompanyIds.length === 0)}
              >
                {bulkSaving ? t("reference.applying") : t("reference.apply")}
              </button>
            </div>
          </div>
        </div>
      )}

      {bulkGroupModalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setBulkGroupModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("reference.moveToGroupTitle", { count: selectedIds.size })}</h3>
              <button className="fp-icon-btn" onClick={() => setBulkGroupModalOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <label>
              {t("reference.projects.group")}
              <select value={bulkGroupTargetId} onChange={(e) => setBulkGroupTargetId(e.target.value)}>
                <option value="">{t("reference.noGroup")}</option>
                {(dynamicOptions.projectGroups || []).map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </label>
            {bulkGroupError && <div className="fp-form-error" style={{ marginTop: 10 }}>{bulkGroupError}</div>}
            <div className="fp-modal-foot">
              <button type="button" className="fp-btn-ghost" onClick={() => setBulkGroupModalOpen(false)}>
                {t("common.cancel")}
              </button>
              <button type="button" className="fp-btn-primary" onClick={handleBulkGroupApply} disabled={bulkGroupSaving}>
                {bulkGroupSaving ? t("reference.applying") : t("reference.apply")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
