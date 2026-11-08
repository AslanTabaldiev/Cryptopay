# 2. Контекстная диаграмма и диаграмма контейнеров

## 2.1 Контекст системы (C4, уровень 1)

Система показана как «чёрный ящик» вместе со всем, с чем она взаимодействует.

```mermaid
flowchart TB
    Merchant([👤 Продавец<br/><i>создаёт счета, следит за оплатой</i>])
    Customer([👤 Покупатель<br/><i>оплачивает счёт</i>])

    Gateway[[🧾 CryptoPay Gateway<br/><i>облачная платёжная система</i>]]

    Wallet[(🦊 MetaMask<br/><i>браузерный кошелёк,<br/>подписывает транзакции</i>)]
    Chain[(⛓ Ethereum Sepolia<br/><i>через JSON-RPC провайдера</i>)]
    MerchantBackend[(🏪 Бэкенд магазина<br/><i>принимает вебхуки;<br/>в проекте — демо-«Кофейня»</i>)]
    Telegram[(✈️ Telegram<br/><i>уведомления продавцу</i>)]

    Merchant -- "создаёт счёт (REST + API-ключ)" --> Gateway
    Customer -- "открывает страницу оплаты (HTTPS)" --> Gateway
    Customer -- "подтверждает платёж" --> Wallet
    Wallet -- "отправляет подписанную транзакцию" --> Chain
    Gateway -- "читает транзакции, квитанции, номер блока (JSON-RPC)" --> Chain
    Gateway -- "invoice.paid / failed / expired (подписанный вебхук)" --> MerchantBackend
    Gateway -- "сообщение об оплате (Bot API)" --> Telegram
```

## 2.2 Контейнеры (C4, уровень 2)

Показывает, из каких развёртываемых частей состоит система и где они работают в облаке.

```mermaid
flowchart TB
    Browser([🌐 Браузер + расширение MetaMask])

    subgraph Render [Облако Render.com]
        subgraph Web [Веб-сервис cryptopay · Docker-контейнер]
            SPA[React SPA<br/><i>главная, кабинет, страница оплаты</i>]
            API[FastAPI REST API<br/><i>/api/invoices, /docs</i>]
            Watcher[Payment Watcher<br/><i>фоновая задача в том же процессе</i>]
        end
        DB[(Render PostgreSQL<br/><i>таблица invoices</i>)]
    end

    RPC[(Sepolia JSON-RPC<br/><i>публичная нода / Alchemy / Infura</i>)]
    Hook[(URL вебхука магазина<br/><i>по умолчанию /api/shop/webhook</i>)]
    TG[(Telegram Bot API)]

    Browser -- "загружает сайт (HTTPS)" --> SPA
    SPA -- "fetch JSON, тот же домен" --> API
    Browser -- "EIP-1193: eth_requestAccounts,<br/>eth_sendTransaction" --> RPC
    API -- "SQLAlchemy" --> DB
    Watcher -- "SQLAlchemy" --> DB
    API -- "eth_getTransactionByHash" --> RPC
    Watcher -- "eth_getTransactionReceipt,<br/>eth_blockNumber" --> RPC
    Watcher -- "HTTP POST + X-Signature" --> Hook
    Watcher -- "sendMessage" --> TG
```

Сайт и API отдаются **одним сервисом с одного домена**. Поэтому не нужна
настройка CORS и отдельный хостинг для фронтенда. Docker-образ собирается в
два этапа: Node собирает React, затем Python-образ получает готовые файлы.

## 2.3 Выбор технологий

| Задача | Выбор | Почему |
|---|---|---|
| Бэкенд | Python 3.12, FastAPI, SQLAlchemy 2, httpx | Быстрая разработка, OpenAPI из коробки, типизация. |
| Фронтенд | React + Vite, прямые вызовы EIP-1193 | Без SDK: MetaMask находится через EIP-6963 и вызывается через стандартный API провайдера EIP-1193. |
| Кошелёк | MetaMask | Самый распространённый браузерный кошелёк, исходный код открыт на GitHub, тестовая сеть Sepolia включается одним переключателем. |
| Блокчейн | Ethereum Sepolia | Бесплатные тестовые ETH с faucet, блок примерно каждые 12 секунд. |
| База данных | SQLite (локально) / PostgreSQL (облако) | Выбирается через `DATABASE_URL`, код не меняется. |
| Хостинг | Render: веб-сервис на Docker + PostgreSQL | Бесплатный тариф, деплой из GitHub по `render.yaml` в один клик. |
