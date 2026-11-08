import { useEffect, useState } from "react";

import { api } from "./api.js";

/** Настройки сервера (/api/config): сеть, адрес магазина, включена ли проверка API-ключа. */
export function useConfig() {
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .config()
      .then((c) => alive && setConfig(c))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);

  return { config, error };
}
