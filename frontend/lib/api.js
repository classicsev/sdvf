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
  verifyEmail: (token) => request("/auth/verify-email", { query: { token } }),
  resendVerification: (token) => request("/auth/resend-verification", { method: "POST", token }),

  listOAuthProviders: () => request("/auth/oauth/providers"),
  oauthStartUrl: (provider) => `${API_BASE}/auth/oauth/${provider}/start`,

  ssoConsent: (token, payload) => request("/oauth/consent", { method: "POST", token, body: payload }),

  getMyCompany: (token) => request("/companies/me", { token }),
  updateCompanyModules: (token, payload) =>
    request("/companies/me/modules", { method: "PATCH", token, body: payload }),

  listUsers: (token) => request("/users", { token }),
  createUser: (token, payload) => request("/users", { method: "POST", token, body: payload }),
  updateUser: (token, id, payload) => request(`/users/${id}`, { method: "PATCH", token, body: payload }),
  deleteUser: (token, id) => request(`/users/${id}`, { method: "DELETE", token }),

  listTransactions: (token, query) => request("/transactions", { token, query }),
  createTransaction: (token, payload) => request("/transactions", { method: "POST", token, body: payload }),
  updateTransaction: (token, id, payload) =>
    request(`/transactions/${id}`, { method: "PATCH", token, body: payload }),
  deleteTransaction: (token, id) => request(`/transactions/${id}`, { method: "DELETE", token }),
  exportTransactions: (token, query) => download("/transactions/export.xlsx", { token, query }),

  dashboardSummary: (token) => request("/reports/dashboard-summary", { token }),
  cashflowReport: (token, query) => request("/reports/cashflow", { token, query }),
  pnlReport: (token, query) => request("/reports/pnl", { token, query }),
  balanceReport: (token, query) => request("/reports/balance", { token, query }),
  debtReport: (token) => request("/reports/debt", { token }),
  profitabilityReport: (token, query) => request("/reports/profitability", { token, query }),
  paymentCalendar: (token, query) => request("/reports/payment-calendar", { token, query }),

  listCategories: (token) => request("/categories", { token }),
  createCategory: (token, payload) => request("/categories", { method: "POST", token, body: payload }),
  updateCategory: (token, id, payload) => request(`/categories/${id}`, { method: "PATCH", token, body: payload }),
  deleteCategory: (token, id) => request(`/categories/${id}`, { method: "DELETE", token }),

  listProjects: (token) => request("/projects", { token }),
  createProject: (token, payload) => request("/projects", { method: "POST", token, body: payload }),
  updateProject: (token, id, payload) => request(`/projects/${id}`, { method: "PATCH", token, body: payload }),
  deleteProject: (token, id) => request(`/projects/${id}`, { method: "DELETE", token }),

  listAccounts: (token) => request("/accounts", { token }),
  createAccount: (token, payload) => request("/accounts", { method: "POST", token, body: payload }),
  updateAccount: (token, id, payload) => request(`/accounts/${id}`, { method: "PATCH", token, body: payload }),
  deleteAccount: (token, id) => request(`/accounts/${id}`, { method: "DELETE", token }),

  listCounterparties: (token) => request("/counterparties", { token }),
  createCounterparty: (token, payload) => request("/counterparties", { method: "POST", token, body: payload }),
  updateCounterparty: (token, id, payload) =>
    request(`/counterparties/${id}`, { method: "PATCH", token, body: payload }),
  deleteCounterparty: (token, id) => request(`/counterparties/${id}`, { method: "DELETE", token }),

  listPlanning: (token, query) => request("/planning", { token, query }),
  createPlanning: (token, payload) => request("/planning", { method: "POST", token, body: payload }),
  updatePlanning: (token, id, payload) => request(`/planning/${id}`, { method: "PATCH", token, body: payload }),
  deletePlanning: (token, id) => request(`/planning/${id}`, { method: "DELETE", token }),

  listEmployees: (token) => request("/payroll/employees", { token }),
  createEmployee: (token, payload) => request("/payroll/employees", { method: "POST", token, body: payload }),
  updateEmployee: (token, id, payload) =>
    request(`/payroll/employees/${id}`, { method: "PATCH", token, body: payload }),
  deleteEmployee: (token, id) => request(`/payroll/employees/${id}`, { method: "DELETE", token }),

  listAccruals: (token, query) => request("/payroll/accruals", { token, query }),
  createAccrual: (token, payload) => request("/payroll/accruals", { method: "POST", token, body: payload }),
  listPayments: (token) => request("/payroll/payments", { token }),
  createPayment: (token, payload) => request("/payroll/payments", { method: "POST", token, body: payload }),
  payrollSummary: (token, query) => request("/payroll/summary-for-viewer", { token, query }),

  listAutomationRules: (token) => request("/automation-rules", { token }),
  createAutomationRule: (token, payload) => request("/automation-rules", { method: "POST", token, body: payload }),
  updateAutomationRule: (token, id, payload) =>
    request(`/automation-rules/${id}`, { method: "PATCH", token, body: payload }),
  deleteAutomationRule: (token, id) => request(`/automation-rules/${id}`, { method: "DELETE", token }),
  listIntegrations: (token) => request("/integrations", { token }),
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

  listWarehouses: (token) => request("/warehouse/warehouses", { token }),
  createWarehouse: (token, payload) => request("/warehouse/warehouses", { method: "POST", token, body: payload }),
  updateWarehouse: (token, id, payload) =>
    request(`/warehouse/warehouses/${id}`, { method: "PATCH", token, body: payload }),
  deleteWarehouse: (token, id) => request(`/warehouse/warehouses/${id}`, { method: "DELETE", token }),

  listWhProducts: (token) => request("/warehouse/products", { token }),
  createWhProduct: (token, payload) => request("/warehouse/products", { method: "POST", token, body: payload }),
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

  listRecipes: (token) => request("/production/recipes", { token }),
  createRecipe: (token, payload) => request("/production/recipes", { method: "POST", token, body: payload }),
  updateRecipe: (token, id, payload) => request(`/production/recipes/${id}`, { method: "PATCH", token, body: payload }),
  deleteRecipe: (token, id) => request(`/production/recipes/${id}`, { method: "DELETE", token }),
  listProductionRuns: (token, query) => request("/production/runs", { token, query }),
  createProductionRun: (token, payload) => request("/production/runs", { method: "POST", token, body: payload }),
  deleteProductionRun: (token, id) => request(`/production/runs/${id}`, { method: "DELETE", token }),
};
