import { useEffect, useState } from "react";

import { api } from "../lib/api.js";

const ICONS = {
  "invoice.created": "🧾",
  "transaction.received": "📨",
  "transaction.validated": "🔎",
  "transaction.confirmation": "⛓",
  "invoice.paid": "✅",
  "invoice.failed": "⚠️",
  "invoice.expired": "⌛",
  "webhook.delivered": "🏪",
  "webhook.failed": "🏪",
  "telegram.sent": "✈️",
};

/** Хронология счёта: каждое событие с точным временем. Обновляется сама. */
export default function Timeline({ invoiceId, final }) {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    let alive = true;
    const load = () => api.getEvents(invoiceId).then((e) => alive && setEvents(e)).catch(() => {});
    load();
    // пока счёт не завершён — опрашиваем; после — ещё пару раз, чтобы поймать вебхук и Telegram
    const timers = final ? [setTimeout(load, 2000), setTimeout(load, 6000)] : [setInterval(load, 4000)];
    return () => {
      alive = false;
      timers.forEach((t) => (final ? clearTimeout(t) : clearInterval(t)));
    };
  }, [invoiceId, final]);

  if (events.length === 0) return null;
  return (
    <section className="card timeline-card" aria-label="Хронология платежа">
      <h2 className="card-title tight">Хронология платежа</h2>
      <ol className="timeline">
        {events.map((e, i) => (
          <li key={i} className={`tl-${e.type.split(".")[1]}`}>
            <span className="tl-icon" aria-hidden>{ICONS[e.type] || "•"}</span>
            <div>
              <p>{e.message}</p>
              <time className="muted small mono">{new Date(e.created_at).toLocaleTimeString("ru-RU")}</time>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
