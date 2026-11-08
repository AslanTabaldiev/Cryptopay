import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import BackLink from "../components/BackLink.jsx";
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

const paymentUrl = (id) => `${window.location.origin}/pay/${id}`;

export default function Dashboard() {
  const [access, setAccess] = useState(null); // { required, api_key } — переключатель API-ключа
  const [accessError, setAccessError] = useState("");
  const [toggling, setToggling] = useState(false);
  const needsKey = access?.required ?? false;

  useEffect(() => {
    api.getAccess().then(setAccess).catch((e) => setAccessError(e.message));
  }, []);

  const [apiKey, setApiKey] = useState(loadKey);
  const [keyDraft, setKeyDraft] = useState(apiKey);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ amount_eth: "0.001", description: "", order_id: "", ttl_minutes: "15" });
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const [copied, setCopied] = useState("");

  const canWork = access && (!needsKey || apiKey);

  const refresh = useCallback(async () => {
    if (!canWork) return;
    setLoading(true);
    try {
      setInvoices(await api.listInvoices(needsKey ? apiKey : null));
      setError("");
    } catch (e) {
      setError(e.status === 401 ? "Неверный API-ключ. Проверьте его и нажмите «Применить» ещё раз." : e.message);
    } finally {
      setLoading(false);
    }
  }, [canWork, needsKey, apiKey]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  function applyKey(value) {
    saveKey(value.trim());
    setApiKey(value.trim());
    setKeyDraft(value.trim());
    setError("");
  }

  async function toggleAccess() {
    setToggling(true);
    try {
      setAccess(await api.setAccess(!needsKey));
      setError("");
    } catch (e) {
      setAccessError(e.message);
    } finally {
      setToggling(false);
    }
  }

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(access.api_key);
      setCopied("key");
      setTimeout(() => setCopied(""), 1500);
    } catch {
      window.prompt("Скопируйте API-ключ", access.api_key);
    }
  }

  async function create(e) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      const invoice = await api.createInvoice(needsKey ? apiKey : null, {
        amount_eth: form.amount_eth.replace(",", "."),
        description: form.description,
        order_id: form.order_id || null,
        ttl_minutes: Number(form.ttl_minutes) || null,
      });
      setCreated(invoice);
      setForm((f) => ({ ...f, description: "", order_id: "" }));
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }

  async function copyLink(id) {
    try {
      await navigator.clipboard.writeText(paymentUrl(id));
      setCopied(id);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      window.prompt("Скопируйте ссылку на оплату", paymentUrl(id));
    }
  }

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  return (
    <div className="page">
      <BackLink fallback="/" label="На главную" />
      <div className="page-head">
        <h1 className="title">Кабинет магазина</h1>
        <p className="subtitle">Создайте счёт, отправьте ссылку покупателю и следите за оплатой.</p>
      </div>

      {accessError && <div className="alert">{accessError}</div>}

      {access && (
        <div className="card access-card">
          <div className="row-between">
            <div>
              <h2 className="card-title tight">Проверка API-ключа</h2>
              <p className="muted small">
                API-ключ — это пароль магазина: без него посторонние не смогут создавать счета от вашего имени.
                Покупателю ключ не нужен. Это учебный проект, поэтому проверку можно включить и выключить здесь.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={needsKey}
              aria-label="Требовать API-ключ"
              className={`switch ${needsKey ? "on" : ""}`}
              onClick={toggleAccess}
              disabled={toggling}
            >
              <span />
            </button>
          </div>

          {needsKey ? (
            <>
              <div className="key-line">
                <span className="muted small">Ключ магазина:</span>
                <code className="mono">{access.api_key}</code>
                <button type="button" className="btn btn-link" onClick={copyKey}>
                  {copied === "key" ? "Скопировано" : "Копировать"}
                </button>
              </div>
              <form className="key-form" onSubmit={(e) => { e.preventDefault(); applyKey(keyDraft); }}>
                <label className="field grow">
                  <span>Введите ключ, чтобы работать с кабинетом</span>
                  <input
                    value={keyDraft}
                    onChange={(e) => setKeyDraft(e.target.value)}
                    placeholder="X-API-Key"
                    autoComplete="off"
                  />
                </label>
                <button className="btn btn-secondary" type="submit">Применить</button>
                <button className="btn btn-link" type="button" onClick={() => applyKey(access.api_key)}>
                  Подставить ключ
                </button>
              </form>
              {apiKey && apiKey === access.api_key && <p className="ok-text small">✓ Ключ принят</p>}
            </>
          ) : (
            <p className="small state-off">Сейчас проверка выключена — счета можно создавать без ключа.</p>
          )}
        </div>
      )}

      {error && <div className="alert">{error}</div>}

      {canWork && (
        <div className="grid">
          <div className="stack">
            <form className="card" onSubmit={create}>
              <h2 className="card-title">Новый счёт</h2>
              <label className="field">
                <span>Сумма (ETH)</span>
                <input value={form.amount_eth} onChange={update("amount_eth")} inputMode="decimal" required />
                <small className="hint">Для теста хватит 0.001 ETH.</small>
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

            {created && (
              <div className="card created-card">
                <div className="check small-check" aria-hidden>✓</div>
                <h3>Счёт создан</h3>
                <p className="muted small">
                  {created.description} · {created.amount_eth} ETH. Отправьте ссылку покупателю или откройте её сами.
                </p>
                <div className="created-actions">
                  <Link className="btn btn-primary full" to={`/pay/${created.id}`}>Перейти к оплате</Link>
                  <button className="btn btn-secondary full" onClick={() => copyLink(created.id)}>
                    {copied === created.id ? "Ссылка скопирована" : "Копировать ссылку"}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="card list-card">
            <div className="row-between">
              <h2 className="card-title">Счета</h2>
              <button className="btn btn-link" onClick={refresh} disabled={loading}>
                {loading ? "Обновляем…" : "Обновить"}
              </button>
            </div>
            {invoices.length === 0 ? (
              <p className="empty">Счетов пока нет. Создайте первый в форме слева — он появится здесь.</p>
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
