"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslation } from "react-i18next";
import {
  Home,
  History,
  BookOpen,
  PenTool,
  Calculator,
  Microscope,
  Edit3,
  Settings,
  Book,
  GraduationCap,
  Lightbulb,
  Menu,
  X,
  CircleOff,
  LucideIcon,
} from "lucide-react";
import { useGlobal } from "@/context/GlobalContext";
import { useAuth } from "@/context/AuthContext";

interface NavItem {
  name: string;
  href: string;
  icon: LucideIcon;
}

const ALL_NAV_ITEMS: Record<string, { icon: LucideIcon; nameKey: string }> = {
  "/": { icon: Home, nameKey: "Home" },
  "/history": { icon: History, nameKey: "History" },
  "/knowledge": { icon: BookOpen, nameKey: "Knowledge Bases" },
  "/notebook": { icon: Book, nameKey: "Notebooks" },
  "/question": { icon: PenTool, nameKey: "Question Generator" },
  "/solver": { icon: Calculator, nameKey: "Smart Solver" },
  "/guide": { icon: GraduationCap, nameKey: "Guided Learning" },
  "/ideagen": { icon: Lightbulb, nameKey: "IdeaGen" },
  "/research": { icon: Microscope, nameKey: "Deep Research" },
  "/co_writer": { icon: Edit3, nameKey: "Co-Writer" },
  "/wrongbook": { icon: CircleOff, nameKey: "错题本" },
};

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
  const { t } = useTranslation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const navGroups = useMemo(() => {
    const buildNavItems = (hrefs: string[]): NavItem[] => {
      return hrefs
        .filter((href) => ALL_NAV_ITEMS[href])
        .map((href) => ({
          name: t(ALL_NAV_ITEMS[href].nameKey),
          href,
          icon: ALL_NAV_ITEMS[href].icon,
        }));
    };

    const start = buildNavItems(sidebarNavOrder.start);
    const learnResearch = buildNavItems(sidebarNavOrder.learnResearch);

    if (session?.role === "student" && !learnResearch.find((item) => item.href === "/wrongbook")) {
      learnResearch.unshift({
        name: "错题本",
        href: "/wrongbook",
        icon: ALL_NAV_ITEMS["/wrongbook"].icon,
      });
    }

    return { start, learnResearch };
  }, [session?.role, sidebarNavOrder, t]);

  return (
    <header className="sticky top-0 z-40 border-b border-white/40 bg-[color:var(--ui-panel)]/95 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-[1800px] items-center justify-between gap-3 px-4 md:px-6">
        <div className="w-4 shrink-0" />

        <nav className="hidden flex-1 items-center justify-center gap-2 overflow-x-auto px-2 lg:flex">
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
            {session?.role === "teacher" ? "教师" : "学生"}：{session?.username}
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
          onClick={() => setMobileOpen((v) => !v)}
          className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white p-2 text-slate-700 lg:hidden"
          aria-label={mobileOpen ? "关闭" : "菜单"}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {mobileOpen && (
        <div className="border-t border-white/60 bg-white/95 p-3 shadow-lg backdrop-blur-xl lg:hidden">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {[...navGroups.start, ...navGroups.learnResearch].map((item) => (
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
