"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import Sidebar from "@/components/Sidebar";

interface AppShellProps {
  children: React.ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isReady } = useAuth();

  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (!isReady) return;

    if (!isAuthenticated && !isLoginPage) {
      router.replace("/login");
      return;
    }

    if (isAuthenticated && isLoginPage) {
      router.replace("/question");
    }
  }, [isAuthenticated, isLoginPage, isReady, router]);

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-sm text-slate-500 dark:text-slate-300">正在加载系统...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    if (!isLoginPage) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
          <div className="text-sm text-slate-500 dark:text-slate-300">正在跳转到登录页...</div>
        </div>
      );
    }
    return <>{children}</>;
  }

  return (
    <div className="ui-shell min-h-screen overflow-hidden transition-colors duration-200">
      <Sidebar />
      <main className="mx-auto w-full max-w-[1800px] flex-1 px-3 pb-4 pt-3 md:px-6 md:pb-6 md:pt-4">
        {children}
      </main>
    </div>
  );
}


