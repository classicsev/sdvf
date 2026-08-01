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

export const api = {
  ApiError,

  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  me: (token) => request("/auth/me", { token }),

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

  listAuditLog: (token) => request("/audit-log", { token }),
};
