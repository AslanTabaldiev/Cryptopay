# 4. Диаграмма классов

Бэкенд — это 10 файлов в одной папке `backend/app/`. Каждый файл отвечает за одну часть системы:

| Файл | Что внутри |
|---|---|
| `models.py` | Счёт `Invoice`, его статусы (конечный автомат) и бизнес-ошибки |
| `blockchain.py` | Интерфейс `BlockchainGateway` и реализация `EthereumRpcGateway` (JSON-RPC) |
| `database.py` | Интерфейсы `InvoiceRepository`, `TimelineRepository` и их реализации на SQLAlchemy |
| `notifications.py` | Интерфейс `PaymentNotifier`: лог, хронология, вебхук, Telegram, рассылка нескольким |
| `payments.py` | Бизнес-логика: правила проверки, `InvoiceService`, `PaymentService` |
| `watcher.py` | Фоновый процесс `PaymentWatcher` |
| `api.py` | REST API: схемы, маршруты, проверка API-ключа `ApiKeyGuard` |
| `main.py` | Сборка всех частей (`Services.build`) и запуск FastAPI |
| `config.py` | Настройки из переменных окружения |
| `shop.py` | Демо-магазин «Кофейня» `DemoShop` — пример клиента шлюза |

```mermaid
classDiagram
    direction TB

    %% ---------- models.py ----------
    class InvoiceStatus {
        <<enumeration>>
        AWAITING_PAYMENT
        CONFIRMING
        PAID
        EXPIRED
        FAILED
    }
    class Invoice {
        +id: str
        +amount_wei: int
        +recipient: str
        +status: InvoiceStatus
        +expires_at: datetime
        +tx_hash: str?
        +confirmations: int
        +create(...)$ Invoice
        +is_overdue(now) bool
        +attach_transaction(tx_hash, payer, now)
        +update_confirmations(n, now)
        +mark_paid(now)
        +mark_failed(reason, now)
        +expire(now)
        +to_dict() dict
    }
    Invoice --> InvoiceStatus

    %% ---------- интерфейсы ----------
    class BlockchainGateway {
        <<interface>>
        +get_transaction(tx_hash) ChainTransaction?
        +get_receipt(tx_hash) ChainReceipt?
        +get_block_number() int
    }
    class InvoiceRepository {
        <<interface>>
        +add(invoice)
        +update(invoice)
        +get(id) Invoice?
        +get_by_tx_hash(tx_hash) Invoice?
        +list_recent(limit) list
        +list_by_status(status) list
    }
    class PaymentNotifier {
        <<interface>>
        +notify(event: PaymentEvent)
    }
    class TimelineRepository {
        <<interface>>
        +add(entry: TimelineEntry)
        +list_for(invoice_id) list
    }

    %% ---------- реализации ----------
    class EthereumRpcGateway {
        +rpc_url: str
        +call(method, params)
    }
    class SqlInvoiceRepository
    class LoggingNotifier
    class TimelineNotifier
    class WebhookNotifier {
        +url: str
        +sign(body) str
    }
    class TelegramNotifier {
        +chat_id: str
        +text(event) str
    }
    class SqlTimelineRepository
    class CompositeNotifier {
        +notifiers: list
    }
    BlockchainGateway <|.. EthereumRpcGateway
    InvoiceRepository <|.. SqlInvoiceRepository
    PaymentNotifier <|.. LoggingNotifier
    PaymentNotifier <|.. WebhookNotifier
    PaymentNotifier <|.. TimelineNotifier
    PaymentNotifier <|.. TelegramNotifier
    TimelineRepository <|.. SqlTimelineRepository
    TimelineNotifier --> TimelineRepository
    PaymentNotifier <|.. CompositeNotifier
    CompositeNotifier o-- PaymentNotifier

    %% ---------- payments.py ----------
    class ValidationRule {
        <<interface>>
        +check(invoice, tx) str?
    }
    class ChainIdRule
    class RecipientRule
    class AmountRule
    class PaymentValidator {
        +rules: list~ValidationRule~
        +validate(invoice, tx) list~str~
    }
    ValidationRule <|.. ChainIdRule
    ValidationRule <|.. RecipientRule
    ValidationRule <|.. AmountRule
    PaymentValidator o-- ValidationRule

    class InvoiceService {
        +create_invoice(amount, description, order_id, ttl) Invoice
        +get_invoice(id) Invoice
        +list_invoices(limit) list
        +expire_overdue() int
    }
    class PaymentService {
        +required_confirmations: int
        +submit_transaction(invoice_id, tx_hash) Invoice
        +refresh(invoice) Invoice
        +process_pending() int
    }
    InvoiceService --> InvoiceRepository
    InvoiceService --> PaymentNotifier
    PaymentService --> InvoiceRepository
    PaymentService --> BlockchainGateway
    PaymentService --> PaymentValidator
    PaymentService --> PaymentNotifier

    %% ---------- watcher.py, api.py, main.py ----------
    class PaymentWatcher {
        +tick()
        +start()
        +stop()
    }
    class ApiKeyGuard {
        +api_key: str
        +required: bool
        +check(provided)
    }
    class DemoShop {
        +create_order(cart) ShopOrder
        +handle_webhook(body, signature) ShopOrder
    }
    DemoShop --> InvoiceService : создаёт счёт
    class Services {
        +settings: Settings
        +invoices: InvoiceService
        +payments: PaymentService
        +watcher: PaymentWatcher
        +guard: ApiKeyGuard
        +shop: DemoShop
        +build(settings)$ Services
    }
    PaymentWatcher --> InvoiceService
    PaymentWatcher --> PaymentService
    Services *-- InvoiceService
    Services *-- PaymentService
    Services *-- PaymentWatcher
    Services *-- ApiKeyGuard
    Services *-- DemoShop
    Services ..> SqlInvoiceRepository : создаёт
    Services ..> EthereumRpcGateway : создаёт
    Services ..> CompositeNotifier : создаёт
```

Тестовые заменители (`FakeBlockchain`, `InMemoryInvoiceRepository` и
`RecordingNotifier` в `backend/tests/fakes.py`) реализуют те же интерфейсы. Поэтому
сервисы можно тестировать без сети и без базы данных (принцип подстановки Лисков).

## Кто от кого зависит

```mermaid
flowchart LR
    api[api.py] --> payments[payments.py]
    watcher[watcher.py] --> payments
    payments --> models[models.py]
    payments -. интерфейсы .-> blockchain[blockchain.py]
    payments -. интерфейсы .-> database[database.py]
    payments -. интерфейсы .-> notifications[notifications.py]
    main[main.py] --> api
    main --> watcher
    main -->|выбирает реализации| blockchain
    main -->|выбирает реализации| database
    main -->|выбирает реализации| notifications
```

`payments.py` работает только с интерфейсами (`BlockchainGateway`,
`InvoiceRepository`, `PaymentNotifier`). Конкретные классы выбираются в одном
месте: `Services.build()` в `main.py`.
