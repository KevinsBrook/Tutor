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
};

type MasteryPoint = {
  course_name: string;
  chapter_title: string;
  mastery_percent: number;
  priority: number;
  practice_count: number;
  correct_count: number;
  wrong_count: number;
  recommendation: string;
  knowledge_point: {
    id: number;
    name: string;
    description: string;
  };
};

type LearningProfile = {
  summary: MasterySummary;
  courses: Array<{
    course_id: number;
    course_name: string;
    summary: MasterySummary;
    weak_points: MasteryPoint[];
  }>;
  weak_points: MasteryPoint[];
  recommended_practice: MasteryPoint[];
  recent_events: Array<{
    id: number;
    knowledge_point_name: string;
    course_name: string;
    source_type: string;
    score?: number | null;
    max_score?: number | null;
    is_correct?: boolean | null;
    mastery_delta: number;
    created_at: string;
  }>;
};

function percent(value?: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function formatDate(value?: string | null) {
  if (!value) return "暂无";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function masteryLabel(value: number) {
  if (value >= 80) return "掌握较好";
  if (value >= 60) return "基本掌握";
  if (value >= 30) return "正在形成";
  return "需要巩固";
}

export default function StudentPage() {
  const router = useRouter();
  const { session, isReady, logout } = useAuth();

  const [studentInfo, setStudentInfo] = useState<any>(null);
  const [scores, setScores] = useState<any[]>([]);
  const [profile, setProfile] = useState<LearningProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadStudentData = async () => {
      if (!isReady) return;

      try {
        if (!session) {
          alert("请先登录");
          router.replace("/login");
          return;
        }
        if (session.role !== "student") {
          alert("当前账号不是学生账号");
          router.replace("/login");
          return;
        }

        const [meRes, scoreRes, profileRes] = await Promise.all([
          fetch(apiUrl(`/api/v1/student/me/${session.username}`)),
          fetch(apiUrl(`/api/v1/student/scores/${session.username}`)),
          fetch(apiUrl(`/api/v1/courses/learning-profile?student_username=${encodeURIComponent(session.username)}`)),
        ]);

        const meData = await meRes.json();
        const scoreData = await scoreRes.json();
        const profileData = await profileRes.json();
        if (!meRes.ok) throw new Error(meData.detail || "获取学生信息失败");
        if (!scoreRes.ok) throw new Error(scoreData.detail || "获取成绩失败");
        if (!profileRes.ok) throw new Error(profileData.detail || "获取学习画像失败");

        setStudentInfo(meData.student);
        setScores(scoreData.scores || []);
        setProfile(profileData);
      } catch (error: any) {
        alert(error.message || "加载学生数据失败");
      } finally {
        setLoading(false);
      }
    };

    loadStudentData();
  }, [isReady, router, session]);

  const summary = profile?.summary;
  const averagePercent = useMemo(() => percent(summary?.average_mastery), [summary?.average_mastery]);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (loading) {
    return <div className="p-8 text-slate-600">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">学生学习中心</h1>
            <p className="mt-1 text-slate-500">欢迎你，{studentInfo?.real_name || session?.username}</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => router.push("/question")}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700"
            >
              进入题目练习
            </button>
            <button
              onClick={handleLogout}
              className="rounded-lg border border-slate-200 px-4 py-2 text-slate-700 hover:bg-slate-100"
            >
              退出登录
            </button>
          </div>
        </div>

        <section className="grid gap-4 md:grid-cols-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">平均掌握度</p>
            <p className="mt-2 text-3xl font-semibold text-indigo-700">{averagePercent}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">已掌握知识点</p>
            <p className="mt-2 text-3xl font-semibold text-emerald-600">{summary?.mastered_count || 0}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">薄弱知识点</p>
            <p className="mt-2 text-3xl font-semibold text-amber-600">{summary?.weak_count || 0}</p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">尚未练习</p>
            <p className="mt-2 text-3xl font-semibold text-slate-700">{summary?.unpracticed_count || 0}</p>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">课程掌握情况</h2>
            <div className="mt-4 space-y-3">
              {(profile?.courses || []).length === 0 ? (
                <p className="text-sm text-slate-500">暂无课程知识点数据。</p>
              ) : (
                profile?.courses.map((course) => {
                  const avg = Math.round(course.summary.average_mastery * 100);
                  return (
                    <div key={course.course_id} className="rounded-xl border border-slate-100 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-medium text-slate-900">{course.course_name}</p>
                          <p className="mt-1 text-xs text-slate-500">
                            {course.summary.knowledge_point_count} 个知识点 · {course.summary.weak_count} 个待巩固
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
            <h2 className="text-lg font-semibold text-slate-900">下一步推荐</h2>
            <div className="mt-4 space-y-3">
              {(profile?.recommended_practice || []).length === 0 ? (
                <p className="text-sm text-slate-500">暂无需要推荐的练习。</p>
              ) : (
                profile?.recommended_practice.slice(0, 5).map((point) => (
                  <div key={point.knowledge_point.id} className="rounded-xl bg-slate-50 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-medium text-slate-900">{point.knowledge_point.name}</p>
                      <span className="text-xs text-slate-500">{masteryLabel(point.mastery_percent)}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {point.course_name} / {point.chapter_title}
                    </p>
                    <p className="mt-2 text-sm text-slate-700">{point.recommendation}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">薄弱知识点</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-100 text-left text-slate-600">
                    <th className="p-3">知识点</th>
                    <th className="p-3">课程</th>
                    <th className="p-3">掌握度</th>
                    <th className="p-3">练习</th>
                  </tr>
                </thead>
                <tbody>
                  {(profile?.weak_points || []).map((point) => (
                    <tr key={point.knowledge_point.id} className="border-t border-slate-100">
                      <td className="p-3">{point.knowledge_point.name}</td>
                      <td className="p-3">{point.course_name}</td>
                      <td className="p-3">{point.mastery_percent}%</td>
                      <td className="p-3">
                        {point.correct_count}/{point.practice_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">最近练习证据</h2>
            <div className="mt-4 space-y-3">
              {(profile?.recent_events || []).length === 0 ? (
                <p className="text-sm text-slate-500">暂无练习证据。</p>
              ) : (
                profile?.recent_events.map((event) => (
                  <div key={event.id} className="rounded-xl border border-slate-100 p-3 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-slate-900">{event.knowledge_point_name}</p>
                      <span className={event.mastery_delta >= 0 ? "text-emerald-600" : "text-rose-600"}>
                        {event.mastery_delta >= 0 ? "+" : ""}
                        {Math.round(event.mastery_delta * 100)}%
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      {event.course_name || "未关联课程"} · {formatDate(event.created_at)}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </section>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">我的作业成绩</h2>
          {scores.length === 0 ? (
            <div className="text-slate-500">暂无成绩记录</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-100 text-left text-slate-600">
                    <th className="p-3">次数</th>
                    <th className="p-3">作业标题</th>
                    <th className="p-3">分数</th>
                    <th className="p-3">反馈</th>
                  </tr>
                </thead>
                <tbody>
                  {scores.map((item) => (
                    <tr key={item.id} className="border-t border-slate-100">
                      <td className="p-3">第 {item.assignment_no} 次</td>
                      <td className="p-3">{item.assignment_title || "未命名作业"}</td>
                      <td className="p-3">{item.score}</td>
                      <td className="p-3">{item.feedback || "无"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
