"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8001";

type Submission = {
  id: number;
  assignment_no: number;
  experiment_title: string;
  original_filename: string;
  status: string;
  created_at: string;
};

type Question = {
  id: number;
  question_id?: number;
  question_no: number;
  question_text: string;
  reference_points?: string;
  answers?: AnswerResult[];
};

type AnswerResult = {
  id: number;
  answer_text: string;
  score_code_understanding: number;
  score_concept_mastery: number;
  score_question_response: number;
  total_score: number;
  feedback: string;
  grading_reason: string;
  created_at: string;
};

export default function StudentExperimentPage() {
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [userRole, setUserRole] = useState("");

  const [loading, setLoading] = useState(true);

  const [uploading, setUploading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [generatingForId, setGeneratingForId] = useState<number | null>(null);
  const [submittingQuestionId, setSubmittingQuestionId] = useState<number | null>(null);

  const [uploadForm, setUploadForm] = useState({
    assignment_no: "",
    experiment_title: "",
  });
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [selectedSubmissionId, setSelectedSubmissionId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answerInputs, setAnswerInputs] = useState<Record<number, string>>({});
  const [latestResults, setLatestResults] = useState<Record<number, AnswerResult>>({});

  const selectedSubmission = useMemo(
    () => submissions.find((item) => item.id === selectedSubmissionId) || null,
    [submissions, selectedSubmissionId],
  );

  useEffect(() => {
    const init = async () => {
      try {
        const rawUser = localStorage.getItem("auth_user");
        if (!rawUser) {
          alert("请先登录");
          router.push("/login");
          return;
        }

        const user = JSON.parse(rawUser);
        if (!user?.username) {
          alert("登录信息无效，请重新登录");
          router.push("/login");
          return;
        }

        if (user.role !== "student") {
          alert("当前账号不是学生账号");
          router.push("/login");
          return;
        }

        setUsername(user.username);
        setUserRole(user.role);

        await fetchMySubmissions(user.username);
      } catch (error: any) {
        alert(error.message || "初始化失败");
      } finally {
        setLoading(false);
      }
    };

    init();
  }, [router]);

  const fetchMySubmissions = async (studentUsername: string) => {
    try {
      setRefreshing(true);

      const res = await fetch(
        `${API_BASE}/api/v1/experiment/my-submissions/${studentUsername}`,
      );
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "获取实验提交列表失败");
      }

      setSubmissions(data.submissions || []);
    } finally {
      setRefreshing(false);
    }
  };

  const handleUpload = async () => {
    if (!username) {
      alert("未获取到当前登录学生");
      return;
    }

    if (!uploadForm.assignment_no.trim()) {
      alert("请填写第几次实验");
      return;
    }

    if (!uploadForm.experiment_title.trim()) {
      alert("请填写实验标题");
      return;
    }

    if (!uploadFile) {
      alert("请选择实验报告文件");
      return;
    }

    try {
      setUploading(true);

      const formData = new FormData();
      formData.append("username", username);
      formData.append("assignment_no", uploadForm.assignment_no);
      formData.append("experiment_title", uploadForm.experiment_title);
      formData.append("file", uploadFile);

      const res = await fetch(`${API_BASE}/api/v1/experiment/upload-report`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "上传实验报告失败");
      }

      alert("实验报告上传成功");

      setUploadForm({
        assignment_no: "",
        experiment_title: "",
      });
      setUploadFile(null);

      const fileInput = document.getElementById(
        "experiment-file-input",
      ) as HTMLInputElement | null;
      if (fileInput) fileInput.value = "";

      await fetchMySubmissions(username);
    } catch (error: any) {
      alert(error.message || "上传实验报告失败");
    } finally {
      setUploading(false);
    }
  };

  const handleGenerateQuestions = async (submissionId: number) => {
    try {
      setGeneratingForId(submissionId);

      const res = await fetch(`${API_BASE}/api/v1/experiment/generate-questions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          submission_id: submissionId,
          question_count: 3,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "生成问题失败");
      }

      alert("问题生成成功");
      setSelectedSubmissionId(submissionId);

      setQuestions(data.questions || []);
      setAnswerInputs({});
      setLatestResults({});

      await fetchMySubmissions(username);
    } catch (error: any) {
      alert(error.message || "生成问题失败");
    } finally {
      setGeneratingForId(null);
    }
  };

  const handleViewQuestions = async (submissionId: number) => {
    try {
      setSelectedSubmissionId(submissionId);

      const res = await fetch(
        `${API_BASE}/api/v1/experiment/submission-detail/${submissionId}`,
      );
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "获取实验详情失败");
      }

      const questionList: Question[] = (data.questions || []).map((q: any) => ({
        id: q.question_id,
        question_id: q.question_id,
        question_no: q.question_no,
        question_text: q.question_text,
        reference_points: q.reference_points,
        answers: q.answers || [],
      }));

      setQuestions(questionList);

      const resultMap: Record<number, AnswerResult> = {};
      for (const q of questionList) {
        if (q.answers && q.answers.length > 0) {
          resultMap[q.id] = q.answers[0];
        }
      }
      setLatestResults(resultMap);
    } catch (error: any) {
      alert(error.message || "获取实验详情失败");
    }
  };

  const handleSubmitAnswer = async (questionId: number) => {
    const answerText = (answerInputs[questionId] || "").trim();
    if (!username) {
      alert("未获取到当前学生用户名");
      return;
    }
    if (!answerText) {
      alert("请输入回答内容");
      return;
    }

    try {
      setSubmittingQuestionId(questionId);

      const res = await fetch(`${API_BASE}/api/v1/experiment/submit-answer`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          question_id: questionId,
          answer_text: answerText,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "提交回答失败");
      }

      alert("回答提交并评分成功");

      setLatestResults((prev) => ({
        ...prev,
        [questionId]: data.answer,
      }));

      await fetchMySubmissions(username);

      if (selectedSubmissionId) {
        await handleViewQuestions(selectedSubmissionId);
      }
    } catch (error: any) {
      alert(error.message || "提交回答失败");
    } finally {
      setSubmittingQuestionId(null);
    }
  };

  const handleBackStudentHome = () => {
    router.push("/student");
  };

  if (loading) {
    return <div className="p-8">加载中...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">学生实验问答</h1>
            <p className="text-slate-500 mt-1">
              当前用户：{username}（{userRole}）
            </p>
          </div>
          <button
            onClick={handleBackStudentHome}
            className="px-4 py-2 rounded-lg bg-slate-600 text-white hover:bg-slate-700"
          >
            返回学生主页
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-xl font-semibold text-slate-900 mb-4">上传实验报告</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              value={uploadForm.assignment_no}
              onChange={(e) =>
                setUploadForm((prev) => ({
                  ...prev,
                  assignment_no: e.target.value,
                }))
              }
              placeholder="第几次实验，如 1"
              className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
            />

            <input
              value={uploadForm.experiment_title}
              onChange={(e) =>
                setUploadForm((prev) => ({
                  ...prev,
                  experiment_title: e.target.value,
                }))
              }
              placeholder="实验标题，如 第一次实验报告"
              className="px-4 py-3 rounded-xl border border-slate-300 outline-none"
            />

            <div className="md:col-span-2">
              <input
                id="experiment-file-input"
                type="file"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="block w-full rounded-xl border border-slate-300 bg-white px-4 py-3"
              />
              <p className="mt-2 text-sm text-slate-500">
                当前第一版建议先上传 txt 文件，后面再扩展 pdf/docx。
              </p>
            </div>

            <div className="md:col-span-2">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="px-5 py-3 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {uploading ? "上传中..." : "上传实验报告"}
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[420px_1fr] gap-6">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-slate-900">我的实验提交</h2>
              <button
                onClick={() => fetchMySubmissions(username)}
                disabled={refreshing}
                className="px-3 py-2 rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50"
              >
                {refreshing ? "刷新中..." : "刷新"}
              </button>
            </div>

            {submissions.length === 0 ? (
              <div className="text-slate-500">暂无实验提交记录</div>
            ) : (
              <div className="space-y-3">
                {submissions.map((item) => (
                  <div
                    key={item.id}
                    className={`rounded-xl border p-4 ${
                      selectedSubmissionId === item.id
                        ? "border-blue-500 bg-blue-50"
                        : "border-slate-200 bg-white"
                    }`}
                  >
                    <div className="font-semibold text-slate-900">
                      第 {item.assignment_no} 次实验
                    </div>
                    <div className="text-slate-700 mt-1">{item.experiment_title}</div>
                    <div className="text-sm text-slate-500 mt-1">
                      文件：{item.original_filename}
                    </div>
                    <div className="text-sm text-slate-500">
                      状态：{item.status}
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => handleGenerateQuestions(item.id)}
                        disabled={generatingForId === item.id}
                        className="px-3 py-2 rounded-lg bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50"
                      >
                        {generatingForId === item.id ? "生成中..." : "生成问题"}
                      </button>

                      <button
                        onClick={() => handleViewQuestions(item.id)}
                        className="px-3 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700"
                      >
                        查看详情
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
            <h2 className="text-xl font-semibold text-slate-900 mb-4">
              {selectedSubmission
                ? `实验详情：第 ${selectedSubmission.assignment_no} 次 - ${selectedSubmission.experiment_title}`
                : "实验问题与回答"}
            </h2>

            {!selectedSubmissionId ? (
              <div className="text-slate-500">
                请先在左侧选择一条实验提交，并生成问题或查看详情。
              </div>
            ) : questions.length === 0 ? (
              <div className="text-slate-500">
                当前还没有问题。请先点击“生成问题”，或者确认该实验已成功生成问题。
              </div>
            ) : (
              <div className="space-y-6">
                {questions.map((q) => {
                  const result = latestResults[q.id];
                  return (
                    <div
                      key={q.id}
                      className="rounded-2xl border border-slate-200 bg-slate-50 p-5"
                    >
                      <div className="text-lg font-semibold text-slate-900">
                        第 {q.question_no} 题
                      </div>
                      <div className="mt-2 text-slate-800 leading-7">
                        {q.question_text}
                      </div>

                      <div className="mt-3 text-sm text-slate-500">
                        参考要点：{q.reference_points || "暂无"}
                      </div>

                      <div className="mt-4">
                        <textarea
                          value={answerInputs[q.id] || ""}
                          onChange={(e) =>
                            setAnswerInputs((prev) => ({
                              ...prev,
                              [q.id]: e.target.value,
                            }))
                          }
                          placeholder="请输入你的回答"
                          className="w-full min-h-[120px] px-4 py-3 rounded-xl border border-slate-300 outline-none bg-white"
                        />
                      </div>

                      <div className="mt-3">
                        <button
                          onClick={() => handleSubmitAnswer(q.id)}
                          disabled={submittingQuestionId === q.id}
                          className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {submittingQuestionId === q.id ? "评分中..." : "提交回答并评分"}
                        </button>
                      </div>

                      {result && (
                        <div className="mt-5 rounded-xl border border-green-200 bg-green-50 p-4">
                          <div className="text-lg font-semibold text-green-800 mb-3">
                            评分结果
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-slate-700">
                            <div>代码理解：{result.score_code_understanding}</div>
                            <div>概念掌握：{result.score_concept_mastery}</div>
                            <div>问题回答：{result.score_question_response}</div>
                            <div className="font-semibold">
                              总分：{result.total_score}
                            </div>
                          </div>

                          <div className="mt-3">
                            <div className="font-medium text-slate-900">反馈</div>
                            <div className="text-slate-700 mt-1">
                              {result.feedback || "无"}
                            </div>
                          </div>

                          <div className="mt-3">
                            <div className="font-medium text-slate-900">评分理由</div>
                            <div className="text-slate-700 mt-1 whitespace-pre-wrap">
                              {result.grading_reason || "无"}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}