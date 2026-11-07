# 6. Принципы SOLID в коде

| Принцип | Где | Как |
|---|---|---|
| **S** — единственная ответственность (Single Responsibility) | `services/invoice_service.py`, `services/payment_service.py`, `services/validation.py`, `adapters/*`, `api/routes.py` | У каждого класса одна причина для изменения. `InvoiceService` отвечает за жизненный цикл счёта (создание, чтение, истечение срока). `PaymentService` проверяет платежи и считает подтверждения. Каждое правило `ValidationRule` проверяет ровно одну вещь. `EthereumJsonRpcGateway` только общается по JSON-RPC. `SqlAlchemyInvoiceRepository` только сохраняет данные. Маршруты только переводят HTTP в вызовы сервисов и обратно. `PaymentWatcher` только запускает проверки по расписанию. |
| **O** — открытость/закрытость (Open/Closed) | `services/validation.py`, `adapters/notifiers.py`, `ports/blockchain.py` | Новая проверка платежа — это новый класс `ValidationRule`, который передаётся в `PaymentValidator`. Сам валидатор не меняется (см. тест `test_custom_rule_can_be_added_without_changing_validator`). Новый канал уведомлений (email, Telegram) — новый класс `PaymentNotifier`, который подключается через `CompositeNotifier`. Поддержка другой EVM-сети или Bitcoin — новый адаптер `BlockchainGateway`, сервисы при этом не меняются. |
| **L** — подстановка Лисков (Liskov Substitution) | `tests/fakes.py` и `adapters/*` | В тестах `FakeBlockchain`, `InMemoryInvoiceRepository` и `RecordingNotifier` заменяют настоящие адаптеры, и сервисы работают одинаково с любой реализацией. `LoggingNotifier`, `WebhookNotifier` и `CompositeNotifier` взаимозаменяемы везде, где ожидается `PaymentNotifier`. Все уведомители соблюдают один контракт: *не выбрасывать исключение при ошибке доставки*. |
| **I** — разделение интерфейсов (Interface Segregation) | `ports/blockchain.py`, `ports/repository.py`, `ports/notifier.py` | Вместо одного общего «инфраструктурного» интерфейса есть три маленьких узких порта. `BlockchainGateway` **только читает** блокчейн (три метода). Шлюз non-custodial, поэтому его не заставляют зависеть от методов подписи и отправки, которые он никогда не использует. У `PaymentNotifier` всего один метод. |
| **D** — инверсия зависимостей (Dependency Inversion) | `container.py`, конструкторы всех сервисов | Сервисы верхнего уровня зависят от абстракций (`InvoiceRepository`, `BlockchainGateway`, `PaymentNotifier`, `Clock`) и никогда не зависят от SQLAlchemy, httpx или FastAPI. Конкретные классы выбираются в одном месте, в корне композиции `Container.build()`, и передаются через конструкторы. Даже время внедряется как зависимость (`Clock`), поэтому логику истечения срока можно протестировать. |

## Использованные паттерны проектирования

| Паттерн | Где |
|---|---|
| **Порты и адаптеры (Hexagonal)** | `ports/` + `adapters/` |
| **Адаптер (Adapter)** | `EthereumJsonRpcGateway` приводит «сырой» JSON-RPC к порту `BlockchainGateway` |
| **Репозиторий (Repository)** | `InvoiceRepository` / `SqlAlchemyInvoiceRepository` |
| **Стратегия / Спецификация (Strategy / Specification)** | реализации `ValidationRule` |
| **Компоновщик (Composite)** | `CompositeNotifier` |
| **Наблюдатель (Observer)** | событие `PaymentEvent` рассылается уведомителям при финальных статусах |
| **Конечный автомат в сущности (State machine)** | `Invoice._move()` разрешает только допустимые переходы |
| **Фабричный метод (Factory method)** | `Invoice.create()`, `PaymentValidator.default()`, `Container.build()` |
| **Корень композиции / DI (Composition Root)** | `container.py` |
