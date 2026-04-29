"use client";

import Link from "next/link";
import {
  BarChart3,
  Book,
  BookOpen,
  CircleOff,
  ClipboardList,
  GraduationCap,
  History,
  MessageCircle,
  PenTool,
  Settings,
  User,
} from "lucide-react";

import { useAuth } from "@/context/AuthContext";

function MingkeIcon() {
  return (
    <div
      className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-500 via-indigo-500 to-emerald-500 shadow-lg shadow-indigo-200"
      aria-hidden="true"
    >
      <svg viewBox="0 0 48 48" className="h-8 w-8" fill="none">
        <path
          d="M12 14.5C12 12.6 13.6 11 15.5 11H24V34H15.5C13.6 34 12 32.4 12 30.5V14.5Z"
          fill="white"
          fillOpacity="0.92"
        />
        <path
          d="M24 11H32.5C34.4 11 36 12.6 36 14.5V30.5C36 32.4 34.4 34 32.5 34H24V11Z"
          fill="white"
          fillOpacity="0.72"
        />
        <path d="M16.5 17H21M27 17H31.5M16.5 22H21M27 22H31.5" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" />
        <path d="M24 34L18 38H30L24 34Z" fill="#FACC15" />
      </svg>
    </div>
  );
}

const moduleCards = [
  {
    title: "智能问答",
    href: "/chat",
    icon: MessageCircle,
    tone: "bg-sky-50 text-sky-700 border-sky-100",
  },
  {
    title: "课程中心",
    href: "/knowledge",
    icon: BookOpen,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-100",
  },
  {
    title: "题目生成",
    href: "/question",
    icon: PenTool,
    tone: "bg-indigo-50 text-indigo-700 border-indigo-100",
  },
  {
    title: "作业批改",
    href: "/assignment-review",
    icon: ClipboardList,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-100",
  },
  {
    title: "错题本",
    href: "/wrongbook",
    icon: CircleOff,
    tone: "bg-rose-50 text-rose-700 border-rose-100",
  },
  {
    title: "学习笔记",
    href: "/notebook",
    icon: Book,
    tone: "bg-amber-50 text-amber-700 border-amber-100",
  },
  {
    title: "历史记录",
    href: "/history",
    icon: History,
    tone: "bg-slate-50 text-slate-700 border-slate-200",
  },
];

export default function HomePage() {
  const { session } = useAuth();
  const roleHref = session?.role === "teacher" ? "/teacher" : "/student";
  const roleTitle = session?.role === "teacher" ? "教师端" : "学生端";
  const RoleIcon = session?.role === "teacher" ? GraduationCap : User;
  const cards = [
    {
      title: roleTitle,
      href: roleHref,
      icon: RoleIcon,
      tone:
        session?.role === "teacher"
          ? "bg-violet-50 text-violet-700 border-violet-100"
          : "bg-cyan-50 text-cyan-700 border-cyan-100",
    },
    ...moduleCards,
    {
      title: "知识点掌握",
      href: "/mastery",
      icon: BarChart3,
      tone: "bg-lime-50 text-lime-700 border-lime-100",
    },
  ];

  return (
    <div className="min-h-[calc(100vh-6rem)] bg-slate-50 px-4 py-6 text-slate-900">
      <section className="mx-auto flex max-w-7xl flex-col gap-8">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
          <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
            <div>
              <div className="flex items-center gap-3">
                <MingkeIcon />
                <p className="text-base font-semibold text-indigo-700">明课学习平台</p>
              </div>
              <h1 className="mt-2 text-3xl font-semibold tracking-normal text-slate-950 md:text-4xl">
                面向课程教学的智能学习平台
              </h1>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="group flex min-h-32 flex-col justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
            >
              <div
                className={`inline-flex h-11 w-11 items-center justify-center rounded-lg border ${item.tone}`}
              >
                <item.icon className="h-5 w-5" />
              </div>
              <div>
                <h2 className="mt-4 text-lg font-semibold text-slate-950">{item.title}</h2>
              </div>
              <span className="mt-4 inline-flex text-sm font-medium text-indigo-600 group-hover:text-indigo-700">
                进入模块
              </span>
            </Link>
          ))}
        </div>

        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-950">平台设置</h2>
            </div>
            <Link
              href="/settings"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            >
              <Settings className="h-4 w-4" />
              打开设置
            </Link>
          </div>
        </section>
      </section>
    </div>
  );
}
