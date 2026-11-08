import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../lib/api.js";
import BackLink from "../components/BackLink.jsx";
import { ORDER_STATUS } from "./Shop.jsx";

/** Страница заказа в демо-магазине. Статус меняется только когда магазин получает вебхук. */
export default function ShopOrder() {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () => api.shopOrder(id).then((o) => alive && setOrder(o)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [id]);

  if (error) {
    return (
      <div className="page narrow">
        <BackLink fallback="/shop" label="В магазин" />
        <div className="alert">{error}</div>
      </div>
    );
  }
  if (!order) return <div className="page narrow muted">Загружаем заказ…</div>;

  const paid = order.status === "paid";
  return (
    <div className="page narrow">
      <BackLink fallback="/shop" label="В магазин" />
      <div className="card pay-card">
        <div className="row-between">
          <span className="muted small">Кофейня «Блок» · заказ</span>
          <span className={`order-status os-${order.status}`}>{ORDER_STATUS[order.status]}</span>
        </div>

        {paid ? (
          <div className="state-box success order-hero">
            <div className="check" aria-hidden>✓</div>
            <p><strong>Заказ оплачен — готовим!</strong></p>
          </div>
        ) : (
          <p className="pay-desc">
            {order.status === "awaiting_payment" ? "Ждём подтверждение оплаты от платёжного шлюза…" : "Заказ не оплачен."}
          </p>
        )}

        <ul className="cart-lines">
          {order.items.map((i) => (
            <li key={i.product_id} className="row-between">
              <span>{i.name} × {i.qty}</span>
              <span className="mono">{(Number(i.price_eth) * i.qty).toFixed(4).replace(/0+$/, "")} ETH</span>
            </li>
          ))}
        </ul>
        <div className="row-between cart-total">
          <span>Итого</span>
          <strong>{order.total_eth} ETH</strong>
        </div>

        <div className="webhook-box">
          {order.webhook_at ? (
            <>
              <p><strong>Вебхук получен</strong> {new Date(order.webhook_at).toLocaleTimeString("ru-RU")}</p>
              <p className="muted small">
                Событие <code>{order.webhook_event}</code>. Подпись HMAC-SHA256 проверена — запрос точно от CryptoPay.
              </p>
            </>
          ) : (
            <p className="muted small">
              Вебхука от платёжного шлюза пока не было. Магазин не верит браузеру на слово: статус поменяется,
              только когда придёт подписанное уведомление.
            </p>
          )}
        </div>

        <div className="next-actions">
          {order.status === "awaiting_payment" && (
            <Link className="btn btn-primary full" to={`${order.payment_path}?return=/shop/orders/${order.id}`}>
              Перейти к оплате
            </Link>
          )}
          <Link className={`btn ${order.status === "awaiting_payment" ? "btn-secondary" : "btn-primary"} full`} to="/shop">
            Сделать ещё заказ
          </Link>
          <Link className="btn btn-link" to={order.payment_path}>Счёт в CryptoPay и хронология ›</Link>
        </div>
      </div>
    </div>
  );
}
