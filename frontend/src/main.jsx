import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";

import Home from "./pages/Home.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Pay from "./pages/Pay.jsx";
import "./styles.css";

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
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/pay/:id" element={<Pay />} />
          <Route path="*" element={<div className="page narrow"><h1 className="title">Страница не найдена</h1></div>} />
        </Routes>
      </Layout>
    </BrowserRouter>
  </StrictMode>
);
