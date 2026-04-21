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

  const publicRoutes = ["/login", "/register/student", "/register/teacher"];
  const authPages = ["/login", "/register/student", "/register/teacher"];

  const isLoginPage = pathname === "/login";
  const isPublicPage = publicRoutes.includes(pathname);
  const isAuthPage = authPages.includes(pathname);

  useEffect(() => {
    if (!isReady) return;
  
    if (!isAuthenticated && !isPublicPage) {
      router.replace("/login");
      return;
    }
  
    if (isAuthenticated && isAuthPage) {
      const rawUser = localStorage.getItem("auth_user");
      const user = rawUser ? JSON.parse(rawUser) : null;
  
      if (user?.role === "teacher") {
        router.replace("/teacher");
      } else if (user?.role === "student") {
        router.replace("/student");
      } else {
        router.replace("/question");
      }
    }
  }, [isAuthenticated, isPublicPage, isAuthPage, isReady, router]);

  if (!isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="text-sm text-slate-500 dark:text-slate-300">正在加载系统...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    if (!isPublicPage) {
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


