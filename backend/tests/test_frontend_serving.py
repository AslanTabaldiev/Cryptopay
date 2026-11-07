"""Сайт и API отдаются одним сервисом: проверяем маршрутизацию."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Container
from app.main import create_app
from tests.fakes import MERCHANT, FakeBlockchain, InMemoryInvoiceRepository, RecordingNotifier


def make_client(static_dir):
    settings = Settings(
        database_url="sqlite://", rpc_url="http://unused", chain_id=11155111, network_name="Sepolia",
        explorer_url="https://sepolia.etherscan.io", merchant_address=MERCHANT, merchant_api_key="k",
        required_confirmations=1, default_ttl_minutes=15, tx_not_found_timeout_minutes=10,
        poll_interval_seconds=60, webhook_url=None, webhook_secret="s", run_watcher=False,
        static_dir=str(static_dir),
    )
    container = Container.build(
        settings, repo=InMemoryInvoiceRepository(), chain=FakeBlockchain(), notifier=RecordingNotifier()
    )
    return TestClient(create_app(container))


def test_spa_routes_and_api_coexist(tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    client = make_client(tmp_path)

    assert client.get("/").text == "<html>app</html>"
    assert client.get("/pay/abc").text == "<html>app</html>"  # клиентский роутинг React
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/invoices/nope").status_code == 404
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/../secret").text == "<html>app</html>"  # без выхода за пределы папки
