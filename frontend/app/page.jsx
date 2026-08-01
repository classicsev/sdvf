"use client";

import { AuthProvider, useAuth } from "../lib/auth-context";
import Login from "../components/Login";
import Shell from "../components/Shell";

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <div className="fp-login-page">Загрузка…</div>;
  if (!user) return <Login />;
  return <Shell />;
}

export default function Page() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
