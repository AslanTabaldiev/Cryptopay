import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router-dom";

import Home from "./pages/Home.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Pay from "./pages/Pay.jsx";
import "./styles.css";

// При переходе между страницами — наверх; ссылки вида /#guide — к нужному разделу.
function ScrollManager() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const el = document.getElementById(hash.slice(1));
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    window.scrollTo(0, 0);
  }, [pathname, hash]);
  return null;
}

function Layout({ children }) {
  return (
    <>
      <header className="nav">
        <div className="nav-inner">
          <NavLink to="/" className="brand">
            <span className="brand-mark" aria-hidden>◆</span> CryptoPay
          </NavLink>
          <nav className="nav-links">
            <NavLink to="/" end>Главная</NavLink>
            <Link to="/#guide" className="nav-optional">Как попробовать</Link>
            <NavLink to="/dashboard">Кабинет</NavLink>
          </nav>
        </div>
      </header>
      <main>{children}</main>
      <footer className="footer">
        Только тестовая сеть Sepolia · Без хранения средств · Оплата через MetaMask
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
