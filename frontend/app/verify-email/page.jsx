"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "../../lib/api";

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState("pending"); // pending | ok | error

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    api
      .verifyEmail(token)
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="fp-login-page">
      <div className="fp-login-card" style={{ textAlign: "center" }}>
        <div className="fp-brand-mark" style={{ margin: "0 auto 14px" }}>
          ₽
        </div>
        {status === "pending" && <p style={{ fontSize: 13.5, color: "#5B6472" }}>Подтверждаем email…</p>}
        {status === "ok" && (
          <>
            <h2 style={{ fontFamily: "'Fraunces', serif", fontSize: 18, margin: "0 0 10px" }}>
              Email подтверждён
            </h2>
            <p style={{ fontSize: 13, color: "#5B6472" }}>Можно закрыть эту вкладку и вернуться в приложение.</p>
          </>
        )}
        {status === "error" && (
          <>
            <h2 style={{ fontFamily: "'Fraunces', serif", fontSize: 18, margin: "0 0 10px" }}>
              Ссылка недействительна
            </h2>
            <p style={{ fontSize: 13, color: "#5B6472" }}>
              Возможно, она устарела (действует 24 часа). Запросите новое письмо из приложения.
            </p>
          </>
        )}
        <a href="/" style={{ display: "inline-block", marginTop: 14, color: "#2F6F5E", fontSize: 12.5 }}>
          Вернуться в приложение
        </a>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  );
}
