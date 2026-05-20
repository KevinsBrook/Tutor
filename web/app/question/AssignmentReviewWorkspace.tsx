"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlarmClock,
  BookOpenCheck,
  CheckCircle2,
  ClipboardList,
  FileText,
  Loader2,
  PenTool,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import { useGlobal } from "@/context/GlobalContext";
import { useAuth } from "@/context/AuthContext";
import { apiUrl } from "@/lib/api";

interface RubricItem {
  name: string;
  score: number;
  description?: string;
}

interface ScoringCriterion {
  id?: string;
  question_no: string;
  criterion: string;
  answer_hint?: string;
  score: number;
  keywords?: string[];
  knowledge_point?: string;
  knowledge_point_id?: number | null;
}

interface CriterionScore {
  criterion_id?: string;
  question_no: string;
  criterion: string;
  max_score: number;
  score: number;
  status: "hit" | "partial" | "missing" | string;
  evidence?: string;
  reason?: string;
  suggestion?: string;
  knowledge_point?: string;
  knowledge_point_id?: number | null;
}

interface AssignmentItem {
  id: string;
  title: string;
  description: string;
  teacher_username: string;
  course_id?: number | null;
  chapter_id?: number | null;
  course_name?: string;
  chapter_title?: string;
  status: "draft" | "published";
  confirmed: boolean;
  rubric_items: RubricItem[];
  criteria_items?: ScoringCriterion[];
  files: Array<{ filename: string; path: string; size: number }>;
  knowledge_links?: KnowledgeLink[];
  knowledge_candidates?: KnowledgeCandidate[];
  created_at: number;
}

interface SubmissionItem {
  id: string;
  student_username: string;
  assignment_id: string;
  assignment_title?: string;
  assignment_rubric_items?: RubricItem[];
  assignment_criteria_items?: ScoringCriterion[];
  answer_text: string;
  files: Array<{ filename: string; path: string; size: number }>;
  status: "submitted" | "reviewed";
  created_at: number;
  review?: {
    teacher_username: string;
    total_score: number;
    feedback: string;
    reviewed_at: number;
    rubric_scores?: Array<{
      name: string;
      score: number;
      max_score: number;
      comment?: string;
    }>;
    criterion_scores?: CriterionScore[];
  } | null;
  auto_review?: {
    relevance_score: number;
    total_score: number;
    max_score?: number;
    summary: string;
    criteria_items?: ScoringCriterion[];
    criterion_scores?: CriterionScore[];
    missing_points?: string[];
    suggestions?: string[];
    knowledge_results?: KnowledgeResult[];
    errors?: Array<{ type: string; dimension?: string; detail: string }>;
    rubric_scores?: Array<{
      name: string;
      score: number;
      max_score: number;
      comment?: string;
    }>;
  } | null;
}

interface WrongbookDraftItem {
  feedback: string;
  error_type?: string;
  knowledge_point: string;
  knowledge_point_id?: number | null;
  suggestion?: string;
  question_text?: string;
  student_answer?: string;
  correct_answer?: string;
  explanation?: string;
  question_type?: string;
}

interface RubricScoreDraft {
  name: string;
  max_score: number;
  score: string;
  comment: string;
}

interface CriterionScoreDraft {
  criterion_id?: string;
  question_no: string;
  criterion: string;
  max_score: number;
  score: string;
  status: "hit" | "partial" | "missing" | string;
  evidence: string;
  reason: string;
  suggestion: string;
  knowledge_point?: string;
  knowledge_point_id?: number | null;
}

interface RubricDraftApiItem {
  name: string;
  description?: string;
  score: number;
}

interface RubricDraftApiResponse {
  task_points: string[];
  rubric_items: RubricDraftApiItem[];
  criteria_items?: ScoringCriterion[];
}

interface QuestionSourceRef {
  id: string | number;
  query: string;
  snippet: string;
}

interface CourseOption {
  id: number;
  name: string;
  description?: string;
  knowledge_point_count?: number;
}

interface ChapterOption {
  id: number;
  title: string;
  order_index: number;
}

interface KnowledgeLink {
  knowledge_point_id: number;
  knowledge_point: string;
  chapter_title?: string;
  match_score?: number;
  priority?: number;
  source?: string;
}

interface KnowledgeCandidate {
  candidate_id: string;
  name: string;
  description?: string;
  chapter_id?: number | null;
  priority?: number;
  status?: string;
}

interface KnowledgeResult {
  knowledge_point_id?: number | null;
  knowledge_point: string;
  chapter_title?: string;
  score_ratio: number;
  status: "correct" | "partial" | "incorrect";
  feedback: string;
}

interface CourseMaterialOption {
  id: number;
  kb_name?: string | null;
  title?: string;
  display_name?: string;
  original_filename?: string | null;
  chapter_id?: number | null;
  chapter_title?: string;
}

interface KnowledgeBaseOption {
  name: string;
  display_name?: string;
  is_default?: boolean;
}

interface CourseKnowledgePointOption {
  id: number;
  name: string;
  description?: string;
  chapter_id?: number | null;
  chapter_title?: string;
  source_material_id?: number | null;
  priority: number;
  is_confirmed: boolean;
  mastery?: {
    mastery_level: number;
    correct_count: number;
    wrong_count: number;
    practice_count: number;
  };
}

interface ReviewDraft {
  totalScore: string;
  feedback: string;
  rubricScores: RubricScoreDraft[];
  criterionScores: CriterionScoreDraft[];
  wrongbookItems: WrongbookDraftItem[];
}

type PracticeStatus = "correct" | "partial" | "incorrect";
type QuestionSourceMode = "manual" | "course";

interface PracticeItemReport {
  question_id: string;
  question_type: string;
  question_text: string;
  student_answer: string;
  correct_answer: string;
  explanation: string;
  status: PracticeStatus;
  score: number;
  max_score: number;
  reason: string;
  knowledge_point?: string;
}

interface PracticeReport {
  total_score: number;
  max_score: number;
  submitted_at: number;
  items: PracticeItemReport[];
}

type FollowupStrategy = "same" | "harder" | "easier" | "variant" | "to_choice";
type PracticeMode = "practice" | "exam";
type WorkspaceMode = "question" | "assignment";
const QUESTION_TYPE_OPTIONS = new Set(["choice", "multiple_choice", "true_false", "fill_blank", "written", "mixed"]);

const FILE_HINT = "支持格式：pdf、doc、docx、txt、md、rtf、html";
const NO_KB_SOURCE = "__none__";
const DIFFICULTY_OPTIONS = [
  { value: "easy", label: "简单" },
  { value: "medium", label: "中等" },
  { value: "hard", label: "困难" },
];
const inputClass = "w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-50 disabled:text-slate-400";

function difficultyLabel(value?: string) {
  return DIFFICULTY_OPTIONS.find((item) => item.value === value)?.label || "中等";
}

function difficultyToCognitiveLevel(value?: string) {
  if (value === "hard") return "analyze";
  if (value === "easy") return "understand";
  return "apply";
}

function ConfigField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-slate-600">{label}</span>
      {children}
    </label>
  );
}

function formatTime(ts?: number) {
  if (!ts) return "--";
  return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false });
}

function formatDuration(totalSeconds: number) {
  const safe = Math.max(0, totalSeconds);
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function parseCriteriaText(raw: string): ScoringCriterion[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, idx) => {
      const [questionPart, criterionPart, scorePart, hintPart] = line.split("|").map((v) => v.trim());
      const score = Number(scorePart || "0");
      return {
        id: `criterion_${idx + 1}`,
        question_no: questionPart || "第1题",
        criterion: criterionPart || questionPart || "未命名得分点",
        score: Number.isFinite(score) ? score : 0,
        answer_hint: hintPart || "",
        keywords: [],
      };
    });
}

function formatCriteriaText(items: ScoringCriterion[] = []) {
  return items
    .map((item) => `${item.question_no || "第1题"}|${item.criterion || ""}|${item.score || 0}|${item.answer_hint || ""}`)
    .join("\n");
}

function statusLabel(status?: string) {
  if (status === "hit") return "命中";
  if (status === "partial") return "部分命中";
  if (status === "missing") return "未命中";
  return status || "未判定";
}

function buildReviewDraft(sub: SubmissionItem): ReviewDraft {
  const rubric = (sub.assignment_rubric_items || []).map((r) => ({
    name: r.name,
    max_score: Number(r.score || 0),
    score: "",
    comment: "",
  }));

  const reviewedRubric = sub.review?.rubric_scores || [];
  if (reviewedRubric.length > 0) {
    for (const rr of reviewedRubric) {
      const target = rubric.find((r) => r.name === rr.name);
      if (target) {
        target.score = String(rr.score ?? "");
        target.comment = rr.comment || "";
        if (rr.max_score) target.max_score = rr.max_score;
      } else {
        rubric.push({
          name: rr.name,
          max_score: rr.max_score || 0,
          score: String(rr.score ?? ""),
          comment: rr.comment || "",
        });
      }
    }
  }

  const baseCriteria =
    (sub.assignment_criteria_items && sub.assignment_criteria_items.length > 0
      ? sub.assignment_criteria_items
      : sub.auto_review?.criteria_items || []
    ).map((item, idx) => ({
      criterion_id: item.id || `criterion_${idx + 1}`,
      question_no: item.question_no || "第1题",
      criterion: item.criterion || "未命名得分点",
      max_score: Number(item.score || 0),
      score: "",
      status: "missing",
      evidence: "",
      reason: "",
      suggestion: "",
      knowledge_point: item.knowledge_point || "",
      knowledge_point_id: item.knowledge_point_id ?? null,
    }));
  const criterionScores = baseCriteria.length > 0 ? baseCriteria : rubric.map((r, idx) => ({
    criterion_id: `rubric_${idx + 1}`,
    question_no: "综合要求",
    criterion: r.name,
    max_score: r.max_score,
    score: "",
    status: "missing",
    evidence: "",
    reason: "",
    suggestion: r.comment,
    knowledge_point: "",
    knowledge_point_id: null,
  }));
  for (const scored of sub.auto_review?.criterion_scores || []) {
    const target = criterionScores.find((item) => item.criterion_id === scored.criterion_id || item.criterion === scored.criterion);
    if (!target) continue;
    target.score = String(scored.score ?? "");
    target.status = scored.status || "missing";
    target.evidence = scored.evidence || "";
    target.reason = scored.reason || "";
    target.suggestion = scored.suggestion || "";
    target.max_score = Number(scored.max_score || target.max_score || 0);
  }
  for (const scored of sub.review?.criterion_scores || []) {
    const target = criterionScores.find((item) => item.criterion_id === scored.criterion_id || item.criterion === scored.criterion);
    if (!target) continue;
    target.score = String(scored.score ?? "");
    target.status = scored.status || target.status;
    target.evidence = scored.evidence || target.evidence;
    target.reason = scored.reason || target.reason;
    target.suggestion = scored.suggestion || target.suggestion;
    target.max_score = Number(scored.max_score || target.max_score || 0);
  }

  return {
    totalScore: sub.review ? String(sub.review.total_score) : sub.auto_review?.total_score !== undefined ? String(sub.auto_review.total_score) : "",
    feedback: sub.review?.feedback || sub.auto_review?.summary || "",
    rubricScores: rubric,
    criterionScores,
    wrongbookItems: [
      {
        feedback: "",
        knowledge_point: "",
        knowledge_point_id: null,
        question_text: "",
        student_answer: "",
        correct_answer: "",
        question_type: "",
      },
    ],
  };
}

function normalizeText(value: string) {
  return (value || "").trim().toLowerCase();
}

function parseMultipleAnswer(answer: string): string[] {
  return answer
    .split(/[,\s;/|、]+/)
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean)
    .sort();
}

function splitValues(raw: string): string[] {
  return raw
    .split(/[,\n;/|、]+/)
    .map((x) => normalizeText(x))
    .filter(Boolean);
}

function downloadTextFile(filename: string, content: string, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function buildPracticeCsv(report: PracticeReport): string {
  const rows = [
    ["题号", "题型", "判定", "得分", "满分", "知识点", "评分理由", "解析"],
    ...report.items.map((item, idx) => [
      String(idx + 1),
      item.question_type,
      item.status,
      String(item.score),
      String(item.max_score),
      item.knowledge_point || "",
      item.reason.replace(/\n/g, " "),
      item.explanation.replace(/\n/g, " "),
    ]),
    ["总分", "", "", String(report.total_score), String(report.max_score), "", "", ""],
  ];
  return rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
}

function buildSubmissionReportPayload(sub: SubmissionItem) {
  return {
    submission_id: sub.id,
    assignment_id: sub.assignment_id,
    assignment_title: sub.assignment_title || "",
    student_username: sub.student_username,
    status: sub.status,
    submitted_at: sub.created_at,
    answer_text: sub.answer_text || "",
    review: sub.review || null,
    auto_review: sub.auto_review || null,
  };
}

function buildSubmissionMarkdown(sub: SubmissionItem): string {
  const lines: string[] = [];
  lines.push(`# 作业评审报告`);
  lines.push("");
  lines.push(`- 提交ID：${sub.id}`);
  lines.push(`- 作业ID：${sub.assignment_id}`);
  lines.push(`- 作业标题：${sub.assignment_title || "-"}`);
  lines.push(`- 学生：${sub.student_username}`);
  lines.push(`- 提交时间：${formatTime(sub.created_at)}`);
  lines.push(`- 状态：${sub.status === "reviewed" ? "已评审" : "待评审"}`);
  lines.push("");
  lines.push(`## 学生作答`);
  lines.push("");
  lines.push(sub.answer_text || "（无文本作答）");
  lines.push("");

  if (sub.review) {
    lines.push(`## 教师评审`);
    lines.push("");
    lines.push(`- 总分：${sub.review.total_score}`);
    lines.push(`- 评语：${sub.review.feedback || "无"}`);
    lines.push("");
    if (sub.review.criterion_scores && sub.review.criterion_scores.length > 0) {
      lines.push(`### 得分点明细`);
      lines.push("");
      sub.review.criterion_scores.forEach((item, idx) => {
        lines.push(`${idx + 1}. ${item.question_no} ${item.criterion}：${item.score}/${item.max_score}（${statusLabel(item.status)}）`);
        if (item.reason) lines.push(`   - 理由：${item.reason}`);
        if (item.evidence) lines.push(`   - 证据：${item.evidence}`);
      });
      lines.push("");
    }
    if (sub.review.rubric_scores && sub.review.rubric_scores.length > 0) {
      lines.push(`### Rubric 明细`);
      lines.push("");
      sub.review.rubric_scores.forEach((r, idx) => {
        lines.push(`${idx + 1}. ${r.name}：${r.score}/${r.max_score}（${r.comment || "无评语"}）`);
      });
      lines.push("");
    }
  }

  if (sub.auto_review) {
    lines.push(`## 自动批改报告`);
    lines.push("");
    lines.push(`- 相关性：${sub.auto_review.relevance_score}`);
    lines.push(`- 参考总分：${sub.auto_review.total_score}`);
    lines.push(`- 摘要：${sub.auto_review.summary}`);
    lines.push("");
    if (sub.auto_review.criterion_scores && sub.auto_review.criterion_scores.length > 0) {
      lines.push(`### 自动逐点批改`);
      lines.push("");
      sub.auto_review.criterion_scores.forEach((item, idx) => {
        lines.push(`${idx + 1}. ${item.question_no} ${item.criterion}：${item.score}/${item.max_score}（${statusLabel(item.status)}）`);
        if (item.reason) lines.push(`   - 理由：${item.reason}`);
      });
      lines.push("");
    }
  }

  return lines.join("\n");
}

function buildSubmissionCsv(sub: SubmissionItem): string {
  const rows = [
    ["字段", "值"],
    ["submission_id", sub.id],
    ["assignment_id", sub.assignment_id],
    ["assignment_title", sub.assignment_title || ""],
    ["student_username", sub.student_username],
    ["status", sub.status],
    ["submitted_at", String(sub.created_at)],
    ["review_total_score", String(sub.review?.total_score ?? "")],
    ["review_feedback", sub.review?.feedback || ""],
    ["auto_review_relevance", String(sub.auto_review?.relevance_score ?? "")],
    ["auto_review_total_score", String(sub.auto_review?.total_score ?? "")],
    ["auto_review_summary", sub.auto_review?.summary || ""],
  ];
  return rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
}

function buildSubmissionsCsv(submissions: SubmissionItem[]): string {
  const rows = [
    [
      "submission_id",
      "assignment_id",
      "assignment_title",
      "student_username",
      "status",
      "submitted_at",
      "review_total_score",
      "review_feedback",
      "auto_review_relevance",
      "auto_review_total_score",
      "auto_review_summary",
    ],
    ...submissions.map((sub) => [
      sub.id,
      sub.assignment_id,
      sub.assignment_title || "",
      sub.student_username,
      sub.status,
      String(sub.created_at),
      String(sub.review?.total_score ?? ""),
      sub.review?.feedback || "",
      String(sub.auto_review?.relevance_score ?? ""),
      String(sub.auto_review?.total_score ?? ""),
      sub.auto_review?.summary || "",
    ]),
  ];
  return rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
}

function buildSubmissionsMarkdown(submissions: SubmissionItem[], title: string): string {
  const lines: string[] = [];
  lines.push(`# ${title}`);
  lines.push("");
  lines.push(`共 ${submissions.length} 条记录`);
  lines.push("");
  submissions.forEach((sub, idx) => {
    lines.push(`## ${idx + 1}. ${sub.assignment_title || sub.assignment_id}`);
    lines.push(`- 提交ID：${sub.id}`);
    lines.push(`- 学生：${sub.student_username}`);
    lines.push(`- 状态：${sub.status === "reviewed" ? "已评审" : "待评审"}`);
    lines.push(`- 提交时间：${formatTime(sub.created_at)}`);
    if (sub.review) {
      lines.push(`- 教师评分：${sub.review.total_score}`);
      lines.push(`- 教师评语：${sub.review.feedback || "无"}`);
    }
    if (sub.auto_review) {
      lines.push(`- 自动批改相关性：${sub.auto_review.relevance_score}`);
      lines.push(`- 自动批改参考总分：${sub.auto_review.total_score}`);
    }
    lines.push("");
  });
  return lines.join("\n");
}

function xmlEscape(value: string): string {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function toAikenLine(label: string) {
  return `${label}.`;
}

function buildQuestionSetMarkdown(results: any[]): string {
  const lines: string[] = ["# 题目导出", ""];
  results.forEach((item: any, idx: number) => {
    const q = item.question || {};
    lines.push(`## 第 ${idx + 1} 题（${q.question_type || "unknown"}）`);
    lines.push("");
    lines.push(q.question || "");
    lines.push("");
    if (q.options) {
      Object.entries(q.options).forEach(([k, v]) => lines.push(`- ${k}. ${v}`));
      lines.push("");
    }
    lines.push(`答案：${q.correct_answer || ""}`);
    lines.push(`解析：${q.explanation || ""}`);
    lines.push("");
  });
  return lines.join("\n");
}

function buildQuestionSetCsv(results: any[]): string {
  const rows = [
    ["题号", "题型", "题干", "选项", "答案", "解析", "知识点", "难度"],
    ...results.map((item: any, idx: number) => {
      const q = item.question || {};
      const options = q.options
        ? Object.entries(q.options)
            .map(([k, v]) => `${k}:${v}`)
            .join(" | ")
        : "";
      return [
        String(idx + 1),
        String(q.question_type || ""),
        String(q.question || "").replace(/\n/g, " "),
        options.replace(/\n/g, " "),
        String(q.correct_answer || "").replace(/\n/g, " "),
        String(q.explanation || "").replace(/\n/g, " "),
        String(q.knowledge_point || ""),
        "",
      ];
    }),
  ];
  return rows
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    .join("\n");
}

function buildGiftExport(results: any[]): string {
  const blocks: string[] = [];
  results.forEach((item: any, idx: number) => {
    const q = item.question || {};
    const qtype = String(q.question_type || "written");
    const title = `题目${idx + 1}`;
    const stem = String(q.question || "").replace(/\n/g, " ");

    if (qtype === "choice" || qtype === "true_false") {
      const correct = String(q.correct_answer || "A").toUpperCase();
      const options = q.options || {};
      const body = Object.entries(options)
        .map(([k, v]) => `${k.toUpperCase() === correct ? "=" : "~"}${String(v)}`)
        .join(" ");
      blocks.push(`::${title}:: ${stem} { ${body} }`);
      return;
    }

    if (qtype === "multiple_choice") {
      const correctSet = new Set(
        String(q.correct_answer || "")
          .split(/[,\s;/|、]+/)
          .map((x) => x.trim().toUpperCase())
          .filter(Boolean),
      );
      const options = q.options || {};
      const body = Object.entries(options)
        .map(([k, v]) => `${correctSet.has(k.toUpperCase()) ? "=" : "~"}${String(v)}`)
        .join(" ");
      blocks.push(`::${title}:: ${stem} { ${body} }`);
      return;
    }

    blocks.push(`::${title}:: ${stem} { =${String(q.correct_answer || "").replace(/\n/g, " ")} }`);
  });
  return blocks.join("\n\n");
}

function buildAikenExport(results: any[]): string {
  const lines: string[] = [];
  results.forEach((item: any, idx: number) => {
    const q = item.question || {};
    const qtype = String(q.question_type || "");
    if (!["choice", "true_false"].includes(qtype)) return;
    lines.push(`${idx + 1}. ${String(q.question || "").replace(/\n/g, " ")}`);
    const options = q.options || {};
    Object.entries(options).forEach(([k, v]) => lines.push(`${toAikenLine(k)} ${String(v)}`));
    lines.push(`ANSWER: ${String(q.correct_answer || "").toUpperCase()}`);
    lines.push("");
  });
  return lines.join("\n");
}

function buildMoodleXmlExport(results: any[]): string {
  const questions = results
    .map((item: any, idx: number) => {
      const q = item.question || {};
      const qtype = String(q.question_type || "essay");
      const name = `题目${idx + 1}`;
      const text = xmlEscape(String(q.question || ""));
      const feedback = xmlEscape(String(q.explanation || ""));

      if (qtype === "choice" || qtype === "true_false" || qtype === "multiple_choice") {
        const options = q.options || {};
        const correctSet = new Set(
          String(q.correct_answer || "")
            .split(/[,\s;/|、]+/)
            .map((x) => x.trim().toUpperCase())
            .filter(Boolean),
        );
        const single = qtype !== "multiple_choice";
        const multiFraction = correctSet.size > 0 ? Math.round(100 / correctSet.size) : 100;
        const answers = Object.entries(options)
          .map(([k, v]) => {
            const hit = correctSet.has(String(k).toUpperCase());
            const fraction = single ? (hit ? "100" : "0") : hit ? String(multiFraction) : "0";
            return `<answer fraction="${fraction}" format="html"><text>${xmlEscape(String(v))}</text></answer>`;
          })
          .join("");
        return `<question type="multichoice"><name><text>${xmlEscape(name)}</text></name><questiontext format="html"><text>${text}</text></questiontext><single>${single ? "true" : "false"}</single>${answers}<generalfeedback format="html"><text>${feedback}</text></generalfeedback></question>`;
      }

      return `<question type="essay"><name><text>${xmlEscape(name)}</text></name><questiontext format="html"><text>${text}</text></questiontext><generalfeedback format="html"><text>${feedback}</text></generalfeedback></question>`;
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8"?><quiz>${questions}</quiz>`;
}

function evaluateObjectiveQuestion(
  question: any,
  answerRaw: string,
): Omit<PracticeItemReport, "question_id" | "question_text" | "student_answer" | "correct_answer" | "explanation"> {
  const qType = String(question.question_type || "written");
  const maxScore = 1;

  if (qType === "choice" || qType === "true_false") {
    const expected = normalizeText(String(question.correct_answer || ""));
    const actual = normalizeText(answerRaw);
    const ok = expected === actual;
    return {
      question_type: qType,
      status: ok ? "correct" : "incorrect",
      score: ok ? 1 : 0,
      max_score: maxScore,
      reason: ok ? "答案正确。" : `正确答案为：${question.correct_answer}`,
      knowledge_point: question.knowledge_point,
    };
  }

  if (qType === "multiple_choice") {
    const expected = parseMultipleAnswer(String(question.correct_answer || ""));
    const actual = parseMultipleAnswer(answerRaw);
    const tp = actual.filter((x) => expected.includes(x)).length;
    const precision = actual.length > 0 ? tp / actual.length : 0;
    const recall = expected.length > 0 ? tp / expected.length : 0;
    const ratio = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
    const status: PracticeStatus = ratio >= 0.99 ? "correct" : ratio >= 0.5 ? "partial" : "incorrect";
    return {
      question_type: qType,
      status,
      score: Number(ratio.toFixed(2)),
      max_score: maxScore,
      reason:
        status === "correct"
          ? "多选答案完全正确。"
          : status === "partial"
            ? `部分正确，参考答案：${expected.join(", ")}`
            : `答案不匹配，参考答案：${expected.join(", ")}`,
      knowledge_point: question.knowledge_point,
    };
  }

  if (qType === "fill_blank") {
    const expected = Array.isArray(question.blanks) && question.blanks.length > 0
      ? question.blanks.map((x: string) => normalizeText(x)).filter(Boolean)
      : splitValues(String(question.correct_answer || ""));
    const actual = splitValues(answerRaw);
    const matchCount = expected.filter((e: string, idx: number) => actual[idx] === e).length;
    const ratio = expected.length > 0 ? matchCount / expected.length : 0;
    const ok = ratio >= 0.99;
    const partial = !ok && ratio >= 0.4;
    return {
      question_type: qType,
      status: ok ? "correct" : partial ? "partial" : "incorrect",
      score: Number(ratio.toFixed(2)),
      max_score: maxScore,
      reason: ok ? "填空正确。" : partial ? `部分正确，参考答案：${expected.join(" / ")}` : `参考答案：${expected.join(" / ")}`,
      knowledge_point: question.knowledge_point,
    };
  }

  return {
    question_type: qType,
    status: "incorrect",
    score: 0,
    max_score: maxScore,
    reason: "题型暂未支持自动客观判分。",
    knowledge_point: question.knowledge_point,
  };
}

export default function AssignmentReviewWorkspace({ workspace = "question" }: { workspace?: WorkspaceMode }) {
  const { questionState, setQuestionState, startQuestionGen, resetQuestionGen } = useGlobal();
  const { session } = useAuth();
  const role = session?.role ?? "student";

  const [kbs, setKbs] = useState<KnowledgeBaseOption[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [submittedMap, setSubmittedMap] = useState<Record<number, boolean>>({});
  const [practiceReport, setPracticeReport] = useState<PracticeReport | null>(null);
  const [gradingPractice, setGradingPractice] = useState(false);
  const [practiceMode, setPracticeMode] = useState<PracticeMode>("practice");
  const [timerMinutes, setTimerMinutes] = useState(15);
  const [timeLeftSec, setTimeLeftSec] = useState(0);
  const [timerRunning, setTimerRunning] = useState(false);
  const [questionSourceMode, setQuestionSourceMode] = useState<QuestionSourceMode>("manual");
  const [courseOptions, setCourseOptions] = useState<CourseOption[]>([]);
  const [questionChapters, setQuestionChapters] = useState<ChapterOption[]>([]);
  const [coursePoints, setCoursePoints] = useState<CourseKnowledgePointOption[]>([]);
  const [courseMaterials, setCourseMaterials] = useState<CourseMaterialOption[]>([]);
  const [selectedQuestionCourseId, setSelectedQuestionCourseId] = useState<number | null>(null);
  const [selectedQuestionChapterId, setSelectedQuestionChapterId] = useState<number | null>(null);
  const [selectedQuestionPointId, setSelectedQuestionPointId] = useState<number | null>(null);
  const [generatedQuestionPointId, setGeneratedQuestionPointId] = useState<number | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [criteriaText, setCriteriaText] = useState("");
  const [taskPoints, setTaskPoints] = useState<string[]>([]);
  const [teacherFiles, setTeacherFiles] = useState<File[]>([]);
  const [assignmentCourseOptions, setAssignmentCourseOptions] = useState<CourseOption[]>([]);
  const [assignmentCourseId, setAssignmentCourseId] = useState<number | null>(null);
  const [assignmentChapterId, setAssignmentChapterId] = useState<number | null>(null);
  const [assignmentChapters, setAssignmentChapters] = useState<ChapterOption[]>([]);
  const [teacherAssignments, setTeacherAssignments] = useState<AssignmentItem[]>([]);
  const [publishChecks, setPublishChecks] = useState<Record<string, boolean>>({});
  const [teacherSubmissions, setTeacherSubmissions] = useState<SubmissionItem[]>([]);
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, ReviewDraft>>({});

  const [studentAssignments, setStudentAssignments] = useState<AssignmentItem[]>([]);
  const [mySubmissions, setMySubmissions] = useState<SubmissionItem[]>([]);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState("");
  const [submissionText, setSubmissionText] = useState("");
  const [submissionFiles, setSubmissionFiles] = useState<File[]>([]);

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [draftingRubric, setDraftingRubric] = useState(false);

  const isAssignmentMode = workspace === "assignment";
  const isConfigMode = questionState.step === "config";
  const isGenerating = questionState.step === "generating";
  const isResult = questionState.step === "result";
  const currentQuestion = questionState.results[activeIndex];
  const canStartCustom = questionState.topic.trim().length > 0;

  const returnToQuestionConfig = () => {
    resetQuestionGen();
    setQuestionState((prev) => ({
      ...prev,
      step: "config",
      results: [],
      logs: [],
    }));
    setAnswers({});
    setSubmittedMap({});
    setPracticeReport(null);
    setActiveIndex(0);
    setTimerRunning(false);
    setTimeLeftSec(0);
    setMessage("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  useEffect(() => {
    setQuestionState((prev) => {
      const desiredMode = isAssignmentMode ? "mimic" : "knowledge";
      if (prev.mode === desiredMode) return prev;
      return { ...prev, mode: desiredMode, step: "config" };
    });
  }, [isAssignmentMode, setQuestionState]);

  useEffect(() => {
    if (isAssignmentMode) return;
    if (!QUESTION_TYPE_OPTIONS.has(questionState.type)) {
      setQuestionState((prev) => ({ ...prev, type: "choice" }));
    }
  }, [isAssignmentMode, questionState.type, setQuestionState]);
  const selectedQuestionCourse = useMemo(
    () => courseOptions.find((course) => course.id === selectedQuestionCourseId) || null,
    [courseOptions, selectedQuestionCourseId],
  );
  const filteredCoursePoints = useMemo(
    () =>
      selectedQuestionChapterId === null
        ? coursePoints
        : coursePoints.filter((point) => (point.chapter_id ?? null) === selectedQuestionChapterId),
    [coursePoints, selectedQuestionChapterId],
  );
  const selectedCoursePoint = useMemo(
    () => filteredCoursePoints.find((point) => point.id === selectedQuestionPointId) || null,
    [filteredCoursePoints, selectedQuestionPointId],
  );
  const selectedCoursePointKb = useMemo(() => {
    if (!selectedCoursePoint?.source_material_id) return "";
    const material = courseMaterials.find((item) => item.id === selectedCoursePoint.source_material_id);
    return material?.kb_name || "";
  }, [courseMaterials, selectedCoursePoint]);
  const selectedCoursePointSourceName = useMemo(() => {
    if (!selectedCoursePoint?.source_material_id) return "";
    const material = courseMaterials.find((item) => item.id === selectedCoursePoint.source_material_id);
    return material?.display_name || material?.title || material?.original_filename || "";
  }, [courseMaterials, selectedCoursePoint]);
  const sourceOptions = useMemo(() => {
    const publicOptions = kbs.map((kb) => ({
      value: kb.name,
      label: kb.display_name || kb.name,
    }));
    const courseMaterialOptions = courseMaterials
      .filter((material) => material.kb_name)
      .map((material) => ({
        value: material.kb_name || "",
        label: `${selectedQuestionCourse?.name || "课程"} · ${
          material.display_name || material.title || material.original_filename || material.kb_name
        }${material.chapter_title ? `（${material.chapter_title}）` : ""}`,
      }));
    const merged = new Map<string, { value: string; label: string }>();
    for (const option of [...courseMaterialOptions, ...publicOptions]) {
      if (option.value && !merged.has(option.value)) merged.set(option.value, option);
    }
    return Array.from(merged.values());
  }, [courseMaterials, kbs, selectedQuestionCourse?.name]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(apiUrl("/api/v1/knowledge/list"), { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => {
        const list = Array.isArray(data)
          ? data
              .map((x: any) => ({
                name: String(x.name || ""),
                display_name: x.display_name || x.description || x.name,
                is_default: Boolean(x.is_default),
              }))
              .filter((item: KnowledgeBaseOption) => item.name)
          : [];
        setKbs(list);
      })
      .catch(() => setKbs([]));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(apiUrl("/api/v1/courses"), { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => {
        const list = Array.isArray(data.courses) ? data.courses : [];
        setCourseOptions(list);
        setSelectedQuestionCourseId((prev) => prev ?? list[0]?.id ?? null);
      })
      .catch(() => setCourseOptions([]));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (role !== "teacher" || !session?.username) {
      setAssignmentCourseOptions([]);
      return;
    }
    const controller = new AbortController();
    fetch(apiUrl(`/api/v1/courses?teacher_username=${encodeURIComponent(session.username)}`), {
      signal: controller.signal,
    })
      .then((res) => res.json())
      .then((data) => {
        const list = Array.isArray(data.courses) ? data.courses : [];
        setAssignmentCourseOptions(list);
        setAssignmentCourseId((prev) =>
          list.some((course: CourseOption) => course.id === prev) ? prev : list[0]?.id ?? null,
        );
      })
      .catch(() => setAssignmentCourseOptions([]));
    return () => controller.abort();
  }, [role, session?.username]);

  useEffect(() => {
    if (!selectedQuestionCourseId) {
      setQuestionChapters([]);
      setCoursePoints([]);
      setCourseMaterials([]);
      setSelectedQuestionChapterId(null);
      setSelectedQuestionPointId(null);
      return;
    }

    const controller = new AbortController();
    const params = new URLSearchParams({ confirmed_only: "true" });
    if (session?.role === "student" && session.username) {
      params.set("student_username", session.username);
    }
    Promise.all([
      fetch(apiUrl(`/api/v1/courses/${selectedQuestionCourseId}/knowledge-points?${params.toString()}`), {
        signal: controller.signal,
      }).then((res) => res.json()),
      fetch(apiUrl(`/api/v1/courses/${selectedQuestionCourseId}/chapters`), {
        signal: controller.signal,
      }).then((res) => res.json()),
      fetch(apiUrl(`/api/v1/courses/${selectedQuestionCourseId}/materials`), {
        signal: controller.signal,
      }).then((res) => res.json()),
    ])
      .then(([pointData, chapterData, materialData]) => {
        const points = Array.isArray(pointData.knowledge_points) ? pointData.knowledge_points : [];
        const chapters = Array.isArray(chapterData.chapters) ? chapterData.chapters : [];
        setCoursePoints(points);
        setQuestionChapters(chapters);
        setCourseMaterials(Array.isArray(materialData.materials) ? materialData.materials : []);
        setSelectedQuestionChapterId((prev) => {
          if (chapters.some((chapter: ChapterOption) => chapter.id === prev)) return prev;
          const firstPointChapterId = points.find((point: CourseKnowledgePointOption) => point.chapter_id)?.chapter_id;
          return firstPointChapterId ?? chapters[0]?.id ?? null;
        });
      })
      .catch(() => {
        setQuestionChapters([]);
        setCoursePoints([]);
        setCourseMaterials([]);
      });
    return () => controller.abort();
  }, [selectedQuestionCourseId, session?.role, session?.username]);

  useEffect(() => {
    if (!assignmentCourseId) {
      setAssignmentChapters([]);
      setAssignmentChapterId(null);
      return;
    }
    const controller = new AbortController();
    fetch(apiUrl(`/api/v1/courses/${assignmentCourseId}/chapters`), { signal: controller.signal })
      .then((res) => res.json())
      .then((data) => {
        const chapters = Array.isArray(data.chapters) ? data.chapters : [];
        setAssignmentChapters(chapters);
        setAssignmentChapterId((prev) =>
          chapters.some((chapter: ChapterOption) => chapter.id === prev) ? prev : chapters[0]?.id ?? null,
        );
      })
      .catch(() => setAssignmentChapters([]));
    return () => controller.abort();
  }, [assignmentCourseId]);

  useEffect(() => {
    setSelectedQuestionPointId((prev) =>
      filteredCoursePoints.some((point) => point.id === prev) ? prev : filteredCoursePoints[0]?.id ?? null,
    );
  }, [filteredCoursePoints]);

  const loadTeacherAssignments = useCallback(async () => {
    if (!session?.username) return;
    const res = await fetch(
      apiUrl(`/api/v1/assignment-review/teacher/assignments?teacher_username=${encodeURIComponent(session.username)}`),
    );
    const data = await res.json();
    setTeacherAssignments(data.assignments || []);
  }, [session?.username]);

  const loadTeacherSubmissions = useCallback(async () => {
    if (!session?.username) return;
    const res = await fetch(
      apiUrl(`/api/v1/assignment-review/teacher/submissions?teacher_username=${encodeURIComponent(session.username)}`),
    );
    const data = await res.json();
    const list = data.submissions || [];
    setTeacherSubmissions(list);
    setReviewDrafts((prev) => {
      const next = { ...prev };
      for (const sub of list) {
        if (!next[sub.id]) next[sub.id] = buildReviewDraft(sub);
      }
      return next;
    });
  }, [session?.username]);

  const loadStudentAssignments = useCallback(async () => {
    const res = await fetch(apiUrl("/api/v1/assignment-review/student/published"));
    const data = await res.json();
    const list = data.assignments || [];
    setStudentAssignments(list);
    if (!selectedAssignmentId && list.length > 0) setSelectedAssignmentId(list[0].id);
  }, [selectedAssignmentId]);

  const loadMySubmissions = useCallback(async () => {
    if (!session?.username) return;
    const res = await fetch(
      apiUrl(`/api/v1/assignment-review/student/submissions?student_username=${encodeURIComponent(session.username)}`),
    );
    const data = await res.json();
    const list = data.submissions || [];
    list.sort((a: SubmissionItem, b: SubmissionItem) => (b.created_at || 0) - (a.created_at || 0));
    setMySubmissions(list);
  }, [session?.username]);

  useEffect(() => {
    if (!isAssignmentMode) return;
    if (role === "teacher") {
      loadTeacherAssignments();
      loadTeacherSubmissions();
    } else {
      loadStudentAssignments();
      loadMySubmissions();
    }
  }, [
    isAssignmentMode,
    role,
    loadTeacherAssignments,
    loadTeacherSubmissions,
    loadStudentAssignments,
    loadMySubmissions,
  ]);

  useEffect(() => {
    if (activeIndex >= questionState.results.length) setActiveIndex(0);
  }, [activeIndex, questionState.results.length]);

  useEffect(() => {
    if (practiceMode !== "exam") {
      setTimerRunning(false);
      setTimeLeftSec(0);
      return;
    }
    if (!isResult || questionState.results.length === 0 || practiceReport || gradingPractice) return;
    if (timeLeftSec > 0) return;
    setTimeLeftSec(Math.max(60, timerMinutes * 60));
    setTimerRunning(true);
  }, [
    gradingPractice,
    isResult,
    practiceMode,
    practiceReport,
    questionState.results.length,
    timeLeftSec,
    timerMinutes,
  ]);

  const createDraft = async () => {
    if (!session?.username || !title.trim()) {
      setMessage("请先填写作业标题。");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const form = new FormData();
      form.append("teacher_username", session.username);
      form.append("title", title.trim());
      form.append("description", description.trim());
      if (assignmentCourseId) form.append("course_id", String(assignmentCourseId));
      if (assignmentChapterId) form.append("chapter_id", String(assignmentChapterId));
      const criteria = parseCriteriaText(criteriaText);
      form.append("criteria_json", JSON.stringify(criteria));
      form.append("rubric_json", JSON.stringify(criteria.map((item) => ({
        name: item.criterion,
        score: item.score,
        description: item.answer_hint || "",
      }))));
      teacherFiles.forEach((f) => form.append("files", f));

      const res = await fetch(apiUrl("/api/v1/assignment-review/teacher/assignments"), { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "创建草稿失败");

      setMessage("草稿创建成功，请在作业列表中勾选确认后发布。发布前学生不可见。");
      setTitle("");
      setDescription("");
      setCriteriaText("");
      setTeacherFiles([]);
      await loadTeacherAssignments();
    } catch (e: any) {
      setMessage(e.message || "创建草稿失败");
    } finally {
      setLoading(false);
    }
  };

  const generateRubricDraft = async () => {
    if (!title.trim() && !description.trim() && teacherFiles.length === 0) {
      setMessage("请至少填写标题、说明或上传附件后再生成草稿。");
      return;
    }
    setDraftingRubric(true);
    setMessage("");
    try {
      const form = new FormData();
      form.append("title", title.trim());
      form.append("description", description.trim());
      if (assignmentCourseId) form.append("course_id", String(assignmentCourseId));
      if (assignmentChapterId) form.append("chapter_id", String(assignmentChapterId));
      form.append("expected_total_score", "100");
      teacherFiles.forEach((f) => form.append("files", f));
      const res = await fetch(apiUrl("/api/v1/assignment-review/teacher/rubric-draft"), {
        method: "POST",
        body: form,
      });
      const data: RubricDraftApiResponse | { detail?: string } = await res.json();
      if (!res.ok) {
        throw new Error("detail" in data ? data.detail || "生成草稿失败" : "生成草稿失败");
      }

      const draft = data as RubricDraftApiResponse;
      setCriteriaText(
        draft.criteria_items && draft.criteria_items.length > 0
          ? formatCriteriaText(draft.criteria_items)
          : draft.rubric_items.map((item: RubricDraftApiItem, idx) => `综合要求|${item.name}|${item.score}|${item.description || ""}`).join("\n"),
      );
      setTaskPoints(draft.task_points || []);
      setMessage("已生成得分点草稿与任务要点，你可以继续编辑后创建作业。");
    } catch (e: any) {
      setMessage(e.message || "生成草稿失败");
    } finally {
      setDraftingRubric(false);
    }
  };

  const publishAssignment = async (assignmentId: string) => {
    if (!session?.username) return;
    if (!publishChecks[assignmentId]) {
      setMessage("请先勾选“我确认发布”后再发布。");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(apiUrl(`/api/v1/assignment-review/teacher/assignments/${assignmentId}/confirm`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teacher_username: session.username }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "发布失败");
      setMessage("作业发布成功，学生端已可见。");
      setPublishChecks((prev) => ({ ...prev, [assignmentId]: false }));
      await loadTeacherAssignments();
    } catch (e: any) {
      setMessage(e.message || "发布失败");
    } finally {
      setLoading(false);
    }
  };

  const deleteAssignment = async (assignmentId: string, assignmentTitle: string) => {
    if (!session?.username) return;
    const ok = window.confirm(`确定删除作业“${assignmentTitle}”吗？删除后学生端将不再看到该作业。`);
    if (!ok) return;
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(apiUrl(`/api/v1/assignment-review/teacher/assignments/${assignmentId}`), {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teacher_username: session.username }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "删除失败");
      setMessage("作业已删除。");
      setPublishChecks((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      await loadTeacherAssignments();
      await loadTeacherSubmissions();
    } catch (e: any) {
      setMessage(e.message || "删除失败");
    } finally {
      setLoading(false);
    }
  };

  const confirmAssignmentCandidate = async (assignment: AssignmentItem, candidate: KnowledgeCandidate) => {
    if (!session?.username) return;
    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(
        apiUrl(`/api/v1/assignment-review/teacher/assignments/${assignment.id}/knowledge-candidates/confirm`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            teacher_username: session.username,
            candidates: [
              {
                name: candidate.name,
                description: candidate.description || "由作业审查模块识别并确认。",
                priority: candidate.priority || 3,
                chapter_id: candidate.chapter_id || assignment.chapter_id || null,
              },
            ],
          }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "候选知识点确认失败");
      setMessage("候选知识点已加入课程知识点库，并关联到该作业。");
      await loadTeacherAssignments();
    } catch (e: any) {
      setMessage(e.message || "候选知识点确认失败");
    } finally {
      setLoading(false);
    }
  };

  const submitAssignment = async () => {
    if (!session?.username || !selectedAssignmentId) {
      setMessage("请先选择作业。");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const form = new FormData();
      form.append("student_username", session.username);
      form.append("assignment_id", selectedAssignmentId);
      form.append("answer_text", submissionText);
      submissionFiles.forEach((f) => form.append("files", f));

      const res = await fetch(apiUrl("/api/v1/assignment-review/student/submissions"), { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "提交失败");

      const autoScore = data?.auto_review?.total_score;
      setMessage(
        Number.isFinite(autoScore)
          ? `提交成功，系统已完成自动批改（当前参考分：${autoScore}）。`
          : "提交成功，系统已完成自动批改。",
      );
      setSubmissionText("");
      setSubmissionFiles([]);
      await loadMySubmissions();
    } catch (e: any) {
      setMessage(e.message || "提交失败");
    } finally {
      setLoading(false);
    }
  };

  const submitReview = async (submissionId: string) => {
    if (!session?.username) return;
    const draft = reviewDrafts[submissionId];
    if (!draft) return;

    const totalScore = Number(draft.totalScore || "0");
    if (!Number.isFinite(totalScore) || totalScore < 0 || totalScore > 100) {
      setMessage("总分请填写 0~100 的数字。\n");
      return;
    }

    const rubricScores = draft.rubricScores
      .filter((r) => r.name.trim())
      .map((r) => ({
        name: r.name,
        max_score: Number(r.max_score || 0),
        score: Number(r.score || 0),
        comment: r.comment || "",
      }));
    const criterionScores = draft.criterionScores
      .filter((item) => item.criterion.trim())
      .map((item) => ({
        criterion_id: item.criterion_id || "",
        question_no: item.question_no || "",
        criterion: item.criterion,
        max_score: Number(item.max_score || 0),
        score: Number(item.score || 0),
        status: item.status || "missing",
        evidence: item.evidence || "",
        reason: item.reason || "",
        suggestion: item.suggestion || "",
        knowledge_point: item.knowledge_point || "",
        knowledge_point_id: item.knowledge_point_id || null,
      }));

    const wrongbookItems = draft.wrongbookItems
      .filter((w) => w.feedback.trim() || w.knowledge_point.trim() || (w.error_type || "").trim())
      .map((w) => ({
        feedback: w.feedback.trim() || "建议复盘本题。",
        error_type: (w.error_type || "").trim(),
        knowledge_point: w.knowledge_point.trim(),
        knowledge_point_id: w.knowledge_point_id || null,
        suggestion: (w.suggestion || "").trim(),
      }));

    setLoading(true);
    setMessage("");
    try {
      const res = await fetch(
        apiUrl(`/api/v1/assignment-review/teacher/submissions/${submissionId}/review`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            teacher_username: session.username,
            total_score: totalScore,
            feedback: draft.feedback.trim(),
            rubric_scores: rubricScores,
            criterion_scores: criterionScores,
            wrongbook_items: wrongbookItems,
          }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "评审提交失败");

      setMessage("评审已保存，错题本已自动更新。");
      await loadTeacherSubmissions();
    } catch (e: any) {
      setMessage(e.message || "评审提交失败");
    } finally {
      setLoading(false);
    }
  };

  const startCustom = () => {
    if (!canStartCustom) return;
    setGeneratedQuestionPointId(null);
    startQuestionGen(
      questionState.topic,
      questionState.difficulty,
      questionState.type,
      difficultyToCognitiveLevel(questionState.difficulty),
      questionState.count,
      questionState.selectedKb,
    );
    setAnswers({});
    setSubmittedMap({});
    setPracticeReport(null);
    setActiveIndex(0);
    if (practiceMode === "exam") {
      setTimeLeftSec(Math.max(60, timerMinutes * 60));
      setTimerRunning(true);
    } else {
      setTimeLeftSec(0);
      setTimerRunning(false);
    }
  };

  const startCoursePointQuestion = () => {
    if (!selectedCoursePoint) {
      setMessage("请先选择课程知识点。");
      return;
    }
    const kbName = selectedCoursePointKb || questionState.selectedKb;
    if (!kbName) {
      setMessage("当前知识点还没有可用知识库，请先在课程中心解析资料，或手动选择一个知识库。");
      return;
    }
    setGeneratedQuestionPointId(selectedCoursePoint.id);
    setQuestionState((prev) => ({
      ...prev,
      topic: selectedCoursePoint.name,
      selectedKb: kbName,
    }));
    startQuestionGen(
      selectedCoursePoint.name,
      questionState.difficulty,
      questionState.type,
      difficultyToCognitiveLevel(questionState.difficulty),
      questionState.count,
      kbName,
    );
    setAnswers({});
    setSubmittedMap({});
    setPracticeReport(null);
    setActiveIndex(0);
    if (practiceMode === "exam") {
      setTimeLeftSec(Math.max(60, timerMinutes * 60));
      setTimerRunning(true);
    } else {
      setTimeLeftSec(0);
      setTimerRunning(false);
    }
  };

  const selectedAssignment = useMemo(
    () => studentAssignments.find((x) => x.id === selectedAssignmentId),
    [selectedAssignmentId, studentAssignments],
  );

  const updateDraft = (id: string, updater: (current: ReviewDraft) => ReviewDraft) => {
    setReviewDrafts((prev) => {
      const current = prev[id] || { totalScore: "", feedback: "", rubricScores: [], criterionScores: [], wrongbookItems: [] };
      return { ...prev, [id]: updater(current) };
    });
  };

  const exportSubmissionReport = useCallback((sub: SubmissionItem, format: "json" | "md" | "csv") => {
    const ts = new Date().toISOString().replace(/[:.]/g, "-");
    if (format === "json") {
      downloadTextFile(
        `submission_report_${sub.id}_${ts}.json`,
        JSON.stringify(buildSubmissionReportPayload(sub), null, 2),
        "application/json;charset=utf-8",
      );
      return;
    }
    if (format === "md") {
      downloadTextFile(
        `submission_report_${sub.id}_${ts}.md`,
        buildSubmissionMarkdown(sub),
        "text/markdown;charset=utf-8",
      );
      return;
    }
    downloadTextFile(
      `submission_report_${sub.id}_${ts}.csv`,
      buildSubmissionCsv(sub),
      "text/csv;charset=utf-8",
    );
  }, []);

  const exportSubmissionCollection = useCallback(
    (submissions: SubmissionItem[], prefix: string, format: "json" | "md" | "csv", title: string) => {
      const ts = new Date().toISOString().replace(/[:.]/g, "-");
      if (!submissions.length) {
        setMessage("当前暂无可导出的记录。");
        return;
      }
      if (format === "json") {
        downloadTextFile(
          `${prefix}_${ts}.json`,
          JSON.stringify(submissions.map((x) => buildSubmissionReportPayload(x)), null, 2),
          "application/json;charset=utf-8",
        );
        return;
      }
      if (format === "md") {
        downloadTextFile(
          `${prefix}_${ts}.md`,
          buildSubmissionsMarkdown(submissions, title),
          "text/markdown;charset=utf-8",
        );
        return;
      }
      downloadTextFile(
        `${prefix}_${ts}.csv`,
        buildSubmissionsCsv(submissions),
        "text/csv;charset=utf-8",
      );
    },
    [],
  );

  const syncWrongbookFromPractice = useCallback(async (reports: PracticeItemReport[]) => {
    if (!session?.username) return;
    const weak = reports.filter((x) => x.status !== "correct");
    for (const item of weak) {
      await fetch(apiUrl("/api/v1/assignment-review/student/wrongbook/custom"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_username: session.username,
          assignment_id: "question_practice",
          assignment_title: "自定义出题练习",
          feedback: item.reason,
          question_text: item.question_text,
          student_answer: item.student_answer,
          correct_answer: item.correct_answer,
          explanation: item.explanation,
          question_type: item.question_type,
          score: item.score,
          max_score: item.max_score,
          knowledge_point: item.knowledge_point || questionState.topic || "未指定知识点",
        }),
      });
    }
  }, [questionState.topic, session?.username]);

  const syncMasteryFromPractice = useCallback(async (reports: PracticeItemReport[]) => {
    if (!session?.username || !generatedQuestionPointId || reports.length === 0) return false;
    const events = reports.map((item) => ({
      knowledge_point_id: generatedQuestionPointId,
      source_type: "question_practice",
      source_id: item.question_id,
      score: item.score,
      max_score: item.max_score,
      is_correct: item.status === "correct" ? true : item.status === "incorrect" ? false : null,
      difficulty: questionState.difficulty,
      answer_quality: item.status === "partial" ? "partial" : undefined,
      note: "课程知识点出题练习自动更新掌握度",
    }));
    const res = await fetch(apiUrl("/api/v1/courses/knowledge-points/mastery-events/batch"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_username: session.username,
        events,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "掌握度更新失败");
    return true;
  }, [generatedQuestionPointId, questionState.difficulty, session?.username]);

  const gradePractice = useCallback(async () => {
    if (questionState.results.length === 0) {
      setMessage("当前没有可评分的题目。");
      return;
    }
    setGradingPractice(true);
    setTimerRunning(false);
    setMessage("");
    try {
      const reportItems: PracticeItemReport[] = [];
      for (let idx = 0; idx < questionState.results.length; idx += 1) {
        const item = questionState.results[idx];
        const answer = answers[idx] || "";
        const qType = String(item.question.question_type || "written");
        const questionText = String(item.question.question || "");
        const correctAnswer = String(item.question.correct_answer || "");
        const explanation = String(item.question.explanation || "");
        if (["written", "essay", "subjective"].includes(qType.toLowerCase())) {
          const res = await fetch(apiUrl("/api/v1/question/evaluate/written"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: item.question, answer }),
          });
          const data = await res.json();
          const ratio = Number(data.score_ratio || 0);
          reportItems.push({
            question_id: item.question_id || `q_${idx + 1}`,
            question_type: qType,
            question_text: questionText,
            student_answer: answer,
            correct_answer: correctAnswer,
            explanation,
            status: (data.status || "incorrect") as PracticeStatus,
            score: Number(ratio.toFixed(2)),
            max_score: 1,
            reason: data.reason || "主观题评分完成。",
            knowledge_point: item.question.knowledge_point,
          });
        } else {
          reportItems.push({
            question_id: item.question_id || `q_${idx + 1}`,
            question_text: questionText,
            student_answer: answer,
            correct_answer: correctAnswer,
            explanation,
            ...evaluateObjectiveQuestion(item.question, answer),
          });
        }
      }

      const total = reportItems.reduce((acc, cur) => acc + cur.score, 0);
      const max = reportItems.reduce((acc, cur) => acc + cur.max_score, 0);
      setPracticeReport({
        total_score: Number(total.toFixed(2)),
        max_score: Number(max.toFixed(2)),
        submitted_at: Date.now(),
        items: reportItems,
      });
      setSubmittedMap(
        reportItems.reduce((acc, _, idx) => ({ ...acc, [idx]: true }), {} as Record<number, boolean>),
      );
      await syncWrongbookFromPractice(reportItems);
      const masterySynced = await syncMasteryFromPractice(reportItems);
      setMessage(masterySynced ? "练习已评分，并同步错题本与知识点掌握度。" : "练习已评分并同步错题本。");
    } catch (e: any) {
      setMessage(e.message || "评分失败，请稍后重试。");
    } finally {
      setGradingPractice(false);
    }
  }, [answers, questionState.results, syncMasteryFromPractice, syncWrongbookFromPractice]);

  useEffect(() => {
    if (!isResult || practiceMode !== "exam" || !timerRunning || gradingPractice || !!practiceReport) return;
    if (timeLeftSec <= 0) {
      gradePractice();
      setMessage("考试时间结束，系统已自动提交并评分。");
      return;
    }
    const timer = window.setTimeout(() => setTimeLeftSec((prev) => Math.max(0, prev - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [
    gradePractice,
    gradingPractice,
    isResult,
    practiceMode,
    practiceReport,
    timeLeftSec,
    timerRunning,
  ]);

  const triggerFollowupGeneration = useCallback(
    (index: number, strategy: FollowupStrategy) => {
      const source = questionState.results[index];
      if (!source) return;

      const topic = source.question.knowledge_point || questionState.topic;
      const baseType = String(source.question.question_type || questionState.type || "written");
      const baseDiff = String(questionState.difficulty || "medium");
      const bloom = difficultyToCognitiveLevel(questionState.difficulty);

      const nextDifficulty = (() => {
        if (strategy === "harder") {
          if (baseDiff === "easy") return "medium";
          return "hard";
        }
        if (strategy === "easier") {
          if (baseDiff === "hard") return "medium";
          return "easy";
        }
        return baseDiff;
      })();

      const nextType = (() => {
        if (strategy === "to_choice") return "choice";
        if (strategy === "variant") {
          if (baseType === "written") return "choice";
          if (baseType === "choice") return "written";
          if (baseType === "true_false") return "multiple_choice";
          return "written";
        }
        return baseType;
      })();

      startQuestionGen(topic, nextDifficulty, nextType, bloom, 1, questionState.selectedKb);
      setPracticeReport(null);
      setAnswers({});
      setSubmittedMap({});
      setActiveIndex(0);
      setMessage("已启动再练生成。");
    },
    [
      questionState.results,
      questionState.topic,
      questionState.type,
      questionState.difficulty,
      questionState.selectedKb,
      startQuestionGen,
    ],
  );

  return (
    <div className="h-[calc(100vh-7rem)] overflow-auto rounded-3xl border border-white/70 bg-[color:var(--ui-panel)]/88 p-5 shadow-[0_18px_46px_rgba(15,23,42,0.14)]">
      <div className="mb-5 flex items-center justify-between rounded-2xl border border-white/70 bg-white/80 p-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-indigo-100 p-2 text-indigo-700">
              {isAssignmentMode ? <ClipboardList className="h-5 w-5" /> : <PenTool className="h-5 w-5" />}
            </div>
            <div>
            <h1 className="text-lg font-semibold text-slate-900">{isAssignmentMode ? "作业批改" : "题目生成"}</h1>
            <p className="text-xs text-slate-500">
              {isAssignmentMode ? "作业发布、评分标准生成与逐点批改" : "输入知识点或按课程章节生成练习题"}
            </p>
          </div>
        </div>
      </div>

      {!isAssignmentMode && isConfigMode && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="mb-4 inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1 text-sm">
            <button
              onClick={() => setQuestionSourceMode("manual")}
              className={`rounded-lg px-3 py-1.5 ${
                questionSourceMode === "manual" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600"
              }`}
            >
              输入知识点出题
            </button>
            <button
              onClick={() => setQuestionSourceMode("course")}
              className={`rounded-lg px-3 py-1.5 ${
                questionSourceMode === "course" ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600"
              }`}
            >
              根据课程章节出题
            </button>
          </div>

          {questionSourceMode === "course" && (
            <div className="mb-4 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
              <div className="grid gap-3 md:grid-cols-3">
                <ConfigField label="选择课程">
                  <select
                    value={selectedQuestionCourseId ?? ""}
                    onChange={(e) => setSelectedQuestionCourseId(Number(e.target.value) || null)}
                    className={inputClass}
                  >
                    {courseOptions.length === 0 ? (
                      <option value="">暂无课程</option>
                    ) : (
                      courseOptions.map((course) => (
                        <option key={course.id} value={course.id}>
                          {course.name}
                        </option>
                      ))
                    )}
                  </select>
                </ConfigField>
                <ConfigField label="选择章节">
                  <select
                    value={selectedQuestionChapterId ?? ""}
                    onChange={(e) => setSelectedQuestionChapterId(e.target.value ? Number(e.target.value) : null)}
                    className={inputClass}
                  >
                    {questionChapters.length === 0 ? (
                      <option value="">全部章节</option>
                    ) : (
                      <>
                        <option value="">全部章节</option>
                        {questionChapters.map((chapter) => (
                          <option key={chapter.id} value={chapter.id}>
                            {chapter.order_index}. {chapter.title}
                          </option>
                        ))}
                      </>
                    )}
                  </select>
                </ConfigField>
                <ConfigField label="选择知识点">
                  <select
                    value={selectedQuestionPointId ?? ""}
                    onChange={(e) => {
                      const pointId = Number(e.target.value) || null;
                      setSelectedQuestionPointId(pointId);
                      const point = filteredCoursePoints.find((item) => item.id === pointId);
                      if (point) {
                        setQuestionState((prev) => ({ ...prev, topic: point.name }));
                      }
                    }}
                    className={inputClass}
                  >
                    {filteredCoursePoints.length === 0 ? (
                      <option value="">暂无知识点</option>
                    ) : (
                      filteredCoursePoints.map((point) => (
                        <option key={point.id} value={point.id}>
                          {point.name}
                          {point.is_confirmed ? "" : "（待确认）"}
                        </option>
                      ))
                    )}
                  </select>
                </ConfigField>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-[1fr_220px]">
                <div className="rounded-lg bg-white/80 px-3 py-2 text-sm text-slate-600">
                  {selectedCoursePoint
                    ? `${selectedCoursePoint.description || "该知识点暂无说明"}`
                    : "从课程中心选择知识点后，系统会按它生成题目并在评分后更新掌握度。"}
                </div>
                <div className="rounded-lg bg-white/80 px-3 py-2 text-sm text-slate-600">
                  资料来源：{selectedCoursePointSourceName || questionState.selectedKb || "未选择"}
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2">
            {questionSourceMode === "manual" && (
              <>
                <ConfigField label="知识点 / 主题">
                  <input
                    value={questionState.topic}
                    onChange={(e) => setQuestionState((p) => ({ ...p, topic: e.target.value }))}
                    className={inputClass}
                    placeholder="例如：条件概率"
                  />
                </ConfigField>
                <ConfigField label="资料来源">
                  <select
                    value={questionState.selectedKb || NO_KB_SOURCE}
                    onChange={(e) =>
                      setQuestionState((p) => ({
                        ...p,
                        selectedKb: e.target.value === NO_KB_SOURCE ? "" : e.target.value,
                      }))
                    }
                    className={inputClass}
                  >
                    <option value={NO_KB_SOURCE}>无资料来源（仅按输入知识点出题）</option>
                    {sourceOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </ConfigField>
              </>
            )}
            <ConfigField label="题型">
              <select value={questionState.type} onChange={(e) => setQuestionState((p) => ({ ...p, type: e.target.value }))} className={inputClass}>
                <option value="choice">单选题</option>
                <option value="multiple_choice">多选题</option>
                <option value="true_false">判断题</option>
                <option value="fill_blank">填空题</option>
                <option value="written">问答题</option>
                <option value="mixed">混合题</option>
              </select>
            </ConfigField>
            <ConfigField label="难度">
              <select value={questionState.difficulty || "medium"} onChange={(e) => setQuestionState((p) => ({ ...p, difficulty: e.target.value }))} className={inputClass}>
                {DIFFICULTY_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </ConfigField>
            <ConfigField label="题量">
              <input
                type="number"
                min={1}
                max={20}
                value={questionState.count}
                onChange={(e) => setQuestionState((p) => ({ ...p, count: Math.max(1, Math.min(20, Number(e.target.value) || 1)) }))}
                className={inputClass}
              />
            </ConfigField>
            <ConfigField label="练习模式">
              <select
                value={practiceMode}
                onChange={(e) => setPracticeMode(e.target.value as PracticeMode)}
                className={inputClass}
              >
                <option value="practice">练习模式（即时评分）</option>
                <option value="exam">考试模式（限时）</option>
              </select>
            </ConfigField>
            {practiceMode === "exam" && (
              <ConfigField label="考试时长（分钟）">
                <input
                  type="number"
                  min={1}
                  max={180}
                  value={timerMinutes}
                  onChange={(e) => setTimerMinutes(Math.max(1, Math.min(180, Number(e.target.value) || 1)))}
                  className={inputClass}
                />
              </ConfigField>
            )}
          </div>
          <button
            onClick={questionSourceMode === "course" ? startCoursePointQuestion : startCustom}
            disabled={questionSourceMode === "course" ? !selectedCoursePoint : !canStartCustom}
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-white disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {questionSourceMode === "course" ? "按课程章节生成" : "开始生成"}
          </button>
        </div>
      )}

      {!isAssignmentMode && isGenerating && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-sm text-slate-600">正在生成题目：{questionState.progress.progress.current || 0}/{questionState.progress.progress.total || questionState.count}</p>
        </div>
      )}

      {!isAssignmentMode && isResult && currentQuestion && (
        <div className="space-y-4">
          <section className="rounded-2xl border border-indigo-200 bg-indigo-50/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-base font-semibold text-indigo-900">题目导出</h3>
                <p className="text-xs text-indigo-700">可导出当前批次题目，便于接入教学平台或线下归档。</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() =>
                    downloadTextFile(
                      `questions_${Date.now()}.json`,
                      JSON.stringify(questionState.results, null, 2),
                      "application/json;charset=utf-8",
                    )
                  }
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  JSON
                </button>
                <button
                  onClick={() =>
                    downloadTextFile(
                      `questions_${Date.now()}.md`,
                      buildQuestionSetMarkdown(questionState.results),
                      "text/markdown;charset=utf-8",
                    )
                  }
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  Markdown
                </button>
                <button
                  onClick={() =>
                    downloadTextFile(`questions_${Date.now()}.csv`, buildQuestionSetCsv(questionState.results), "text/csv;charset=utf-8")
                  }
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  CSV
                </button>
                <button
                  onClick={() => downloadTextFile(`questions_${Date.now()}.gift.txt`, buildGiftExport(questionState.results))}
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  GIFT
                </button>
                <button
                  onClick={() => downloadTextFile(`questions_${Date.now()}.aiken.txt`, buildAikenExport(questionState.results))}
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  AIKEN
                </button>
                <button
                  onClick={() =>
                    downloadTextFile(
                      `questions_${Date.now()}.xml`,
                      buildMoodleXmlExport(questionState.results),
                      "application/xml;charset=utf-8",
                    )
                  }
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  Moodle XML
                </button>
              </div>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-semibold text-slate-900">练习作答区</h3>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>
                  第 {activeIndex + 1}/{questionState.results.length} 题 · {currentQuestion.question.question_type} ·
                  难度 {difficultyLabel(questionState.difficulty)}
                </span>
                {practiceMode === "exam" && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-700">
                    <AlarmClock className="h-3.5 w-3.5" />
                    剩余时间 {formatDuration(timeLeftSec)}
                  </span>
                )}
                <button
                  type="button"
                  onClick={returnToQuestionConfig}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
                >
                  返回出题选择
                </button>
              </div>
            </div>
            <p className="mt-3 whitespace-pre-wrap text-sm text-slate-800">{currentQuestion.question.question}</p>
            {(String(currentQuestion.question.question_type || "").toLowerCase() === "choice" ||
              String(currentQuestion.question.question_type || "").toLowerCase() === "multiple_choice" ||
              String(currentQuestion.question.question_type || "").toLowerCase() === "true_false") &&
              currentQuestion.question.options && (
              <div className="mt-3 space-y-2 text-sm">
                {Object.entries(
                  currentQuestion.question.options as Record<string, string | number | boolean>,
                ).map(([key, value]) => (
                  <label key={key} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2">
                    <input
                      type={
                        String(currentQuestion.question.question_type || "").toLowerCase() === "multiple_choice"
                          ? "checkbox"
                          : "radio"
                      }
                      name={`q-${activeIndex}`}
                      checked={
                        String(currentQuestion.question.question_type || "").toLowerCase() === "multiple_choice"
                          ? parseMultipleAnswer(answers[activeIndex] || "").includes(key.toUpperCase())
                          : (answers[activeIndex] || "") === key
                      }
                      onChange={(e) => {
                        if (String(currentQuestion.question.question_type || "").toLowerCase() === "multiple_choice") {
                          const current = parseMultipleAnswer(answers[activeIndex] || "");
                          const next = e.target.checked
                            ? [...new Set([...current, key.toUpperCase()])]
                            : current.filter((x) => x !== key.toUpperCase());
                          setAnswers((prev) => ({ ...prev, [activeIndex]: next.join(",") }));
                        } else {
                          setAnswers((prev) => ({ ...prev, [activeIndex]: key }));
                        }
                      }}
                    />
                    <span className="text-slate-700">{key}. {String(value)}</span>
                  </label>
                ))}
              </div>
            )}
            {String(currentQuestion.question.question_type || "").toLowerCase() === "fill_blank" && (
              <textarea
                value={answers[activeIndex] || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [activeIndex]: e.target.value }))}
                className="mt-3 h-20 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                placeholder="请按顺序填写答案，多个空用逗号分隔"
              />
            )}
            {(String(currentQuestion.question.question_type || "").toLowerCase() === "written" ||
              (!currentQuestion.question.options &&
                !["fill_blank"].includes(
                  String(currentQuestion.question.question_type || "").toLowerCase(),
                ))) && (
              <textarea
                value={answers[activeIndex] || ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [activeIndex]: e.target.value }))}
                className="mt-3 h-28 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm"
                placeholder="请输入你的答案"
              />
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                onClick={() => setActiveIndex((idx) => Math.max(0, idx - 1))}
                disabled={activeIndex === 0}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
              >
                上一题
              </button>
              <button
                onClick={() => setActiveIndex((idx) => Math.min(questionState.results.length - 1, idx + 1))}
                disabled={activeIndex >= questionState.results.length - 1}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm disabled:opacity-40"
              >
                下一题
              </button>
              <button
                onClick={gradePractice}
                disabled={gradingPractice}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                {gradingPractice ? "评分中..." : practiceMode === "exam" ? "交卷并评分" : "提交本次练习并评分"}
              </button>
              <button
                type="button"
                onClick={returnToQuestionConfig}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
              >
                返回出题选择
              </button>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="text-base font-semibold text-slate-900">题目审核面板（增强）</h3>
            {currentQuestion.validation.audit ? (
              <div className="mt-3 grid gap-2 text-xs text-slate-700 md:grid-cols-2">
                <p>相关性：{currentQuestion.validation.audit.relevance}</p>
                <p>难度匹配：{currentQuestion.validation.audit.difficulty_alignment}</p>
                <p>答案唯一性：{currentQuestion.validation.audit.answer_uniqueness}</p>
                <p>干扰项质量：{currentQuestion.validation.audit.distractor_quality}</p>
                <p>表述清晰度：{currentQuestion.validation.audit.clarity}</p>
                <p>超纲风险：{currentQuestion.validation.audit.out_of_scope_risk}</p>
                <p>题干含糊：{currentQuestion.validation.audit.ambiguous_stem}</p>
                <p>LaTeX 格式异常：{currentQuestion.validation.audit.latex_format_issue}</p>
                <p>检索溯源条数：{currentQuestion.validation.audit.source_count ?? 0}</p>
                <p>干扰项候选数：{currentQuestion.validation.audit.distractor_candidate_count ?? 0}</p>
                <p>干扰项入选数：{currentQuestion.validation.audit.distractor_selected_count ?? 0}</p>
                <p>去重移除数：{currentQuestion.validation.audit.distractor_duplicate_removed ?? 0}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">暂无审核数据。</p>
            )}
            {Array.isArray(currentQuestion.question.source_refs) && currentQuestion.question.source_refs.length > 0 && (
              <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50/70 p-3">
                <p className="text-sm font-medium text-indigo-800">题目溯源</p>
                <div className="mt-2 space-y-2 text-xs text-indigo-900">
                  {(currentQuestion.question.source_refs as QuestionSourceRef[]).map((ref: QuestionSourceRef) => (
                    <div key={ref.id} className="rounded-lg bg-white/90 p-2">
                      <p className="font-medium">检索点：{ref.query}</p>
                      <p className="mt-1 whitespace-pre-wrap text-indigo-800">{ref.snippet}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {practiceReport && (
            <section className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold text-emerald-900">本次练习成绩单</h3>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      const name = `practice_report_${new Date(practiceReport.submitted_at).toISOString().replace(/[:.]/g, "-")}.json`;
                      downloadTextFile(name, JSON.stringify(practiceReport, null, 2), "application/json;charset=utf-8");
                    }}
                    className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100"
                  >
                    导出 JSON
                  </button>
                  <button
                    onClick={() => {
                      const name = `practice_report_${new Date(practiceReport.submitted_at).toISOString().replace(/[:.]/g, "-")}.csv`;
                      downloadTextFile(name, buildPracticeCsv(practiceReport), "text/csv;charset=utf-8");
                    }}
                    className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-100"
                  >
                    导出 CSV
                  </button>
                </div>
              </div>
              <p className="mt-1 text-sm text-emerald-800">
                得分：{practiceReport.total_score} / {practiceReport.max_score}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={returnToQuestionConfig}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
                >
                  返回出题选择
                </button>
                <button
                  onClick={returnToQuestionConfig}
                  className="rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-100"
                >
                  生成新题目
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {practiceReport.items.map((item, idx) => (
                  <div key={item.question_id} className="rounded-lg bg-white p-3 text-sm">
                    <p className="font-medium text-slate-900">
                      第 {idx + 1} 题：{item.status === "correct" ? "正确" : item.status === "partial" ? "部分正确" : "错误"}（{item.score}/{item.max_score}）
                    </p>
                    <p className="mt-1 text-slate-600">{item.reason}</p>
                    {item.explanation && (
                      <div className="mt-2 rounded-lg bg-slate-50 p-3 text-slate-700">
                        <p className="text-xs font-semibold text-slate-500">解析</p>
                        <p className="mt-1 whitespace-pre-wrap">{item.explanation}</p>
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button onClick={() => triggerFollowupGeneration(idx, "same")} className="rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs text-indigo-700 hover:bg-indigo-100">同知识点再练</button>
                      <button onClick={() => triggerFollowupGeneration(idx, "harder")} className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs text-rose-700 hover:bg-rose-100">提高难度</button>
                      <button onClick={() => triggerFollowupGeneration(idx, "easier")} className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs text-emerald-700 hover:bg-emerald-100">降低难度</button>
                      <button onClick={() => triggerFollowupGeneration(idx, "variant")} className="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-700 hover:bg-amber-100">变式题</button>
                      <button onClick={() => triggerFollowupGeneration(idx, "to_choice")} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-100">换成选择题</button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {isAssignmentMode && role === "teacher" && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-emerald-200 bg-gradient-to-r from-emerald-50 to-cyan-50 p-4">
            <div className="flex items-center gap-2 text-emerald-700"><BookOpenCheck className="h-5 w-5" /><p className="font-medium">作业评审流程</p></div>
            <p className="mt-1 text-sm text-emerald-700">系统会先解析作业得分点，再按学生答案逐点批改并沉淀错题。</p>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <section className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="mb-3 text-base font-semibold text-slate-900">创建作业草稿</h3>
              <div className="space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <select
                    value={assignmentCourseId ?? ""}
                    onChange={(e) => setAssignmentCourseId(Number(e.target.value) || null)}
                    className="rounded-xl border border-slate-200 px-3 py-2"
                  >
                    <option value="">不关联课程</option>
                    {assignmentCourseOptions.map((course) => (
                      <option key={course.id} value={course.id}>
                        {course.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={assignmentChapterId ?? ""}
                    onChange={(e) => setAssignmentChapterId(Number(e.target.value) || null)}
                    className="rounded-xl border border-slate-200 px-3 py-2"
                    disabled={!assignmentCourseId}
                  >
                    <option value="">不限定章节</option>
                    {assignmentChapters.map((chapter) => (
                      <option key={chapter.id} value={chapter.id}>
                        {chapter.order_index}. {chapter.title}
                      </option>
                    ))}
                  </select>
                </div>
                <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-xl border border-slate-200 px-3 py-2" placeholder="作业标题（必填）" />
                <textarea value={description} onChange={(e) => setDescription(e.target.value)} className="h-24 w-full rounded-xl border border-slate-200 px-3 py-2" placeholder="作业说明（可选）" />
                <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-indigo-700">任务要点与得分点草稿</p>
                    <button
                      onClick={generateRubricDraft}
                      disabled={draftingRubric}
                      className="inline-flex items-center gap-1 rounded-lg border border-indigo-200 bg-white px-3 py-1.5 text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                    >
                      {draftingRubric ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                      自动生成草稿
                    </button>
                  </div>
                  {taskPoints.length === 0 ? (
                    <p className="text-xs text-indigo-600/80">点击“自动生成草稿”后，这里会展示作业要考查的关键要求。</p>
                  ) : (
                    <ul className="space-y-1 text-xs text-indigo-700">
                      {taskPoints.map((point, idx) => (
                        <li key={`${point}-${idx}`}>{idx + 1}. {point}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <textarea value={criteriaText} onChange={(e) => setCriteriaText(e.target.value)} className="h-32 w-full rounded-xl border border-slate-200 px-3 py-2" placeholder="得分点：每行填写“题号|得分点|分值|判分依据”，留空时系统会在创建草稿时自动解析" />
                <div className="rounded-xl border border-slate-200 p-3">
                  <p className="mb-2 text-sm font-medium text-slate-700">上传作业附件</p>
                  <input type="file" multiple onChange={(e) => setTeacherFiles(Array.from(e.target.files || []))} className="w-full rounded-xl border border-slate-200 px-3 py-2" />
                  <p className="mt-1 text-xs text-slate-500">{FILE_HINT}</p>
                </div>
                <button onClick={createDraft} disabled={loading} className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm text-white hover:bg-emerald-700 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}创建草稿</button>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="mb-3 text-base font-semibold text-slate-900">发布前检查</h3>
              <ul className="space-y-2 text-sm text-slate-600">
                <li>1. 标题、说明、得分点是否完整。</li>
                <li>2. 发布前必须勾选确认。</li>
                <li>3. 未发布状态学生不可见。</li>
                <li>4. 发布后即可接收提交并评审。</li>
              </ul>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 xl:col-span-2">
              <div className="mb-3 flex items-center justify-between"><h3 className="text-base font-semibold text-slate-900">作业列表管理</h3><button onClick={loadTeacherAssignments} className="text-sm text-indigo-600 hover:text-indigo-700">刷新列表</button></div>
              {teacherAssignments.length === 0 ? <p className="text-sm text-slate-500">暂无作业草稿，请先创建。</p> : (
                <div className="space-y-3">{teacherAssignments.map((item) => (
                  <div key={item.id} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-medium text-slate-900">{item.title}</p><p className="text-xs text-slate-500">创建时间：{formatTime(item.created_at)} · {item.course_name || "未关联课程"}{item.chapter_title ? ` / ${item.chapter_title}` : ""}</p></div><span className={`rounded-full px-3 py-1 text-xs ${item.confirmed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{item.confirmed ? "已发布" : "草稿"}</span></div>
                    <div className="mt-3 flex justify-end">
                      <button
                        type="button"
                        onClick={() => deleteAssignment(item.id, item.title)}
                        disabled={loading}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-white px-2.5 py-1 text-xs text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                      >
                        <Trash2 className="h-3.5 w-3.5" />删除作业
                      </button>
                    </div>
                    <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                      <p className="font-medium text-slate-700">关联知识点</p>
                      {(item.knowledge_links || []).length === 0 ? (
                        <p className="mt-1">暂未匹配到已有知识点。</p>
                      ) : (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {(item.knowledge_links || []).map((link) => (
                            <span key={link.knowledge_point_id} className="rounded-full bg-white px-2 py-1 text-indigo-700">
                              {link.knowledge_point}
                            </span>
                          ))}
                        </div>
                      )}
                      {(item.knowledge_candidates || []).filter((candidate) => candidate.status !== "confirmed").length > 0 && (
                        <div className="mt-3">
                          <p className="font-medium text-amber-700">待确认候选知识点</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {(item.knowledge_candidates || [])
                              .filter((candidate) => candidate.status !== "confirmed")
                              .map((candidate) => (
                                <button
                                  key={candidate.candidate_id}
                                  onClick={() => confirmAssignmentCandidate(item, candidate)}
                                  className="rounded-full border border-amber-200 bg-white px-2 py-1 text-amber-700 hover:bg-amber-50"
                                >
                                  + {candidate.name}
                                </button>
                              ))}
                          </div>
                        </div>
                      )}
                      {(item.criteria_items || []).length > 0 && (
                        <div className="mt-3">
                          <p className="font-medium text-slate-700">作业得分点</p>
                          <div className="mt-2 grid gap-2 md:grid-cols-2">
                            {(item.criteria_items || []).slice(0, 8).map((criterion, idx) => (
                              <div key={`${item.id}-criterion-${criterion.id || idx}`} className="rounded-lg bg-white p-2 text-slate-700">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-medium text-slate-900">{criterion.question_no} · {criterion.criterion}</span>
                                  <span>{criterion.score} 分</span>
                                </div>
                                {criterion.answer_hint && <p className="mt-1">{criterion.answer_hint}</p>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                    {!item.confirmed && <div className="mt-3 flex flex-wrap items-center gap-3"><label className="inline-flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!publishChecks[item.id]} onChange={(e) => setPublishChecks((prev) => ({ ...prev, [item.id]: e.target.checked }))} />我确认该作业可以发布给学生</label><button onClick={() => publishAssignment(item.id)} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-700"><CheckCircle2 className="h-4 w-4" />确认发布</button></div>}
                  </div>
                ))}</div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 xl:col-span-2">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-semibold text-slate-900">学生提交评审</h3>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => exportSubmissionCollection(teacherSubmissions, "teacher_submissions", "json", "教师评审总览")}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    批量导出JSON
                  </button>
                  <button
                    onClick={() => exportSubmissionCollection(teacherSubmissions, "teacher_submissions", "md", "教师评审总览")}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    批量导出Markdown
                  </button>
                  <button
                    onClick={() => exportSubmissionCollection(teacherSubmissions, "teacher_submissions", "csv", "教师评审总览")}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                  >
                    批量导出CSV
                  </button>
                  <button onClick={loadTeacherSubmissions} className="text-sm text-indigo-600 hover:text-indigo-700">刷新提交</button>
                </div>
              </div>
              {teacherSubmissions.length === 0 ? <p className="text-sm text-slate-500">暂无学生提交。</p> : (
                <div className="space-y-4">{teacherSubmissions.map((sub) => {
                  const draft = reviewDrafts[sub.id] || buildReviewDraft(sub);
                  return (
                    <div key={sub.id} className="rounded-xl border border-slate-200 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-medium text-slate-900">{sub.assignment_title || sub.assignment_id}</p><p className="text-xs text-slate-500">学生：{sub.student_username} · 提交时间：{formatTime(sub.created_at)}</p></div><span className={`rounded-full px-3 py-1 text-xs ${sub.status === "reviewed" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{sub.status === "reviewed" ? "已评审" : "待评审"}</span></div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button onClick={() => exportSubmissionReport(sub, "json")} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50">导出JSON</button>
                        <button onClick={() => exportSubmissionReport(sub, "md")} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50">导出Markdown</button>
                        <button onClick={() => exportSubmissionReport(sub, "csv")} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50">导出CSV</button>
                      </div>
                      <div className="mt-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{sub.answer_text || "学生未填写文本答案（可能仅上传附件）。"}</div>
                      {sub.auto_review?.criterion_scores && sub.auto_review.criterion_scores.length > 0 && (
                        <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                          <p className="text-sm font-medium text-emerald-800">系统逐点初评</p>
                          <div className="mt-2 space-y-2">
                            {sub.auto_review.criterion_scores.map((item, idx) => (
                              <div key={`${sub.id}-auto-criterion-${idx}`} className="rounded-lg bg-white p-2 text-xs text-slate-700">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <span className="font-medium text-slate-900">{item.question_no} · {item.criterion}</span>
                                  <span className="text-emerald-700">{statusLabel(item.status)} · {item.score}/{item.max_score}</span>
                                </div>
                                {item.evidence && <p className="mt-1 text-slate-600">证据：{item.evidence}</p>}
                                {item.reason && <p className="mt-1 text-slate-600">理由：{item.reason}</p>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      {sub.auto_review?.knowledge_results && sub.auto_review.knowledge_results.length > 0 && (
                        <div className="mt-3 rounded-xl border border-indigo-100 bg-indigo-50/60 p-3">
                          <p className="text-sm font-medium text-indigo-800">知识点自动评审</p>
                          <div className="mt-2 grid gap-2 md:grid-cols-2">
                            {sub.auto_review.knowledge_results.map((result) => (
                              <div key={`${sub.id}-${result.knowledge_point_id || result.knowledge_point}`} className="rounded-lg bg-white p-2 text-xs text-slate-700">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-medium text-slate-900">{result.knowledge_point}</span>
                                  <span>{Math.round(result.score_ratio * 100)}%</span>
                                </div>
                                <p className="mt-1">{result.feedback}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="mt-3 grid gap-3 md:grid-cols-[140px_1fr]"><input value={draft.totalScore} onChange={(e) => updateDraft(sub.id, (c) => ({ ...c, totalScore: e.target.value }))} className="rounded-xl border border-slate-200 px-3 py-2" placeholder="总分 0-100" /><textarea value={draft.feedback} onChange={(e) => updateDraft(sub.id, (c) => ({ ...c, feedback: e.target.value }))} className="h-20 rounded-xl border border-slate-200 px-3 py-2" placeholder="总体评语" /></div>
                      <div className="mt-3 rounded-xl border border-slate-200 p-3">
                        <p className="mb-2 text-sm font-medium text-slate-700">得分点逐项批改</p>
                        <div className="space-y-3">
                          {draft.criterionScores.map((item, idx) => (
                            <div key={`${sub.id}-criterion-${idx}`} className="rounded-lg border border-slate-200 bg-slate-50/70 p-3">
                              <div className="grid gap-2 md:grid-cols-[110px_1fr_120px_120px]">
                                <input value={item.question_no} readOnly className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                                <input value={item.criterion} readOnly className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" />
                                <input value={item.score} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.criterionScores]; next[idx]={...next[idx],score:e.target.value}; return {...c,criterionScores:next}; })} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" placeholder={`/${item.max_score}`} />
                                <select value={item.status} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.criterionScores]; next[idx]={...next[idx],status:e.target.value}; return {...c,criterionScores:next}; })} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                                  <option value="hit">命中</option>
                                  <option value="partial">部分命中</option>
                                  <option value="missing">未命中</option>
                                </select>
                              </div>
                              <div className="mt-2 grid gap-2 md:grid-cols-3">
                                <textarea value={item.evidence} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.criterionScores]; next[idx]={...next[idx],evidence:e.target.value}; return {...c,criterionScores:next}; })} className="h-20 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" placeholder="学生答案证据" />
                                <textarea value={item.reason} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.criterionScores]; next[idx]={...next[idx],reason:e.target.value}; return {...c,criterionScores:next}; })} className="h-20 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" placeholder="判分理由" />
                                <textarea value={item.suggestion} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.criterionScores]; next[idx]={...next[idx],suggestion:e.target.value}; return {...c,criterionScores:next}; })} className="h-20 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm" placeholder="改进建议" />
                              </div>
                            </div>
                          ))}
                          {draft.criterionScores.length === 0 && <p className="text-sm text-slate-500">暂无得分点，建议重新生成作业得分点后再评审。</p>}
                        </div>
                      </div>
                      <div className="mt-3 rounded-xl border border-slate-200 p-3"><div className="mb-2 flex items-center justify-between"><p className="text-sm font-medium text-slate-700">结构化错题项（可选）</p><button onClick={() => updateDraft(sub.id, (c) => ({ ...c, wrongbookItems: [...c.wrongbookItems, { feedback: "", error_type: "", knowledge_point: "", suggestion: "" }] }))} className="text-xs text-indigo-600 hover:text-indigo-700">+ 新增错题项</button></div><div className="space-y-2">{draft.wrongbookItems.map((w, idx) => <div key={`${sub.id}-wrong-${idx}`} className="rounded-lg border border-slate-200 p-2"><div className="grid gap-2 md:grid-cols-2"><input value={w.error_type} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.wrongbookItems]; next[idx]={...next[idx],error_type:e.target.value}; return {...c,wrongbookItems:next}; })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="错误类型" /><input value={w.knowledge_point} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.wrongbookItems]; next[idx]={...next[idx],knowledge_point:e.target.value}; return {...c,wrongbookItems:next}; })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm" placeholder="知识点" /><input value={w.feedback} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.wrongbookItems]; next[idx]={...next[idx],feedback:e.target.value}; return {...c,wrongbookItems:next}; })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-2" placeholder="问题反馈" /><input value={w.suggestion} onChange={(e) => updateDraft(sub.id, (c) => { const next=[...c.wrongbookItems]; next[idx]={...next[idx],suggestion:e.target.value}; return {...c,wrongbookItems:next}; })} className="rounded-lg border border-slate-200 px-3 py-2 text-sm md:col-span-2" placeholder="改进建议" /></div></div>)}</div></div>
                      <div className="mt-3 flex justify-end"><button onClick={() => submitReview(sub.id)} disabled={loading} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">提交评审</button></div>
                    </div>
                  );
                })}</div>
              )}
            </section>
          </div>
        </div>
      )}

      {isAssignmentMode && role !== "teacher" && (
        <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="mb-3 text-base font-semibold text-slate-900">已发布作业</h3>
            {studentAssignments.length === 0 ? (
              <p className="text-sm text-slate-500">当前暂无可提交作业。</p>
            ) : (
              <div className="space-y-2">
                {studentAssignments.map((item) => (
                  <button key={item.id} onClick={() => setSelectedAssignmentId(item.id)} className={`w-full rounded-xl border px-3 py-2 text-left ${selectedAssignmentId === item.id ? "border-indigo-400 bg-indigo-50" : "border-slate-200"}`}>
                    <p className="font-medium text-slate-900">{item.title}</p>
                    <p className="text-xs text-slate-500">教师：{item.teacher_username}</p>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="mb-3 text-base font-semibold text-slate-900">提交作业</h3>
            {!selectedAssignment ? (
              <p className="text-sm text-slate-500">请先在左侧选择作业。</p>
            ) : (
              <div className="space-y-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
                  <p className="font-medium text-slate-900">{selectedAssignment.title}</p>
                  <p className="mt-1 text-slate-600">{selectedAssignment.description || "暂无说明"}</p>
                  {(selectedAssignment.knowledge_links || []).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {(selectedAssignment.knowledge_links || []).map((link) => (
                        <span key={link.knowledge_point_id} className="rounded-full bg-white px-2 py-1 text-indigo-700">
                          {link.knowledge_point}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <textarea value={submissionText} onChange={(e) => setSubmissionText(e.target.value)} className="h-28 w-full rounded-xl border border-slate-200 px-3 py-2" placeholder="请输入作答内容（可选）" />
                <div>
                  <input type="file" multiple onChange={(e) => setSubmissionFiles(Array.from(e.target.files || []))} className="w-full rounded-xl border border-slate-200 px-3 py-2" />
                  <p className="mt-1 text-xs text-slate-500">{FILE_HINT}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button onClick={submitAssignment} disabled={loading} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm text-white hover:bg-indigo-700 disabled:opacity-50">{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}提交作业</button>
                  <Link href="/wrongbook" className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm text-rose-700 hover:bg-rose-100"><FileText className="h-4 w-4" />错题本</Link>
                </div>
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5 xl:col-span-2">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-base font-semibold text-slate-900">我的提交记录</h3>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => exportSubmissionCollection(mySubmissions, "my_submissions", "json", "我的提交记录")}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                >
                  批量导出JSON
                </button>
                <button
                  onClick={() => exportSubmissionCollection(mySubmissions, "my_submissions", "md", "我的提交记录")}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                >
                  批量导出Markdown
                </button>
                <button
                  onClick={() => exportSubmissionCollection(mySubmissions, "my_submissions", "csv", "我的提交记录")}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50"
                >
                  批量导出CSV
                </button>
                <button onClick={loadMySubmissions} className="text-sm text-indigo-600 hover:text-indigo-700">刷新记录</button>
              </div>
            </div>
            {mySubmissions.length === 0 ? (
              <p className="text-sm text-slate-500">你还没有提交记录。</p>
            ) : (
              <div className="space-y-3">
                {mySubmissions.map((sub) => (
                  <div key={sub.id} className="rounded-xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium text-slate-900">作业 ID：{sub.assignment_id}</p>
                      <span className={`rounded-full px-3 py-1 text-xs ${sub.status === "reviewed" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{sub.status === "reviewed" ? "已评审" : "待评审"}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">提交时间：{formatTime(sub.created_at)}</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button onClick={() => exportSubmissionReport(sub, "json")} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50">导出JSON</button>
                      <button onClick={() => exportSubmissionReport(sub, "md")} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50">导出Markdown</button>
                      <button onClick={() => exportSubmissionReport(sub, "csv")} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 hover:bg-slate-50">导出CSV</button>
                    </div>
                    {sub.review ? (
                      <div className="mt-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900"><p>得分：{sub.review.total_score}</p><p className="mt-1">评语：{sub.review.feedback || "无"}</p></div>
                    ) : (
                      <div className="mt-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">教师尚未完成评审。</div>
                    )}
                    {sub.auto_review && (
                      <div className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50/70 p-3 text-sm">
                        <p className="font-semibold text-indigo-900">自动批改结构化报告</p>
                        <p className="mt-1 text-indigo-800">
                          相关性：{sub.auto_review.relevance_score} 分 · 参考总分：{sub.auto_review.total_score}
                        </p>
                        <p className="mt-1 text-indigo-800">{sub.auto_review.summary}</p>
                        {sub.auto_review.criterion_scores && sub.auto_review.criterion_scores.length > 0 && (
                          <div className="mt-3">
                            <p className="font-medium text-indigo-900">得分点明细</p>
                            <div className="mt-2 space-y-2">
                              {sub.auto_review.criterion_scores.map((item, idx) => (
                                <div key={`${sub.id}-student-criterion-${idx}`} className="rounded-lg bg-white/80 p-2 text-xs text-indigo-900">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                    <span className="font-medium">{item.question_no} · {item.criterion}</span>
                                    <span>{statusLabel(item.status)} · {item.score}/{item.max_score}</span>
                                  </div>
                                  {item.reason && <p className="mt-1">{item.reason}</p>}
                                  {item.suggestion && <p className="mt-1">建议：{item.suggestion}</p>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {sub.auto_review.knowledge_results && sub.auto_review.knowledge_results.length > 0 && (
                          <div className="mt-3">
                            <p className="font-medium text-indigo-900">知识点表现</p>
                            <div className="mt-2 grid gap-2 md:grid-cols-2">
                              {sub.auto_review.knowledge_results.map((result) => (
                                <div key={`${sub.id}-kp-${result.knowledge_point_id || result.knowledge_point}`} className="rounded-lg bg-white/80 p-2 text-xs text-indigo-900">
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="font-medium">{result.knowledge_point}</span>
                                    <span>{Math.round(result.score_ratio * 100)}%</span>
                                  </div>
                                  <p className="mt-1">{result.feedback}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {sub.auto_review.errors && sub.auto_review.errors.length > 0 && (
                          <div className="mt-2">
                            <p className="font-medium text-indigo-900">识别到的问题</p>
                            <ul className="mt-1 space-y-1 text-indigo-800">
                              {sub.auto_review.errors.map((err, idx) => (
                                <li key={`${sub.id}-err-${idx}`}>
                                  {idx + 1}. {err.detail}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {sub.auto_review.missing_points && sub.auto_review.missing_points.length > 0 && (
                          <div className="mt-2">
                            <p className="font-medium text-indigo-900">缺失要点</p>
                            <ul className="mt-1 space-y-1 text-indigo-800">
                              {sub.auto_review.missing_points.map((point, idx) => (
                                <li key={`${sub.id}-miss-${idx}`}>{idx + 1}. {point}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {sub.auto_review.suggestions && sub.auto_review.suggestions.length > 0 && (
                          <div className="mt-2">
                            <p className="font-medium text-indigo-900">改进建议</p>
                            <ul className="mt-1 space-y-1 text-indigo-800">
                              {sub.auto_review.suggestions.map((item, idx) => (
                                <li key={`${sub.id}-sug-${idx}`}>{idx + 1}. {item}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {message && (
        <div className="mt-4 inline-flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          <AlertCircle className="mt-0.5 h-4 w-4" />
          <span>{message}</span>
        </div>
      )}
    </div>
  );
}
