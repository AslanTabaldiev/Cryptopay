# 5. Диаграмма состояний: жизненный цикл счёта

Сущность `Invoice` сама следит за допустимыми переходами (см.
`backend/app/models.py`). Любой другой переход выбрасывает
`InvalidStateTransition`.

```mermaid
stateDiagram-v2
    [*] --> AWAITING_PAYMENT : продавец создал счёт

    AWAITING_PAYMENT --> CONFIRMING : получен верный хэш транзакции<br/>[получатель, сумма, сеть верны]
    AWAITING_PAYMENT --> AWAITING_PAYMENT : неверная транзакция отклонена<br/>(422, статус не меняется)
    AWAITING_PAYMENT --> EXPIRED : истёк TTL<br/>[транзакция не отправлена]

    CONFIRMING --> CONFIRMING : новый блок<br/>[подтверждений < N]
    CONFIRMING --> PAID : receipt.status = 1<br/>[подтверждений ≥ N]
    CONFIRMING --> FAILED : receipt.status = 0 (reverted)<br/>или tx не найдена за отведённое время<br/>или tx оказалась неверной

    PAID --> [*]
    EXPIRED --> [*]
    FAILED --> [*]

    note right of CONFIRMING
        транзакция в мемпуле или в блоке,
        ждём N подтверждений
    end note
    note right of PAID
        вебхук invoice.paid
    end note
```

| Статус | Значение | Финальный? | Вебхук |
|---|---|---|---|
| `AWAITING_PAYMENT` | Счёт создан, ждём покупателя. | нет | — |
| `CONFIRMING` | Транзакция принята, ждём подтверждений. | нет | — |
| `PAID` | Платёж подтверждён в блокчейне. | да | `invoice.paid` |
| `EXPIRED` | Не оплачен в течение срока действия. | да | `invoice.expired` |
| `FAILED` | Транзакция отклонена сетью, пропала или оказалась неверной. | да | `invoice.failed` |
