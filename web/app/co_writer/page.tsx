"use client";

import CoWriterEditor from "@/components/CoWriterEditor";
import { Edit3, Sparkles, Wand2, FilePenLine } from "lucide-react";
import { useTranslation } from "react-i18next";

export default function CoWriterPage() {
  const { t } = useTranslation();
  return (
    <div className="animate-fade-in grid h-[calc(100vh-7rem)] min-h-0 grid-rows-[auto_1fr] gap-4">
      <div className="grid gap-3 rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/88 p-4 shadow-[0_12px_40px_rgba(15,23,42,0.18)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/82 md:grid-cols-[1.6fr_1fr]">
        <div className="rounded-2xl border border-fuchsia-200/70 bg-gradient-to-r from-fuchsia-100/80 via-rose-50 to-indigo-100/80 px-5 py-4 dark:border-fuchsia-900/60 dark:from-fuchsia-950/50 dark:via-slate-900 dark:to-indigo-950/50">
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            <Edit3 className="h-6 w-6 text-fuchsia-600 dark:text-fuchsia-300" />
            {t("Co-Writer")}
          </h1>
          <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">
            {t("Intelligent markdown editor with AI-powered writing assistance.")}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
            <Sparkles className="mb-1 h-4 w-4 text-fuchsia-500" />
            {t("Draft polish")}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
            <Wand2 className="mb-1 h-4 w-4 text-indigo-500" />
            {t("Tone adjust")}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300">
            <FilePenLine className="mb-1 h-4 w-4 text-emerald-500" />
            {t("Outline support")}
          </div>
        </div>
      </div>

      <div className="min-h-0 rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/90 p-2 shadow-[0_12px_40px_rgba(15,23,42,0.18)] dark:border-slate-700 dark:bg-slate-900/85">
        <CoWriterEditor />
      </div>
    </div>
  );
}
