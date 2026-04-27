"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  FileText,
  GraduationCap,
  Layers,
  Loader2,
  Network,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
  X,
} from "lucide-react";

import { useAuth } from "@/context/AuthContext";
import { apiUrl } from "@/lib/api";

interface Course {
  id: number;
  name: string;
  description: string;
  teacher_name?: string;
  status: string;
  chapter_count: number;
  material_count: number;
  knowledge_point_count: number;
}

interface Chapter {
  id: number;
  course_id: number;
  title: string;
  description: string;
  order_index: number;
  material_count: number;
  knowledge_point_count: number;
}

interface Material {
  id: number;
  course_id: number;
  chapter_id?: number | null;
  chapter_title?: string;
  title: string;
  display_name?: string;
  description: string;
  source_type: string;
  original_filename?: string | null;
  file_type?: string | null;
  kb_name?: string | null;
  rag_provider?: string | null;
  parse_status: string;
}

interface KnowledgeBaseProgress {
  stage?: string;
  message?: string;
  current?: number;
  total?: number;
  file_name?: string;
  progress_percent?: number;
  percent?: number;
  error?: string;
}

interface KnowledgeMastery {
  mastery_level: number;
  correct_count: number;
  wrong_count: number;
  practice_count: number;
}

interface KnowledgePoint {
  id: number;
  course_id: number;
  chapter_id?: number | null;
  chapter_title?: string;
  source_material_id?: number | null;
  source_material_title?: string;
  name: string;
  description: string;
  priority: number;
  source_type: string;
  is_confirmed: boolean;
  mastery?: KnowledgeMastery;
}

interface RagProvider {
  id: string;
  name: string;
  description?: string;
  supported_extensions?: string[];
}

interface KnowledgeGraphPreview {
  kb_name: string;
  rag_provider?: string;
  nodes: Array<{ id: string; label?: string; degree?: number }>;
  edges: Array<{ id: string; source: string; target: string; label?: string }>;
  stats?: { returned_nodes?: number; returned_edges?: number; truncated?: boolean };
  message?: string;
}

type ModalKind = "course" | "chapter" | "upload" | "point" | null;

const FALLBACK_PROVIDERS: RagProvider[] = [
  { id: "raganything", name: "RAG-Anything", description: "适合课件、教材、图文混合资料" },
  { id: "lightrag", name: "LightRAG", description: "适合轻量知识图谱检索" },
  { id: "llamaindex", name: "LlamaIndex", description: "适合普通文本和 PDF 检索" },
];

const PROVIDER_EXTENSIONS: Record<string, string[]> = {
  raganything: [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md", ".html", ".htm"],
  raganything_docling: [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md", ".html", ".htm"],
  lightrag: [".pdf", ".txt", ".md", ".html", ".htm", ".json"],
  llamaindex: [".pdf", ".txt", ".md", ".html", ".htm", ".json"],
};

const SOURCE_LABELS: Record<string, string> = {
  teacher_material: "教师资料",
  student_note: "学生笔记",
  assignment_question: "作业题目",
  wrongbook_practice: "错题练习",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "待解析",
  uploaded: "已上传",
  parsing: "解析中",
  parsed: "已解析",
  failed: "解析失败",
};

const PRIORITY_OPTIONS = [
  { value: "5", label: "核心" },
  { value: "4", label: "高" },
  { value: "3", label: "中" },
  { value: "2", label: "低" },
  { value: "1", label: "了解" },
];

const progressPercent = (progress?: KnowledgeBaseProgress) => {
  const raw = progress?.progress_percent ?? progress?.percent ?? 0;
  return Math.max(0, Math.min(100, Number(raw) || 0));
};

const progressLabel = (progress?: KnowledgeBaseProgress) => {
  if (!progress) return "等待解析任务开始";
  if (progress.error) return progress.error;
  const name = progress.file_name ? `：${progress.file_name}` : "";
  const count = progress.total ? `（${progress.current || 0}/${progress.total}）` : "";
  return `${progress.message || progress.stage || "解析中"}${name}${count}`;
};

const materialName = (material: Material) =>
  material.display_name || material.title || material.original_filename || "未命名资料";

export default function CourseKnowledgePanel({ courseId }: { courseId?: number }) {
  const { session } = useAuth();
  const isTeacher = session?.role === "teacher";
  const isStudent = session?.role === "student";

  const [courses, setCourses] = useState<Course[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [points, setPoints] = useState<KnowledgePoint[]>([]);
  const [providers, setProviders] = useState<RagProvider[]>(FALLBACK_PROVIDERS);
  const [selectedChapterId, setSelectedChapterId] = useState<number | null>(null);
  const [modal, setModal] = useState<ModalKind>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState<Record<string, KnowledgeBaseProgress>>({});
  const [graphPreview, setGraphPreview] = useState<KnowledgeGraphPreview | null>(null);
  const [graphTitle, setGraphTitle] = useState("");
  const [graphLoading, setGraphLoading] = useState(false);

  const [courseForm, setCourseForm] = useState({ name: "", description: "" });
  const [chapterForm, setChapterForm] = useState({ title: "", description: "", order_index: "1" });
  const [uploadForm, setUploadForm] = useState({ title: "", description: "" });
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [providerId, setProviderId] = useState("raganything");
  const [pointForm, setPointForm] = useState({ name: "", description: "", priority: "3" });

  const selectedCourse = useMemo(
    () => courses.find((course) => course.id === courseId) || null,
    [courses, courseId],
  );
  const selectedChapter = useMemo(
    () => chapters.find((chapter) => chapter.id === selectedChapterId) || null,
    [chapters, selectedChapterId],
  );
  const visibleMaterials = useMemo(
    () =>
      selectedChapterId === null
        ? materials.filter((item) => !item.chapter_id)
        : materials.filter((item) => item.chapter_id === selectedChapterId),
    [materials, selectedChapterId],
  );
  const visiblePoints = useMemo(
    () =>
      selectedChapterId === null
        ? points.filter((item) => !item.chapter_id)
        : points.filter((item) => item.chapter_id === selectedChapterId),
    [points, selectedChapterId],
  );
  const nextChapterOrder = useMemo(() => {
    if (!chapters.length) return 1;
    return Math.max(...chapters.map((chapter) => chapter.order_index || 0)) + 1;
  }, [chapters]);
  const selectedProvider = providers.find((provider) => provider.id === providerId) || providers[0];
  const selectedExtensions =
    selectedProvider?.supported_extensions || PROVIDER_EXTENSIONS[providerId] || PROVIDER_EXTENSIONS.raganything;

  const requestJson = async <T,>(url: string, options?: RequestInit): Promise<T> => {
    const res = await fetch(apiUrl(url), options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "操作失败，请稍后重试");
    return data as T;
  };

  const loadProviders = async () => {
    try {
      const data = await requestJson<{ providers?: RagProvider[] }>("/api/v1/knowledge/rag-providers");
      const next = (data.providers?.length ? data.providers : FALLBACK_PROVIDERS).map((provider) => ({
        ...provider,
        supported_extensions:
          provider.supported_extensions || PROVIDER_EXTENSIONS[provider.id] || PROVIDER_EXTENSIONS.raganything,
      }));
      setProviders(next);
      setProviderId((prev) => (next.some((item) => item.id === prev) ? prev : next[0]?.id || "raganything"));
    } catch {
      setProviders(FALLBACK_PROVIDERS);
    }
  };

  const loadCourses = async () => {
    if (!session?.username) return;
    setLoading(true);
    setMessage("");
    try {
      const query = isTeacher ? `?teacher_username=${encodeURIComponent(session.username)}` : "";
      const data = await requestJson<{ courses: Course[] }>(`/api/v1/courses${query}`);
      setCourses(data.courses || []);
    } catch (error: any) {
      setMessage(error.message || "课程加载失败");
    } finally {
      setLoading(false);
    }
  };

  const loadCourseDetail = async (id: number, silent = false) => {
    if (!silent) {
      setLoading(true);
      setMessage("");
    }
    try {
      const pointQuery =
        isStudent && session?.username
          ? `?student_username=${encodeURIComponent(session.username)}&confirmed_only=true`
          : "";
      const [chapterData, materialData, pointData] = await Promise.all([
        requestJson<{ chapters: Chapter[] }>(`/api/v1/courses/${id}/chapters`),
        requestJson<{ materials: Material[] }>(`/api/v1/courses/${id}/materials`),
        requestJson<{ knowledge_points: KnowledgePoint[] }>(`/api/v1/courses/${id}/knowledge-points${pointQuery}`),
      ]);
      const nextChapters = chapterData.chapters || [];
      setChapters(nextChapters);
      setMaterials(materialData.materials || []);
      setPoints(pointData.knowledge_points || []);
      setSelectedChapterId((prev) => {
        if (prev === null) return nextChapters[0]?.id ?? null;
        return nextChapters.some((chapter) => chapter.id === prev) ? prev : nextChapters[0]?.id ?? null;
      });
    } catch (error: any) {
      if (!silent) setMessage(error.message || "课程详情加载失败");
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const refresh = async () => {
    await loadCourses();
    if (courseId) await loadCourseDetail(courseId, true);
  };

  const loadMaterialProgress = async () => {
    const kbNames = Array.from(
      new Set(
        materials
          .filter((item) => item.kb_name && !["parsed", "failed"].includes(item.parse_status))
          .map((item) => item.kb_name as string),
      ),
    );
    if (!kbNames.length) return;
    const entries = await Promise.all(
      kbNames.map(async (kbName) => {
        try {
          return [
            kbName,
            await requestJson<KnowledgeBaseProgress>(`/api/v1/knowledge/${encodeURIComponent(kbName)}/progress`),
          ] as const;
        } catch {
          return [kbName, null] as const;
        }
      }),
    );
    setProgress((prev) => {
      const next = { ...prev };
      entries.forEach(([kbName, item]) => {
        if (item) next[kbName] = item;
      });
      return next;
    });
  };

  useEffect(() => {
    loadProviders();
  }, []);

  useEffect(() => {
    loadCourses();
  }, [session?.username, session?.role]);

  useEffect(() => {
    if (courseId) loadCourseDetail(courseId);
  }, [courseId, session?.username, session?.role]);

  useEffect(() => {
    setChapterForm((prev) => ({ ...prev, order_index: String(nextChapterOrder) }));
  }, [nextChapterOrder]);

  useEffect(() => {
    if (!courseId || !materials.some((item) => item.kb_name && !["parsed", "failed"].includes(item.parse_status))) {
      return;
    }
    loadMaterialProgress();
    const timer = window.setInterval(() => {
      loadMaterialProgress();
      loadCourseDetail(courseId, true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [materials, courseId]);

  const createCourse = async () => {
    if (!session?.username || !courseForm.name.trim()) return;
    setLoading(true);
    try {
      const data = await requestJson<{ course: Course }>("/api/v1/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_username: session.username,
          name: courseForm.name.trim(),
          description: courseForm.description.trim(),
        }),
      });
      setCourseForm({ name: "", description: "" });
      setModal(null);
      await loadCourses();
      window.location.href = `/knowledge/courses/${data.course.id}`;
    } catch (error: any) {
      setMessage(error.message || "课程创建失败");
    } finally {
      setLoading(false);
    }
  };

  const createChapter = async () => {
    if (!session?.username || !courseId || !chapterForm.title.trim()) return;
    setLoading(true);
    try {
      const data = await requestJson<{ chapter: Chapter }>(`/api/v1/courses/${courseId}/chapters`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_username: session.username,
          title: chapterForm.title.trim(),
          description: chapterForm.description.trim(),
          order_index: Number(chapterForm.order_index) || nextChapterOrder,
        }),
      });
      setChapterForm({ title: "", description: "", order_index: String(nextChapterOrder + 1) });
      setModal(null);
      await loadCourseDetail(courseId, true);
      setSelectedChapterId(data.chapter.id);
    } catch (error: any) {
      setMessage(error.message || "章节创建失败");
    } finally {
      setLoading(false);
    }
  };

  const uploadMaterial = async () => {
    if (!session?.username || !courseId || !uploadFile) return;
    const ext = `.${uploadFile.name.split(".").pop()?.toLowerCase() || ""}`;
    if (!selectedExtensions.includes(ext)) {
      setMessage(`${selectedProvider?.name || providerId} 不支持 ${ext} 文件，请选择：${selectedExtensions.join(" / ")}`);
      return;
    }
    setLoading(true);
    try {
      const form = new FormData();
      form.append("uploader_username", session.username);
      form.append("title", (uploadForm.title || uploadFile.name).trim());
      form.append("description", uploadForm.description.trim());
      form.append("source_type", isTeacher ? "teacher_material" : "student_note");
      form.append("material_scope", selectedChapterId ? "chapter" : "course_public");
      form.append("rag_provider", providerId);
      if (selectedChapterId) form.append("chapter_id", String(selectedChapterId));
      form.append("file", uploadFile);
      await requestJson(`/api/v1/courses/${courseId}/materials/upload`, { method: "POST", body: form });
      setUploadForm({ title: "", description: "" });
      setUploadFile(null);
      setModal(null);
      await loadCourseDetail(courseId, true);
      setMessage("资料已上传，解析完成后即可用于出题与检索");
    } catch (error: any) {
      setMessage(error.message || "资料上传失败");
    } finally {
      setLoading(false);
    }
  };

  const createPoint = async () => {
    if (!session?.username || !courseId || !pointForm.name.trim()) return;
    setLoading(true);
    try {
      await requestJson(`/api/v1/courses/${courseId}/knowledge-points`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_username: session.username,
          chapter_id: selectedChapterId,
          name: pointForm.name.trim(),
          description: pointForm.description.trim(),
          priority: Number(pointForm.priority) || 3,
          source_type: "teacher_material",
          is_confirmed: true,
        }),
      });
      setPointForm({ name: "", description: "", priority: "3" });
      setModal(null);
      await loadCourseDetail(courseId, true);
    } catch (error: any) {
      setMessage(error.message || "知识点创建失败");
    } finally {
      setLoading(false);
    }
  };

  const deleteCourse = async (course: Course) => {
    if (!session?.username || !window.confirm(`确定删除课程“${course.name}”吗？`)) return;
    await requestJson(`/api/v1/courses/${course.id}?teacher_username=${encodeURIComponent(session.username)}`, {
      method: "DELETE",
    });
    await loadCourses();
  };

  const deleteChapter = async (chapter: Chapter) => {
    if (!session?.username || !courseId || !window.confirm(`确定删除章节“${chapter.title}”吗？`)) return;
    await requestJson(`/api/v1/courses/chapters/${chapter.id}?teacher_username=${encodeURIComponent(session.username)}`, {
      method: "DELETE",
    });
    await loadCourseDetail(courseId, true);
  };

  const deleteMaterial = async (material: Material) => {
    if (!session?.username || !courseId || !window.confirm(`确定删除资料“${materialName(material)}”吗？`)) return;
    await requestJson(`/api/v1/courses/materials/${material.id}?operator_username=${encodeURIComponent(session.username)}`, {
      method: "DELETE",
    });
    await loadCourseDetail(courseId, true);
  };

  const deletePoint = async (point: KnowledgePoint) => {
    if (!session?.username || !courseId || !window.confirm(`确定删除知识点“${point.name}”吗？`)) return;
    await requestJson(
      `/api/v1/courses/knowledge-points/${point.id}?teacher_username=${encodeURIComponent(session.username)}`,
      { method: "DELETE" },
    );
    await loadCourseDetail(courseId, true);
  };

  const recordMastery = async (point: KnowledgePoint, isCorrect: boolean) => {
    if (!session?.username || !courseId) return;
    await requestJson(`/api/v1/courses/knowledge-points/${point.id}/mastery-events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_username: session.username,
        source_type: "manual",
        is_correct: isCorrect,
        note: "课程中心手动练习反馈",
      }),
    });
    await loadCourseDetail(courseId, true);
  };

  const openGraph = async (material: Material) => {
    if (!material.kb_name) return;
    setGraphLoading(true);
    setGraphTitle(materialName(material));
    try {
      const data = await requestJson<KnowledgeGraphPreview>(
        `/api/v1/knowledge/${encodeURIComponent(material.kb_name)}/graph?max_nodes=80&max_edges=160&min_degree=0&filter_noise=true`,
      );
      setGraphPreview(data);
    } catch (error: any) {
      setGraphPreview(null);
      setMessage(error.message || "知识图谱加载失败，可能仍在解析中");
    } finally {
      setGraphLoading(false);
    }
  };

  const handleUploadFile = (file: File | null) => {
    setUploadFile(file);
    if (file) {
      setUploadForm((prev) => ({ ...prev, title: prev.title || file.name }));
    }
  };

  if (!session?.username) {
    return (
      <section className="mb-6 rounded-lg border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
        <p className="text-sm text-slate-500">请先登录后查看课程中心。</p>
      </section>
    );
  }

  const actionButton =
    "inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800";

  if (!courseId) {
    return (
      <section className="mb-8 rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
              <GraduationCap className="h-6 w-6 text-emerald-600" />
              课程中心
            </h1>
            <p className="mt-1 text-sm text-slate-500">按课程组织章节、资料和知识点，课程资料不会出现在底层知识库列表中。</p>
          </div>
          <div className="flex gap-2">
            <button className={actionButton} onClick={refresh} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              刷新
            </button>
            {isTeacher && (
              <button className={actionButton} onClick={() => setModal("course")}>
                <Plus className="h-4 w-4" />
                新建课程
              </button>
            )}
          </div>
        </div>

        {message && <div className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">{message}</div>}

        {loading && courses.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-slate-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载课程
          </div>
        ) : courses.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-700">
            暂无课程。教师可以从右上角创建第一门课程。
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {courses.map((course) => (
              <Link
                key={course.id}
                href={`/knowledge/courses/${course.id}`}
                className="group rounded-lg border border-slate-200 p-4 transition hover:border-emerald-300 hover:bg-emerald-50/40 dark:border-slate-800 dark:hover:border-emerald-800 dark:hover:bg-emerald-950/20"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-semibold text-slate-950 dark:text-slate-50">{course.name}</h2>
                    <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-500">
                      {course.description || "暂无课程说明"}
                    </p>
                  </div>
                  {isTeacher && (
                    <button
                      className="rounded-md p-1 text-slate-400 hover:bg-white hover:text-red-600"
                      onClick={(event) => {
                        event.preventDefault();
                        deleteCourse(course);
                      }}
                      title="删除课程"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
                </div>
                <div className="mt-4 grid grid-cols-3 gap-2 text-xs text-slate-500">
                  <span className="rounded-md bg-slate-50 px-2 py-1 dark:bg-slate-800">{course.chapter_count} 章</span>
                  <span className="rounded-md bg-slate-50 px-2 py-1 dark:bg-slate-800">{course.material_count} 份资料</span>
                  <span className="rounded-md bg-slate-50 px-2 py-1 dark:bg-slate-800">{course.knowledge_point_count} 个知识点</span>
                </div>
              </Link>
            ))}
          </div>
        )}

        <CourseModal
          open={modal === "course"}
          loading={loading}
          form={courseForm}
          setForm={setCourseForm}
          onClose={() => setModal(null)}
          onSubmit={createCourse}
        />
      </section>
    );
  }

  return (
    <section className="mb-8 rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-200 p-5 dark:border-slate-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <Link href="/knowledge" className="mb-2 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900">
              <ArrowLeft className="h-4 w-4" />
              返回课程列表
            </Link>
            <h1 className="truncate text-2xl font-semibold text-slate-950 dark:text-slate-50">
              {selectedCourse?.name || "课程详情"}
            </h1>
            <p className="mt-1 text-sm text-slate-500">{selectedCourse?.description || "暂无课程说明"}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className={actionButton} onClick={refresh} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              刷新
            </button>
            {isTeacher && (
              <>
                <button className={actionButton} onClick={() => setModal("chapter")}>
                  <Plus className="h-4 w-4" />
                  新建章节
                </button>
                <button className={actionButton} onClick={() => setModal("upload")}>
                  <Upload className="h-4 w-4" />
                  上传资料
                </button>
                <button className={actionButton} onClick={() => setModal("point")}>
                  <BookOpen className="h-4 w-4" />
                  新增知识点
                </button>
              </>
            )}
          </div>
        </div>
        {message && <div className="mt-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-700">{message}</div>}
      </div>

      <div className="grid min-h-[520px] lg:grid-cols-[280px_1fr]">
        <aside className="border-b border-slate-200 p-4 dark:border-slate-800 lg:border-b-0 lg:border-r">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
            <Layers className="h-4 w-4" />
            章节
          </div>
          <button
            className={`mb-2 w-full rounded-md px-3 py-2 text-left text-sm ${
              selectedChapterId === null
                ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                : "text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800"
            }`}
            onClick={() => setSelectedChapterId(null)}
          >
            课程公共资料
          </button>
          <div className="space-y-1">
            {chapters.map((chapter) => (
              <button
                key={chapter.id}
                className={`group w-full rounded-md px-3 py-2 text-left ${
                  selectedChapterId === chapter.id
                    ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                    : "text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
                onClick={() => setSelectedChapterId(chapter.id)}
              >
                <span className="block truncate text-sm font-medium">
                  {chapter.order_index}. {chapter.title}
                </span>
                <span className="mt-1 block text-xs text-slate-500">
                  {chapter.material_count} 份资料 · {chapter.knowledge_point_count} 个知识点
                </span>
              </button>
            ))}
          </div>
        </aside>

        <main className="p-5">
          {loading && chapters.length === 0 ? (
            <div className="flex h-64 items-center justify-center text-sm text-slate-500">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              正在加载课程内容
            </div>
          ) : (
            <div className="space-y-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold text-slate-950 dark:text-slate-50">
                    {selectedChapter ? selectedChapter.title : "课程公共资料"}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {selectedChapter?.description || "当前区域可查看资料、知识点和解析状态。"}
                  </p>
                </div>
                {isTeacher && selectedChapter && (
                  <button className="rounded-md p-2 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={() => deleteChapter(selectedChapter)} title="删除章节">
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
                  <FileText className="h-4 w-4 text-teal-600" />
                  本章节资料
                </div>
                {visibleMaterials.length === 0 ? (
                  <Empty text="暂无资料。教师可通过右上角上传，学生资料会作为章节笔记归档。" />
                ) : (
                  <div className="grid gap-3 xl:grid-cols-2">
                    {visibleMaterials.map((material) => {
                      const itemProgress = material.kb_name ? progress[material.kb_name] : undefined;
                      const percent = progressPercent(itemProgress);
                      return (
                        <div key={material.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h3 className="break-words text-sm font-semibold text-slate-950 dark:text-slate-50">
                                {materialName(material)}
                              </h3>
                              <p className="mt-1 text-xs text-slate-500">
                                {SOURCE_LABELS[material.source_type] || material.source_type} ·{" "}
                                {STATUS_LABELS[material.parse_status] || material.parse_status} ·{" "}
                                {material.rag_provider || "RAG"}
                              </p>
                            </div>
                            {(isTeacher || (isStudent && material.source_type === "student_note")) && (
                              <button className="rounded-md p-1 text-slate-400 hover:bg-red-50 hover:text-red-600" onClick={() => deleteMaterial(material)} title="删除资料">
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                          {material.description && <p className="mt-2 text-sm leading-5 text-slate-600 dark:text-slate-300">{material.description}</p>}
                          {material.kb_name && material.parse_status !== "parsed" && (
                            <div className="mt-3 rounded-md bg-slate-50 p-2 dark:bg-slate-800">
                              <div className="mb-1 flex justify-between gap-3 text-xs text-slate-500">
                                <span className="truncate">{progressLabel(itemProgress)}</span>
                                <span>{percent}%</span>
                              </div>
                              <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${percent}%` }} />
                              </div>
                            </div>
                          )}
                          {material.kb_name && (
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button
                                disabled={material.parse_status !== "parsed"}
                                onClick={() => openGraph(material)}
                                className="inline-flex items-center gap-1 rounded-md border border-teal-200 bg-teal-50 px-2 py-1 text-xs font-medium text-teal-700 hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-teal-900 dark:bg-teal-950/40 dark:text-teal-200"
                              >
                                <Network className="h-3.5 w-3.5" />
                                查看图谱
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div>
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
                  <BookOpen className="h-4 w-4 text-emerald-600" />
                  知识点
                </div>
                {visiblePoints.length === 0 ? (
                  <Empty text="暂无知识点。资料解析后会生成候选知识点，教师也可以手动添加。" />
                ) : (
                  <div className="grid gap-3 xl:grid-cols-2">
                    {visiblePoints.map((point) => {
                      const mastery = point.mastery;
                      const masteryValue = Math.round((mastery?.mastery_level || 0) * 100);
                      return (
                        <div key={point.id} className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <h3 className="font-semibold text-slate-950 dark:text-slate-50">{point.name}</h3>
                              <p className="mt-1 text-xs text-slate-500">
                                优先级 {PRIORITY_OPTIONS.find((item) => Number(item.value) === point.priority)?.label || "中"} ·{" "}
                                {point.is_confirmed ? "已确认" : "待确认"}
                                {point.source_material_title ? ` · 来源：${point.source_material_title}` : ""}
                              </p>
                            </div>
                            {point.is_confirmed && <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />}
                          </div>
                          {point.description && <p className="mt-2 text-sm leading-5 text-slate-600 dark:text-slate-300">{point.description}</p>}
                          {isStudent && (
                            <div className="mt-3">
                              <div className="mb-1 flex justify-between text-xs text-slate-500">
                                <span>掌握度 {masteryValue}%</span>
                                <span>对 {mastery?.correct_count || 0} · 错 {mastery?.wrong_count || 0}</span>
                              </div>
                              <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                                <div className="h-full rounded-full bg-emerald-500" style={{ width: `${masteryValue}%` }} />
                              </div>
                              <div className="mt-2 flex gap-2">
                                <button className={actionButton} onClick={() => recordMastery(point, true)}>会了</button>
                                <button className={actionButton} onClick={() => recordMastery(point, false)}>还要练</button>
                              </div>
                            </div>
                          )}
                          {isTeacher && (
                            <div className="mt-3">
                              <button className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50" onClick={() => deletePoint(point)}>
                                <Trash2 className="h-3.5 w-3.5" />
                                删除
                              </button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {(graphLoading || graphPreview) && (
                <div className="rounded-lg border border-teal-200 bg-teal-50/70 p-4 dark:border-teal-900 dark:bg-teal-950/25">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                      <Network className="h-4 w-4 text-teal-700" />
                      {graphTitle || "资料知识图谱"}
                    </h3>
                    {graphPreview?.kb_name && (
                      <Link href={`/knowledge/${encodeURIComponent(graphPreview.kb_name)}/graph`} className="text-xs font-medium text-teal-700 hover:underline">
                        打开完整图谱
                      </Link>
                    )}
                  </div>
                  {graphLoading ? (
                    <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      正在读取图谱
                    </div>
                  ) : graphPreview ? (
                    <div className="mt-3 space-y-3">
                      <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-3">
                        <span className="rounded-md bg-white px-2 py-1 dark:bg-slate-900">节点 {graphPreview.stats?.returned_nodes ?? graphPreview.nodes.length}</span>
                        <span className="rounded-md bg-white px-2 py-1 dark:bg-slate-900">关系 {graphPreview.stats?.returned_edges ?? graphPreview.edges.length}</span>
                        <span className="rounded-md bg-white px-2 py-1 dark:bg-slate-900">{graphPreview.stats?.truncated ? "已截断预览" : "完整预览"}</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {graphPreview.nodes.slice(0, 18).map((node) => (
                          <span key={node.id} className="rounded-full border border-teal-200 bg-white px-2 py-1 text-xs text-teal-800 dark:border-teal-900 dark:bg-slate-900 dark:text-teal-200">
                            {node.label || node.id}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          )}
        </main>
      </div>

      <ChapterModal
        open={modal === "chapter"}
        loading={loading}
        form={chapterForm}
        setForm={setChapterForm}
        onClose={() => setModal(null)}
        onSubmit={createChapter}
      />
      <UploadModal
        open={modal === "upload"}
        loading={loading}
        form={uploadForm}
        setForm={setUploadForm}
        file={uploadFile}
        onFile={handleUploadFile}
        providers={providers}
        providerId={providerId}
        setProviderId={setProviderId}
        accept={selectedExtensions.join(",")}
        chapterTitle={selectedChapter?.title || "课程公共资料"}
        onClose={() => setModal(null)}
        onSubmit={uploadMaterial}
      />
      <PointModal
        open={modal === "point"}
        loading={loading}
        form={pointForm}
        setForm={setPointForm}
        chapterTitle={selectedChapter?.title || "课程公共资料"}
        onClose={() => setModal(null)}
        onSubmit={createPoint}
      />
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-6 text-sm text-slate-500 dark:border-slate-700">
      {text}
    </div>
  );
}

function ModalFrame({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-5 shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-950 dark:text-slate-50">{title}</h3>
          <button className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800" onClick={onClose}>
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-200">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/15 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50";
const primaryButton =
  "inline-flex h-10 flex-1 items-center justify-center rounded-md bg-emerald-600 px-4 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60";
const secondaryButton =
  "inline-flex h-10 flex-1 items-center justify-center rounded-md border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800";

function CourseModal({
  open,
  loading,
  form,
  setForm,
  onClose,
  onSubmit,
}: {
  open: boolean;
  loading: boolean;
  form: { name: string; description: string };
  setForm: (form: { name: string; description: string }) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <ModalFrame open={open} title="新建课程" onClose={onClose}>
      <div className="space-y-4">
        <Field label="课程名称">
          <input className={inputClass} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </Field>
        <Field label="课程说明">
          <textarea className={`${inputClass} h-24 resize-none`} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
        </Field>
        <div className="flex gap-3 pt-2">
          <button className={secondaryButton} onClick={onClose}>取消</button>
          <button className={primaryButton} onClick={onSubmit} disabled={loading || !form.name.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "创建"}
          </button>
        </div>
      </div>
    </ModalFrame>
  );
}

function ChapterModal({
  open,
  loading,
  form,
  setForm,
  onClose,
  onSubmit,
}: {
  open: boolean;
  loading: boolean;
  form: { title: string; description: string; order_index: string };
  setForm: (form: { title: string; description: string; order_index: string }) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <ModalFrame open={open} title="新建章节" onClose={onClose}>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
          <Field label="章节标题">
            <input className={inputClass} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </Field>
          <Field label="顺序">
            <input type="number" min="1" className={inputClass} value={form.order_index} onChange={(event) => setForm({ ...form, order_index: event.target.value })} />
          </Field>
        </div>
        <Field label="章节说明">
          <textarea className={`${inputClass} h-24 resize-none`} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
        </Field>
        <div className="flex gap-3 pt-2">
          <button className={secondaryButton} onClick={onClose}>取消</button>
          <button className={primaryButton} onClick={onSubmit} disabled={loading || !form.title.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "创建章节"}
          </button>
        </div>
      </div>
    </ModalFrame>
  );
}

function UploadModal({
  open,
  loading,
  form,
  setForm,
  file,
  onFile,
  providers,
  providerId,
  setProviderId,
  accept,
  chapterTitle,
  onClose,
  onSubmit,
}: {
  open: boolean;
  loading: boolean;
  form: { title: string; description: string };
  setForm: (form: { title: string; description: string }) => void;
  file: File | null;
  onFile: (file: File | null) => void;
  providers: RagProvider[];
  providerId: string;
  setProviderId: (id: string) => void;
  accept: string;
  chapterTitle: string;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <ModalFrame open={open} title="上传课程资料" onClose={onClose}>
      <div className="space-y-4">
        <div className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          归属：{chapterTitle}
        </div>
        <Field label="资料文件">
          <input
            className={inputClass}
            type="file"
            accept={accept}
            onChange={(event) => onFile(event.target.files?.[0] || null)}
          />
        </Field>
        <Field label="资料名称">
          <input
            className={inputClass}
            value={form.title}
            placeholder={file?.name || "默认使用上传文件名"}
            onChange={(event) => setForm({ ...form, title: event.target.value })}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="解析方式">
            <select className={inputClass} value={providerId} onChange={(event) => setProviderId(event.target.value)}>
              {providers.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="文件名">
            <div className="truncate rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-500 dark:border-slate-700">
              {file?.name || "尚未选择文件"}
            </div>
          </Field>
        </div>
        <Field label="资料说明">
          <textarea className={`${inputClass} h-20 resize-none`} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
        </Field>
        <div className="flex gap-3 pt-2">
          <button className={secondaryButton} onClick={onClose}>取消</button>
          <button className={primaryButton} onClick={onSubmit} disabled={loading || !file}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "上传并解析"}
          </button>
        </div>
      </div>
    </ModalFrame>
  );
}

function PointModal({
  open,
  loading,
  form,
  setForm,
  chapterTitle,
  onClose,
  onSubmit,
}: {
  open: boolean;
  loading: boolean;
  form: { name: string; description: string; priority: string };
  setForm: (form: { name: string; description: string; priority: string }) => void;
  chapterTitle: string;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <ModalFrame open={open} title="新增知识点" onClose={onClose}>
      <div className="space-y-4">
        <div className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          归属：{chapterTitle}
        </div>
        <Field label="知识点名称">
          <input className={inputClass} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </Field>
        <Field label="优先级">
          <select className={inputClass} value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value })}>
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="说明">
          <textarea className={`${inputClass} h-24 resize-none`} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} />
        </Field>
        <div className="flex gap-3 pt-2">
          <button className={secondaryButton} onClick={onClose}>取消</button>
          <button className={primaryButton} onClick={onSubmit} disabled={loading || !form.name.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "添加"}
          </button>
        </div>
      </div>
    </ModalFrame>
  );
}
