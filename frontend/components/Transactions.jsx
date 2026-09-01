"use client";

import { useMemo, useState, useEffect } from "react";
import { Plus, Download, X, Pencil, Trash2, Lock, RefreshCw, CalendarCheck, Wallet, List as ListIcon } from "lucide-react";
import { useAuth } from "../lib/auth-context";
import { api } from "../lib/api";
import { useResource } from "../lib/useResource";
import { fmt, fmtDate } from "../lib/format";
import { canEditTransactions } from "../lib/roles";
import { Combobox } from "./Combobox";
import AmountInput from "./AmountInput";
import AttachmentList from "./AttachmentList";
import { backdropClickProps } from "../lib/modalBackdrop";
import { useTranslation } from "../lib/i18n";

const SOURCE_LABELS = { tbank: "Т-Банк", amocrm: "amoCRM", alfabank: "Альфа-Банк" };
// Тот же провайдер, что и в Automation.jsx::PROVIDER_LABELS (banner ошибок
// синка нужен здесь отдельно от справочника интеграций — не тянем весь
// компонент ради одной константы).
const SYNC_PROVIDER_LABELS = {
  tinkoff: "Т-Банк",
  alfa: "Альфа-Банк",
  amocrm: "amoCRM",
  jump: "Jump.Finance",
};

function sourceBadge(externalRef, t) {
  if (!externalRef) return null;
  const provider = externalRef.split(":")[0];
  const label = SOURCE_LABELS[provider];
  if (!label) return null;
  return (
    <span className={`fp-source-badge ${provider}`} title={t("tx.sourceTitle")}>
      {label}
    </span>
  );
}

const EMPTY_FORM = {
  date_odds: new Date().toISOString().slice(0, 10),
  date_opu: new Date().toISOString().slice(0, 10),
  account_id: "",
  category_id: "",
  project_id: "",
  counterparty_id: "",
  order_id: "",
  type: "expense",
  amount: "",
  currency: "RUB",
  commission: "0",
  comment: "",
  bank_payment_purpose: "",
  from_account_id: "",
  to_account_id: "",
  from_category_id: "",
  to_category_id: "",
  payment_confirmed: true,
  accrual_confirmed: true,
};

export default function Transactions() {
  const { token, user } = useAuth();
  const { t } = useTranslation();
  const companies = user.companies || [];
  const multiCompany = companies.length > 1;
  const roleForCompany = (companyId) => companies.find((m) => m.company.id === companyId)?.role;
  const canEditAnyCompany = companies.some((m) => canEditTransactions(m.role));
  // Обратная совместимость для однокомпанийного случая — совпадает со старым canEdit.
  const canEdit = canEditAnyCompany;
  // Синк банковских интеграций — доступ строже, чем canEdit (там ещё и оператор):
  // /integrations/sync-all на бэкенде требует именно admin, как и весь раздел
  // "Автоматизация".
  const canSyncIntegrations = companies.some((m) => m.role === "admin");

  const [view, setView] = useState("operations"); // "operations" | "balances"
  const [filters, setFilters] = useState({
    company: "",
    project: "",
    project_group: "",
    account: "",
    category: "",
    date_from: "",
    date_to: "",
    confirmed: "",
  });
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  // Превратить операцию (обычно "Импорт из банка") в Перемещение/Начисление —
  // не редактируем на месте (см. isTransfer/isReclass = !editing — парные
  // записи нельзя менять через форму одиночной операции), а открываем форму
  // создания новой пары с предзаполненными данными; исходную запись удаляем
  // только ПОСЛЕ успешного создания пары, чтобы не потерять данные при отмене.
  const [convertingFromId, setConvertingFromId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formCompanyId, setFormCompanyId] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [addAnother, setAddAnother] = useState(false);
  const [saveConfirmMsg, setSaveConfirmMsg] = useState("");
  const [closeMonthOpen, setCloseMonthOpen] = useState(false);
  const [closeMonthCompanyId, setCloseMonthCompanyId] = useState("");
  const [closeMonthValue, setCloseMonthValue] = useState(new Date().toISOString().slice(0, 7));
  const [closeMonthBusy, setCloseMonthBusy] = useState(false);
  const [closeMonthError, setCloseMonthError] = useState("");
  const [closeMonthMsg, setCloseMonthMsg] = useState("");
  const [exporting, setExporting] = useState(false);
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(0);
  const [useAllForDates, setUseAllForDates] = useState(false);
  const [selectedTransactionIds, setSelectedTransactionIds] = useState(new Set());
  const [selectedAllMatching, setSelectedAllMatching] = useState(false);
  const [matchingCount, setMatchingCount] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const { data: accounts } = useResource(() => api.listAccounts(token), [token]);
  const { data: categories, reload: reloadCategories } = useResource(() => api.listCategories(token), [token]);
  const { data: projects, reload: reloadProjects } = useResource(() => api.listProjects(token), [token]);
  const { data: projectGroups } = useResource(() => api.listProjectGroups(token, {}), [token]);
  const { data: counterparties, reload: reloadCounterparties } = useResource(
    () => api.listCounterparties(token),
    [token]
  );
  // Заказы — необязательная связь (см. HANDOVER.md, "Связь Заказа с оплатой").
  // Склад может быть выключен для компании — .catch(() => []) вместо падения формы.
  const { data: orders } = useResource(
    () => api.listOrders(token).catch(() => []),
    [token]
  );

  const query = {
    company_id: filters.company || undefined,
    project: filters.project || undefined,
    project_group_id: filters.project ? undefined : filters.project_group || undefined,
    account: filters.account || undefined,
    category: filters.category || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    confirmed: filters.confirmed || undefined,
    limit: useAllForDates ? undefined : pageSize,
    skip: useAllForDates ? undefined : currentPage * pageSize,
    all_records: useAllForDates || undefined,
  };
  const {
    data: transactions,
    loading,
    error,
    reload,
  } = useResource(() => api.listTransactions(token, query), [token, JSON.stringify(query)]);

  const countQuery = {
    company_id: filters.company || undefined,
    project: filters.project || undefined,
    project_group_id: filters.project ? undefined : filters.project_group || undefined,
    account: filters.account || undefined,
    category: filters.category || undefined,
    date_from: filters.date_from || undefined,
    date_to: filters.date_to || undefined,
    confirmed: filters.confirmed || undefined,
  };
  useEffect(() => {
    if (!token) return;
    api.countTransactions(token, countQuery)
      .then((count) => setMatchingCount(Number(count) || 0))
      .catch(() => setMatchingCount(null));
  }, [token, JSON.stringify(countQuery)]);

  const accountsById = useMemo(() => Object.fromEntries((accounts || []).map((a) => [a.id, a])), [accounts]);
  const categoriesById = useMemo(() => Object.fromEntries((categories || []).map((c) => [c.id, c])), [categories]);
  const projectsById = useMemo(() => Object.fromEntries((projects || []).map((p) => [p.id, p])), [projects]);
  const counterpartiesById = useMemo(
    () => Object.fromEntries((counterparties || []).map((c) => [c.id, c])),
    [counterparties]
  );

  const hasDateFilter = !!(filters.date_from || filters.date_to);

  // Сброс выбора и страницы при изменении фильтров
  useEffect(() => {
    setSelectedTransactionIds(new Set());
    setSelectedAllMatching(false);
    setCurrentPage(0);
    if (!hasDateFilter) setUseAllForDates(false);
  }, [JSON.stringify(filters), pageSize, hasDateFilter]);

  // Автосинк банковских интеграций при открытии/фильтрации Операций — бэкенд
  // сам решает, не рано ли реально идти в банк (integration.autosync_interval_minutes),
  // поэтому безопасно дёргать при каждой смене компании, не только по кнопке.
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
      const r = await api.syncAllIntegrations(token, filters.company || undefined, force);
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
    if (canSyncIntegrations) runIntegrationSync(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filters.company, canSyncIntegrations]);

  function openAdd() {
    setEditing(null);
    // Если операции сейчас отфильтрованы по проекту — подхватываем его в
    // форму создания, как уже делается для компании ниже.
    setForm({ ...EMPTY_FORM, project_id: filters.project || "" });
    const editableCompanies = companies.filter((m) => canEditTransactions(m.role));
    const preselected = editableCompanies.find((m) => m.company.id === filters.company) || editableCompanies[0];
    setFormCompanyId(preselected?.company.id || "");
    setFormError("");
    setAddAnother(false);
    setSaveConfirmMsg("");
    setModalOpen(true);
    // Сбросить выбор при добавлении новой операции
    setSelectedTransactionIds(new Set());
  }

  function openEdit(tx) {
    setEditing(tx);
    setAddAnother(false);
    setSaveConfirmMsg("");
    setForm({
      date_odds: tx.date_odds,
      date_opu: tx.date_opu || "",
      account_id: tx.account_id,
      category_id: tx.category_id,
      project_id: tx.project_id || "",
      counterparty_id: tx.counterparty_id || "",
      order_id: tx.order_id || "",
      type: tx.type,
      amount: String(tx.amount),
      currency: tx.currency,
      commission: String(tx.commission || 0),
      comment: tx.comment || "",
      bank_payment_purpose: tx.bank_payment_purpose || "",
      from_account_id: "",
      to_account_id: "",
      from_category_id: "",
      to_category_id: "",
      payment_confirmed: tx.payment_confirmed !== false,
      accrual_confirmed: tx.accrual_confirmed !== false,
    });
    setFormCompanyId(tx.company_id || "");
    setFormError("");
    setModalOpen(true);
  }

  // targetType: "transfer" | "reclass" — типичный случай: банк прислал приход
  // на одном счёте и расход на другом (или в другой своей же компании) для
  // одного и того же реального перевода денег между своими счетами — по
  // отдельности это исказило бы Приход/Расход, а Перемещение корректно
  // исключается из отчётов (см. is_internal_transfer). Начисление — тот же
  // принцип, но перенос между статьями внутри одного счёта, без движения денег.
  function openConvert(tx, targetType) {
    setEditing(null);
    setConvertingFromId(tx.id);
    setAddAnother(false);
    setSaveConfirmMsg("");
    const base = {
      ...EMPTY_FORM,
      type: targetType,
      date_odds: tx.date_odds,
      date_opu: tx.date_opu || "",
      amount: String(Math.abs(tx.amount)),
      currency: tx.currency,
      commission: String(tx.commission || 0),
      comment: tx.comment || "",
    };
    if (targetType === "transfer") {
      // Расход = деньги ушли с этого счёта → он "откуда"; приход = "куда".
      // Вторую сторону (другой свой счёт) пользователь выбирает сам.
      if (tx.type === "expense") base.from_account_id = tx.account_id;
      else base.to_account_id = tx.account_id;
    } else if (targetType === "reclass") {
      base.account_id = tx.account_id;
      base.from_category_id = tx.category_id;
    }
    setForm(base);
    setFormCompanyId(tx.company_id || "");
    setFormError("");
    setModalOpen(true);
  }

  // Company.show_accrual_date_field === false (см. "Модули", по образцу
  // ПланФакт) — поле "Дата начисления" в форме скрыто, а не просто пустое:
  // дата начисления/подтверждение начисления держатся синхронно с датой
  // оплаты/подтверждением оплаты прямо в состоянии формы, чтобы во всех
  // трёх путях отправки (обычная операция/перемещение/начисление) на
  // бэкенд ушли согласованные значения без дублирования логики в каждом.
  const activeCompanyForForm =
    companies.find((m) => m.company.id === formCompanyId)?.company || companies[0]?.company;
  const showAccrualField = activeCompanyForForm ? activeCompanyForForm.show_accrual_date_field !== false : true;

  function updateField(field, value) {
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      if (field === "account_id") {
        const acc = accountsById[value];
        if (acc) next.currency = acc.currency;
      }
      if (!showAccrualField) {
        if (field === "date_odds") next.date_opu = value;
        if (field === "payment_confirmed") next.accrual_confirmed = value;
      }
      return next;
    });
  }

  function updateFormCompany(companyId) {
    setFormCompanyId(companyId);
    // Счёт/статья/проект/контрагент из прошлой компании могут не подойти к новой — сбрасываем.
    setForm((prev) => ({
      ...prev,
      account_id: "",
      category_id: "",
      project_id: "",
      counterparty_id: "",
      from_account_id: "",
      to_account_id: "",
      from_category_id: "",
      to_category_id: "",
    }));
  }

  // Инлайн-создание статьи/проекта/контрагента прямо из выпадающего списка
  // операции — не нужно уходить в Справочники, чтобы завести то, чего пока
  // нет (см. Combobox.jsx::onCreateNew).
  async function handleCreateCategory(name) {
    const created = await api.createCategory(token, { name, type: form.type }, formCompanyId || undefined);
    reloadCategories();
    return created;
  }

  async function handleCreateProject(name) {
    const created = await api.createProject(token, { name }, formCompanyId || undefined);
    reloadProjects();
    return created;
  }

  async function handleCreateCounterparty(name) {
    const created = await api.createCounterparty(token, { name }, formCompanyId || undefined);
    reloadCounterparties();
    return created;
  }

  async function handleTransferSubmit() {
    if (form.from_account_id === form.to_account_id) {
      throw new Error(t("tx.form.sameAccountError"));
    }
    await api.createTransfer(token, {
      date_odds: form.date_odds,
      date_opu: form.date_opu || null,
      from_account_id: form.from_account_id,
      to_account_id: form.to_account_id,
      amount: Number(form.amount),
      commission: Number(form.commission || 0),
      comment: form.comment || null,
      payment_confirmed: form.payment_confirmed,
    });
    if (addAnother) {
      // Те же параметры, что и в предыдущей операции — очищаем только сумму.
      setForm((prev) => ({ ...prev, amount: "" }));
      setSaveConfirmMsg(t("tx.savedConfirm"));
      setTimeout(() => setSaveConfirmMsg(""), 1500);
    } else {
      setModalOpen(false);
    }
  }

  async function handleReclassSubmit() {
    if (form.from_category_id === form.to_category_id) {
      throw new Error(t("tx.form.sameCategoryError"));
    }
    await api.createReclass(
      token,
      {
        date_odds: form.date_odds,
        date_opu: form.date_opu || null,
        account_id: form.account_id,
        from_category_id: form.from_category_id,
        to_category_id: form.to_category_id,
        currency: form.currency,
        amount: Number(form.amount),
        comment: form.comment || null,
      },
      formCompanyId || undefined
    );
    if (addAnother) {
      // Те же параметры, что и в предыдущей операции — очищаем только сумму.
      setForm((prev) => ({ ...prev, amount: "" }));
      setSaveConfirmMsg(t("tx.savedConfirm"));
      setTimeout(() => setSaveConfirmMsg(""), 1500);
    } else {
      setModalOpen(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError("");
    setSaving(true);
    try {
      if (!editing && form.type === "transfer") {
        await handleTransferSubmit();
        if (convertingFromId) {
          await api.deleteTransaction(token, convertingFromId);
          setConvertingFromId(null);
        }
        reload();
        setSelectedTransactionIds(new Set());
        return;
      }
      if (!editing && form.type === "reclass") {
        await handleReclassSubmit();
        if (convertingFromId) {
          await api.deleteTransaction(token, convertingFromId);
          setConvertingFromId(null);
        }
        reload();
        setSelectedTransactionIds(new Set());
        return;
      }
      const payload = {
        date_odds: form.date_odds,
        date_opu: form.date_opu || null,
        account_id: form.account_id,
        category_id: form.category_id,
        project_id: form.project_id || null,
        counterparty_id: form.counterparty_id || null,
        order_id: form.order_id || null,
        type: form.type,
        amount: Number(form.amount),
        currency: form.currency,
        commission: Number(form.commission || 0),
        comment: form.comment || null,
        bank_payment_purpose: form.bank_payment_purpose || null,
        payment_confirmed: form.payment_confirmed,
        accrual_confirmed: form.accrual_confirmed,
      };
      if (editing) {
        await api.updateTransaction(token, editing.id, payload);
        setModalOpen(false);
      } else {
        await api.createTransaction(token, payload, formCompanyId || undefined);
        if (addAnother) {
          // Те же параметры, что и в предыдущей операции — очищаем только сумму.
          setForm((prev) => ({ ...prev, amount: "" }));
          setSaveConfirmMsg(t("tx.savedConfirm"));
          setTimeout(() => setSaveConfirmMsg(""), 1500);
        } else {
          setModalOpen(false);
        }
      }
      reload();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
    // Сбросить выбор после сохранения
    setSelectedTransactionIds(new Set());
  }

  async function handleDelete(tx) {
    const confirmMsg = tx.transfer_pair_id || tx.reclass_pair_id ? t("tx.deleteConfirmTransfer") : t("tx.deleteConfirm");
    if (!window.confirm(confirmMsg)) return;
    try {
      await api.deleteTransaction(token, tx.id);
      reload();
    } catch (err) {
      window.alert(err.message);
    }
  }

  function toggleTransactionSelection(txId) {
    setSelectedAllMatching(false);
    setSelectedTransactionIds((prev) => {
      const next = new Set(prev);
      if (next.has(txId)) {
        next.delete(txId);
      } else {
        next.add(txId);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedAllMatching || selectedTransactionIds.size === transactions.length) {
      // Если всё выбрано — отменяем выбор
      setSelectedTransactionIds(new Set());
      setSelectedAllMatching(false);
    } else {
      // Выбираем все на текущей странице
      setSelectedTransactionIds(new Set((transactions || []).map((t) => t.id)));
    }
  }

  function selectAllMatching() {
    // Выбираем все операции, соответствующие текущим фильтрам (не только на странице)
    setSelectedTransactionIds(new Set((transactions || []).map((t) => t.id)));
    setSelectedAllMatching(true);
  }

  async function handleBatchDelete() {
    if (!selectedAllMatching && selectedTransactionIds.size === 0) {
      window.alert(t("tx.selectToDelete"));
      return;
    }

    const confirmText = selectedAllMatching
      ? t("tx.confirmDeleteAllMatching", { count: matchingCount ?? "?" })
      : t("tx.confirmDeleteCount", { count: selectedTransactionIds.size });
    if (!window.confirm(confirmText)) return;

    setDeleting(true);
    try {
      let result;
      if (selectedAllMatching) {
        result = await api.batchDeleteTransactionsByFilter(token, {
          company_id: filters.company || undefined,
          project: filters.project || undefined,
          project_group_id: filters.project ? undefined : filters.project_group || undefined,
          account: filters.account || undefined,
          category: filters.category || undefined,
          date_from: filters.date_from || undefined,
          date_to: filters.date_to || undefined,
          confirmed: filters.confirmed || undefined,
        });
      } else {
        result = await api.batchDeleteTransactions(token, Array.from(selectedTransactionIds));
      }
      setSelectedTransactionIds(new Set());
      setSelectedAllMatching(false);
      reload();
      window.alert(t("tx.deletedCount", { count: result.deleted }));
    } catch (err) {
      window.alert(err.message);
    } finally {
      setDeleting(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      await api.exportTransactions(token, query);
    } catch (err) {
      window.alert(err.message);
    } finally {
      setExporting(false);
    }
  }

  const adminCompanies = companies.filter((m) => m.role === "admin");

  function openCloseMonth() {
    const preselected = adminCompanies.find((m) => m.company.id === filters.company) || adminCompanies[0];
    setCloseMonthCompanyId(preselected?.company.id || "");
    setCloseMonthValue(new Date().toISOString().slice(0, 7));
    setCloseMonthError("");
    setCloseMonthMsg("");
    setCloseMonthOpen(true);
  }

  async function handleCloseMonth() {
    setCloseMonthBusy(true);
    setCloseMonthError("");
    setCloseMonthMsg("");
    try {
      const result = await api.closeMonth(token, closeMonthCompanyId, `${closeMonthValue}-01`);
      setCloseMonthMsg(t("tx.closeMonth.result", { count: result.updated }));
      reload();
    } catch (err) {
      setCloseMonthError(err.message);
    } finally {
      setCloseMonthBusy(false);
    }
  }

  const selectable = (list, selectedId) =>
    (list || [])
      .filter((x) => x.is_active !== false || x.id === selectedId)
      .filter(
        (x) =>
          !multiCompany ||
          !formCompanyId ||
          x.company_id === formCompanyId ||
          x.id === selectedId ||
          // Статьи/проекты могут быть видны в компании не только "своей" —
          // is_global (везде) или visible_company_ids (конкретный список),
          // см. Reference.jsx/reference.py::apply_visibility_filter. У счетов
          // и контрагентов этих полей нет — здесь просто не совпадёт, без эффекта.
          x.is_global ||
          (x.visible_company_ids || []).includes(formCompanyId)
      );

  const filteredCategories = selectable(categories, form.category_id).filter((c) => c.type === form.type);
  const selectableAccounts = selectable(accounts, form.account_id);
  const selectableProjects = selectable(projects, form.project_id);
  const selectableCounterparties = selectable(counterparties, form.counterparty_id);
  const selectableOrders = selectable(orders, form.order_id);
  const editableCompanies = companies.filter((m) => canEditTransactions(m.role));
  const showCompanyColumn = multiCompany && !filters.company;
  // Перемещение — не привязано к одной выбранной в форме компании: счета
  // списания/зачисления могут принадлежать РАЗНЫМ компаниям одного холдинга
  // (см. app/holding_transfers.py на бэкенде), поэтому список счетов здесь —
  // все доступные пользователю на редактирование, без фильтра по formCompanyId.
  const isTransfer = !editing && form.type === "transfer";
  const transferAccountOptions = (accounts || [])
    .filter((a) => a.is_active !== false)
    .map((a) => ({ id: a.id, name: `${a.name} (${a.currency})` }));

  // Начисление — перенос суммы между статьями ОДНОЙ компании (не холдинга,
  // в отличие от Перемещения — тут ничего не движется между юрлицами),
  // поэтому категории/счёт берём из уже отфильтрованных по formCompanyId
  // списков. "Статья зачисления" сужена под тип "статьи списания" — нельзя
  // мешать доход/расход, иначе перенос не netится в ноль (см. бэкенд).
  const isReclass = !editing && form.type === "reclass";
  const reclassFromCategoryOptions = selectable(categories, form.from_category_id);
  const reclassFromCategoryType = categories?.find((c) => c.id === form.from_category_id)?.type;
  const reclassToCategoryOptions = selectable(categories, form.to_category_id).filter(
    (c) => !reclassFromCategoryType || c.type === reclassFromCategoryType
  );

  return (
    <div className="fp-dash">
      <div className="fp-tabs">
        <button className={view === "operations" ? "active" : ""} onClick={() => setView("operations")}>
          <ListIcon size={14} />
          {t("tx.view.operations")}
        </button>
        <button className={view === "balances" ? "active" : ""} onClick={() => setView("balances")}>
          <Wallet size={14} />
          {t("tx.view.balances")}
        </button>
      </div>

      {view === "balances" ? (
        <AccountBalancesPanel token={token} companyId={filters.company} />
      ) : (
      <>
      <div className="fp-tabs-row">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {multiCompany && (
            <div className="fp-filter-combobox">
              <Combobox
                value={filters.company}
                onChange={(val) => setFilters((f) => ({ ...f, company: val }))}
                options={companies.map((m) => ({ id: m.company.id, name: m.company.name }))}
                placeholder={t("dashboard.allCompanies")}
              />
            </div>
          )}
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.project_group}
              onChange={(val) =>
                setFilters((f) => ({
                  ...f,
                  project_group: val,
                  project: (projects || []).find((p) => p.id === f.project)?.group_id === val ? f.project : "",
                }))
              }
              options={(projectGroups || []).map((g) => ({ id: g.id, name: g.name }))}
              placeholder={t("tx.filter.allGroups")}
            />
          </div>
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.project}
              onChange={(val) => setFilters((f) => ({ ...f, project: val }))}
              options={(filters.project_group
                ? (projects || []).filter((p) => p.group_id === filters.project_group)
                : projects || []
              ).map((p) => ({ id: p.id, name: p.name }))}
              placeholder={t("tx.filter.allProjects")}
            />
          </div>
          <select
            value={filters.confirmed}
            onChange={(e) => setFilters((f) => ({ ...f, confirmed: e.target.value }))}
          >
            <option value="">{t("tx.filter.allConfirmStatus")}</option>
            <option value="confirmed">{t("tx.filter.confirmedOnly")}</option>
            <option value="unconfirmed">{t("tx.filter.unconfirmedOnly")}</option>
          </select>
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.account}
              onChange={(val) => setFilters((f) => ({ ...f, account: val }))}
              options={(accounts || []).map((a) => ({ id: a.id, name: `${a.name} (${a.currency})` }))}
              placeholder={t("tx.filter.allAccounts")}
            />
          </div>
          <div className="fp-filter-combobox">
            <Combobox
              value={filters.category}
              onChange={(val) => setFilters((f) => ({ ...f, category: val }))}
              options={(categories || []).map((c) => ({ id: c.id, name: c.name }))}
              placeholder={t("tx.filter.allCategories")}
            />
          </div>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))}
          />
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))}
          />
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {canSyncIntegrations && (
            <button className="fp-btn-ghost" onClick={() => runIntegrationSync(true)} disabled={syncing}>
              <RefreshCw size={15} /> {syncing ? t("dashboard.syncing") : t("dashboard.sync")}
            </button>
          )}
          {adminCompanies.length > 0 && (
            <button className="fp-btn-ghost" onClick={openCloseMonth}>
              <CalendarCheck size={15} /> {t("tx.closeMonth")}
            </button>
          )}
          <button className="fp-btn-ghost" onClick={handleExport} disabled={exporting}>
            <Download size={15} /> {exporting ? t("tx.exporting") : t("tx.exportExcel")}
          </button>
          {canEdit && (selectedAllMatching || selectedTransactionIds.size > 0) && (
            <button
              className="fp-btn-danger"
              onClick={handleBatchDelete}
              disabled={deleting}
              title={
                selectedAllMatching
                  ? t("tx.deleteAllMatching", { count: matchingCount ?? "?" })
                  : t("tx.confirmDeleteCount", { count: selectedTransactionIds.size })
              }
            >
              <Trash2 size={16} />{" "}
              {deleting
                ? t("tx.deleting")
                : selectedAllMatching
                ? t("tx.deleteAllMatching", { count: matchingCount ?? "?" })
                : t("tx.deleteCount", { count: selectedTransactionIds.size })}
            </button>
          )}
          {canEdit && (
            <button className="fp-btn-primary" onClick={openAdd}>
              <Plus size={16} /> {t("tx.newTransaction")}
            </button>
          )}
        </div>
      </div>

      {syncBanner && (
        <div className="fp-panel" style={{ padding: "10px 14px", fontSize: 13, marginBottom: 14 }}>
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

      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 12, justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <label style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
            {t("tx.rowsPerPage")}
            <select
              value={useAllForDates ? "dates" : String(pageSize)}
              onChange={(e) => {
                if (e.target.value === "dates") {
                  setUseAllForDates(true);
                } else {
                  setUseAllForDates(false);
                  setPageSize(Number(e.target.value));
                }
                setCurrentPage(0);
              }}
              style={{
                marginLeft: 8,
                padding: "4px 8px",
                border: "1px solid var(--line)",
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              <option value="20">20</option>
              <option value="50">50</option>
              <option value="100">100</option>
              {hasDateFilter && <option value="dates">{t("tx.selectedDates")}</option>}
            </select>
          </label>
        </div>
        {selectedAllMatching ? (
          <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
            {t("tx.selectedAllMatching", { count: matchingCount ?? "?" })}
            <button
              type="button"
              onClick={() => {
                setSelectedAllMatching(false);
                setSelectedTransactionIds(new Set());
              }}
              style={{
                marginLeft: 10,
                background: "none",
                border: "none",
                color: "var(--accent)",
                cursor: "pointer",
                textDecoration: "underline",
                fontSize: "13px",
                padding: 0,
              }}
            >
              {t("tx.clearSelection")}
            </button>
          </div>
        ) : selectedTransactionIds.size > 0 ? (
          <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
            {t("tx.selectedCount", { count: selectedTransactionIds.size })}
            {matchingCount > selectedTransactionIds.size && !useAllForDates && (
              <button
                type="button"
                onClick={selectAllMatching}
                style={{
                  marginLeft: 10,
                  background: "none",
                  border: "none",
                  color: "var(--accent)",
                  cursor: "pointer",
                  textDecoration: "underline",
                  fontSize: "13px",
                  padding: 0,
                }}
              >
                {t("tx.selectAllMatching", { count: matchingCount ?? "?" })}
              </button>
            )}
          </div>
        ) : null}
      </div>

      <div className="fp-panel fp-table-panel">
        {loading ? (
          <div className="fp-loading">{t("common.loading")}</div>
        ) : (transactions || []).length === 0 ? (
          <div className="fp-empty">{t("tx.notFound")}</div>
        ) : (
          <table className="fp-table">
            <thead>
              <tr>
                {canEdit && (
                  <th style={{ width: 40, textAlign: "center", paddingLeft: 8 }}>
                    <input
                      type="checkbox"
                      checked={selectedAllMatching || (selectedTransactionIds.size === (transactions || []).length && transactions.length > 0)}
                      onChange={toggleSelectAll}
                      title={selectedAllMatching || selectedTransactionIds.size > 0 ? t("tx.deselectAllTitle") : t("tx.selectAllTitle")}
                      style={{ cursor: "pointer" }}
                    />
                  </th>
                )}
                {showCompanyColumn && <th>{t("dashboard.table.company")}</th>}
                <th>{t("tx.col.date")}</th>
                <th>{t("tx.col.dateOpu")}</th>
                <th>{t("tx.col.account")}</th>
                <th>{t("tx.col.category")}</th>
                <th>{t("tx.col.project")}</th>
                <th>{t("tx.col.counterparty")}</th>
                <th>{t("tx.col.comment")}</th>
                <th>{t("tx.col.source")}</th>
                <th className="right">{t("tx.col.commission")}</th>
                <th className="right fp-table-amount-col" style={{ right: canEdit ? 90 : 0 }}>
                  {t("tx.col.amount")}
                </th>
                {canEdit && <th className="fp-table-actions-col"></th>}
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => {
                const acc = accountsById[tx.account_id];
                const cat = categoriesById[tx.category_id];
                const proj = tx.project_id ? projectsById[tx.project_id] : null;
                const cp = tx.counterparty_id ? counterpartiesById[tx.counterparty_id] : null;
                const rowRole = roleForCompany(tx.company_id);
                const canEditRow =
                  canEditTransactions(rowRole) && (rowRole === "admin" || tx.created_by === user.id);
                return (
                  <tr key={tx.id}>
                    {canEdit && (
                      <td style={{ width: 40, textAlign: "center", paddingLeft: 8 }}>
                        <input
                          type="checkbox"
                          checked={selectedAllMatching || selectedTransactionIds.has(tx.id)}
                          onChange={() => toggleTransactionSelection(tx.id)}
                          style={{ cursor: "pointer" }}
                        />
                      </td>
                    )}
                    {showCompanyColumn && (
                      <td>{companies.find((m) => m.company.id === tx.company_id)?.company.name || "—"}</td>
                    )}
                    <td>{fmtDate(tx.date_odds)}</td>
                    <td className="fp-muted">{tx.date_opu ? fmtDate(tx.date_opu) : "—"}</td>
                    <td>
                      {acc?.name || "—"}
                      {acc && <span className={`fp-currency-badge ${acc.currency}`}>{acc.currency}</span>}
                    </td>
                    <td>
                      <span className={`fp-cat-dot ${tx.type}`} />
                      {cat?.name || "—"}
                      {tx.transfer_pair_id && (
                        <span className="fp-source-badge" title={t("tx.transferBadge")} style={{ marginLeft: 6 }}>
                          🔁
                        </span>
                      )}
                      {tx.reclass_pair_id && (
                        <span className="fp-source-badge" title={t("tx.reclassBadge")} style={{ marginLeft: 6 }}>
                          ↔️
                        </span>
                      )}
                    </td>
                    <td>{proj?.name || <span className="fp-muted">—</span>}</td>
                    <td>{cp?.name || <span className="fp-muted">—</span>}</td>
                    <td
                      className="fp-muted fp-table-comment-col"
                      title={[tx.comment, tx.bank_payment_purpose].filter(Boolean).join(" / ")}
                    >
                      {tx.comment || tx.bank_payment_purpose || "—"}
                    </td>
                    <td>{sourceBadge(tx.external_ref, t) || <span className="fp-muted">{t("tx.manually")}</span>}</td>
                    <td className="right fp-mono">{tx.commission ? fmt(tx.commission, tx.currency) : "—"}</td>
                    <td
                      className={`right fp-mono fp-amount-${tx.type} fp-table-amount-col`}
                      style={{ right: canEdit ? 90 : 0 }}
                    >
                      {(tx.payment_confirmed === false || tx.accrual_confirmed === false) && (
                        <span
                          title={[
                            tx.payment_confirmed === false ? t("tx.form.confirmPayment") : null,
                            tx.accrual_confirmed === false ? t("tx.form.confirmAccrual") : null,
                          ]
                            .filter(Boolean)
                            .join(" / ") + ` — ${t("tx.notConfirmedTitle")}`}
                        >
                          <span className={`fp-dk-badge ${tx.type === "income" ? "income" : "expense"}`}>
                            {tx.type === "income" ? "Д" : "К"}
                          </span>
                          <span className="fp-unconfirmed-mark">!</span>
                        </span>
                      )}
                      {tx.reclass_pair_id ? "" : tx.type === "expense" ? "-" : ""}
                      {fmt(tx.reclass_pair_id ? Math.abs(tx.amount) : tx.amount, tx.currency)}
                      {tx.reclass_pair_id && tx.amount < 0 && " (−)"}
                      {tx.currency !== "RUB" && (
                        <div className="fp-sub-value">≈ {fmt(tx.amount_rub, "RUB")}</div>
                      )}
                    </td>
                    {canEdit && (
                      <td className="fp-table-actions-col">
                        {canEditRow ? (
                          <span className="fp-row-actions">
                            <button className="fp-icon-btn" onClick={() => openEdit(tx)}>
                              <Pencil size={14} />
                            </button>
                            <button className="fp-icon-btn" onClick={() => handleDelete(tx)}>
                              <Trash2 size={14} />
                            </button>
                          </span>
                        ) : (
                          <span className="fp-muted">—</span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {(transactions || []).length > 0 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderTop: "1px solid var(--line)" }}>
            <div style={{ fontSize: "13px", color: "var(--ink-soft)" }}>
              {useAllForDates
                ? t("tx.allForPeriod", { count: (transactions || []).length })
                : t("tx.pageInfo", { page: currentPage + 1, count: (transactions || []).length })}
            </div>
            {!useAllForDates && (
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  className="fp-btn-ghost"
                  onClick={() => setCurrentPage(Math.max(0, currentPage - 1))}
                  disabled={currentPage === 0 || loading}
                >
                  {t("tx.pagePrev")}
                </button>
                <button
                  className="fp-btn-ghost"
                  onClick={() => setCurrentPage(currentPage + 1)}
                  disabled={(transactions || []).length < pageSize || loading}
                >
                  {t("tx.pageNext")}
                </button>
              </div>
            )}
          </div>
        )}
        {!canEdit && (
          <div className="fp-viewer-note">
            <Lock size={13} /> {t("tx.viewerNote")}
          </div>
        )}
      </div>
      </>
      )}

      {modalOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setModalOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{editing ? t("tx.editTransaction") : t("tx.newTransaction")}</h3>
              <button className="fp-icon-btn" onClick={() => setModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            {editing && !editing.transfer_pair_id && !editing.reclass_pair_id && (
              <div className="fp-convert-row">
                <span className="fp-muted">{t("tx.form.convertHint")}</span>
                <button type="button" className="fp-btn-tiny" onClick={() => openConvert(editing, "transfer")}>
                  {t("tx.convertToTransfer")}
                </button>
                <button type="button" className="fp-btn-tiny" onClick={() => openConvert(editing, "reclass")}>
                  {t("tx.convertToReclass")}
                </button>
              </div>
            )}

            <div className="fp-type-toggle">
              <button
                type="button"
                className={form.type === "income" ? "active income" : ""}
                onClick={() => updateField("type", "income")}
              >
                {t("tx.income")}
              </button>
              <button
                type="button"
                className={form.type === "expense" ? "active expense" : ""}
                onClick={() => updateField("type", "expense")}
              >
                {t("tx.expense")}
              </button>
              {!editing && (
                <button
                  type="button"
                  className={form.type === "transfer" ? "active transfer" : ""}
                  onClick={() => updateField("type", "transfer")}
                >
                  {t("tx.transfer")}
                </button>
              )}
              {!editing && (
                <button
                  type="button"
                  className={form.type === "reclass" ? "active reclass" : ""}
                  onClick={() => updateField("type", "reclass")}
                >
                  {t("tx.reclass")}
                </button>
              )}
            </div>

            <form className="fp-form-grid" onSubmit={handleSubmit}>
              {multiCompany && !isTransfer && !isReclass && (
                <label className="fp-span-2">
                  {t("tx.form.company")}
                  {editing ? (
                    <input
                      type="text"
                      disabled
                      value={companies.find((m) => m.company.id === formCompanyId)?.company.name || ""}
                    />
                  ) : (
                    <select
                      value={formCompanyId}
                      onChange={(e) => updateFormCompany(e.target.value)}
                      required
                    >
                      {editableCompanies.map((m) => (
                        <option key={m.company.id} value={m.company.id}>
                          {m.company.name}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
              )}
              <label>
                {t("tx.form.date")}
                <input
                  type="date"
                  required
                  value={form.date_odds}
                  onChange={(e) => updateField("date_odds", e.target.value)}
                />
              </label>
              {showAccrualField && (
                <label>
                  {t("tx.form.dateOpu")}
                  <input type="date" value={form.date_opu} onChange={(e) => updateField("date_opu", e.target.value)} />
                </label>
              )}

              {isTransfer ? (
                <>
                  <label>
                    {t("tx.form.fromAccount")}
                    <Combobox
                      value={form.from_account_id}
                      onChange={(val) => updateField("from_account_id", val)}
                      options={transferAccountOptions}
                      placeholder={t("tx.form.selectFromAccount")}
                      required
                    />
                  </label>
                  <label>
                    {t("tx.form.toAccount")}
                    <Combobox
                      value={form.to_account_id}
                      onChange={(val) => updateField("to_account_id", val)}
                      options={transferAccountOptions}
                      placeholder={t("tx.form.selectToAccount")}
                      required
                    />
                  </label>
                </>
              ) : isReclass ? (
                <>
                  <label>
                    {t("tx.form.account")} <span className="fp-muted">{t("tx.form.reclassAccountHint")}</span>
                    <Combobox
                      value={form.account_id}
                      onChange={(val) => updateField("account_id", val)}
                      options={selectableAccounts.map((a) => ({
                        id: a.id,
                        name: `${a.name} (${a.currency})${a.is_active === false ? t("tx.deactivatedSuffix") : ""}`
                      }))}
                      placeholder={t("tx.form.selectAccount")}
                      required
                    />
                  </label>
                  <label>
                    {t("tx.form.fromCategory")}
                    <Combobox
                      value={form.from_category_id}
                      onChange={(val) => updateField("from_category_id", val)}
                      options={reclassFromCategoryOptions.map((c) => ({
                        id: c.id,
                        name: `${c.name}${c.is_active === false ? t("tx.deactivatedSuffixF") : ""}`
                      }))}
                      placeholder={t("tx.form.selectFromCategory")}
                      required
                    />
                  </label>
                  <label>
                    {t("tx.form.toCategory")}
                    <Combobox
                      value={form.to_category_id}
                      onChange={(val) => updateField("to_category_id", val)}
                      options={reclassToCategoryOptions.map((c) => ({
                        id: c.id,
                        name: `${c.name}${c.is_active === false ? t("tx.deactivatedSuffixF") : ""}`
                      }))}
                      placeholder={t("tx.form.selectToCategory")}
                      required
                    />
                  </label>
                  <label>
                    {t("tx.form.currency")}
                    <input value={form.currency} onChange={(e) => updateField("currency", e.target.value.toUpperCase())} />
                  </label>
                </>
              ) : (
                <>
                  <label>
                    {t("tx.form.account")}
                    <Combobox
                      value={form.account_id}
                      onChange={(val) => updateField("account_id", val)}
                      options={selectableAccounts.map((a) => ({
                        id: a.id,
                        name: `${a.name} (${a.currency})${a.is_active === false ? t("tx.deactivatedSuffix") : ""}`
                      }))}
                      placeholder={t("tx.form.selectAccount")}
                      required
                    />
                  </label>

                  <label>
                    {t("tx.form.category")}
                    <Combobox
                      value={form.category_id}
                      onChange={(val) => updateField("category_id", val)}
                      options={filteredCategories.map((c) => ({
                        id: c.id,
                        name: `${c.name}${c.is_active === false ? t("tx.deactivatedSuffixF") : ""}`
                      }))}
                      placeholder={t("tx.form.selectCategory")}
                      required
                      onCreateNew={handleCreateCategory}
                    />
                  </label>
                  <label>
                    {t("tx.form.project")}
                    <Combobox
                      value={form.project_id}
                      onChange={(val) => updateField("project_id", val)}
                      options={selectableProjects.map((p) => ({
                        id: p.id,
                        name: `${p.name}${p.is_active === false ? t("tx.deactivatedSuffix") : ""}`
                      }))}
                      placeholder={t("tx.form.notSpecified")}
                      onCreateNew={handleCreateProject}
                    />
                  </label>

                  <label>
                    {t("tx.form.counterparty")}
                    <Combobox
                      value={form.counterparty_id}
                      onChange={(val) => updateField("counterparty_id", val)}
                      options={selectableCounterparties.map((c) => ({
                        id: c.id,
                        name: `${c.name}${c.is_active === false ? t("tx.deactivatedSuffix") : ""}`
                      }))}
                      placeholder={t("tx.form.notSpecified")}
                      onCreateNew={handleCreateCounterparty}
                    />
                  </label>

                  <label>
                    {t("tx.form.order")}
                    <Combobox
                      value={form.order_id}
                      onChange={(val) => updateField("order_id", val)}
                      options={selectableOrders.map((o) => ({
                        id: o.id,
                        name: o.lines?.length
                          ? `${o.requested_date || ""} · ${o.lines.length} поз.${o.balance_due_rub > 0 ? ` · остаток ${fmt(o.balance_due_rub, "RUB")}` : ""}`.trim()
                          : o.id,
                      }))}
                      placeholder={t("tx.form.notSpecified")}
                    />
                  </label>

                  <label>
                    {t("tx.form.currency")}
                    <input value={form.currency} onChange={(e) => updateField("currency", e.target.value.toUpperCase())} />
                  </label>
                </>
              )}

              <label>
                {t("tx.form.amount")}
                <AmountInput required value={form.amount} onChange={(v) => updateField("amount", v)} />
              </label>
              {!isReclass && (
                <label>
                  {t("tx.form.commission")}
                  <AmountInput value={form.commission} onChange={(v) => updateField("commission", v)} />
                </label>
              )}

              {!isTransfer && !isReclass && (
                <label className="fp-span-2">
                  {t("tx.form.bankPurpose")} {editing?.external_ref ? t("tx.form.fromBank") : t("tx.form.optional")}
                  <input
                    value={form.bank_payment_purpose}
                    onChange={(e) => updateField("bank_payment_purpose", e.target.value)}
                    placeholder={t("tx.form.bankPurposePlaceholder")}
                  />
                </label>
              )}

              <label className="fp-span-2">
                {t("tx.form.comment")}
                <input
                  value={form.comment}
                  onChange={(e) => updateField("comment", e.target.value)}
                  placeholder={t("tx.form.commentPlaceholder")}
                />
              </label>

              {!isReclass && (
                <div className="fp-span-2" style={{ display: "flex", gap: 18 }}>
                  <label className="fp-checkbox-row" style={{ margin: 0, padding: 0 }}>
                    <input
                      type="checkbox"
                      checked={form.payment_confirmed}
                      onChange={(e) => updateField("payment_confirmed", e.target.checked)}
                    />
                    {t("tx.form.confirmPayment")}
                  </label>
                  {!isTransfer && showAccrualField && (
                    <label className="fp-checkbox-row" style={{ margin: 0, padding: 0 }}>
                      <input
                        type="checkbox"
                        checked={form.accrual_confirmed}
                        onChange={(e) => updateField("accrual_confirmed", e.target.checked)}
                      />
                      {t("tx.form.confirmAccrual")}
                    </label>
                  )}
                </div>
              )}

              {editing && <AttachmentList token={token} entityType="transaction" entityId={editing.id} />}

              {formError && <div className="fp-form-error fp-span-2">{formError}</div>}

              <div className="fp-modal-foot fp-span-2" style={{ justifyContent: "space-between" }}>
                {!editing && (
                  <label className="fp-checkbox-row" style={{ marginRight: "auto" }}>
                    <input type="checkbox" checked={addAnother} onChange={(e) => setAddAnother(e.target.checked)} />
                    {t("tx.addAnother")}
                  </label>
                )}
                {saveConfirmMsg && (
                  <span style={{ color: "var(--accent)", fontSize: 13 }}>✓ {saveConfirmMsg}</span>
                )}
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

      {closeMonthOpen && (
        <div className="fp-modal-backdrop" {...backdropClickProps(() => setCloseMonthOpen(false))}>
          <div className="fp-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fp-modal-head">
              <h3>{t("tx.closeMonth.title")}</h3>
              <button className="fp-icon-btn" onClick={() => setCloseMonthOpen(false)}>
                <X size={18} />
              </button>
            </div>
            <div className="fp-form-grid">
              <label>
                {t("tx.form.company")}
                <select value={closeMonthCompanyId} onChange={(e) => setCloseMonthCompanyId(e.target.value)}>
                  {adminCompanies.map((m) => (
                    <option key={m.company.id} value={m.company.id}>
                      {m.company.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("tx.closeMonth.month")}
                <input type="month" value={closeMonthValue} onChange={(e) => setCloseMonthValue(e.target.value)} />
              </label>
              <p className="fp-note fp-span-2">{t("tx.closeMonth.confirm")}</p>
              {closeMonthError && <div className="fp-form-error fp-span-2">{closeMonthError}</div>}
              {closeMonthMsg && <div className="fp-span-2" style={{ color: "var(--accent)", fontSize: 13 }}>✓ {closeMonthMsg}</div>}
              <div className="fp-modal-foot fp-span-2">
                <button type="button" className="fp-btn-ghost" onClick={() => setCloseMonthOpen(false)}>
                  {t("common.cancel")}
                </button>
                <button
                  type="button"
                  className="fp-btn-primary"
                  onClick={handleCloseMonth}
                  disabled={closeMonthBusy || !closeMonthCompanyId}
                >
                  {closeMonthBusy ? t("common.saving") : t("tx.closeMonth")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Остатки по счетам прямо на экране Операций — без перехода на Дашборд.
// Отдельный лёгкий эндпоинт (/reports/account-balances), а не dashboardSummary
// целиком: тот попутно считает доход/расход за период дважды (текущий и
// предыдущий) — данные, которые здесь не нужны.
function AccountBalancesPanel({ token, companyId }) {
  const { t } = useTranslation();
  const { data, loading, error } = useResource(
    () => api.accountBalances(token, { company_id: companyId || undefined }),
    [token, companyId]
  );
  const accounts = data?.accounts || [];

  return (
    <div className="fp-panel">
      <div className="fp-panel-head">
        <h3>{t("dashboard.accounts.title")}</h3>
      </div>
      {error && <div className="fp-error-banner">{error}</div>}
      {loading ? (
        <div className="fp-loading">{t("common.loading")}</div>
      ) : accounts.length === 0 ? (
        <div className="fp-empty">{t("dashboard.accounts.empty")}</div>
      ) : (
        <div className="fp-ledger">
          {accounts.map((a) => (
            <div className="ledger-row" key={a.id}>
              <span className="label">
                {a.name}
                <span className={`fp-currency-badge ${a.currency}`}>{a.currency}</span>
              </span>
              <span className="fill" />
              <span className="value" style={{ color: a.balance < 0 ? "#A8503F" : "#1B2430" }}>
                {fmt(a.balance, a.currency)}
                {a.currency !== "RUB" && a.balance_rub !== null && (
                  <span className="fp-sub-value"> ≈ {fmt(a.balance_rub, "RUB")}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
