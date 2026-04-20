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
  login: (username: string, password: string) => LoginResult;
  logout: () => void;
}

const AUTH_STORAGE_KEY = "deeptutor-auth-session";

const DEMO_CREDENTIALS: Record<string, { password: string; role: UserRole }> = {
  teacher: { password: "teacher123", role: "teacher" },
  student: { password: "student123", role: "student" },
};

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [isReady, setIsReady] = useState(false);

  React.useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = localStorage.getItem(AUTH_STORAGE_KEY);
      if (!raw) {
        setSession(null);
        setIsReady(true);
        return;
      }
      const parsed = JSON.parse(raw) as AuthSession;
      if (parsed?.username && parsed?.role) {
        setSession(parsed);
      } else {
        setSession(null);
      }
    } catch {
      localStorage.removeItem(AUTH_STORAGE_KEY);
      setSession(null);
    } finally {
      setIsReady(true);
    }
  }, []);

  const login = (username: string, password: string): LoginResult => {
    const normalized = username.trim().toLowerCase();
    const expected = DEMO_CREDENTIALS[normalized];

    if (!expected || expected.password !== password) {
      return { success: false, error: "用户名或密码错误" };
    }

    const nextSession: AuthSession = {
      username: normalized,
      role: expected.role,
      loggedInAt: Date.now(),
    };

    setSession(nextSession);
    if (typeof window !== "undefined") {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(nextSession));
    }

    return { success: true };
  };

  const logout = () => {
    setSession(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  };

  const value = useMemo<AuthContextType>(
    () => ({
      session,
      isAuthenticated: !!session,
      isReady,
      login,
      logout,
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

