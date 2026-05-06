"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BookX, RefreshCw } from "lucide-react";

import { apiUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

interface GeneratedQuestion {
  question_type?: string;
  question?: string;
  options?: Record<string, string>;
  correct_answer?: string;
  explanation?: string;
}

interface WrongbookPractice {
  id: string;
  strategy: string;
  strategy_label: string;
  difficulty: string;
  title: string;
  prompt: string;
  question?: GeneratedQuestion;
  generation_error?: string;
  checklist?: string[];
  expected_answer_points?: string[];
  created_at: number;
}

interface WrongbookItem {
  id: string;
  assignment_id: string;
  assignment_title: string;
  feedback: string;
  knowledge_point?: string;
  knowledge_point_id?: number | null;
  question_text?: string;
  student_answer?: string;
  correct_answer?: string;
  explanation?: string;
  question_type?: string;
  score?: number | null;
  max_score?: number | null;
  created_at: number;
  practice_history?: WrongbookPractice[];
}

interface ActivePractice {
  item: WrongbookItem;
  practice: WrongbookPractice;
}

interface PracticeResult {
  status: "correct" | "partial" | "incorrect" | "review";
  score: number | null;
  maxScore: number | null;
  reason: string;
}

function formatScore(item: WrongbookItem) {
  if (item.score === null || item.score === undefined) return "";
  if (item.max_score === null || item.max_score === undefined) return String(item.score);
  return `${item.score} / ${item.max_score}`;
}

function normalizeAnswer(text: string) {
  return text.trim().replace(/\s+/g, "").toUpperCase();
}

function splitAnswer(text: string) {
  return text
    .split(/[,\n;/|、，]+/)
    .map((x) => normalizeAnswer(x))
    .filter(Boolean)
    .sort();
}

function evaluatePracticeAnswer(question: GeneratedQuestion, answer: string): PracticeResult {
  const qType = String(question.question_type || "written").toLowerCase();
  const correct = String(question.correct_answer || "");
  if (["choice", "true_false"].includes(qType)) {
    const ok = normalizeAnswer(answer) === normalizeAnswer(correct);
    return {
      status: ok ? "correct" : "incorrect",
      score: ok ? 1 : 0,
      maxScore: 1,
      reason: ok ? "回答正确。" : `回答错误，参考答案为：${correct || "暂无"}`,
    };
  }
  if (qType === "multiple_choice") {
    const actual = splitAnswer(answer);
    const expected = splitAnswer(correct);
    const same = actual.length === expected.length && actual.every((x, idx) => x === expected[idx]);
    const hit = actual.filter((x) => expected.includes(x)).length;
    const ratio = expected.length > 0 ? hit / expected.length : 0;
    return {
      status: same ? "correct" : ratio > 0 ? "partial" : "incorrect",
      score: same ? 1 : Number(ratio.toFixed(2)),
      maxScore: 1,
      reason: same ? "多选答案完全正确。" : `参考答案为：${expected.join(", ") || "暂无"}`,
    };
  }
  if (qType === "fill_blank") {
    const actual = splitAnswer(answer);
    const expected = splitAnswer(correct);
    const hit = expected.filter((x, idx) => actual[idx] === x).length;
    const ratio = expected.length > 0 ? hit / expected.length : 0;
    return {
      status: ratio >= 1 ? "correct" : ratio > 0 ? "partial" : "incorrect",
      score: Number(ratio.toFixed(2)),
      maxScore: 1,
      reason: ratio >= 1 ? "填空正确。" : `参考答案为：${correct || "暂无"}`,
    };
  }
  return {
    status: "review",
    score: null,
    maxScore: null,
    reason: "主观题已提交，请对照参考答案和解析自查。",
  };
}

export default function WrongbookPage() {
  const { session } = useAuth();
  const [items, setItems] = useState<WrongbookItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string>("");
  const [activePractice, setActivePractice] = useState<ActivePractice | null>(null);
  const [practiceAnswer, setPracticeAnswer] = useState("");
  const [practiceResult, setPracticeResult] = useState<PracticeResult | null>(null);
  const practicePanelRef = useRef<HTMLElement | null>(null);

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
      const sourceItem = items.find((item) => item.id === itemId);
      if (sourceItem && data.practice?.question?.question) {
        setActivePractice({ item: sourceItem, practice: data.practice });
        setPracticeAnswer("");
        setPracticeResult(null);
      }
      await loadItems();
    } catch {
      // Keep the existing list visible.
    } finally {
      setActionLoading("");
    }
  };

  const startPractice = (item: WrongbookItem, practice: WrongbookPractice) => {
    if (!practice.question?.question) return;
    setActivePractice({ item, practice });
    setPracticeAnswer("");
    setPracticeResult(null);
  };

  const submitActivePractice = async () => {
    if (!activePractice?.practice.question || !session?.username) return;
    const result = evaluatePracticeAnswer(activePractice.practice.question, practiceAnswer);
    setPracticeResult(result);
    try {
      await fetch(apiUrl(`/api/v1/assignment-review/student/wrongbook/${activePractice.item.id}/practice-result`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_username: session.username,
          knowledge_point_id: activePractice.item.knowledge_point_id ?? null,
          source_id: activePractice.practice.id,
          score: result.score,
          max_score: result.maxScore,
          is_correct: result.status === "correct" ? true : result.status === "incorrect" ? false : null,
          difficulty: activePractice.practice.difficulty || "medium",
          answer_quality:
            result.status === "partial" ? "partial" : result.status === "review" ? "hinted" : undefined,
          used_hint: false,
          note: result.reason,
        }),
      });
    } catch {
      // The local result remains visible even if mastery sync fails.
    }
  };

  useEffect(() => {
    loadItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.username]);

  useEffect(() => {
    if (activePractice) {
      practicePanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [activePractice]);

  return (
    <div className="h-[calc(100vh-7rem)] overflow-auto rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/85 p-6 shadow-[0_12px_40px_rgba(15,23,42,0.16)]">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookX className="h-7 w-7 text-rose-500" />
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">错题本</h1>
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

      {activePractice?.practice.question && (
        (() => {
          const question = activePractice.practice.question;
          const qType = String(question.question_type || "written").toLowerCase();
          const optionEntries = Object.entries(question.options || {});
          const selectedMulti = splitAnswer(practiceAnswer);
          return (
            <section ref={practicePanelRef} className="mb-5 rounded-2xl border border-indigo-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">{activePractice.practice.title}</h2>
                  <p className="mt-1 text-xs text-slate-500">
                    {activePractice.practice.strategy_label} · {activePractice.practice.difficulty}
                  </p>
                </div>
                <button
                  onClick={() => setActivePractice(null)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                >
                  关闭练习
                </button>
              </div>

              <div className="mt-4 rounded-xl bg-slate-50 p-4">
                <p className="whitespace-pre-wrap text-sm font-medium text-slate-900">{question.question}</p>
                {optionEntries.length > 0 && (
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {optionEntries.map(([key, value]) => {
                      const checked =
                        qType === "multiple_choice"
                          ? selectedMulti.includes(normalizeAnswer(key))
                          : normalizeAnswer(practiceAnswer) === normalizeAnswer(key);
                      return (
                        <label
                          key={key}
                          className={`flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 text-sm ${
                            checked ? "border-indigo-300 bg-indigo-50" : "border-slate-200 bg-white"
                          }`}
                        >
                          <input
                            type={qType === "multiple_choice" ? "checkbox" : "radio"}
                            checked={checked}
                            onChange={(event) => {
                              if (qType === "multiple_choice") {
                                const next = new Set(selectedMulti);
                                if (event.target.checked) next.add(normalizeAnswer(key));
                                else next.delete(normalizeAnswer(key));
                                setPracticeAnswer(Array.from(next).sort().join(","));
                              } else {
                                setPracticeAnswer(key);
                              }
                              setPracticeResult(null);
                            }}
                            className="mt-1"
                            name={`wrongbook-practice-${activePractice.practice.id}`}
                          />
                          <span>
                            <span className="font-semibold">{key}.</span> {value}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}

                {optionEntries.length === 0 && (
                  <textarea
                    value={practiceAnswer}
                    onChange={(event) => {
                      setPracticeAnswer(event.target.value);
                      setPracticeResult(null);
                    }}
                    className="mt-3 h-28 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                    placeholder={qType === "fill_blank" ? "请输入答案，多个空用逗号分隔" : "请输入你的答案"}
                  />
                )}

                {qType === "fill_blank" && optionEntries.length > 0 && (
                  <input
                    value={practiceAnswer}
                    onChange={(event) => {
                      setPracticeAnswer(event.target.value);
                      setPracticeResult(null);
                    }}
                    className="mt-3 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                    placeholder="请输入答案，多个空用逗号分隔"
                  />
                )}

                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    onClick={submitActivePractice}
                    disabled={!practiceAnswer.trim()}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    提交答案
                  </button>
                  <button
                    onClick={() => {
                      setPracticeAnswer("");
                      setPracticeResult(null);
                    }}
                    className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  >
                    重新作答
                  </button>
                </div>
              </div>

              {practiceResult && (
                <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                  <p className="font-semibold">
                    {practiceResult.status === "correct"
                      ? "回答正确"
                      : practiceResult.status === "partial"
                        ? "部分正确"
                        : practiceResult.status === "incorrect"
                          ? "回答错误"
                          : "已提交"}
                    {practiceResult.score !== null && practiceResult.maxScore !== null
                      ? `（${practiceResult.score}/${practiceResult.maxScore}）`
                      : ""}
                  </p>
                  <p className="mt-1">{practiceResult.reason}</p>
                  <div className="mt-3 rounded-lg bg-white/80 p-3">
                    <p>
                      <span className="font-semibold">参考答案：</span>
                      {question.correct_answer || "暂无"}
                    </p>
                    {question.explanation && (
                      <p className="mt-2 whitespace-pre-wrap">
                        <span className="font-semibold">解析：</span>
                        {question.explanation}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </section>
          );
        })()
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-slate-500">
          暂无错题记录。
          <div className="mt-4">
            <Link href="/question" className="text-indigo-600 hover:underline">
              返回题目生成
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const scoreText = formatScore(item);
            return (
              <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{item.assignment_title}</div>
                    <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                      {item.knowledge_point && <span>知识点：{item.knowledge_point}</span>}
                      {item.question_type && <span>题型：{item.question_type}</span>}
                      {scoreText && <span>得分：{scoreText}</span>}
                    </div>
                  </div>
                </div>

                <div className="mt-3 grid gap-3 lg:grid-cols-3">
                  <div className="rounded-lg bg-slate-50 p-3">
                    <div className="text-xs font-medium text-slate-500">题目</div>
                    <div className="mt-1 whitespace-pre-wrap text-sm text-slate-800">
                      {item.question_text || item.feedback || "暂无题目内容"}
                    </div>
                  </div>
                  <div className="rounded-lg bg-rose-50 p-3">
                    <div className="text-xs font-medium text-rose-600">错误作答</div>
                    <div className="mt-1 whitespace-pre-wrap text-sm text-rose-900">
                      {item.student_answer || "暂无作答记录"}
                    </div>
                  </div>
                  <div className="rounded-lg bg-emerald-50 p-3">
                    <div className="text-xs font-medium text-emerald-700">参考答案</div>
                    <div className="mt-1 whitespace-pre-wrap text-sm text-emerald-900">
                      {item.correct_answer || "暂无参考答案"}
                    </div>
                  </div>
                </div>

                {item.feedback && (
                  <div className="mt-3 rounded-lg bg-indigo-50 p-3 text-sm text-indigo-900">
                    <span className="font-medium">评分原因：</span>
                    {item.feedback}
                  </div>
                )}

                {item.explanation && (
                  <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-800">
                    <div className="text-xs font-medium text-slate-500">解析</div>
                    <div className="mt-1 whitespace-pre-wrap">{item.explanation}</div>
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
                          {practice.question?.question ? (
                            <div className="mt-2 space-y-2 text-xs text-indigo-900">
                              <p className="whitespace-pre-wrap font-medium">{practice.question.question}</p>
                              {practice.question.options && (
                                <div className="grid gap-1 sm:grid-cols-2">
                                  {Object.entries(practice.question.options).map(([key, value]) => (
                                    <div key={key} className="rounded-md bg-white/80 px-2 py-1">
                                      <span className="font-semibold">{key}.</span> {value}
                                    </div>
                                  ))}
                                </div>
                              )}
                              <button
                                onClick={() => startPractice(item, practice)}
                                className="rounded-md border border-indigo-200 bg-white px-2.5 py-1 text-xs text-indigo-700 hover:bg-indigo-100"
                              >
                                开始作答
                              </button>
                              <div className="hidden">
                                <span className="font-semibold">参考答案：</span>
                                {practice.question.correct_answer || "暂无"}
                              </div>
                              {practice.question.explanation && (
                                <div className="hidden">
                                  <span className="font-semibold">解析：</span>
                                  <span className="whitespace-pre-wrap">{practice.question.explanation}</span>
                                </div>
                              )}
                            </div>
                          ) : (
                            <p className="mt-1 whitespace-pre-line text-xs text-indigo-800">
                              {practice.generation_error ? `生成失败：${practice.generation_error}` : practice.prompt}
                            </p>
                          )}
                        </div>
                      ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
