const LABELS = {
  awaiting_payment: "Ожидает оплаты",
  confirming: "Подтверждается",
  paid: "Оплачен",
  expired: "Истёк",
  failed: "Ошибка",
};

export default function StatusPill({ status }) {
  return <span className={`pill pill-${status}`}>{LABELS[status] || status}</span>;
}
