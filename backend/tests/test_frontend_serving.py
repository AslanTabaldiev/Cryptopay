"""Сайт и API отдаются одним сервером: проверяем маршрутизацию."""

from tests.fakes import make_client


def test_spa_routes_and_api_coexist(tmp_path):
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    client, *_ = make_client(static_dir=str(tmp_path))

    assert client.get("/").text == "<html>app</html>"
    assert client.get("/pay/abc").text == "<html>app</html>"  # клиентский роутинг React
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/invoices/nope").status_code == 404
    assert client.get("/api/unknown").status_code == 404
    assert client.get("/../secret").text == "<html>app</html>"  # без выхода за пределы папки
