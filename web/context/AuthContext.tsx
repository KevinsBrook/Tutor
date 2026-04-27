"use client";

import React, { createContext, useContext, useMemo, useState } from "react";

import { apiUrl } from "@/lib/api";

export type UserRole = "teacher" | "student";

export interface AuthSession {
  username: string;
  role: UserRole;
  loggedInAt: number;
}

export interface AuthProfile {
  id?: number;
  real_name?: string;
  [key: string]: unknown;
}

interface LoginResult {
  success: boolean;
  error?: string;
}

interface AuthContextType {
  session: AuthSession | null;
  profile: AuthProfile | null;
  isAuthenticated: boolean;
  isReady: boolean;
  login: (username: string, password: string) => Promise<LoginResult>;
  logout: () => void;
  refreshSession: () => void;
}

const AUTH_USER_KEY = "auth_user";
const AUTH_PROFILE_KEY = "auth_profile";

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

function readProfileFromStorage(): AuthProfile | null {
  if (typeof window === "undefined") return null;

  try {
    const rawProfile = localStorage.getItem(AUTH_PROFILE_KEY);
    return rawProfile ? JSON.parse(rawProfile) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [profile, setProfile] = useState<AuthProfile | null>(null);
  const [isReady, setIsReady] = useState(false);

  const refreshSession = () => {
    const nextSession = readSessionFromStorage();
    setSession(nextSession);
    setProfile(readProfileFromStorage());
  };

  React.useEffect(() => {
    refreshSession();
    setIsReady(true);
  }, []);

  const login = async (username: string, password: string): Promise<LoginResult> => {
    try {
      const res = await fetch(apiUrl("/api/v1/auth/login"), {
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
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));
        localStorage.setItem(AUTH_PROFILE_KEY, JSON.stringify(data.profile || {}));
      }

      setProfile(data.profile || null);
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
    setProfile(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem(AUTH_USER_KEY);
      localStorage.removeItem(AUTH_PROFILE_KEY);
    }
  };

  const value = useMemo<AuthContextType>(
    () => ({
      session,
      profile,
      isAuthenticated: !!session,
      isReady,
      login,
      logout,
      refreshSession,
    }),
    [isReady, profile, session],
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
