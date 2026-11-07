import { useNavigate } from "react-router-dom";

/** «← Назад»: возвращает на предыдущую страницу, а если её нет — на fallback. */
export default function BackLink({ fallback = "/", label = "Назад" }) {
  const navigate = useNavigate();
  function goBack() {
    if (window.history.state?.idx > 0) navigate(-1);
    else navigate(fallback);
  }
  return (
    <button type="button" className="back-link" onClick={goBack}>
      ‹ {label}
    </button>
  );
}
