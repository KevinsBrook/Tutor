"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8001";

export default function TeacherStudentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const studentId = params.id;

  const [student, setStudent] = useState<any>(null);
  const [scores, setScores] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [teacherUser, setTeacherUser] = useState<any>(null);
  const [scoreForm, setScoreForm] = useState({
    assignment_no: "",
    assignment_title: "",
    score: "",
    feedback: "",
  });
const [submittingScore, setSubmittingScore] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      try {
        const storedUser = localStorage.getItem("auth_user");
        if (!storedUser) {
          alert("请先登录");
          router.push("/login");
          return;
        }

        const parsedUser = JSON.parse(storedUser);
        if (parsedUser.role !== "teacher") {
          alert("当前账号不是教师账号");
          router.push("/login");
          return;
        }
        setTeacherUser(parsedUser);

        const detailRes = await fetch(
          `${API_BASE}/api/v1/teacher/students/${studentId}`
        );
        const detailData = await detailRes.json();
        if (!detailRes.ok) {
          throw new Error(detailData.detail || "获取学生详情失败");
        }
        setStudent(detailData.student);

        const scoreRes = await fetch(
          `${API_BASE}/api/v1/teacher/students/${studentId}/scores`
        );
        const scoreData = await scoreRes.json();
        if (!scoreRes.ok) {
          throw new Error(scoreData.detail || "获取学生成绩失败");
        }
        setScores(scoreData.scores || []);
      } catch (error: any) {
        alert(error.message || "加载失败");
      } finally {
        setLoading(false);
      }
    };

    if (studentId) {
      loadData();
    }
  }, [studentId, router]);

  if (loading) {
    return <div className="p-8">加载中...</div>;
  }
  const handleAddScore = async () => {
    if (!student?.id) {
      alert("学生信息未加载完成");
      return;
    }
  
    if (!teacherUser) {
      alert("教师信息未加载完成");
      return;
    }
  
    if (!scoreForm.assignment_no || !scoreForm.score) {
      alert("请填写第几次作业和分数");
      return;
    }
  
    try {
      setSubmittingScore(true);
  
      const teacherProfileRaw = localStorage.getItem("auth_profile");
      const teacherProfile = teacherProfileRaw ? JSON.parse(teacherProfileRaw) : null;
  
      const res = await fetch(`${API_BASE}/api/v1/teacher/scores/add`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          student_id: student.id,
          assignment_no: Number(scoreForm.assignment_no),
          assignment_title: scoreForm.assignment_title || null,
          score: Number(scoreForm.score),
          feedback: scoreForm.feedback || null,
          graded_by: teacherProfile?.id || 1,
        }),
      });
  
      const data = await res.json();
  
      if (!res.ok) {
        throw new Error(data.detail || "录入成绩失败");
      }
  
      alert("成绩录入成功");
  
      setScoreForm({
        assignment_no: "",
        assignment_title: "",
        score: "",
        feedback: "",
      });
  
      // 重新拉取成绩列表
      const scoreRes = await fetch(
        `${API_BASE}/api/v1/teacher/students/${studentId}/scores`,
      );
      const scoreData = await scoreRes.json();
      if (!scoreRes.ok) {
        throw new Error(scoreData.detail || "刷新成绩失败");
      }
      setScores(scoreData.scores || []);
    } catch (error: any) {
      alert(error.message || "录入成绩失败");
    } finally {
      setSubmittingScore(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">学生详情</h1>
            <p className="text-slate-500 mt-1">{student?.real_name}</p>
          </div>
          <button
            onClick={() => router.push("/teacher")}
            className="px-4 py-2 rounded-lg bg-slate-600 text-white hover:bg-slate-700"
          >
            返回教师页
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">基本信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-slate-700">
            <div>姓名：{student?.real_name}</div>
            <div>学号：{student?.student_no}</div>
            <div>年级：{student?.grade_name}</div>
            <div>班级：{student?.class_name}</div>
            <div>专业：{student?.major || "未填写"}</div>
            <div>用户名：{student?.username}</div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">录入成绩</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              value={scoreForm.assignment_no}
              onChange={(e) =>
                setScoreForm((prev) => ({ ...prev, assignment_no: e.target.value }))
              }
              placeholder="第几次作业，如 1"
              className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
            />

            <input
              value={scoreForm.assignment_title}
              onChange={(e) =>
                setScoreForm((prev) => ({ ...prev, assignment_title: e.target.value }))
              }
              placeholder="作业标题，如 第一次实验报告"
              className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
            />

            <input
              value={scoreForm.score}
              onChange={(e) =>
                setScoreForm((prev) => ({ ...prev, score: e.target.value }))
              }
              placeholder="分数，如 88"
              className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
            />

            <div className="flex items-center text-sm text-slate-500 px-2">
              当前学生：{student?.real_name}（{student?.student_no}）
            </div>

            <textarea
              value={scoreForm.feedback}
              onChange={(e) =>
                setScoreForm((prev) => ({ ...prev, feedback: e.target.value }))
              }
              placeholder="评分反馈"
              className="md:col-span-2 min-h-[110px] px-4 py-3 rounded-xl border border-slate-300 outline-none"
            />

            <div className="md:col-span-2">
              <button
                onClick={handleAddScore}
                disabled={submittingScore}
                className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {submittingScore ? "提交中..." : "提交成绩"}
              </button>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">作业成绩</h2>

          {scores.length === 0 ? (
            <div className="text-slate-500">暂无成绩记录</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-slate-100 text-left">
                    <th className="p-3">第几次作业</th>
                    <th className="p-3">作业标题</th>
                    <th className="p-3">分数</th>
                    <th className="p-3">反馈</th>
                    <th className="p-3">评分教师</th>
                  </tr>
                </thead>
                <tbody>
                  {scores.map((item) => (
                    <tr key={item.id} className="border-t border-slate-200">
                      <td className="p-3">第 {item.assignment_no} 次</td>
                      <td className="p-3">{item.assignment_title || "未命名作业"}</td>
                      <td className="p-3">{item.score}</td>
                      <td className="p-3">{item.feedback || "无"}</td>
                      <td className="p-3">{item.graded_by_name || "未记录"}</td>
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