"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { KeyRound, LogIn, ShieldCheck, UserRound } from "lucide-react";

import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const result = login(username, password);
    if (!result.success) {
      setError(result.error || "登录失败");
      return;
    }

    router.replace("/question");
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[radial-gradient(circle_at_20%_20%,#dbeafe_0%,transparent_45%),radial-gradient(circle_at_80%_10%,#ccfbf1_0%,transparent_45%),linear-gradient(135deg,#f8fafc,#eef2ff)] px-4 py-8">
      <div className="pointer-events-none absolute -left-24 top-20 h-60 w-60 rounded-full bg-sky-200/35 blur-3xl" />
      <div className="pointer-events-none absolute -right-16 bottom-8 h-72 w-72 rounded-full bg-teal-200/35 blur-3xl" />

      <div className="mx-auto grid min-h-[88vh] w-full max-w-6xl items-center gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-3xl border border-white/70 bg-white/70 p-8 shadow-[0_20px_50px_rgba(15,23,42,0.12)] backdrop-blur-xl">
          <div className="inline-flex items-center gap-2 rounded-full bg-indigo-50 px-3 py-1 text-sm text-indigo-700">
            <ShieldCheck className="h-4 w-4" /> 教师/学生双端入口
          </div>
          <h1 className="mt-4 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">欢迎使用智能教学平台</h1>
          <p className="mt-3 max-w-xl text-slate-600">
            本系统提供作业发布、作业提交、后续评审与错题沉淀能力。当前为演示登录模式，使用固定账号即可体验教师端与学生端。
          </p>

          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-indigo-100 bg-indigo-50/70 p-4">
              <p className="text-sm font-semibold text-indigo-700">教师端账号</p>
              <p className="mt-2 font-mono text-sm text-indigo-900">teacher / teacher123</p>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4">
              <p className="text-sm font-semibold text-emerald-700">学生端账号</p>
              <p className="mt-2 font-mono text-sm text-emerald-900">student / student123</p>
            </div>
          </div>
        </section>

        <section className="rounded-3xl border border-white/80 bg-white/88 p-6 shadow-[0_16px_40px_rgba(15,23,42,0.14)] backdrop-blur-xl">
          <h2 className="text-2xl font-bold text-slate-900">登录</h2>
          <p className="mt-1 text-sm text-slate-500">请输入账号和密码进入系统</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <label className="block">
              <span className="text-sm text-slate-700">用户名</span>
              <div className="mt-1 flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
                <UserRound className="h-4 w-4 text-slate-400" />
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-transparent text-slate-800 outline-none"
                  placeholder="teacher 或 student"
                />
              </div>
            </label>

            <label className="block">
              <span className="text-sm text-slate-700">密码</span>
              <div className="mt-1 flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
                <KeyRound className="h-4 w-4 text-slate-400" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-transparent text-slate-800 outline-none"
                  placeholder="请输入密码"
                />
              </div>
            </label>

            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
            )}

            <button
              type="submit"
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 font-medium text-white transition hover:bg-indigo-700"
            >
              <LogIn className="h-4 w-4" /> 进入系统
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
