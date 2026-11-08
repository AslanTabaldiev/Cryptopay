import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../lib/api.js";
import BackLink from "../components/BackLink.jsx";

const ORDER_STATUS = {
  awaiting_payment: "Ждёт оплаты",
  paid: "Оплачен",
  failed: "Ошибка оплаты",
  expired: "Истёк",
};

function addEth(a, b) {
  // считаем в «микро-ETH», чтобы не ловить ошибки округления дробных чисел
  return (Math.round(Number(a) * 1e6) + Math.round(Number(b) * 1e6)) / 1e6;
}

export default function Shop() {
  const navigate = useNavigate();
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState({});
  const [orders, setOrders] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.shopProducts().then(setProducts).catch((e) => setError(e.message));
    api.shopOrders().then(setOrders).catch(() => {});
  }, []);

  const change = (id, delta) => setCart((c) => ({ ...c, [id]: Math.max(0, (c[id] || 0) + delta) }));
  const lines = products.filter((p) => cart[p.id] > 0);
  const total = lines.reduce((sum, p) => {
    let s = sum;
    for (let i = 0; i < cart[p.id]; i++) s = addEth(s, p.price_eth);
    return s;
  }, 0);

  async function checkout() {
    setBusy(true);
    setError("");
    try {
      const order = await api.createShopOrder(cart);
      navigate(`${order.payment_path}?return=/shop/orders/${order.id}`);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <BackLink fallback="/" label="На главную" />
      <div className="page-head">
        <p className="eyebrow left">Демо-магазин · пример интеграции</p>
        <h1 className="title">Кофейня «Блок»</h1>
        <p className="subtitle">
          Обычный интернет-магазин, который принимает оплату через CryptoPay. Соберите заказ и оплатите его в MetaMask —
          магазин узнает об оплате из вебхука.
        </p>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="shop-layout">
        <div className="products">
          {products.map((p) => (
            <div className="card product" key={p.id}>
              <span className="product-emoji" aria-hidden>{p.emoji}</span>
              <h3>{p.name}</h3>
              <p className="muted small">{p.note}</p>
              <div className="row-between product-foot">
                <strong>{p.price_eth} ETH</strong>
                {cart[p.id] > 0 ? (
                  <div className="qty">
                    <button type="button" onClick={() => change(p.id, -1)} aria-label={`Убрать ${p.name}`}>−</button>
                    <span>{cart[p.id]}</span>
                    <button type="button" onClick={() => change(p.id, 1)} aria-label={`Добавить ${p.name}`}>+</button>
                  </div>
                ) : (
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => change(p.id, 1)}>
                    В корзину
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        <aside className="card cart">
          <h2 className="card-title">Корзина</h2>
          {lines.length === 0 ? (
            <p className="muted small">Пока пусто. Добавьте что-нибудь из меню.</p>
          ) : (
            <ul className="cart-lines">
              {lines.map((p) => (
                <li key={p.id} className="row-between">
                  <span>{p.name} × {cart[p.id]}</span>
                  <span className="mono">{(Number(p.price_eth) * cart[p.id]).toFixed(4).replace(/0+$/, "")}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="row-between cart-total">
            <span>Итого</span>
            <strong>{total} ETH</strong>
          </div>
          <button className="btn btn-primary full" disabled={lines.length === 0 || busy} onClick={checkout}>
            {busy ? "Оформляем…" : "Оплатить криптовалютой"}
          </button>
          <p className="muted small center-text">Тестовая сеть Sepolia — деньги ненастоящие.</p>
        </aside>
      </div>

      {orders.length > 0 && (
        <section className="section-sm">
          <h2 className="card-title">Последние заказы</h2>
          <ul className="card order-list">
            {orders.slice(0, 5).map((o) => (
              <li key={o.id} className="row-between">
                <Link to={`/shop/orders/${o.id}`}>
                  {o.items.map((i) => `${i.name} ×${i.qty}`).join(", ")}
                </Link>
                <span className={`order-status os-${o.status}`}>{ORDER_STATUS[o.status] || o.status}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export { ORDER_STATUS };
