"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BookX, RefreshCw } from "lucide-react";

import { apiUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface WrongbookItem {
  id: string;
  assignment_id: string;
  assignment_title: string;
  feedback: string;
  error_type?: string;
  knowledge_point?: string;
  suggestion?: string;
  created_at: number;
  practice_history?: Array<{
    id: string;
    strategy: string;
    strategy_label: string;
    difficulty: string;
    title: string;
    prompt: string;
    checklist?: string[];
    expected_answer_points?: string[];
    created_at: number;
  }>;
}

export default function WrongbookPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<WrongbookItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string>("");

  const loadItems = async () => {
    if (!session?.username) return;

    setLoading(true);
    try {
      const res = await fetch(
        apiUrl(`/api/v1/assignment-review/student/wrongbook?student_username=${encodeURIComponent(session.username)}`),
      );
      const data = await res.json();
      setItems(data.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  const generatePractice = async (
    itemId: string,
    strategy: "same_point" | "harder" | "easier" | "variant",
  ) => {
    if (!session?.username) return;
    setActionLoading(`${itemId}-${strategy}`);
    try {
      const res = await fetch(apiUrl(`/api/v1/assignment-review/student/wrongbook/${itemId}/practice`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_username: session.username,
          strategy,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "生成练习失败");
      await loadItems();
    } catch {
      // ignore and keep current list
    } finally {
      setActionLoading("");
    }
  };

  useEffect(() => {
    loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.username]);

  return (
    <div className="h-[calc(100vh-7rem)] rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/85 shadow-[0_12px_40px_rgba(15,23,42,0.16)] p-6 overflow-auto">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookX className="h-7 w-7 text-rose-500" />
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">错题本</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">用于汇总作业评审后的错题与反馈。</p>
          </div>
        </div>

        <button
          onClick={loadItems}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-slate-500">
          暂无错题记录。作业评审链路接入后，错题会自动沉淀到这里。
          <div className="mt-4">
            <Link href="/question" className="text-indigo-600 hover:underline">
              返回作业评审
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="font-semibold text-slate-800">{item.assignment_title}</div>
              <div className="mt-2 text-sm text-slate-600">{item.feedback}</div>
              {(item.error_type || item.knowledge_point || item.suggestion) && (
                <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600 space-y-1">
                  {item.error_type && <div>错误类型：{item.error_type}</div>}
                  {item.knowledge_point && <div>知识点：{item.knowledge_point}</div>}
                  {item.suggestion && <div>建议：{item.suggestion}</div>}
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={() => generatePractice(item.id, "same_point")}
                  className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  {actionLoading === `${item.id}-same_point` ? "生成中..." : "同知识点再练"}
                </button>
                <button
                  onClick={() => generatePractice(item.id, "harder")}
                  className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs text-rose-700 hover:bg-rose-100"
                >
                  {actionLoading === `${item.id}-harder` ? "生成中..." : "提升难度"}
                </button>
                <button
                  onClick={() => generatePractice(item.id, "easier")}
                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100"
                >
                  {actionLoading === `${item.id}-easier` ? "生成中..." : "降低难度"}
                </button>
                <button
                  onClick={() => generatePractice(item.id, "variant")}
                  className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs text-amber-700 hover:bg-amber-100"
                >
                  {actionLoading === `${item.id}-variant` ? "生成中..." : "变式训练"}
                </button>
              </div>

              {item.practice_history && item.practice_history.length > 0 && (
                <div className="mt-3 space-y-2">
                  {item.practice_history
                    .slice()
                    .reverse()
                    .slice(0, 2)
                    .map((practice) => (
                      <div key={practice.id} className="rounded-lg border border-indigo-100 bg-indigo-50/60 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-indigo-900">{practice.title}</p>
                          <span className="rounded-full bg-white px-2 py-0.5 text-xs text-indigo-700">
                            {practice.difficulty}
                          </span>
                        </div>
                        <p className="mt-1 whitespace-pre-line text-xs text-indigo-800">{practice.prompt}</p>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
