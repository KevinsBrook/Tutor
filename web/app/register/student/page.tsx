"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8001";

export default function StudentRegisterPage() {
  const router = useRouter();

  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    real_name: "",
    student_no: "",
    grade_name: "",
    class_name: "",
    major: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const updateField = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (
      !form.username.trim() ||
      !form.password.trim() ||
      !form.real_name.trim() ||
      !form.student_no.trim() ||
      !form.grade_name.trim() ||
      !form.class_name.trim()
    ) {
      setError("请把必填项填写完整");
      return;
    }

    try {
      setLoading(true);

      const res = await fetch(`${API_BASE}/api/v1/auth/register/student`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ...form,
          email: form.email.trim() || null,
          major: form.major.trim() || null,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "学生注册失败");
      }

      alert("学生注册成功，请登录");
      router.push("/login");
    } catch (err: any) {
      setError(err.message || "学生注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-2xl mx-auto bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">学生注册</h1>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <input
            value={form.username}
            onChange={(e) => updateField("username", e.target.value)}
            placeholder="用户名 *"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            value={form.email}
            onChange={(e) => updateField("email", e.target.value)}
            placeholder="邮箱"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            type="password"
            value={form.password}
            onChange={(e) => updateField("password", e.target.value)}
            placeholder="密码 *"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            value={form.real_name}
            onChange={(e) => updateField("real_name", e.target.value)}
            placeholder="姓名 *"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            value={form.student_no}
            onChange={(e) => updateField("student_no", e.target.value)}
            placeholder="学号 *"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            value={form.grade_name}
            onChange={(e) => updateField("grade_name", e.target.value)}
            placeholder="年级，如 2023级 *"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            value={form.class_name}
            onChange={(e) => updateField("class_name", e.target.value)}
            placeholder="班级，如 计科1班 *"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />
          <input
            value={form.major}
            onChange={(e) => updateField("major", e.target.value)}
            placeholder="专业"
            className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
          />

          {error && (
            <div className="md:col-span-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <div className="md:col-span-2 flex gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "注册中..." : "注册"}
            </button>
            <button
              type="button"
              onClick={() => router.push("/login")}
              className="px-5 py-3 rounded-xl bg-slate-200 text-slate-700 hover:bg-slate-300"
            >
              返回登录
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}