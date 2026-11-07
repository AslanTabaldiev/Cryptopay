import { useEffect, useState } from "react";

import { api } from "./api.js";

let cached = null;

/** Настройки сервера (/api/config): сеть, адрес магазина, нужен ли API-ключ. */
export function useConfig() {
  const [config, setConfig] = useState(cached);
  const [error, setError] = useState("");

  useEffect(() => {
    if (cached) return;
    let alive = true;
    api
      .config()
      .then((c) => {
        cached = c;
        if (alive) setConfig(c);
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);

  return { config, error };
}
