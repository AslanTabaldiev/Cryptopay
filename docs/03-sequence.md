# 3. Диаграммы последовательности

Три главных сценария: продавец создаёт счёт, покупатель платит, сервер ждёт
подтверждений и сообщает магазину. Внутренние классы сервера здесь не показаны,
они есть на диаграмме классов (`04-class.md`).

## 3.1 Создание счёта

```mermaid
sequenceDiagram
    autonumber
    actor M as Продавец (или магазин)
    participant S as Сервер CryptoPay
    participant DB as База данных

    M->>S: POST /api/invoices {сумма, описание}
    S->>S: проверить API-ключ и сумму
    S->>DB: сохранить счёт «Ждёт оплаты»
    S-->>M: id счёта и ссылка на оплату /pay/{id}
```

## 3.2 Оплата через MetaMask

```mermaid
sequenceDiagram
    autonumber
    actor C as Покупатель
    participant UI as Страница оплаты
    participant W as MetaMask
    participant Chain as Блокчейн Sepolia
    participant S as Сервер CryptoPay

    C->>UI: открыть ссылку на оплату
    UI->>S: получить счёт (сумма, адрес продавца)
    C->>W: подключить кошелёк и нажать «Оплатить»
    W->>Chain: отправить ETH продавцу
    W-->>UI: хэш транзакции
    UI->>S: вот хэш транзакции
    S->>Chain: найти транзакцию по хэшу
    alt не та сеть, не тот получатель или мало денег
        S-->>UI: ошибка с причиной
    else всё верно
        S-->>UI: статус «Подтверждается»
    end
```

## 3.3 Подтверждение и уведомления

Сервер сам, без участия покупателя, проверяет транзакцию каждые несколько секунд.

```mermaid
sequenceDiagram
    autonumber
    participant S as Сервер CryptoPay (фоновая проверка)
    participant Chain as Блокчейн Sepolia
    participant Shop as Магазин (Кофейня)
    participant TG as Telegram

    loop каждые несколько секунд
        S->>Chain: сколько блоков после транзакции?
        Chain-->>S: число подтверждений
    end
    alt подтверждений достаточно
        S->>S: счёт → «Оплачен»
        S->>Shop: вебхук invoice.paid + подпись HMAC
        Shop->>Shop: проверить подпись, заказ → «Оплачен»
        S->>TG: сообщение «Счёт оплачен»
    else транзакция отклонена сетью или счёт просрочен
        S->>S: счёт → «Ошибка» или «Истёк»
        S->>Shop: вебхук invoice.failed / invoice.expired
    end
```
