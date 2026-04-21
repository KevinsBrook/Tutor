"use client";

import React, { createContext, useContext, useMemo, useState } from "react";

export type UserRole = "teacher" | "student";

export interface AuthSession {
  username: string;
  role: UserRole;
  loggedInAt: number;
}

interface LoginResult {
  success: boolean;
  error?: string;
}

interface AuthContextType {
  session: AuthSession | null;
  isAuthenticated: boolean;
  isReady: boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => void;
  refreshSession: () => void;
}

const AUTH_USER_KEY = "auth_user";

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function readSessionFromStorage(): AuthSession | null {
  if (typeof window === "undefined") return null;

  try {
    const rawUser = localStorage.getItem(AUTH_USER_KEY);
    if (!rawUser) return null;

    const parsedUser = JSON.parse(rawUser);
    if (!parsedUser?.username || !parsedUser?.role) return null;

    return {
      username: parsedUser.username,
      role: parsedUser.role,
      loggedInAt: Date.now(),
    };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isReady, setIsReady] = useState(false);

  const refreshSession = () => {
    const nextSession = readSessionFromStorage();
    setSession(nextSession);
  };

  React.useEffect(() => {
    refreshSession();
    setIsReady(true);
  }, []);

  const login = async (username: string, password: string): Promise<LoginResult> => {
    const API_BASE =
      process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8001";

    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: username.trim(),
          password,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        return { success: false, error: data.detail || "用户名或密码错误" };
      }

      if (typeof window !== "undefined") {
        localStorage.setItem("auth_user", JSON.stringify(data.user));
        localStorage.setItem("auth_profile", JSON.stringify(data.profile || {}));
      }

      setSession({
        username: data.user.username,
        role: data.user.role,
        loggedInAt: Date.now(),
      });

      return { success: true };
    } catch (e: any) {
      return { success: false, error: e?.message || "登录失败" };
    }
  };

  const logout = () => {
    setSession(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_user");
      localStorage.removeItem("auth_profile");
    }
  };

  const value = useMemo<AuthContextType>(
    () => ({
      session,
      isAuthenticated: !!session,
      isReady,
      login,
      logout,
      refreshSession,
    }),
    [isReady, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}