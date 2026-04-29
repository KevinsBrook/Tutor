"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bell,
  BookOpen,
  CheckCircle2,
  ClipboardList,
  FileText,
  PenTool,
  RefreshCw,
} from "lucide-react";

import { apiUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useGlobal } from "@/context/GlobalContext";

interface CourseOption {
  id: number;
  name: string;
}

interface ChapterOption {
  id: number;
  course_id: number;
  title: string;
  order_index: number;
}

interface KnowledgePointInfo {
  id: number;
  course_id: number;
  chapter_id?: number | null;
  name: string;
  description?: string;
  priority: number;
  is_confirmed?: boolean;
}

interface MaterialInfo {
  id: number;
  title: string;
  source_type: string;
  parse_status: string;
}

interface MasteryRow {
  knowledge_point: KnowledgePointInfo;
  course_id: number;
  course_name: string;
  chapter_id?: number | null;
  chapter_title: string;
  mastery_level: number;
  mastery_percent: number;
  band: string;
  priority: number;
  practice_count: number;
  correct_count: number;
  wrong_count: number;
  wrongbook_count: number;
  last_practiced_at?: string | null;
  recommendation?: string;
  related_materials?: MaterialInfo[];
}

interface StudentInfo {
  id: number;
  username: string;
  real_name: string;
  student_no?: string;
  class_name?: string;
}

interface TeacherMatrixRow extends MasteryRow {
  student: StudentInfo;
}

interface Reminder {
  id: string;
  teacher_name: string;
  student_username: string;
  knowledge_point_name: string;
  course_name: string;
  chapter_title?: string;
  content: string;
  created_at: string;
  read: boolean;
}

interface Summary {
  knowledge_point_count: number;
  mastered_count: number;
  basic_count?: number;
  forming_count?: number;
  weak_count: number;
  unpracticed_count?: number;
  average_mastery: number;
  student_count?: number;
  course_count?: number;
}

interface StudentPayload {
  courses: CourseOption[];
  chapters: ChapterOption[];
  summary: Summary;
  knowledge_points: MasteryRow[];
  reminders: Reminder[];
}

interface TeacherKnowledgeAggregate {
  knowledge_point: KnowledgePointInfo;
  course_name: string;
  chapter_title: string;
  priority: number;
  average_mastery?: number;
  mastery_percent?: number;
  weak_count?: number;
  unpracticed_count?: number;
  wrongbook_count?: number;
  student_count?: number;
}

interface TeacherPayload {
  courses: CourseOption[];
  chapters: ChapterOption[];
  summary: Summary;
  knowledge_points: TeacherKnowledgeAggregate[];
  matrix_rows: TeacherMatrixRow[];
  weak_knowledge_points: TeacherKnowledgeAggregate[];
  lagging_students: TeacherMatrixRow[];
  students: StudentInfo[];
}

const priorityOptions = [
  { value: "", label: "全部优先级" },
  { value: "5", label: "最高优先级" },
  { value: "4", label: "高优先级" },
  { value: "3", label: "中优先级" },
  { value: "2", label: "低优先级" },
  { value: "1", label: "最低优先级" },
];

function priorityLabel(priority: number) {
  const labels: Record<number, string> = {
    5: "最高",
    4: "高",
    3: "中",
    2: "低",
    1: "最低",
  };
  return labels[priority] || "中";
}

function formatDate(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "暂无";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function masteryTone(level: number) {
  if (level >= 0.8) return "bg-emerald-500";
  if (level >= 0.6) return "bg-sky-500";
  if (level >= 0.3) return "bg-amber-500";
  return "bg-rose-500";
}

function SummaryCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function FilterBar({
  courses,
  chapters,
  courseId,
  chapterId,
  priority,
  onCourseChange,
  onChapterChange,
  onPriorityChange,
}: {
  courses: CourseOption[];
  chapters: ChapterOption[];
  courseId: string;
  chapterId: string;
  priority: string;
  onCourseChange: (value: string) => void;
  onChapterChange: (value: string) => void;
  onPriorityChange: (value: string) => void;
}) {
  const visibleChapters = courseId
    ? chapters.filter((chapter) => String(chapter.course_id) === courseId)
    : chapters;

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <select
        value={courseId}
        onChange={(event) => {
          onCourseChange(event.target.value);
          onChapterChange("");
        }}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
      >
        <option value="">全部课程</option>
        {courses.map((course) => (
          <option key={course.id} value={course.id}>
            {course.name}
          </option>
        ))}
      </select>
      <select
        value={chapterId}
        onChange={(event) => onChapterChange(event.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
      >
        <option value="">全部章节</option>
        {visibleChapters.map((chapter) => (
          <option key={chapter.id} value={chapter.id}>
            第{chapter.order_index}章 {chapter.title}
          </option>
        ))}
      </select>
      <select
        value={priority}
        onChange={(event) => onPriorityChange(event.target.value)}
        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
      >
        {priorityOptions.map((item) => (
          <option key={item.value || "all"} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function MasteryBar({ percent, level }: { percent: number; level: number }) {
  return (
    <div className="flex min-w-[150px] items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${masteryTone(level)}`}
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </div>
      <span className="w-12 text-right text-xs font-medium text-slate-700">
        {percent.toFixed(1)}%
      </span>
    </div>
  );
}

export default function MasteryPage() {
  const { session } = useAuth();
  if (session?.role === "teacher") return <TeacherMasteryPage />;
  return <StudentMasteryPage />;
}

function StudentMasteryPage() {
  const router = useRouter();
  const { session } = useAuth();
  const { setQuestionState } = useGlobal();
  const [data, setData] = useState<StudentPayload | null>(null);
  const [courseId, setCourseId] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [priority, setPriority] = useState("");
  const [loading, setLoading] = useState(false);
  const [materialPointId, setMaterialPointId] = useState<number | null>(null);

  const loadData = async () => {
    if (!session?.username) return;
    setLoading(true);
    const params = new URLSearchParams({ student_username: session.username });
    if (courseId) params.set("course_id", courseId);
    if (chapterId) params.set("chapter_id", chapterId);
    if (priority) params.set("priority", priority);
    try {
      const response = await fetch(apiUrl(`/api/v1/courses/mastery-page/student?${params}`));
      const payload = await response.json();
      setData(payload);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.username, courseId, chapterId, priority]);

  const startQuestion = (row: MasteryRow) => {
    setQuestionState((prev) => ({
      ...prev,
      step: "config",
      mode: "knowledge",
      topic: row.knowledge_point.name,
      difficulty: row.mastery_level < 0.3 ? "easy" : "medium",
      type: "选择题",
      bloomLevel: prev.bloomLevel || "理解",
      count: 3,
      results: [],
      logs: [],
      progress: { stage: null, progress: {} },
    }));
    router.push("/question");
  };

  const markReminderRead = async (reminderId: string) => {
    if (!session?.username) return;
    await fetch(
      apiUrl(
        `/api/v1/courses/mastery-reminders/${reminderId}/read?student_username=${encodeURIComponent(session.username)}`,
      ),
      { method: "POST" },
    );
    await loadData();
  };

  const rows = data?.knowledge_points || [];
  const summary = data?.summary;
  const unreadCount = data?.reminders.filter((item) => !item.read).length || 0;

  return (
    <div className="min-h-[calc(100vh-7rem)] space-y-5 rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/85 p-6 shadow-[0_12px_40px_rgba(15,23,42,0.16)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">知识点掌握</h1>
        </div>
        <button
          onClick={loadData}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      <FilterBar
        courses={data?.courses || []}
        chapters={data?.chapters || []}
        courseId={courseId}
        chapterId={chapterId}
        priority={priority}
        onCourseChange={setCourseId}
        onChapterChange={setChapterId}
        onPriorityChange={setPriority}
      />

      <div className="grid gap-3 md:grid-cols-4">
        <SummaryCard label="知识点" value={summary?.knowledge_point_count || 0} />
        <SummaryCard
          label="平均掌握"
          value={`${Math.round((summary?.average_mastery || 0) * 100)}%`}
        />
        <SummaryCard label="已掌握" value={summary?.mastered_count || 0} />
        <SummaryCard label="待加强" value={summary?.weak_count || 0} hint={`未练习 ${summary?.unpracticed_count || 0}`} />
      </div>

      {data?.reminders && data.reminders.length > 0 && (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4">
          <div className="mb-3 flex items-center gap-2 font-semibold text-amber-900">
            <Bell className="h-5 w-5" />
            教师提醒 {unreadCount > 0 && <span className="text-xs text-amber-700">未读 {unreadCount}</span>}
          </div>
          <div className="space-y-2">
            {data.reminders.slice(0, 4).map((reminder) => (
              <div key={reminder.id} className="rounded-xl border border-amber-100 bg-white p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-800">
                    {reminder.course_name} · {reminder.knowledge_point_name}
                  </span>
                  <span className="text-xs text-slate-500">{formatDate(reminder.created_at)}</span>
                </div>
                <p className="mt-1 text-slate-600">{reminder.content}</p>
                {!reminder.read && (
                  <button
                    onClick={() => markReminderRead(reminder.id)}
                    className="mt-2 text-xs font-medium text-amber-700 hover:text-amber-900"
                  >
                    标为已读
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1.4fr] gap-3 border-b border-slate-100 bg-slate-50 px-4 py-3 text-xs font-medium text-slate-500">
          <span>知识点</span>
          <span>掌握程度</span>
          <span>练习证据</span>
          <span>错题</span>
          <span>操作</span>
        </div>
        {rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">当前筛选下暂无知识点掌握记录。</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {rows.map((row) => (
              <div key={row.knowledge_point.id}>
                <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1.4fr] items-center gap-3 px-4 py-4 text-sm">
                  <div>
                    <div className="font-semibold text-slate-900">{row.knowledge_point.name}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {row.course_name} · {row.chapter_title} · {priorityLabel(row.priority)}优先级
                    </div>
                  </div>
                  <MasteryBar percent={row.mastery_percent} level={row.mastery_level} />
                  <div className="text-xs text-slate-600">
                    <div>正确 {row.correct_count} · 错误 {row.wrong_count}</div>
                    <div>最近 {formatDate(row.last_practiced_at)}</div>
                  </div>
                  <div className="text-sm font-semibold text-rose-600">{row.wrongbook_count}</div>
                  <div className="flex flex-wrap gap-2">
                    <button onClick={() => startQuestion(row)} className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white">
                      <PenTool className="h-3.5 w-3.5" />
                      生成新题
                    </button>
                    <button onClick={() => router.push("/wrongbook")} className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-xs font-medium text-rose-700">
                      <ClipboardList className="h-3.5 w-3.5" />
                      查看错题
                    </button>
                    <button onClick={() => router.push("/wrongbook")} className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-700">
                      重做错题
                    </button>
                    <button
                      onClick={() =>
                        setMaterialPointId((current) =>
                          current === row.knowledge_point.id ? null : row.knowledge_point.id,
                        )
                      }
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-700"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      相关资料
                    </button>
                  </div>
                </div>
                {materialPointId === row.knowledge_point.id && (
                  <div className="mx-4 mb-4 rounded-xl border border-slate-100 bg-slate-50 p-3">
                    {row.related_materials && row.related_materials.length > 0 ? (
                      <div className="grid gap-2 md:grid-cols-2">
                        {row.related_materials.map((material) => (
                          <button
                            key={material.id}
                            onClick={() => router.push("/knowledge")}
                            className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 hover:border-indigo-200"
                          >
                            <span className="font-medium">{material.title}</span>
                            <span className="text-slate-400">{material.parse_status}</span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="text-xs text-slate-500">暂无直接关联资料，可到课程中心查看本章节资料。</div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TeacherMasteryPage() {
  const { session } = useAuth();
  const [data, setData] = useState<TeacherPayload | null>(null);
  const [courseId, setCourseId] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [priority, setPriority] = useState("");
  const [studentUsername, setStudentUsername] = useState("");
  const [knowledgePointId, setKnowledgePointId] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");

  const loadData = async () => {
    if (!session?.username) return;
    setLoading(true);
    const params = new URLSearchParams({ teacher_username: session.username });
    if (courseId) params.set("course_id", courseId);
    if (chapterId) params.set("chapter_id", chapterId);
    if (priority) params.set("priority", priority);
    try {
      const response = await fetch(apiUrl(`/api/v1/courses/mastery-page/teacher?${params}`));
      const payload = await response.json();
      setData(payload);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.username, courseId, chapterId, priority]);

  const reminderPoints = useMemo(() => {
    const map = new Map<number, TeacherKnowledgeAggregate>();
    for (const item of data?.knowledge_points || []) {
      map.set(item.knowledge_point.id, item);
    }
    return Array.from(map.values());
  }, [data?.knowledge_points]);

  const sendReminder = async () => {
    if (!session?.username || !studentUsername || !knowledgePointId || !content.trim()) {
      setNotice("请选择学生、知识点，并填写提醒内容。");
      return;
    }
    setSending(true);
    setNotice("");
    try {
      const response = await fetch(apiUrl("/api/v1/courses/mastery-reminders"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_username: session.username,
          student_username: studentUsername,
          knowledge_point_id: Number(knowledgePointId),
          content,
        }),
      });
      if (!response.ok) throw new Error("send failed");
      setContent("");
      setNotice("提醒已发送，学生端会在知识点掌握页看到。");
    } catch {
      setNotice("提醒发送失败，请稍后重试。");
    } finally {
      setSending(false);
    }
  };

  const summary = data?.summary;

  return (
    <div className="min-h-[calc(100vh-7rem)] space-y-5 rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/85 p-6 shadow-[0_12px_40px_rgba(15,23,42,0.16)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">知识点掌握</h1>
        </div>
        <button
          onClick={loadData}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      <FilterBar
        courses={data?.courses || []}
        chapters={data?.chapters || []}
        courseId={courseId}
        chapterId={chapterId}
        priority={priority}
        onCourseChange={setCourseId}
        onChapterChange={setChapterId}
        onPriorityChange={setPriority}
      />

      <div className="grid gap-3 md:grid-cols-5">
        <SummaryCard label="学生数" value={summary?.student_count || 0} />
        <SummaryCard label="课程数" value={summary?.course_count || 0} />
        <SummaryCard label="知识点记录" value={summary?.knowledge_point_count || 0} />
        <SummaryCard label="平均掌握" value={`${Math.round((summary?.average_mastery || 0) * 100)}%`} />
        <SummaryCard label="薄弱记录" value={summary?.weak_count || 0} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2 font-semibold text-slate-900">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            整体薄弱知识点
          </div>
          <div className="space-y-2">
            {(data?.weak_knowledge_points || []).slice(0, 8).map((item) => (
              <div key={item.knowledge_point.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{item.knowledge_point.name}</span>
                  <span className="text-xs text-slate-500">{priorityLabel(item.priority)}优先级</span>
                </div>
                <div className="mt-2 flex items-center justify-between gap-3 text-xs text-slate-500">
                  <span>{item.course_name} · {item.chapter_title || "公共资料"}</span>
                  <span>平均 {item.mastery_percent?.toFixed(1) || "0.0"}% · 薄弱 {item.weak_count || 0}</span>
                </div>
              </div>
            ))}
            {data?.weak_knowledge_points.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
                当前筛选下暂无薄弱知识点。
              </div>
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2 font-semibold text-slate-900">
            <Bell className="h-5 w-5 text-indigo-500" />
            发送学习提醒
          </div>
          <div className="space-y-3">
            <select
              value={studentUsername}
              onChange={(event) => setStudentUsername(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="">选择学生</option>
              {(data?.students || []).map((student) => (
                <option key={student.id} value={student.username}>
                  {student.real_name || student.username} {student.class_name ? `· ${student.class_name}` : ""}
                </option>
              ))}
            </select>
            <select
              value={knowledgePointId}
              onChange={(event) => setKnowledgePointId(event.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <option value="">选择知识点</option>
              {reminderPoints.map((item) => (
                <option key={item.knowledge_point.id} value={item.knowledge_point.id}>
                  {item.knowledge_point.name}
                </option>
              ))}
            </select>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={4}
              className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm"
              placeholder="写给学生的提醒内容"
            />
            <button
              onClick={sendReminder}
              disabled={sending}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              <Bell className="h-4 w-4" />
              {sending ? "发送中..." : "发送提醒"}
            </button>
            {notice && <div className="text-xs text-slate-500">{notice}</div>}
          </div>
        </section>
      </div>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="grid grid-cols-[1fr_1.2fr_1fr_1fr_0.8fr] gap-3 border-b border-slate-100 bg-slate-50 px-4 py-3 text-xs font-medium text-slate-500">
          <span>学生</span>
          <span>知识点</span>
          <span>掌握程度</span>
          <span>证据</span>
          <span>状态</span>
        </div>
        {(data?.lagging_students || []).length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">当前筛选下暂无需要重点关注的学生。</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {(data?.lagging_students || []).map((row) => (
              <div
                key={`${row.student.id}-${row.knowledge_point.id}`}
                className="grid grid-cols-[1fr_1.2fr_1fr_1fr_0.8fr] items-center gap-3 px-4 py-4 text-sm"
              >
                <div>
                  <div className="font-semibold text-slate-900">{row.student.real_name || row.student.username}</div>
                  <div className="text-xs text-slate-500">{row.student.class_name || row.student.student_no || "未填写班级"}</div>
                </div>
                <div>
                  <div className="font-medium text-slate-900">{row.knowledge_point.name}</div>
                  <div className="text-xs text-slate-500">{row.course_name} · {row.chapter_title}</div>
                </div>
                <MasteryBar percent={row.mastery_percent} level={row.mastery_level} />
                <div className="text-xs text-slate-600">
                  <div>正确 {row.correct_count} · 错误 {row.wrong_count}</div>
                  <div>错题 {row.wrongbook_count} · 最近 {formatDate(row.last_practiced_at)}</div>
                </div>
                <div className="inline-flex w-fit items-center gap-1 rounded-full bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  待关注
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center gap-2 font-semibold text-slate-900">
          <BookOpen className="h-5 w-5 text-emerald-500" />
          全部掌握记录
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {(data?.matrix_rows || []).slice(0, 36).map((row) => (
            <div key={`${row.student.id}-${row.knowledge_point.id}-all`} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-medium text-slate-900">{row.student.real_name || row.student.username}</div>
                  <div className="mt-1 text-xs text-slate-500">{row.knowledge_point.name}</div>
                </div>
                {row.mastery_level >= 0.8 ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                ) : (
                  <AlertTriangle className="h-5 w-5 text-amber-500" />
                )}
              </div>
              <div className="mt-3">
                <MasteryBar percent={row.mastery_percent} level={row.mastery_level} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
