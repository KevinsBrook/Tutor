"use client";

import Link from "next/link";
import {
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

const moduleCards = [
  {
    title: "智能问答",
    description: "围绕课程资料、练习记录和学习问题进行对话式学习。",
    href: "/chat",
    icon: MessageCircle,
    tone: "bg-sky-50 text-sky-700 border-sky-100",
  },
  {
    title: "课程中心",
    description: "管理课程、章节、教学资料、学生笔记和知识点。",
    href: "/knowledge",
    icon: BookOpen,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-100",
  },
  {
    title: "题目生成",
    description: "按知识点、题型、难度和资料来源自定义生成练习题。",
    href: "/question",
    icon: PenTool,
    tone: "bg-indigo-50 text-indigo-700 border-indigo-100",
  },
  {
    title: "作业批改",
    description: "教师发布作业，系统生成评分标准并对学生答案逐点批改。",
    href: "/assignment-review",
    icon: ClipboardList,
    tone: "bg-emerald-50 text-emerald-700 border-emerald-100",
  },
  {
    title: "错题本",
    description: "沉淀练习和作业中的薄弱点，支持后续复盘与再练。",
    href: "/wrongbook",
    icon: CircleOff,
    tone: "bg-rose-50 text-rose-700 border-rose-100",
  },
  {
    title: "学习笔记",
    description: "整理个人笔记和学习记录。",
    href: "/notebook",
    icon: Book,
    tone: "bg-amber-50 text-amber-700 border-amber-100",
  },
  {
    title: "历史记录",
    description: "查看历史学习、问答和生成记录。",
    href: "/history",
    icon: History,
    tone: "bg-slate-50 text-slate-700 border-slate-200",
  },
];

export default function HomePage() {
  const { session } = useAuth();
  const roleHref = session?.role === "teacher" ? "/teacher" : "/student";
  const roleLabel = session?.role === "teacher" ? "进入教师端" : "进入学生端";
  const RoleIcon = session?.role === "teacher" ? GraduationCap : User;

  return (
    <div className="min-h-[calc(100vh-6rem)] bg-slate-50 px-4 py-6 text-slate-900">
      <section className="mx-auto flex max-w-7xl flex-col gap-8">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
          <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-medium text-indigo-600">DeepTutor Platform</p>
              <h1 className="mt-2 text-3xl font-semibold tracking-normal text-slate-950 md:text-4xl">
                面向课程教学的智能学习平台
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600 md:text-base">
                教师可以建设课程、维护知识点并批改作业；学生可以围绕课程资料练习、提交作业和整理错题。
              </p>
            </div>
            <Link
              href={roleHref}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              <RoleIcon className="h-4 w-4" />
              {roleLabel}
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {moduleCards.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
            >
              <div
                className={`inline-flex h-11 w-11 items-center justify-center rounded-lg border ${item.tone}`}
              >
                <item.icon className="h-5 w-5" />
              </div>
              <h2 className="mt-4 text-lg font-semibold text-slate-950">{item.title}</h2>
              <p className="mt-2 min-h-[3.5rem] text-sm leading-6 text-slate-600">
                {item.description}
              </p>
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
              <p className="mt-1 text-sm text-slate-600">
                调整接口地址、界面偏好和导航顺序。
              </p>
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
