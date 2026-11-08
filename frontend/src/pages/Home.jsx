import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, BASE_URL } from "../lib/api.js";
import { useConfig } from "../lib/useConfig.js";
import { METAMASK_DOWNLOAD_URL } from "../lib/wallet.js";

const FAUCET_URL = "https://cloud.google.com/application/web3/faucet/ethereum/sepolia";

const HOW_IT_WORKS = [
  { n: "1", title: "Магазин создаёт счёт", text: "Указывает сумму и описание — и получает ссылку на оплату." },
  { n: "2", title: "Покупатель платит", text: "Открывает ссылку и подтверждает перевод в MetaMask. Деньги идут сразу продавцу." },
  { n: "3", title: "Сервис подтверждает", text: "Проверяет транзакцию в блокчейне, ждёт подтверждений и уведомляет магазин." },
];

function StatusStrip({ config }) {
  const online = Boolean(config);
  return (
    <ul className="status-strip" aria-label="Состояние системы">
      <li><span className={`dot ${online ? "dot-ok" : "dot-wait"}`} /> API {online ? "онлайн" : "подключается…"}</li>
      <li>Сеть {config?.network_name ?? "Sepolia"}</li>
      <li>{config?.required_confirmations ?? 2} подтверждения</li>
      <li>API-ключ: {config ? (config.auth_required ? "включён" : "выключен") : "…"}</li>
    </ul>
  );
}

export default function Home() {
  const navigate = useNavigate();
  const { config } = useConfig();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const demoMode = config && !config.auth_required;

  async function tryPayment() {
    if (!demoMode) {
      navigate("/dashboard");
      return;
    }
    setCreating(true);
    setError("");
    try {
      const invoice = await api.createInvoice(null, {
        amount_eth: "0.001",
        description: "Демо-заказ: кофе в зёрнах",
        order_id: `DEMO-${Date.now().toString().slice(-5)}`,
      });
      navigate(`/pay/${invoice.id}`);
    } catch (e) {
      setError(e.message);
      setCreating(false);
    }
  }

  return (
    <div className="page">
      <section className="hero">
        <p className="eyebrow">Учебная платёжная система · тестовая сеть</p>
        <h1 className="hero-title">
          Оплата криптовалютой.
          <br />
          <span className="muted">В пару кликов.</span>
        </h1>
        <p className="lead">
          CryptoPay принимает платежи в ETH через MetaMask и сам проверяет их в блокчейне.
          Всё работает в тестовой сети Sepolia — деньги ненастоящие, рисковать нечем.
        </p>
        <div className="actions center">
          <button className="btn btn-primary btn-lg" onClick={tryPayment} disabled={creating}>
            {creating ? "Создаём счёт…" : "Попробовать оплату"}
          </button>
          <Link className="btn btn-secondary btn-lg" to="/shop">Демо-магазин «Кофейня»</Link>
        </div>
        {error && <div className="alert narrow-alert">{error}</div>}
        <p className="muted small hero-note">
          {config?.auth_required
            ? "Сейчас включена проверка API-ключа — счёт создаётся в кабинете, ключ показан там же."
            : "«Попробовать оплату» создаст тестовый счёт на 0.001 ETH и откроет страницу оплаты. Регистрация не нужна."}
        </p>
        <StatusStrip config={config} />
      </section>

      <section className="section">
        <h2 className="section-title">Кто вы?</h2>
        <div className="roles">
          <Link to="/dashboard" className="card role-card">
            <span className="role-icon" aria-hidden>🏪</span>
            <h3>Я продавец</h3>
            <p>Создаю счета, отправляю ссылку покупателю и вижу, какие счета оплачены.</p>
            <span className="role-cta">Открыть кабинет ›</span>
          </Link>
          <a href="#guide" className="card role-card">
            <span className="role-icon" aria-hidden>🛍</span>
            <h3>Я покупатель</h3>
            <p>Получил ссылку на оплату. Нужен только MetaMask с тестовыми ETH — ниже инструкция.</p>
            <span className="role-cta">Как подготовиться ›</span>
          </a>
        </div>
      </section>

      <section className="section" id="guide">
        <h2 className="section-title">Как попробовать за 2 минуты</h2>
        <ol className="card guide">
          <li>
            <strong>Установите MetaMask</strong>
            <span>
              Расширение для Chrome с официального сайта:{" "}
              <a href={METAMASK_DOWNLOAD_URL} target="_blank" rel="noreferrer">metamask.io ↗</a>
            </span>
          </li>
          <li>
            <strong>Включите сеть Sepolia</strong>
            <span>В MetaMask: выбор сети → «Show test networks» → Sepolia. Если забудете — страница оплаты переключит сама.</span>
          </li>
          <li>
            <strong>Получите тестовые ETH</strong>
            <span>
              Бесплатно, нужен только Google-аккаунт:{" "}
              <a href={FAUCET_URL} target="_blank" rel="noreferrer">Google Sepolia Faucet ↗</a>
            </span>
          </li>
          <li>
            <strong>Нажмите «Попробовать оплату»</strong>
            <span>Подтвердите перевод в MetaMask — через 20–40 секунд статус сменится на «Оплачен».</span>
          </li>
        </ol>
      </section>

      <section className="section" id="how">
        <h2 className="section-title">Как это устроено</h2>
        <div className="steps">
          {HOW_IT_WORKS.map((s) => (
            <div className="card step" key={s.n}>
              <span className="step-n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
          ))}
        </div>
        <p className="center-text muted small section-foot">
          Для разработчиков: <a href={`${BASE_URL}/docs`} target="_blank" rel="noreferrer">документация REST API ↗</a>
        </p>
      </section>
    </div>
  );
}
