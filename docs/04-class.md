# 4. Диаграмма классов

Бэкенд построен по **гексагональной архитектуре (порты и адаптеры)**:

- **domain** — чистые бизнес-объекты, без фреймворков;
- **ports** — абстрактные интерфейсы, которые нужны ядру (`BlockchainGateway`, `InvoiceRepository`, `PaymentNotifier`);
- **services** — сценарии использования, зависят только от портов;
- **adapters** — конкретная инфраструктура (JSON-RPC, SQLAlchemy, вебхуки);
- **api / workers** — точки входа (HTTP и фоновый цикл);
- **container** — корень композиции: подставляет адаптеры в сервисы (внедрение зависимостей).

```mermaid
classDiagram
    direction TB

    %% ---------- Domain ----------
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
        +chain_id: int
        +description: str
        +order_id: str?
        +status: InvoiceStatus
        +created_at: datetime
        +expires_at: datetime
        +tx_hash: str?
        +payer_address: str?
        +confirmations: int
        +failure_reason: str?
        +paid_at: datetime?
        +create(...)$ Invoice
        +is_overdue(now) bool
        +is_final() bool
        +attach_transaction(tx_hash, payer, now)
        +update_confirmations(n)
        +mark_paid(now)
        +mark_failed(reason, now)
        +expire(now)
    }
    Invoice --> InvoiceStatus

    %% ---------- Ports ----------
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
        +get(invoice_id) Invoice?
        +get_by_tx_hash(tx_hash) Invoice?
        +list_recent(limit) list~Invoice~
        +list_by_status(status) list~Invoice~
    }
    class PaymentNotifier {
        <<interface>>
        +notify(event: PaymentEvent)
    }
    class ChainTransaction {
        +hash: str
        +from_address: str
        +to_address: str?
        +value_wei: int
        +chain_id: int?
        +block_number: int?
    }
    class ChainReceipt {
        +success: bool
        +block_number: int
    }
    class PaymentEvent {
        +type: str
        +invoice: Invoice
        +occurred_at: datetime
    }
    BlockchainGateway ..> ChainTransaction
    BlockchainGateway ..> ChainReceipt
    PaymentNotifier ..> PaymentEvent

    %% ---------- Services ----------
    class ValidationRule {
        <<interface>>
        +check(invoice, tx) str?
    }
    class RecipientRule
    class AmountRule
    class ChainIdRule
    class PaymentValidator {
        -rules: list~ValidationRule~
        +validate(invoice, tx) list~str~
    }
    ValidationRule <|.. RecipientRule
    ValidationRule <|.. AmountRule
    ValidationRule <|.. ChainIdRule
    PaymentValidator o-- ValidationRule

    class InvoiceService {
        -repo: InvoiceRepository
        -notifier: PaymentNotifier
        +create_invoice(amount_eth, description, order_id, ttl) Invoice
        +get_invoice(id) Invoice
        +list_invoices(limit) list~Invoice~
        +expire_overdue() int
    }
    class PaymentService {
        -repo: InvoiceRepository
        -chain: BlockchainGateway
        -validator: PaymentValidator
        -notifier: PaymentNotifier
        -required_confirmations: int
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

    %% ---------- Adapters ----------
    class EthereumJsonRpcGateway {
        -rpc_url: str
        -http: httpx.Client
        -call(method, params)
    }
    class SqlAlchemyInvoiceRepository {
        -session_factory
    }
    class LoggingNotifier
    class WebhookNotifier {
        -url: str
        -secret: str
        +sign(body) str
    }
    class CompositeNotifier {
        -notifiers: list~PaymentNotifier~
    }
    BlockchainGateway <|.. EthereumJsonRpcGateway
    InvoiceRepository <|.. SqlAlchemyInvoiceRepository
    PaymentNotifier <|.. LoggingNotifier
    PaymentNotifier <|.. WebhookNotifier
    PaymentNotifier <|.. CompositeNotifier
    CompositeNotifier o-- PaymentNotifier

    %% ---------- Entry points ----------
    class PaymentWatcher {
        -invoices: InvoiceService
        -payments: PaymentService
        -interval: float
        +start()
        +stop()
        +tick()
    }
    class Container {
        +settings: Settings
        +invoice_service: InvoiceService
        +payment_service: PaymentService
        +watcher: PaymentWatcher
        +build(settings)$ Container
    }
    PaymentWatcher --> InvoiceService
    PaymentWatcher --> PaymentService
    Container ..> EthereumJsonRpcGateway : creates
    Container ..> SqlAlchemyInvoiceRepository : creates
    Container ..> CompositeNotifier : creates
    Container *-- InvoiceService
    Container *-- PaymentService
    Container *-- PaymentWatcher
```

Тестовые заменители (`FakeBlockchain`, `InMemoryInvoiceRepository` и
`RecordingNotifier` в `backend/tests/fakes.py`) реализуют те же порты. Поэтому
сервисы можно тестировать без сети и без базы данных (принцип подстановки Лисков).

## Слои и направление зависимостей

```mermaid
flowchart LR
    API[api / workers] --> Services[services]
    Services --> Ports[ports]
    Services --> Domain[domain]
    Adapters[adapters] -. реализуют .-> Ports
    Container[container] --> Adapters
    Container --> Services
```

Все стрелки направлены **внутрь**, к домену. Ядро ничего не знает о FastAPI,
SQLAlchemy или Ethereum JSON-RPC.
