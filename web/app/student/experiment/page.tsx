"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/context/AuthContext";
import { apiUrl } from "@/lib/api";

declare global {
  interface Window {
    webkitSpeechRecognition: any;
    SpeechRecognition: any;
    __currentRecognition?: any;
  }
}

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
  const { session, isReady } = useAuth();

  const [username, setUsername] = useState("");
  const [userRole, setUserRole] = useState("");

  const [loading, setLoading] = useState(true);
  
  const [interimInputs, setInterimInputs] = useState<Record<number, string>>({});
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


  const [deadlineAt, setDeadlineAt] = useState<string | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState<number>(0);

  const [pauseStats, setPauseStats] = useState<
    Record<number, { pauseCount: number; longestPauseMs: number; answerStartedAt: number }>
  >({});

  const recognitionRef = useRef<any>(null);
  const shouldKeepRecordingRef = useRef(false); 
  const [recordingQuestionId, setRecordingQuestionId] = useState<number | null>(null);
  const [speechSupported, setSpeechSupported] = useState(false);
  const selectedSubmission = useMemo(
    () => submissions.find((item) => item.id === selectedSubmissionId) || null,
    [submissions, selectedSubmissionId],
  );

  useEffect(() => {
    const init = async () => {
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

        setUsername(session.username);
        setUserRole(session.role);

        await fetchMySubmissions(session.username);
      } catch (error: any) {
        alert(error.message || "初始化失败");
      } finally {
        setLoading(false);
      }
    };

    init();
  }, [isReady, router, session]);
  useEffect(() => {
    const SpeechRecognition =
      typeof window !== "undefined"
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;
  
    setSpeechSupported(!!SpeechRecognition);
  }, []);
  useEffect(() => {
    if (!deadlineAt) {
      setRemainingSeconds(0);
      return;
    }
  
    const updateRemaining = () => {
      const normalizedDeadline =
        typeof deadlineAt === "string" && deadlineAt.includes("T")
          ? deadlineAt
          : String(deadlineAt).replace(" ", "T");
  
      const deadline = new Date(normalizedDeadline).getTime();
      const now = Date.now();
      const diff = Math.max(0, Math.floor((deadline - now) / 1000));
      setRemainingSeconds(diff);
  
      if (diff <= 0 && recognitionRef.current) {
        shouldKeepRecordingRef.current = false;
        recognitionRef.current.stop();
      }
    };
  
    updateRemaining();
    const timer = setInterval(updateRemaining, 1000);
  
    return () => clearInterval(timer);
  }, [deadlineAt]);

  const fetchMySubmissions = async (studentUsername: string) => {
    try {
      setRefreshing(true);

      const res = await fetch(
        apiUrl(`/api/v1/experiment/my-submissions/${studentUsername}`),
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

      const res = await fetch(apiUrl("/api/v1/experiment/upload-report"), {
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

      const res = await fetch(apiUrl("/api/v1/experiment/generate-questions"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          submission_id: submissionId,
          question_count: Math.floor(Math.random() * 3) + 4, // 4~6
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "生成问题失败");
      }

      alert("问题生成成功");
      setSelectedSubmissionId(submissionId);
      setDeadlineAt(data.answer_deadline_at || null);
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
        apiUrl(`/api/v1/experiment/submission-detail/${submissionId}`),
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
      setDeadlineAt(data.submission?.answer_deadline_at || null);
    } catch (error: any) {
      alert(error.message || "获取实验详情失败");
    }
  };
  const handleStartSpeech = (questionId: number) => {
    const SpeechRecognition =
      typeof window !== "undefined"
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;
  
    if (!SpeechRecognition) {
      alert("当前浏览器不支持语音识别，建议使用最新版 Chrome");
      return;
    }
  
    if (remainingSeconds <= 0) {
      alert("答题时间已结束，无法继续语音输入");
      return;
    }
  
    // 如果之前有识别对象，先停止，避免多个识别同时运行
    if (recognitionRef.current) {
      shouldKeepRecordingRef.current = false;
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
  
    const recognition = new SpeechRecognition();
  
    recognition.lang = "zh-CN";
  
    // 关键修改 1：开启连续识别
    recognition.continuous = true;
  
    // 保留中间结果，让学生说话时页面能实时显示文字
    recognition.interimResults = true;
  
    recognitionRef.current = recognition;
    shouldKeepRecordingRef.current = true;
    setRecordingQuestionId(questionId);
  
    // 保留已有回答内容，避免自动重启后把前面的识别文本清空
    let finalTranscript = answerInputs[questionId] || "";
  
    const hasAnswerTimeLeft = () => {
      if (!deadlineAt) return true;
  
      const normalizedDeadline =
        typeof deadlineAt === "string" && deadlineAt.includes("T")
          ? deadlineAt
          : String(deadlineAt).replace(" ", "T");
  
      return Date.now() < new Date(normalizedDeadline).getTime();
    };
  
    recognition.onresult = (event: any) => {
      let newInterimTranscript = "";
      let hasNewFinal = false;
    
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const transcript = result[0]?.transcript || "";
    
        if (result.isFinal) {
          finalTranscript += transcript;
          hasNewFinal = true;
        } else {
          newInterimTranscript += transcript;
        }
      }
    
      // 只把最终结果写入正式回答框
      if (hasNewFinal) {
        setAnswerInputs((prev) => {
          if (prev[questionId] === finalTranscript) return prev;
          return {
            ...prev,
            [questionId]: finalTranscript,
          };
        });
      }
    
      // 中间结果单独显示，不写进正式回答框
      setInterimInputs((prev) => {
        if (prev[questionId] === newInterimTranscript) return prev;
        return {
          ...prev,
          [questionId]: newInterimTranscript,
        };
      });
    };
    recognition.onerror = (event: any) => {
      console.warn("Speech recognition error:", event);
  
      // 停顿过久时，Chrome 可能会触发 no-speech。
      // 这种情况不要弹窗，也不要真正结束，交给 onend 自动重启。
      if (event.error === "no-speech") {
        return;
      }
  
      // 用户主动停止时可能触发 aborted，也不需要报错
      if (event.error === "aborted") {
        return;
      }
  
      shouldKeepRecordingRef.current = false;
      setRecordingQuestionId(null);
      alert("语音识别失败，请重试");
    };
  
    recognition.onend = () => {
      if (!shouldKeepRecordingRef.current || !hasAnswerTimeLeft()) {
        setInterimInputs((prev) => ({
          ...prev,
          [questionId]: "",
        }));
    
        setRecordingQuestionId(null);
        recognitionRef.current = null;
        shouldKeepRecordingRef.current = false;
        return;
      }
    
      setTimeout(() => {
        try {
          if (shouldKeepRecordingRef.current && hasAnswerTimeLeft()) {
            recognition.start();
          }
        } catch (error) {
          console.warn("语音识别自动重启失败：", error);
        }
      }, 250);
    };
  
    try {
      recognition.start();
      (window as any).__currentRecognition = recognition;
    } catch (error) {
      console.warn("语音识别启动失败：", error);
      shouldKeepRecordingRef.current = false;
      setRecordingQuestionId(null);
    }
  };
  const handleStopSpeech = () => {
    shouldKeepRecordingRef.current = false;
  
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (error) {
        console.warn("停止语音识别失败：", error);
      }
      recognitionRef.current = null;
    }
  
    if (recordingQuestionId !== null) {
      setInterimInputs((prev) => ({
        ...prev,
        [recordingQuestionId]: "",
      }));
    }
  
    setRecordingQuestionId(null);
  };
  const handleSubmitAnswer = async (questionId: number) => {
    if (remainingSeconds <= 0) {
      alert("答题时间已结束，无法继续提交");
      return;
    }
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

      const res = await fetch(apiUrl("/api/v1/experiment/submit-answer"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          question_id: questionId,
          answer_text: answerText,
          pause_count: pauseStats[questionId]?.pauseCount || 0,
          longest_pause_ms: pauseStats[questionId]?.longestPauseMs || 0,
          answer_duration_seconds: pauseStats[questionId]?.answerStartedAt
            ? Math.floor((Date.now() - pauseStats[questionId].answerStartedAt) / 1000)
            : null,
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
                accept=".txt,.docx,.pdf"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="block w-full rounded-xl border border-slate-300 bg-white px-4 py-3"
              />
              <p className="mt-2 text-sm text-slate-500">
                当前支持上传 txt、docx、pdf 文件；扫描版 pdf 可能无法正确提取文字。
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
            {deadlineAt && (
              <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-800">
                答题剩余时间：
                <span className="font-bold ml-2">
                  {Math.floor(remainingSeconds / 60)} 分 {remainingSeconds % 60} 秒
                </span>
              </div>
            )}

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
                        readOnly
                        placeholder="请点击“开始语音输入”后口头回答，识别结果会显示在这里"
                        className="w-full min-h-[120px] px-4 py-3 rounded-xl border border-slate-300 outline-none bg-slate-50"
                      />
                        {!speechSupported && (
                          <div className="mt-2 text-sm text-slate-500">
                             当前浏览器不支持语音识别，请使用文本输入，或换用最新版 Chrome。
                          </div>
                        )}
                      </div>

                      <div className="mt-3 flex flex-wrap gap-3">
                        {speechSupported && (
                          <>
                            <button
                              onClick={() => handleStartSpeech(q.id)}
                              disabled={recordingQuestionId === q.id || remainingSeconds <= 0}
                              className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                            >
                              {recordingQuestionId === q.id ? "正在识别..." : "开始语音输入"}
                            </button>

                            <button
                              onClick={handleStopSpeech}
                              disabled={recordingQuestionId !== q.id}
                              className="px-4 py-2 rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50"
                            >
                              停止语音输入
                            </button>
                         </>
                        )}

                        <button
                         onClick={() => handleSubmitAnswer(q.id)}
                          disabled={submittingQuestionId === q.id || remainingSeconds <= 0}
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
