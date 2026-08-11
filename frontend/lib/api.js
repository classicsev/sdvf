const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function buildQuery(params) {
  if (!params) return "";
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") usp.set(key, value);
  });
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", token, body, query } = {}) {
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null;

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join("; ")
      : detail || `Ошибка запроса (${res.status})`;
    throw new ApiError(message, res.status);
  }

  return data;
}

async function download(path, { token, query } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, { headers });
  if (!res.ok) {
    throw new ApiError(`Не удалось скачать файл (${res.status})`, res.status);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : "export.xlsx";

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function openPdf(path, { token, query } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}${buildQuery(query)}`, { headers });
  if (!res.ok) {
    throw new ApiError(`Не удалось открыть документ (${res.status})`, res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  // Blob-URL, не прямая ссылка на СДВФ — секрет интеграции (X-API-Key) не
  // должен попадать в браузер, PDF идёт через бэкенд (см. orders.py::sdvf_pdf).
  // window.open() после await блокируется popup-блокером (это уже не "прямой"
  // отклик на клик с точки зрения браузера) — клик по синтетической ссылке
  // проходит надёжно, тот же приём, что и в download() для xlsx-экспорта.
  const a = document.createElement("a");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export const api = {
  ApiError,

  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  registerCompany: (payload) => request("/auth/register-company", { method: "POST", body: payload }),
  me: (token) => request("/auth/me", { token }),
  updateMyProfile: (token, payload) => request("/auth/me/profile", { method: "PATCH", token, body: payload }),
  uploadMyAvatar: async (token, file) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/auth/me/avatar`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw new ApiError(data?.detail || `Ошибка запроса (${res.status})`, res.status);
    }
    return data;
  },
  verifyEmail: (token) => request("/auth/verify-email", { query: { token } }),
  resendVerification: (token) => request("/auth/resend-verification", { method: "POST", token }),

  listOAuthProviders: () => request("/auth/oauth/providers"),
  oauthStartUrl: (provider) => `${API_BASE}/auth/oauth/${provider}/start`,

  ssoConsent: (token, payload) => request("/oauth/consent", { method: "POST", token, body: payload }),

  getMyCompany: (token) => request("/companies/me", { token }),
  updateCompanyModules: (token, payload) =>
    request("/companies/me/modules", { method: "PATCH", token, body: payload }),

  // Мульти-компании — любая компания пользователя, не только "первая" (см.
  // план "Мульти-компании"). Список бэкенд уже отдаёт при логине (user.companies),
  // listCompanies тут для повторного запроса после изменений (создание/приглашение).
  listCompanies: (token) => request("/companies", { token }),
  createCompany: (token, payload) => request("/companies", { method: "POST", token, body: payload }),
  updateCompanyModulesFor: (token, companyId, payload) =>
    request(`/companies/${companyId}/modules`, { method: "PATCH", token, body: payload }),
  addCompanyMember: (token, companyId, payload) =>
    request(`/companies/${companyId}/members`, { method: "POST", token, body: payload }),
  updateCompanyMember: (token, companyId, userId, payload) =>
    request(`/companies/${companyId}/members/${userId}`, { method: "PATCH", token, body: payload }),
  removeCompanyMember: (token, companyId, userId) =>
    request(`/companies/${companyId}/members/${userId}`, { method: "DELETE", token }),

  listUsers: (token, query) => request("/users", { token, query }),
  createUser: (token, payload, companyId) =>
    request("/users", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateUser: (token, id, payload, companyId) =>
    request(`/users/${id}`, { method: "PATCH", token, body: payload, query: { company_id: companyId } }),
  deleteUser: (token, id, companyId) =>
    request(`/users/${id}`, { method: "DELETE", token, query: { company_id: companyId } }),

  listTransactions: (token, query) => request("/transactions", { token, query }),
  createTransaction: (token, payload, companyId) =>
    request("/transactions", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateTransaction: (token, id, payload) =>
    request(`/transactions/${id}`, { method: "PATCH", token, body: payload }),
  deleteTransaction: (token, id) => request(`/transactions/${id}`, { method: "DELETE", token }),
  exportTransactions: (token, query) => download("/transactions/export.xlsx", { token, query }),

  dashboardSummary: (token) => request("/reports/dashboard-summary", { token }),
  cashflowReport: (token, query) => request("/reports/cashflow", { token, query }),
  pnlReport: (token, query) => request("/reports/pnl", { token, query }),
  balanceReport: (token, query) => request("/reports/balance", { token, query }),
  debtReport: (token, query) => request("/reports/debt", { token, query }),
  profitabilityReport: (token, query) => request("/reports/profitability", { token, query }),
  paymentCalendar: (token, query) => request("/reports/payment-calendar", { token, query }),

  listCategories: (token, query) => request("/categories", { token, query }),
  createCategory: (token, payload, companyId) =>
    request("/categories", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateCategory: (token, id, payload) => request(`/categories/${id}`, { method: "PATCH", token, body: payload }),
  deleteCategory: (token, id) => request(`/categories/${id}`, { method: "DELETE", token }),

  listProjects: (token, query) => request("/projects", { token, query }),
  createProject: (token, payload, companyId) =>
    request("/projects", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateProject: (token, id, payload) => request(`/projects/${id}`, { method: "PATCH", token, body: payload }),
  deleteProject: (token, id) => request(`/projects/${id}`, { method: "DELETE", token }),

  listAccounts: (token, query) => request("/accounts", { token, query }),
  createAccount: (token, payload, companyId) =>
    request("/accounts", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateAccount: (token, id, payload) => request(`/accounts/${id}`, { method: "PATCH", token, body: payload }),
  deleteAccount: (token, id) => request(`/accounts/${id}`, { method: "DELETE", token }),

  listCounterparties: (token, query) => request("/counterparties", { token, query }),
  createCounterparty: (token, payload, companyId) =>
    request("/counterparties", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateCounterparty: (token, id, payload) =>
    request(`/counterparties/${id}`, { method: "PATCH", token, body: payload }),
  deleteCounterparty: (token, id) => request(`/counterparties/${id}`, { method: "DELETE", token }),

  listPlanning: (token, query) => request("/planning", { token, query }),
  createPlanning: (token, payload, companyId) =>
    request("/planning", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updatePlanning: (token, id, payload) => request(`/planning/${id}`, { method: "PATCH", token, body: payload }),
  deletePlanning: (token, id) => request(`/planning/${id}`, { method: "DELETE", token }),

  listEmployees: (token, query) => request("/payroll/employees", { token, query }),
  createEmployee: (token, payload, companyId) =>
    request("/payroll/employees", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateEmployee: (token, id, payload) =>
    request(`/payroll/employees/${id}`, { method: "PATCH", token, body: payload }),
  deleteEmployee: (token, id) => request(`/payroll/employees/${id}`, { method: "DELETE", token }),

  listAccruals: (token, query) => request("/payroll/accruals", { token, query }),
  createAccrual: (token, payload) => request("/payroll/accruals", { method: "POST", token, body: payload }),
  listPayments: (token, query) => request("/payroll/payments", { token, query }),
  createPayment: (token, payload) => request("/payroll/payments", { method: "POST", token, body: payload }),
  payrollSummary: (token, query) => request("/payroll/summary-for-viewer", { token, query }),

  listAutomationRules: (token, query) => request("/automation-rules", { token, query }),
  createAutomationRule: (token, payload, companyId) =>
    request("/automation-rules", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateAutomationRule: (token, id, payload) =>
    request(`/automation-rules/${id}`, { method: "PATCH", token, body: payload }),
  deleteAutomationRule: (token, id) => request(`/automation-rules/${id}`, { method: "DELETE", token }),
  listIntegrations: (token, query) => request("/integrations", { token, query }),
  connectIntegration: (token, id, payload) =>
    request(`/integrations/${id}/connect`, { method: "POST", token, body: payload }),
  disconnectIntegration: (token, id) => request(`/integrations/${id}/disconnect`, { method: "POST", token }),
  syncIntegration: (token, id, payload) =>
    request(`/integrations/${id}/sync`, { method: "POST", token, body: payload }),
  connectAmoCrm: (token, id, payload) =>
    request(`/integrations/${id}/connect-amocrm`, { method: "POST", token, body: payload }),
  syncAmoCrm: (token, id, payload) =>
    request(`/integrations/${id}/sync-amocrm`, { method: "POST", token, body: payload }),

  listAuditLog: (token) => request("/audit-log", { token }),

  listApiKeys: (token) => request("/api-keys", { token }),
  createApiKey: (token, payload) => request("/api-keys", { method: "POST", token, body: payload }),
  revokeApiKey: (token, id) => request(`/api-keys/${id}`, { method: "DELETE", token }),

  listWarehouses: (token, query) => request("/warehouse/warehouses", { token, query }),
  createWarehouse: (token, payload, companyId) =>
    request("/warehouse/warehouses", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateWarehouse: (token, id, payload) =>
    request(`/warehouse/warehouses/${id}`, { method: "PATCH", token, body: payload }),
  deleteWarehouse: (token, id) => request(`/warehouse/warehouses/${id}`, { method: "DELETE", token }),

  listWhProducts: (token, query) => request("/warehouse/products", { token, query }),
  createWhProduct: (token, payload, companyId) =>
    request("/warehouse/products", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateWhProduct: (token, id, payload) =>
    request(`/warehouse/products/${id}`, { method: "PATCH", token, body: payload }),
  deleteWhProduct: (token, id) => request(`/warehouse/products/${id}`, { method: "DELETE", token }),

  listWhVariants: (token, query) => request("/warehouse/variants", { token, query }),
  createWhVariant: (token, payload) => request("/warehouse/variants", { method: "POST", token, body: payload }),
  updateWhVariant: (token, id, payload) =>
    request(`/warehouse/variants/${id}`, { method: "PATCH", token, body: payload }),
  deleteWhVariant: (token, id) => request(`/warehouse/variants/${id}`, { method: "DELETE", token }),

  listWhEmployees: (token) => request("/warehouse/employees", { token }),
  listWhBalances: (token, query) => request("/warehouse/balances", { token, query }),
  listWhMovements: (token, query) => request("/warehouse/movements", { token, query }),
  createWhMovement: (token, payload) => request("/warehouse/movements", { method: "POST", token, body: payload }),
  deleteWhMovement: (token, id) => request(`/warehouse/movements/${id}`, { method: "DELETE", token }),
  transferWhStock: (token, payload) =>
    request("/warehouse/movements/transfer", { method: "POST", token, body: payload }),

  listOrders: (token, query) => request("/orders", { token, query }),
  createOrder: (token, payload) => request("/orders", { method: "POST", token, body: payload }),
  updateOrder: (token, id, payload) => request(`/orders/${id}`, { method: "PATCH", token, body: payload }),
  deleteOrder: (token, id) => request(`/orders/${id}`, { method: "DELETE", token }),
  addOrderLine: (token, id, payload) => request(`/orders/${id}/lines`, { method: "POST", token, body: payload }),
  removeOrderLine: (token, id, lineId) => request(`/orders/${id}/lines/${lineId}`, { method: "DELETE", token }),
  reserveOrder: (token, id) => request(`/orders/${id}/reserve`, { method: "POST", token }),
  cancelOrder: (token, id) => request(`/orders/${id}/cancel`, { method: "POST", token }),
  shipOrder: (token, id) => request(`/orders/${id}/ship`, { method: "POST", token }),
  generateInvoice: (token, id, payload) =>
    request(`/orders/${id}/generate-invoice`, { method: "POST", token, body: payload }),
  generateUtd: (token, id, payload) =>
    request(`/orders/${id}/generate-utd`, { method: "POST", token, body: payload }),
  openSdvfPdf: (token, id, doc) => openPdf(`/orders/${id}/sdvf-pdf`, { token, query: { doc } }),

  listRecipes: (token, query) => request("/production/recipes", { token, query }),
  createRecipe: (token, payload, companyId) =>
    request("/production/recipes", { method: "POST", token, body: payload, query: { company_id: companyId } }),
  updateRecipe: (token, id, payload) => request(`/production/recipes/${id}`, { method: "PATCH", token, body: payload }),
  deleteRecipe: (token, id) => request(`/production/recipes/${id}`, { method: "DELETE", token }),
  listProductionRuns: (token, query) => request("/production/runs", { token, query }),
  createProductionRun: (token, payload) => request("/production/runs", { method: "POST", token, body: payload }),
  deleteProductionRun: (token, id) => request(`/production/runs/${id}`, { method: "DELETE", token }),
};
