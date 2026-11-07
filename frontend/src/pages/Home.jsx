import { Link } from "react-router-dom";

import { BASE_URL } from "../lib/api.js";

const STEPS = [
  { n: "1", title: "Создайте счёт", text: "Магазин вызывает один REST-метод и получает ссылку на оплату." },
  { n: "2", title: "Клиент платит", text: "Один клик в MetaMask. Деньги идут сразу вам." },
  { n: "3", title: "Мы подтверждаем", text: "Шлюз проверяет транзакцию в блокчейне и отправляет подписанный вебхук." },
];

export default function Home() {
  return (
    <div className="page">
      <section className="hero">
        <p className="eyebrow">CryptoPay Gateway</p>
        <h1 className="hero-title">
          Криптоплатежи.
          <br />
          <span className="muted">Проверено блокчейном.</span>
        </h1>
        <p className="lead">
          Принимайте ETH через MetaMask. Никаких приватных ключей на сервере — только счета,
          проверка в блокчейне и вебхуки.
        </p>
        <div className="actions center">
          <Link className="btn btn-primary" to="/dashboard">Открыть кабинет</Link>
          <a className="btn btn-link" href={`${BASE_URL}/docs`} target="_blank" rel="noreferrer">
            Документация API ›
          </a>
        </div>
      </section>

      <section className="steps">
        {STEPS.map((s) => (
          <div className="card step" key={s.n}>
            <span className="step-n">{s.n}</span>
            <h3>{s.title}</h3>
            <p>{s.text}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
