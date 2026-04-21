"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8001";

export default function TeacherPage() {
  const router = useRouter();

  const [user, setUser] = useState<any>(null);
  const [students, setStudents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadTeacherData = async () => {
      try {
        const storedUser = localStorage.getItem("auth_user");
        if (!storedUser) {
          alert("请先登录");
          router.push("/login");
          return;
        }

        const parsedUser = JSON.parse(storedUser);
        setUser(parsedUser);

        if (parsedUser.role !== "teacher") {
          alert("当前账号不是教师账号");
          router.push("/login");
          return;
        }

        const res = await fetch(`${API_BASE}/api/v1/teacher/students`);
        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || "获取学生列表失败");
        }

        setStudents(data.students || []);
      } catch (error: any) {
        alert(error.message || "加载学生列表失败");
      } finally {
        setLoading(false);
      }
    };

    loadTeacherData();
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("auth_user");
    localStorage.removeItem("auth_profile");
    router.push("/login");
  };

  const goToDetail = (studentId: number) => {
    router.push(`/teacher/students/${studentId}`);
  };

  if (loading) {
    return <div className="p-8">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">教师主页</h1>
            <p className="text-slate-500 mt-1">欢迎你，{user?.username}</p>
          </div>
          <button
            onClick={handleLogout}
            className="px-4 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600"
          >
            退出登录
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">学生列表</h2>

          {students.length === 0 ? (
            <div className="text-slate-500">暂无学生数据</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-slate-100 text-left">
                    <th className="p-3">姓名</th>
                    <th className="p-3">学号</th>
                    <th className="p-3">年级</th>
                    <th className="p-3">班级</th>
                    <th className="p-3">专业</th>
                    <th className="p-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((item) => (
                    <tr key={item.id} className="border-t border-slate-200">
                      <td className="p-3">{item.real_name}</td>
                      <td className="p-3">{item.student_no}</td>
                      <td className="p-3">{item.grade_name}</td>
                      <td className="p-3">{item.class_name}</td>
                      <td className="p-3">{item.major || "未填写"}</td>
                      <td className="p-3">
                        <button
                          onClick={() => goToDetail(item.id)}
                          className="px-3 py-1 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
                        >
                          查看详情
                        </button>
                      </td>
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