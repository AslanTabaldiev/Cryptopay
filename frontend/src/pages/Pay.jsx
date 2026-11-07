import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, FINAL_STATUSES } from "../lib/api.js";
import {
  METAMASK_DOWNLOAD_URL,
  connectWallet,
  ensureChain,
  getMetaMask,
  onMetaMaskDetected,
  sendPayment,
  shortAddress,
} from "../lib/wallet.js";
import BackLink from "../components/BackLink.jsx";
import StatusPill from "../components/StatusPill.jsx";

function useCountdown(expiresAt) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!expiresAt) return null;
  const left = Math.max(0, Math.floor((new Date(expiresAt).getTime() - now) / 1000));
  return `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
}

async function submitWithRetry(id, hash, attempts = 3) {
  for (let i = 1; ; i++) {
    try {
      return await api.submitTransaction(id, hash);
    } catch (e) {
      // повторяем только при сетевых/серверных ошибках; для того же хэша метод идемпотентен
      if (i >= attempts || (e.status && e.status < 500)) throw e;
      await new Promise((r) => setTimeout(r, 2000 * i));
    }
  }
}

export default function Pay() {
  const { id } = useParams();
  const [invoice, setInvoice] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [account, setAccount] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const countdown = useCountdown(invoice?.expires_at);
  const [metamask, setMetaMask] = useState(getMetaMask);

  // MetaMask может объявить себя (EIP-6963) уже после первой отрисовки.
  useEffect(() => onMetaMaskDetected(() => setMetaMask(getMetaMask())), []);

  const load = useCallback(async () => {
    try {
      setInvoice(await api.getInvoice(id));
      setLoadError("");
    } catch (e) {
      setLoadError(e.message);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  // Опрашиваем сервер, пока статус не финальный.
  useEffect(() => {
    if (!invoice || FINAL_STATUSES.includes(invoice.status)) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [invoice, load]);

  // Синхронизируем выбранный аккаунт с MetaMask.
  useEffect(() => {
    if (!metamask?.on) return;
    const onAccounts = (accounts) => setAccount(accounts[0] || "");
    metamask.on("accountsChanged", onAccounts);
    return () => metamask.removeListener?.("accountsChanged", onAccounts);
  }, [metamask]);

  async function onConnect() {
    setError("");
    setBusy("connect");
    try {
      setAccount(await connectWallet());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  async function onPay() {
    setError("");
    try {
      setBusy("network");
      await ensureChain(invoice.chain_id);
      setBusy("wallet");
      const hash = await sendPayment({ from: account, to: invoice.recipient, valueWei: invoice.amount_wei });
      setBusy("submit");
      setInvoice(await submitWithRetry(invoice.id, hash));
    } catch (e) {
      setError(e.message);
      load();
    } finally {
      setBusy("");
    }
  }

  if (loadError) {
    return (
      <div className="page narrow">
        <BackLink fallback="/" />
        <div className="card pay-card center-text">
          <h1 className="title-sm">Счёт недоступен</h1>
          <p className="muted">{loadError}</p>
          <div className="next-actions">
            <Link className="btn btn-primary full" to="/">На главную</Link>
          </div>
        </div>
      </div>
    );
  }
  if (!invoice) {
    return (
      <div className="page narrow">
        <div className="card pay-card center-text muted">Загружаем счёт…</div>
      </div>
    );
  }

  const { status } = invoice;
  const progress = Math.min(100, Math.round((invoice.confirmations / invoice.required_confirmations) * 100));

  return (
    <div className="page narrow">
      <BackLink fallback="/" />
      <div className="card pay-card">
        <div className="row-between">
          <span className="muted small">Оплата криптовалютой</span>
          <StatusPill status={status} />
        </div>

        <p className="pay-desc">{invoice.description}</p>
        <div className="pay-amount">
          {invoice.amount_eth} <span>ETH</span>
        </div>

        <dl className="details">
          <div><dt>Сеть</dt><dd>{invoice.network_name} (тестовая)</dd></div>
          <div><dt>Получатель</dt><dd className="mono" title={invoice.recipient}>{shortAddress(invoice.recipient)}</dd></div>
          {invoice.order_id && <div><dt>Заказ</dt><dd>{invoice.order_id}</dd></div>}
          {status === "awaiting_payment" && <div><dt>Истекает через</dt><dd className="mono">{countdown}</dd></div>}
          {invoice.tx_hash && (
            <div>
              <dt>Транзакция</dt>
              <dd><a href={invoice.explorer_tx_url} target="_blank" rel="noreferrer" className="mono">{shortAddress(invoice.tx_hash)} ↗</a></dd>
            </div>
          )}
        </dl>

        {status === "awaiting_payment" && (
          <div className="pay-actions">
            <ol className="mini-steps">
              <li className={account ? "done" : "current"}>Подключите MetaMask</li>
              <li className={account ? "current" : ""}>Нажмите «Оплатить» и подтвердите перевод</li>
              <li>Дождитесь подтверждения сети</li>
            </ol>
            {!metamask ? (
              <>
                <a className="btn btn-primary full" href={METAMASK_DOWNLOAD_URL} target="_blank" rel="noreferrer">
                  Установить MetaMask
                </a>
                <p className="muted small center-text">
                  MetaMask не найден в этом браузере. Откройте страницу в Chrome, где установлен MetaMask,
                  или установите расширение и обновите страницу.
                </p>
              </>
            ) : !account ? (
              <button className="btn btn-primary full" onClick={onConnect} disabled={!!busy}>
                {busy === "connect" ? "Подключаем…" : "Подключить MetaMask"}
              </button>
            ) : (
              <>
                <button className="btn btn-primary full" onClick={onPay} disabled={!!busy}>
                  {busy === "network" && "Переключаем сеть…"}
                  {busy === "wallet" && "Подтвердите в MetaMask…"}
                  {busy === "submit" && "Отправляем…"}
                  {!busy && `Оплатить ${invoice.amount_eth} ETH`}
                </button>
                <p className="muted small center-text">Подключён: <span className="mono">{shortAddress(account)}</span></p>
              </>
            )}
            <p className="muted small center-text">
              Нет тестовых ETH? <Link to="/#guide">Как получить бесплатно</Link>
            </p>
          </div>
        )}

        {status === "confirming" && (
          <div className="state-box">
            <div className="spinner" aria-hidden />
            <p><strong>Ждём подтверждений сети</strong></p>
            <div className="progress"><div style={{ width: `${progress}%` }} /></div>
            <p className="muted small">
              {invoice.confirmations} из {invoice.required_confirmations} · обычно меньше минуты
            </p>
            <p className="muted small">Страницу можно закрыть — платёж всё равно будет засчитан.</p>
          </div>
        )}

        {status === "paid" && (
          <div className="state-box success">
            <div className="check" aria-hidden>✓</div>
            <p><strong>Оплата получена</strong></p>
            <p className="muted small">
              Подтверждено в блокчейне в {invoice.paid_at && new Date(invoice.paid_at).toLocaleTimeString("ru-RU")}.
              Продавец уже получил деньги и уведомление.
            </p>
            <div className="next-actions">
              <a className="btn btn-primary full" href={invoice.explorer_tx_url} target="_blank" rel="noreferrer">
                Посмотреть транзакцию в Etherscan ↗
              </a>
              <Link className="btn btn-secondary full" to="/dashboard">Создать новый счёт</Link>
              <Link className="btn btn-link" to="/">На главную</Link>
            </div>
          </div>
        )}

        {status === "expired" && (
          <div className="state-box">
            <p><strong>Срок действия счёта истёк</strong></p>
            <p className="muted small">Оплатить этот счёт уже нельзя. Попросите у продавца новую ссылку или создайте новый счёт.</p>
            <div className="next-actions">
              <Link className="btn btn-primary full" to="/dashboard">Создать новый счёт</Link>
              <Link className="btn btn-link" to="/">На главную</Link>
            </div>
          </div>
        )}

        {status === "failed" && (
          <div className="state-box danger">
            <p><strong>Оплата не прошла</strong></p>
            <p className="muted small">{invoice.failure_reason}</p>
            <div className="next-actions">
              <Link className="btn btn-primary full" to="/dashboard">Создать новый счёт</Link>
              <Link className="btn btn-link" to="/">На главную</Link>
            </div>
          </div>
        )}

        {error && <div className="alert">{error}</div>}
      </div>
    </div>
  );
}
