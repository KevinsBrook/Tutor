"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Book,
  BookOpen,
  Calculator,
  CircleOff,
  ClipboardList,
  Edit3,
  GraduationCap,
  History,
  Home,
  Lightbulb,
  LucideIcon,
  Menu,
  MessageCircle,
  Microscope,
  PenTool,
  Settings,
  User,
  X,
} from "lucide-react";

import { useAuth } from "@/context/AuthContext";
import { useGlobal } from "@/context/GlobalContext";

interface NavItem {
  name: string;
  href: string;
  icon: LucideIcon;
}

const ALL_NAV_ITEMS: Record<string, { icon: LucideIcon; name: string }> = {
  "/": { icon: Home, name: "首页" },
  "/chat": { icon: MessageCircle, name: "智能问答" },
  "/student": { icon: User, name: "学生端" },
  "/teacher": { icon: GraduationCap, name: "教师端" },
  "/history": { icon: History, name: "历史记录" },
  "/knowledge": { icon: BookOpen, name: "课程中心" },
  "/notebook": { icon: Book, name: "学习笔记" },
  "/question": { icon: PenTool, name: "题目生成" },
  "/assignment-review": { icon: ClipboardList, name: "作业批改" },
  "/mastery": { icon: BarChart3, name: "知识点掌握" },
  "/solver": { icon: Calculator, name: "智能求解" },
  "/guide": { icon: GraduationCap, name: "引导学习" },
  "/ideagen": { icon: Lightbulb, name: "创意生成" },
  "/research": { icon: Microscope, name: "深度研究" },
  "/co_writer": { icon: Edit3, name: "协同写作" },
  "/wrongbook": { icon: CircleOff, name: "错题本" },
};

const HIDDEN_NAV_HREFS = new Set([
  "/solver",
  "/guide",
  "/ideagen",
  "/research",
  "/co_writer",
]);

function NavLink({
  item,
  isActive,
  compact = false,
  onClick,
}: {
  item: NavItem;
  isActive: boolean;
  compact?: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={`group inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-all ${
        isActive
          ? "border-[color:var(--ui-accent-2)] bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent-2)] shadow-sm"
          : "border-transparent bg-white/65 text-slate-700 hover:border-slate-200 hover:bg-white"
      } ${compact ? "w-full justify-start" : "justify-center"}`}
    >
      <item.icon className="h-4 w-4" />
      <span>{item.name}</span>
    </Link>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarNavOrder } = useGlobal();
  const { session, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navGroups = useMemo(() => {
    const buildNavItems = (hrefs: string[]): NavItem[] => {
      return hrefs
        .filter((href) => ALL_NAV_ITEMS[href] && !HIDDEN_NAV_HREFS.has(href))
        .map((href) => ({
          name: ALL_NAV_ITEMS[href].name,
          href,
          icon: ALL_NAV_ITEMS[href].icon,
        }));
    };

    const roleItems: NavItem[] =
      session?.role === "teacher"
        ? [{ name: "教师端", href: "/teacher", icon: ALL_NAV_ITEMS["/teacher"].icon }]
        : session?.role === "student"
          ? [{ name: "学生端", href: "/student", icon: ALL_NAV_ITEMS["/student"].icon }]
          : [];

    const start = buildNavItems(
      sidebarNavOrder.start.filter((href) => href !== "/student" && href !== "/teacher"),
    );

    if (!start.find((item) => item.href === "/chat")) {
      const homeIndex = start.findIndex((item) => item.href === "/");
      start.splice(homeIndex >= 0 ? homeIndex + 1 : 0, 0, {
        name: "智能问答",
        href: "/chat",
        icon: ALL_NAV_ITEMS["/chat"].icon,
      });
    }

    const learnResearch = buildNavItems(
      sidebarNavOrder.learnResearch.filter((href) => href !== "/student" && href !== "/teacher"),
    );

    if (!learnResearch.find((item) => item.href === "/assignment-review")) {
      const questionIndex = learnResearch.findIndex((item) => item.href === "/question");
      learnResearch.splice(questionIndex >= 0 ? questionIndex + 1 : 0, 0, {
        name: ALL_NAV_ITEMS["/assignment-review"].name,
        href: "/assignment-review",
        icon: ALL_NAV_ITEMS["/assignment-review"].icon,
      });
    }

    if (!learnResearch.find((item) => item.href === "/mastery")) {
      const assignmentIndex = learnResearch.findIndex((item) => item.href === "/assignment-review");
      learnResearch.splice(assignmentIndex >= 0 ? assignmentIndex + 1 : 0, 0, {
        name: ALL_NAV_ITEMS["/mastery"].name,
        href: "/mastery",
        icon: ALL_NAV_ITEMS["/mastery"].icon,
      });
    }

    if (session?.role === "student" && !learnResearch.find((item) => item.href === "/wrongbook")) {
      learnResearch.unshift({
        name: "错题本",
        href: "/wrongbook",
        icon: ALL_NAV_ITEMS["/wrongbook"].icon,
      });
    }

    return { roleItems, start, learnResearch };
  }, [session?.role, sidebarNavOrder]);

  const userRoleLabel = session?.role === "teacher" ? "教师" : "学生";

  return (
    <header className="sticky top-0 z-40 border-b border-white/40 bg-[color:var(--ui-panel)]/95 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-[1800px] items-center justify-between gap-3 px-4 md:px-6">
        <div className="w-4 shrink-0" />

        <nav className="hidden flex-1 items-center justify-center gap-2 overflow-x-auto px-2 lg:flex">
          {navGroups.roleItems.map((item) => (
            <NavLink key={item.href} item={item} isActive={pathname === item.href} />
          ))}

          {navGroups.roleItems.length > 0 && <div className="mx-1 h-6 w-px bg-slate-200" />}

          {navGroups.start.map((item) => (
            <NavLink key={item.href} item={item} isActive={pathname === item.href} />
          ))}

          <div className="mx-1 h-6 w-px bg-slate-200" />

          {navGroups.learnResearch.map((item) => (
            <NavLink key={item.href} item={item} isActive={pathname === item.href} />
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          <div className="rounded-xl border border-slate-200 bg-white/65 px-3 py-2 text-xs text-slate-700">
            {userRoleLabel}: {session?.username}
          </div>
          <Link
            href="/settings"
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm transition ${
              pathname === "/settings"
                ? "border-[color:var(--ui-accent-2)] bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent-2)]"
                : "border-transparent bg-white/65 text-slate-700 hover:border-slate-200 hover:bg-white"
            }`}
          >
            <Settings className="h-4 w-4" />
            <span>设置</span>
          </Link>
          <button
            onClick={logout}
            className="inline-flex items-center gap-1.5 rounded-xl border border-transparent bg-white/65 px-3 py-2 text-sm text-slate-700 transition hover:border-slate-200 hover:bg-white"
          >
            <X className="h-4 w-4" />
            <span>退出登录</span>
          </button>
        </div>

        <button
          onClick={() => setMobileOpen((value) => !value)}
          className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white p-2 text-slate-700 lg:hidden"
          aria-label={mobileOpen ? "关闭菜单" : "打开菜单"}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-white/60 bg-white/95 p-3 shadow-lg backdrop-blur-xl lg:hidden">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {[...navGroups.roleItems, ...navGroups.start, ...navGroups.learnResearch].map((item) => (
              <NavLink
                key={item.href}
                item={item}
                compact
                isActive={pathname === item.href}
                onClick={() => setMobileOpen(false)}
              />
            ))}
            <NavLink
              item={{ name: "设置", href: "/settings", icon: Settings }}
              compact
              isActive={pathname === "/settings"}
              onClick={() => setMobileOpen(false)}
            />
            <button
              onClick={() => {
                logout();
                setMobileOpen(false);
              }}
              className="inline-flex w-full items-center justify-start gap-2 rounded-xl border border-transparent bg-white/65 px-3 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-200 hover:bg-white"
            >
              <X className="h-4 w-4" />
              <span>退出登录</span>
            </button>
          </div>
        </div>
      )}
    </header>
  );
}
