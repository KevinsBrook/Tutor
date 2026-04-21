"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8001";

export default function StudentPage() {
  const router = useRouter();

  const [user, setUser] = useState<any>(null);
  const [studentInfo, setStudentInfo] = useState<any>(null);
  const [scores, setScores] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadStudentData = async () => {
      try {
        const storedUser = localStorage.getItem("auth_user");
        if (!storedUser) {
          alert("请先登录");
          router.push("/login");
          return;
        }

        const parsedUser = JSON.parse(storedUser);
        setUser(parsedUser);

        if (parsedUser.role !== "student") {
          alert("当前账号不是学生账号");
          router.push("/login");
          return;
        }

        const meRes = await fetch(
          `${API_BASE}/api/v1/student/me/${parsedUser.username}`
        );
        const meData = await meRes.json();
        if (!meRes.ok) {
          throw new Error(meData.detail || "获取学生信息失败");
        }
        setStudentInfo(meData.student);

        const scoreRes = await fetch(
          `${API_BASE}/api/v1/student/scores/${parsedUser.username}`
        );
        const scoreData = await scoreRes.json();
        if (!scoreRes.ok) {
          throw new Error(scoreData.detail || "获取成绩失败");
        }
        setScores(scoreData.scores || []);
      } catch (error: any) {
        alert(error.message || "加载学生数据失败");
      } finally {
        setLoading(false);
      }
    };

    loadStudentData();
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("auth_user");
    localStorage.removeItem("auth_profile");
    router.push("/login");
  };

  if (loading) {
    return <div className="p-8">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">学生主页</h1>
            <p className="text-slate-500 mt-1">
              欢迎你，{studentInfo?.real_name || user?.username}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => router.push("/student/experiment")}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
            >
              进入实验问答
            </button>
            <button
              onClick={handleLogout}
              className="px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600"
            >
              退出登录
            </button>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">个人信息</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-slate-700">
            <div>姓名：{studentInfo?.real_name}</div>
            <div>学号：{studentInfo?.student_no}</div>
            <div>年级：{studentInfo?.grade_name}</div>
            <div>班级：{studentInfo?.class_name}</div>
            <div>专业：{studentInfo?.major || "未填写"}</div>
            <div>用户名：{user?.username}</div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">我的作业成绩</h2>

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
                  </tr>
                </thead>
                <tbody>
                  {scores.map((item) => (
                    <tr key={item.id} className="border-t border-slate-200">
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