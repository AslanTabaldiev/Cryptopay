// Тонкий клиент REST API CryptoPay.
// В продакшене сайт и API на одном домене (Render), поэтому базовый URL пустой.
// При локальной разработке Vite работает на :5173, а API — на :8000.

export const BASE_URL = (
  import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/$/, "");

async function request(path, { method = "GET", body, apiKey } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["X-API-Key"] = apiKey;

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Сервер недоступен. Возможно, он просыпается — попробуйте через несколько секунд.");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg).join("; ")
      : data.detail || `Ошибка запроса (${response.status})`;
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return data;
}

export const api = {
  config: () => request("/api/config"),
  getInvoice: (id) => request(`/api/invoices/${encodeURIComponent(id)}`),
  listInvoices: (apiKey) => request("/api/invoices", { apiKey }),
  createInvoice: (apiKey, body) => request("/api/invoices", { method: "POST", apiKey, body }),
  submitTransaction: (id, txHash) =>
    request(`/api/invoices/${encodeURIComponent(id)}/transaction`, {
      method: "POST",
      body: { tx_hash: txHash },
    }),
};

export const FINAL_STATUSES = ["paid", "expired", "failed"];
