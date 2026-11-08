import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router-dom";

import Home from "./pages/Home.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Pay from "./pages/Pay.jsx";
import Shop from "./pages/Shop.jsx";
import ShopOrder from "./pages/ShopOrder.jsx";
import { BASE_URL } from "./lib/api.js";
import "./styles.css";

// При переходе между страницами — наверх; ссылки вида /#guide — к нужному разделу.
function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) {
      window.scrollTo(0, 0);
      return;
    }
    // ждём один кадр, чтобы страница успела отрисоваться
    const timer = setTimeout(() => {
      const el = document.getElementById(hash.slice(1));
      if (el) window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - 64, behavior: "smooth" });
    }, 50);
    return () => clearTimeout(timer);
  }, [pathname, hash]);
  return null;
}

const GITHUB_URL = "https://github.com/AslanTabaldiev/Cryptopay";

function Layout({ children }) {
  return (
    <>
      <header className="nav">
        <div className="nav-inner">
          <NavLink to="/" className="brand">
            <span className="brand-mark" aria-hidden>◆</span> CryptoPay
          </NavLink>
          <nav className="nav-links">
            <Link to="/#how" className="nav-optional">Как работает</Link>
            <Link to="/#guide" className="nav-optional">Попробовать</Link>
            <NavLink to="/shop">Кофейня</NavLink>
            <a href={`${BASE_URL}/docs`} target="_blank" rel="noreferrer" className="nav-optional">API</a>
            <NavLink to="/dashboard" className="nav-cta">Кабинет</NavLink>
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <footer className="footer">
        <p>Учебный проект · тестовая сеть Sepolia · деньги ненастоящие</p>
        <p>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">Код и документация на GitHub ↗</a>
          {" · "}
          <a href={`${GITHUB_URL}/tree/main/docs`} target="_blank" rel="noreferrer">Диаграммы и SOLID ↗</a>
          {" · "}
          <a href={`${BASE_URL}/docs`} target="_blank" rel="noreferrer">Swagger API ↗</a>
        </p>
      </footer>
    </>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <ScrollManager />
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/pay/:id" element={<Pay />} />
          <Route path="/shop" element={<Shop />} />
          <Route path="/shop/orders/:id" element={<ShopOrder />} />
          <Route
            path="*"
            element={
              <div className="page narrow center-text">
                <h1 className="title">Страница не найдена</h1>
                <p className="subtitle">Возможно, ссылка устарела или в ней опечатка.</p>
                <div className="actions center"><Link className="btn btn-primary" to="/">На главную</Link></div>
              </div>
            }
          />
        </Routes>
      </Layout>
    </BrowserRouter>
  </StrictMode>
);
