"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

const TOKEN_KEY = "fp_token";
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = window.localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setLoading(false);
      return;
    }
    api
      .me(stored)
      .then((me) => {
        setToken(stored);
        setUser(me);
      })
      .catch(() => {
        window.localStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => setLoading(false));
  }, []);

  // Общая точка входа для уже полученного access_token — используется login'ом,
  // а также страницей /oauth-callback и Register.jsx (там применяется не сразу
  // после регистрации, а после того, как пользователь закроет предупреждение
  // про папку "Спам" — см. Register.jsx).
  const applyToken = useCallback(async (access_token) => {
    const me = await api.me(access_token);
    window.localStorage.setItem(TOKEN_KEY, access_token);
    setToken(access_token);
    setUser(me);
  }, []);

  const login = useCallback(
    async (email, password) => {
      const { access_token } = await api.login(email, password);
      await applyToken(access_token);
    },
    [applyToken]
  );

  // Перечитать /auth/me после смены модулей компании — чтобы меню обновилось
  // без релогина.
  const refreshUser = useCallback(async () => {
    if (!token) return;
    const me = await api.me(token);
    setUser(me);
  }, [token]);

  const logout = useCallback(() => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, login, applyToken, refreshUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
