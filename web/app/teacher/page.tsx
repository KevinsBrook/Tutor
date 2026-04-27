"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import { apiUrl } from "@/lib/api";

type MasterySummary = {
  knowledge_point_count: number;
  mastered_count: number;
  basic_count: number;
  forming_count: number;
  weak_count: number;
  unpracticed_count: number;
  average_mastery: number;
  student_count?: number;
  course_count?: number;
};

type TeacherDashboard = {
  summary: MasterySummary;
  courses: Array<{ id: number; name: string }>;
  course_cards: Array<{
    course: { id: number; name: string };
    summary: MasterySummary;
  }>;
  student_profiles: Array<{
    student: {
      id: number;
      username?: string;
      real_name: string;
      student_no: string;
      class_name: string;
      grade_name: string;
      major?: string;
    };
    summary: MasterySummary;
    weak_points: Array<{
      course_name: string;
      chapter_title: string;
      mastery_percent: number;
      knowledge_point: { id: number; name: string };
    }>;
    last_practiced_at?: string | null;
  }>;
};

function percent(value?: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function formatDate(value?: string | null) {
  if (!value) return "暂无";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function riskLabel(value: number) {
  if (value >= 0.8) return "稳定";
  if (value >= 0.6) return "基本";
  if (value >= 0.3) return "需关注";
  return "高风险";
}

export default function TeacherPage() {
  const router = useRouter();
  const { session, isReady, logout } = useAuth();

  const [students, setStudents] = useState<any[]>([]);
  const [dashboard, setDashboard] = useState<TeacherDashboard | null>(null);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadTeacherData = async () => {
      if (!isReady) return;

      try {
        if (!session) {
          alert("请先登录");
          router.replace("/login");
          return;
        }
        if (session.role !== "teacher") {
          alert("当前账号不是教师账号");
          router.replace("/login");
          return;
        }

        const query = new URLSearchParams({ teacher_username: session.username });
        if (selectedCourseId) query.set("course_id", selectedCourseId);
        const [studentRes, dashboardRes] = await Promise.all([
          fetch(apiUrl("/api/v1/teacher/students")),
          fetch(apiUrl(`/api/v1/courses/teacher-dashboard?${query.toString()}`)),
        ]);
        const studentData = await studentRes.json();
        const dashboardData = await dashboardRes.json();

        if (!studentRes.ok) throw new Error(studentData.detail || "获取学生列表失败");
        if (!dashboardRes.ok) throw new Error(dashboardData.detail || "获取教师看板失败");

        setStudents(studentData.students || []);
        setDashboard(dashboardData);
      } catch (error: any) {
        alert(error.message || "加载教师数据失败");
      } finally {
        setLoading(false);
      }
    };

    loadTeacherData();
  }, [isReady, router, selectedCourseId, session]);

  const summary = dashboard?.summary;
  const highRiskStudents = useMemo(() => {
    return (dashboard?.student_profiles || [])
      .filter((item) => item.summary.knowledge_point_count > 0 && item.summary.average_mastery < 0.4)
      .slice(0, 6);
  }, [dashboard?.student_profiles]);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (loading) {
    return <div className="p-8 text-slate-600">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">教师教学看板</h1>
            <p className="mt-1 text-slate-500">欢迎你，{session?.username}</p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedCourseId}
              onChange={(event) => {
                setLoading(true);
                setSelectedCourseId(event.target.value);
              }}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm"
            >
              <option value="">全部课程</option>
              {(dashboard?.courses || []).map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name}
                </option>
              ))}
            </select>
            <button
              onClick={handleLogout}
              className="rounded-lg border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-100"
            >
              退出登录
            </button>
          </div>
        </div>

        <section className="grid gap-4 md:grid-cols-5">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">课程数</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">{summary?.course_count || 0}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">学生数</p>
            <p className="mt-2 text-3xl font-semibold text-slate-900">{summary?.student_count || students.length}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">平均掌握度</p>
            <p className="mt-2 text-3xl font-semibold text-indigo-700">{percent(summary?.average_mastery)}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">薄弱记录</p>
            <p className="mt-2 text-3xl font-semibold text-amber-600">{summary?.weak_count || 0}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">未练习记录</p>
            <p className="mt-2 text-3xl font-semibold text-slate-700">{summary?.unpracticed_count || 0}</p>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">课程整体情况</h2>
            <div className="mt-4 space-y-3">
              {(dashboard?.course_cards || []).length === 0 ? (
                <p className="text-sm text-slate-500">暂无课程数据。</p>
              ) : (
                dashboard?.course_cards.map((item) => {
                  const avg = Math.round(item.summary.average_mastery * 100);
                  return (
                    <div key={item.course.id} className="rounded-xl border border-slate-100 p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-medium text-slate-900">{item.course.name}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            {item.summary.knowledge_point_count} 条学习记录 · {item.summary.weak_count} 条薄弱记录
                          </p>
                        </div>
                        <span className="text-sm font-semibold text-indigo-700">{avg}%</span>
                      </div>
                      <div className="mt-3 h-2 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full bg-indigo-600" style={{ width: `${avg}%` }} />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">需要优先关注的学生</h2>
            <div className="mt-4 space-y-3">
              {highRiskStudents.length === 0 ? (
                <p className="text-sm text-slate-500">当前暂无高风险学生。</p>
              ) : (
                highRiskStudents.map((item) => (
                  <button
                    key={item.student.id}
                    onClick={() => router.push(`/teacher/students/${item.student.id}`)}
                    className="block w-full rounded-xl bg-amber-50 p-4 text-left hover:bg-amber-100"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-slate-900">{item.student.real_name}</p>
                      <span className="text-sm font-semibold text-amber-700">
                        {percent(item.summary.average_mastery)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {item.student.class_name} · 薄弱 {item.summary.weak_count} · 未练习{" "}
                      {item.summary.unpracticed_count}
                    </p>
                  </button>
                ))
              )}
            </div>
          </div>
        </section>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">学生学习画像列表</h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-slate-100 text-left text-slate-600">
                  <th className="p-3">姓名</th>
                  <th className="p-3">学号</th>
                  <th className="p-3">班级</th>
                  <th className="p-3">平均掌握度</th>
                  <th className="p-3">状态</th>
                  <th className="p-3">薄弱点</th>
                  <th className="p-3">最近练习</th>
                  <th className="p-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {(dashboard?.student_profiles || []).map((item) => (
                  <tr key={item.student.id} className="border-t border-slate-100">
                    <td className="p-3">{item.student.real_name}</td>
                    <td className="p-3">{item.student.student_no}</td>
                    <td className="p-3">{item.student.class_name}</td>
                    <td className="p-3">{percent(item.summary.average_mastery)}</td>
                    <td className="p-3">{riskLabel(item.summary.average_mastery)}</td>
                    <td className="p-3">
                      {item.weak_points.length === 0
                        ? "暂无"
                        : item.weak_points.map((point) => point.knowledge_point.name).join("、")}
                    </td>
                    <td className="p-3">{formatDate(item.last_practiced_at)}</td>
                    <td className="p-3">
                      <button
                        onClick={() => router.push(`/teacher/students/${item.student.id}`)}
                        className="rounded-lg bg-indigo-600 px-3 py-1.5 text-white hover:bg-indigo-700"
                      >
                        查看详情
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">学生基础名单</h2>
          {students.length === 0 ? (
            <div className="text-slate-500">暂无学生数据</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {students.map((item) => (
                <button
                  key={item.id}
                  onClick={() => router.push(`/teacher/students/${item.id}`)}
                  className="rounded-xl border border-slate-100 p-4 text-left hover:bg-slate-50"
                >
                  <p className="font-medium text-slate-900">{item.real_name}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    {item.student_no} · {item.class_name}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">{item.major || "未填写专业"}</p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
