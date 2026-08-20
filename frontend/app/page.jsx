"use client";

import { useState } from "react";
import { AuthProvider, useAuth } from "../lib/auth-context";
import { LanguageProvider } from "../lib/i18n";
import Login from "../components/Login";
import Register from "../components/Register";
import Shell from "../components/Shell";

function Gate() {
  const { user, loading } = useAuth();
  const [mode, setMode] = useState("login"); // "login" | "register"

  if (loading) return <div className="fp-login-page">Загрузка…</div>;
  if (user) return <Shell />;
  if (mode === "register") return <Register onSwitchToLogin={() => setMode("login")} />;
  return <Login onSwitchToRegister={() => setMode("register")} />;
}

export default function Page() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </LanguageProvider>
  );
}
