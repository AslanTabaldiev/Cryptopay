import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import StatusPill from "../components/StatusPill.jsx";

const KEY_STORAGE = "cryptopay.apiKey";

function loadKey() {
  try {
    return localStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function saveKey(value) {
  try {
    localStorage.setItem(KEY_STORAGE, value);
  } catch {
    /* хранилище недоступно — ключ просто не запомнится */
  }
}

export default function Dashboard() {
  const [apiKey, setApiKey] = useState(loadKey);
  const [keyDraft, setKeyDraft] = useState(apiKey);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ amount_eth: "0.001", description: "", order_id: "", ttl_minutes: "15" });
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState("");

  const refresh = useCallback(async () => {
    if (!apiKey) return;
    setLoading(true);
    try {
      setInvoices(await api.listInvoices(apiKey));
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiKey]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  function applyKey(e) {
    e.preventDefault();
    saveKey(keyDraft.trim());
    setApiKey(keyDraft.trim());
  }

  async function create(e) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      await api.createInvoice(apiKey, {
        amount_eth: form.amount_eth,
        description: form.description,
        order_id: form.order_id || null,
        ttl_minutes: Number(form.ttl_minutes) || null,
      });
      setForm((f) => ({ ...f, description: "", order_id: "" }));
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function copyLink(id) {
    const url = `${window.location.origin}/pay/${id}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(id);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      window.prompt("Скопируйте ссылку на оплату", url);
    }
  }

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  return (
    <div className="page">
      <div className="page-head">
        <h1 className="title">Кабинет магазина</h1>
        <p className="subtitle">Создавайте счета и следите за оплатой.</p>
      </div>

      <form className="card key-card" onSubmit={applyKey}>
        <label className="field grow">
          <span>API-ключ магазина</span>
          <input
            type="password"
            value={keyDraft}
            onChange={(e) => setKeyDraft(e.target.value)}
            placeholder="X-API-Key"
            autoComplete="off"
          />
        </label>
        <button className="btn btn-secondary" type="submit">Применить</button>
      </form>

      {error && <div className="alert">{error}</div>}

      {apiKey && (
        <div className="grid">
          <form className="card" onSubmit={create}>
            <h2 className="card-title">Новый счёт</h2>
            <label className="field">
              <span>Сумма (ETH)</span>
              <input value={form.amount_eth} onChange={update("amount_eth")} inputMode="decimal" required />
            </label>
            <label className="field">
              <span>Описание</span>
              <input value={form.description} onChange={update("description")} placeholder="Кофе в зёрнах 250 г" required maxLength={255} />
            </label>
            <label className="field">
              <span>Номер заказа <em>необязательно</em></span>
              <input value={form.order_id} onChange={update("order_id")} placeholder="ORDER-1042" maxLength={128} />
            </label>
            <label className="field">
              <span>Срок действия (минуты)</span>
              <input value={form.ttl_minutes} onChange={update("ttl_minutes")} type="number" min="1" max="1440" />
            </label>
            <button className="btn btn-primary full" disabled={creating}>
              {creating ? "Создаём…" : "Создать счёт"}
            </button>
          </form>

          <div className="card list-card">
            <div className="row-between">
              <h2 className="card-title">Счета</h2>
              <button className="btn btn-link" onClick={refresh} disabled={loading}>
                {loading ? "Обновляем…" : "Обновить"}
              </button>
            </div>
            {invoices.length === 0 ? (
              <p className="empty">Счетов пока нет.</p>
            ) : (
              <ul className="invoice-list">
                {invoices.map((inv) => (
                  <li key={inv.id} className="invoice-row">
                    <div className="invoice-main">
                      <strong>{inv.description}</strong>
                      <span className="muted small">
                        {inv.order_id ? `${inv.order_id} · ` : ""}
                        {new Date(inv.created_at).toLocaleString("ru-RU")}
                      </span>
                    </div>
                    <div className="invoice-amount">{inv.amount_eth} ETH</div>
                    <StatusPill status={inv.status} />
                    <div className="invoice-actions">
                      <button className="btn btn-link" onClick={() => copyLink(inv.id)}>
                        {copied === inv.id ? "Скопировано" : "Копировать ссылку"}
                      </button>
                      <Link className="btn btn-link" to={`/pay/${inv.id}`}>Открыть ›</Link>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
