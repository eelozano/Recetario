import { useEffect, useState } from "react";
import { api, API_BASE_URL } from "../api/client";

type Status = "checking" | "ok" | "down";

/** Small connectivity indicator that pings the local API's /health endpoint. */
export function HealthBadge() {
  const [status, setStatus] = useState<Status>("checking");

  async function check() {
    setStatus("checking");
    try {
      const { data, error } = await api.GET("/health");
      setStatus(!error && data?.status === "ok" ? "ok" : "down");
    } catch {
      setStatus("down");
    }
  }

  useEffect(() => {
    check();
    const id = setInterval(check, 10_000);
    return () => clearInterval(id);
  }, []);

  const label =
    status === "ok" ? "API connected" : status === "down" ? "API offline" : "Connecting…";

  return (
    <button className={`health health--${status}`} onClick={check} title={API_BASE_URL}>
      <span className="health__dot" />
      {label}
    </button>
  );
}
