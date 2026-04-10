"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
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
  Github,
  Globe,
  Menu,
  X,
  LucideIcon,
} from "lucide-react";
import { useGlobal } from "@/context/GlobalContext";

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
  const { sidebarDescription, sidebarNavOrder } = useGlobal();
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

    return {
      start: buildNavItems(sidebarNavOrder.start),
      learnResearch: buildNavItems(sidebarNavOrder.learnResearch),
    };
  }, [sidebarNavOrder, t]);

  return (
    <header className="sticky top-0 z-40 border-b border-white/40 bg-[color:var(--ui-panel)]/95 backdrop-blur-xl">
      <div className="mx-auto flex h-16 w-full max-w-[1800px] items-center justify-between gap-3 px-4 md:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-sm ring-1 ring-slate-200/70">
            <Image
              src="/logo.png"
              alt={t("DeepTutor Logo")}
              width={30}
              height={30}
              className="object-contain"
              priority
            />
          </div>
          <div className="hidden sm:block">
            <div className="text-sm font-semibold tracking-wide text-slate-900">
              DeepTutor
            </div>
            <div className="text-xs text-slate-500">{sidebarDescription}</div>
          </div>
        </div>

        <nav className="hidden flex-1 items-center justify-center gap-2 overflow-x-auto px-2 lg:flex">
          {navGroups.start.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              isActive={pathname === item.href}
            />
          ))}
          <div className="mx-1 h-6 w-px bg-slate-200" />
          {navGroups.learnResearch.map((item) => (
            <NavLink
              key={item.href}
              item={item}
              isActive={pathname === item.href}
            />
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          <a
            href="https://hkuds.github.io/DeepTutor/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl border border-transparent bg-white/65 px-3 py-2 text-sm text-slate-700 transition hover:border-slate-200 hover:bg-white"
          >
            <Globe className="h-4 w-4" />
            <span>{t("Website")}</span>
          </a>
          <a
            href="https://github.com/HKUDS/DeepTutor"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl border border-transparent bg-white/65 px-3 py-2 text-sm text-slate-700 transition hover:border-slate-200 hover:bg-white"
          >
            <Github className="h-4 w-4" />
            <span>GitHub</span>
          </a>
          <Link
            href="/settings"
            className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-sm transition ${
              pathname === "/settings"
                ? "border-[color:var(--ui-accent-2)] bg-[color:var(--ui-accent-soft)] text-[color:var(--ui-accent-2)]"
                : "border-transparent bg-white/65 text-slate-700 hover:border-slate-200 hover:bg-white"
            }`}
          >
            <Settings className="h-4 w-4" />
            <span>{t("Settings")}</span>
          </Link>
        </div>

        <button
          onClick={() => setMobileOpen((v) => !v)}
          className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white p-2 text-slate-700 lg:hidden"
          aria-label={mobileOpen ? t("Close") : t("Menu")}
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
              item={{ name: t("Settings"), href: "/settings", icon: Settings }}
              compact
              isActive={pathname === "/settings"}
              onClick={() => setMobileOpen(false)}
            />
          </div>
        </div>
      )}
    </header>
  );
}
