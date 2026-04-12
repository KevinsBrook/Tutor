"use client";

import { useState, useEffect, useRef } from "react";
import {
  Send,
  Loader2,
  Bot,
  User,
  Database,
  Globe,
  Calculator,
  FileText,
  Microscope,
  Lightbulb,
  Trash2,
  ExternalLink,
  BookOpen,
  Sparkles,
  Edit3,
  GraduationCap,
  PenTool,
  Save,
} from "lucide-react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { useGlobal } from "@/context/GlobalContext";
import { apiUrl } from "@/lib/api";
import { processLatexContent } from "@/lib/latex";
import AddToNotebookModal from "@/components/AddToNotebookModal";
import { useTranslation } from "react-i18next";

interface KnowledgeBase {
  name: string;
  is_default?: boolean;
}

export default function HomePage() {
  const {
    chatState,
    setChatState,
    sendChatMessage,
    clearChatHistory,
    newChatSession,
  } = useGlobal();
  const { t } = useTranslation();

  const [inputMessage, setInputMessage] = useState("");
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [showNotebookModal, setShowNotebookModal] = useState(false);
  const [saveToNotebookLoading, setSaveToNotebookLoading] = useState(false);
  const [generatedNotebookContent, setGeneratedNotebookContent] = useState<any>(null);

  // Format chat history for notebook
  const formatChatForNotebook = () => {
    if (chatState.messages.length === 0)
      return { title: "", userQuery: "", output: "" };

    // Use the first user message as title
    const firstUserMsg = chatState.messages.find((m) => m.role === "user");
    const title =
      firstUserMsg?.content.slice(0, 50) +
        (firstUserMsg && firstUserMsg.content.length > 50 ? "..." : "") ||
      t("Chat Session");

    // Format all messages as markdown
    const formattedMessages = chatState.messages
      .map((msg, idx) => {
        const roleLabel =
          msg.role === "user"
            ? `👤 **${t("User")}**`
            : `🤖 **${t("Assistant")}**`;
        return `### ${roleLabel}\n\n${msg.content}`;
      })
      .join("\n\n---\n\n");

    // User query is the concatenation of all user messages
    const userQueries = chatState.messages
      .filter((m) => m.role === "user")
      .map((m) => m.content)
      .join("\n\n");

    return {
      title: `Chat: ${title}`,
      userQuery: userQueries,
      output: formattedMessages,
    };
  };

  // Fetch knowledge bases
  useEffect(() => {
    fetch(apiUrl("/api/v1/knowledge/list"))
      .then((res) => res.json())
      .then((data) => {
        // Ensure data is an array before processing
        const kbList = Array.isArray(data) ? data : [];
        setKbs(kbList);
        if (!chatState.selectedKb && kbList.length > 0) {
          const defaultKb = kbList.find((kb: KnowledgeBase) => kb.is_default);
          if (defaultKb) {
            setChatState((prev) => ({ ...prev, selectedKb: defaultKb.name }));
          } else {
            setChatState((prev) => ({ ...prev, selectedKb: kbList[0].name }));
          }
        }
      })
      .catch((err) => console.error("Failed to fetch KBs:", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesContainerRef.current) {
      const container = messagesContainerRef.current;
      // Use scrollTop instead of scrollIntoView to prevent page-level scrolling
      container.scrollTo({
        top: container.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [chatState.messages]);
  const getChatSessionId = () => {
    return (
      (chatState as any).sessionId ||
      (chatState as any).session_id ||
      (chatState as any).currentSessionId ||
      (chatState as any).current_session_id ||
      ""
    );
  };
  const buildGeneratedNoteForNotebook = () => {
    const fallback = formatChatForNotebook();
  
    const firstUserMsg = chatState.messages.find((m) => m.role === "user");
    const titleBase =
      firstUserMsg?.content?.slice(0, 50) +
        (firstUserMsg && firstUserMsg.content.length > 50 ? "..." : "") ||
      t("Chat Session");
  
    if (!generatedNotebookContent) {
      return {
        title: fallback.title || `Chat: ${titleBase}`,
        userQuery: fallback.userQuery || "",
        output: fallback.output || "",
        metadata: {
          source_type: "chat_raw",
          session_id:
            (chatState as any).sessionId ||
            (chatState as any).session_id ||
            (chatState as any).currentSessionId ||
            (chatState as any).current_session_id ||
            null,
          message_count: chatState.messages.length,
          enable_rag: chatState.enableRag,
          enable_web_search: chatState.enableWebSearch,
        },
      };
    }
  
    const summaryPart = generatedNotebookContent.summary
      ? `## 总结\n\n${
          typeof generatedNotebookContent.summary === "string"
            ? generatedNotebookContent.summary
            : JSON.stringify(generatedNotebookContent.summary, null, 2)
        }`
      : "";
  
    const outlinePart = generatedNotebookContent.outline
      ? `## 大纲\n\n\`\`\`json\n${JSON.stringify(
          generatedNotebookContent.outline,
          null,
          2,
        )}\n\`\`\``
      : "";
  
    const mindmapPart = generatedNotebookContent.mindmap
      ? `## 思维导图\n\n\`\`\`json\n${JSON.stringify(
          generatedNotebookContent.mindmap,
          null,
          2,
        )}\n\`\`\``
      : "";
    
  
    return {
      title: `Chat Note: ${titleBase}`,
      userQuery:
        chatState.messages
          .filter((m) => m.role === "user")
          .map((m) => m.content)
          .join("\n\n") || fallback.userQuery || "",
      output: [summaryPart, outlinePart, mindmapPart]
        .filter(Boolean)
        .join("\n\n---\n\n"),
      metadata: {
        source_type: "chat_generated_note",
        session_id:
          (chatState as any).sessionId ||
          (chatState as any).session_id ||
          (chatState as any).currentSessionId ||
          (chatState as any).current_session_id ||
          null,
        message_count: chatState.messages.length,
        enable_rag: chatState.enableRag,
        enable_web_search: chatState.enableWebSearch,
        generated_summary: generatedNotebookContent.summary || null,
        generated_outline: generatedNotebookContent.outline || null,
        generated_mindmap: generatedNotebookContent.mindmap || null,
      },
    };
  };
  const handleSaveToNotebook = async () => {
    try {
      if (chatState.messages.length === 0) return;
  
      const sessionId = getChatSessionId();
  
      if (!sessionId) {
        alert("当前对话没有有效的 session_id，无法生成整理笔记。请先确认聊天会话已成功保存。");
        return;
      }
  
      setSaveToNotebookLoading(true);
  
      const response = await fetch(apiUrl("/api/v1/notebook/generate-from-chat"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          generate_summary: true,
          generate_outline: true,
          generate_mindmap: true,
        }),
      });
  
      const data = await response.json();
  
      if (!response.ok) {
        throw new Error(data.detail || "生成整理笔记失败");
      }
  
      setGeneratedNotebookContent(data.result);
      setShowNotebookModal(true);
    } catch (error: any) {
      console.error("Failed to generate notebook content:", error);
      alert(error.message || "保存到笔记本失败");
    } finally {
      setSaveToNotebookLoading(false);
    }
  };
  

  const handleSend = () => {
    if (!inputMessage.trim() || chatState.isLoading) return;
    sendChatMessage(inputMessage);
    setInputMessage("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const quickActions = [
    {
      icon: Calculator,
      label: t("Smart Problem Solving"),
      href: "/solver",
      cardClass:
        "border-cyan-200/70 bg-cyan-50/70 text-cyan-700 hover:border-cyan-400 dark:border-cyan-800 dark:bg-cyan-950/30 dark:text-cyan-300",
      iconClass:
        "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/50 dark:text-cyan-300",
      description: t("Multi-agent reasoning"),
    },
    {
      icon: PenTool,
      label: t("Generate Practice Questions"),
      href: "/question",
      cardClass:
        "border-fuchsia-200/70 bg-fuchsia-50/70 text-fuchsia-700 hover:border-fuchsia-400 dark:border-fuchsia-800 dark:bg-fuchsia-950/30 dark:text-fuchsia-300",
      iconClass:
        "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/50 dark:text-fuchsia-300",
      description: t("Auto-validated quizzes"),
    },
    {
      icon: Microscope,
      label: t("Deep Research Reports"),
      href: "/research",
      cardClass:
        "border-emerald-200/70 bg-emerald-50/70 text-emerald-700 hover:border-emerald-400 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300",
      iconClass:
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
      description: t("Comprehensive analysis"),
    },
    {
      icon: Lightbulb,
      label: t("Generate Novel Ideas"),
      href: "/ideagen",
      cardClass:
        "border-amber-200/70 bg-amber-50/70 text-amber-700 hover:border-amber-400 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300",
      iconClass:
        "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
      description: t("Brainstorm & synthesize"),
    },
    {
      icon: GraduationCap,
      label: t("Guided Learning"),
      href: "/guide",
      cardClass:
        "border-indigo-200/70 bg-indigo-50/70 text-indigo-700 hover:border-indigo-400 dark:border-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-300",
      iconClass:
        "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300",
      description: t("Step-by-step tutoring"),
    },
    {
      icon: Edit3,
      label: t("Co-Writer"),
      href: "/co_writer",
      cardClass:
        "border-rose-200/70 bg-rose-50/70 text-rose-700 hover:border-rose-400 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-300",
      iconClass:
        "bg-rose-100 text-rose-700 dark:bg-rose-900/50 dark:text-rose-300",
      description: t("Collaborative writing"),
    },
  ];

  const hasMessages = chatState.messages.length > 0;
  const generatedNotebookRecord = buildGeneratedNoteForNotebook();

  return (
    <div className="animate-fade-in flex h-[calc(100vh-7rem)] min-h-0 flex-col overflow-hidden">
      {/* Empty State / Welcome Screen */}
      {!hasMessages && (
        <div className="flex-1 rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/85 px-6 shadow-[0_12px_40px_rgba(15,23,42,0.16)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/80">
          <div className="mx-auto grid h-full w-full max-w-6xl min-h-0 gap-6 py-8 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="flex min-h-0 flex-col justify-center">
              <div className="inline-flex w-fit items-center gap-2 rounded-full border border-indigo-200/70 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 dark:border-indigo-800 dark:bg-indigo-950/30 dark:text-indigo-300">
                <Sparkles className="h-3.5 w-3.5" />
                {t("DeepTutor Workspace")}
              </div>
              <h1 className="mt-4 text-4xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              {t("Welcome to DeepTutor")}
              </h1>
              <p className="mt-3 text-lg text-slate-500 dark:text-slate-400">
              {t("How can I help you today?")}
              </p>

              {/* Input Box - Centered */}
              <div className="mt-8 w-full max-w-2xl rounded-2xl border border-white/70 bg-white/70 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
            {/* Mode Toggles */}
            <div className="flex items-center justify-between mb-3 px-1">
              <div className="flex items-center gap-2">
                {/* RAG Toggle */}
                <button
                  onClick={() =>
                    setChatState((prev) => ({
                      ...prev,
                      enableRag: !prev.enableRag,
                    }))
                  }
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    chatState.enableRag
                      ? "bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-700"
                      : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
                >
                  <Database className="w-3.5 h-3.5" />
                  {t("RAG")}
                </button>

                {/* Web Search Toggle */}
                <button
                  onClick={() =>
                    setChatState((prev) => ({
                      ...prev,
                      enableWebSearch: !prev.enableWebSearch,
                    }))
                  }
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                    chatState.enableWebSearch
                      ? "bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700"
                      : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700"
                  }`}
                >
                  <Globe className="w-3.5 h-3.5" />
                  {t("Web Search")}
                </button>
              </div>

              {/* KB Selector */}
              {chatState.enableRag && (
                <select
                  value={chatState.selectedKb}
                  onChange={(e) =>
                    setChatState((prev) => ({
                      ...prev,
                      selectedKb: e.target.value,
                    }))
                  }
                  className="text-sm bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-1.5 outline-none focus:border-blue-400 dark:text-slate-200"
                >
                  {kbs.map((kb) => (
                    <option key={kb.name} value={kb.name}>
                      {kb.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

                {/* Input Field */}
                <div className="relative">
              <input
                ref={inputRef}
                type="text"
                className="w-full px-5 py-4 pr-14 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-2xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 text-slate-700 dark:text-slate-200 shadow-lg shadow-slate-200/50 dark:shadow-slate-900/50"
                placeholder={t("Ask anything...")}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={chatState.isLoading}
              />
              <button
                onClick={handleSend}
                disabled={chatState.isLoading || !inputMessage.trim()}
                className="absolute right-2 top-2 bottom-2 aspect-square bg-blue-600 text-white rounded-xl flex items-center justify-center hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 transition-all shadow-md shadow-blue-500/20"
              >
                {chatState.isLoading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </button>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-white/70 bg-white/65 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900/65">
              <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                {t("Explore Modules")}
              </h3>
              <div className="space-y-3">
                {quickActions.map((action, i) => (
                  <Link
                    key={i}
                    href={action.href}
                    className={`group flex items-center gap-3 rounded-2xl border px-4 py-3 transition-all hover:shadow-lg ${action.cardClass}`}
                  >
                    <div
                      className={`h-10 w-10 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform ${action.iconClass}`}
                    >
                      <action.icon className="w-5 h-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h4 className="text-sm font-semibold">{action.label}</h4>
                      <p className="text-xs opacity-85">{action.description}</p>
                    </div>
                    <ExternalLink className="h-4 w-4 opacity-60" />
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chat Interface - When there are messages */}
      {hasMessages && (
        <div className="grid h-full min-h-0 grid-rows-[auto_1fr_auto] rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/88 shadow-[0_12px_40px_rgba(15,23,42,0.16)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/82">
          {/* Header Bar */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-white/60 dark:border-slate-700 bg-white/75 dark:bg-slate-900/70 backdrop-blur-xl rounded-t-3xl">
            <div className="flex items-center gap-3">
              {/* Mode Toggles */}
              <button
                onClick={() =>
                  setChatState((prev) => ({
                    ...prev,
                    enableRag: !prev.enableRag,
                  }))
                }
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  chatState.enableRag
                    ? "bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
                }`}
              >
                <Database className="w-3 h-3" />
                {t("RAG")}
              </button>

              <button
                onClick={() =>
                  setChatState((prev) => ({
                    ...prev,
                    enableWebSearch: !prev.enableWebSearch,
                  }))
                }
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                  chatState.enableWebSearch
                    ? "bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
                }`}
              >
                <Globe className="w-3 h-3" />
                {t("Web Search")}
              </button>

              {chatState.enableRag && (
                <select
                  value={chatState.selectedKb}
                  onChange={(e) =>
                    setChatState((prev) => ({
                      ...prev,
                      selectedKb: e.target.value,
                    }))
                  }
                  className="text-xs bg-slate-100 dark:bg-slate-800 border-0 rounded-lg px-2 py-1 outline-none dark:text-slate-200"
                >
                  {kbs.map((kb) => (
                    <option key={kb.name} value={kb.name}>
                      {kb.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleSaveToNotebook}
                disabled={saveToNotebookLoading}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded-lg transition-colors disabled:opacity-50"
                title={t("Save to Notebook")}
              >
                {saveToNotebookLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Save className="w-3.5 h-3.5" />
                )}
                {t("Save to Notebook")}
              </button>
              <button
                onClick={newChatSession}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t("New Chat")}
              </button>
            </div>
          </div>

          {/* Messages Area */}
          <div
            ref={messagesContainerRef}
            className="min-h-0 overflow-y-auto px-6 py-6 space-y-6 bg-[color:var(--ui-panel)]/80"
          >
            {chatState.messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex w-full max-w-4xl animate-in fade-in slide-in-from-bottom-2 ${msg.role === "user" ? "ml-auto justify-end" : "mr-auto justify-start"}`}
              >
                {msg.role === "user" ? (
                  <div className="order-2 w-8 h-8 rounded-full bg-slate-200 dark:bg-slate-700 flex items-center justify-center shrink-0">
                      <User className="w-4 h-4 text-slate-500 dark:text-slate-400" />
                  </div>
                ) : (
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0 shadow-lg shadow-blue-500/30">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                )}
                <div className={`max-w-[86%] ${msg.role === "user" ? "order-1 mr-3" : "ml-3"} space-y-3`}>
                  {msg.role === "user" ? (
                    <div className="bg-slate-100 dark:bg-slate-700 px-4 py-3 rounded-2xl rounded-tr-none text-slate-800 dark:text-slate-200">
                      {msg.content}
                    </div>
                  ) : (
                    <div className="bg-white dark:bg-slate-800 px-5 py-4 rounded-2xl rounded-tl-none border border-slate-200 dark:border-slate-700 shadow-sm">
                        <div className="prose prose-slate dark:prose-invert prose-sm max-w-none">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[rehypeKatex]}
                          >
                            {processLatexContent(msg.content)}
                          </ReactMarkdown>
                        </div>

                        {/* Loading indicator */}
                        {msg.isStreaming && (
                          <div className="flex items-center gap-2 mt-3 text-blue-600 dark:text-blue-400 text-sm">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>{t("Generating response...")}</span>
                          </div>
                        )}
                    </div>
                  )}

                  {/* Sources */}
                  {msg.role !== "user" &&
                    msg.sources &&
                    (msg.sources.rag?.length ?? 0) + (msg.sources.web?.length ?? 0) >
                      0 && (
                      <div className="flex flex-wrap gap-2">
                        {msg.sources.rag?.map((source, i) => (
                          <div
                            key={`rag-${i}`}
                            className="flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded-lg text-xs"
                          >
                            <BookOpen className="w-3 h-3" />
                            <span>{source.kb_name}</span>
                          </div>
                        ))}
                        {msg.sources.web?.slice(0, 3).map((source, i) => (
                          <a
                            key={`web-${i}`}
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 rounded-lg text-xs hover:bg-emerald-100 dark:hover:bg-emerald-900/50 transition-colors"
                          >
                            <Globe className="w-3 h-3" />
                            <span className="max-w-[150px] truncate">
                              {source.title || source.url}
                            </span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        ))}
                      </div>
                    )}
                </div>
              </div>
            ))}

            {/* Status indicator */}
            {chatState.isLoading && chatState.currentStage && (
              <div className="flex gap-4 w-full max-w-4xl mx-auto">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shrink-0">
                  <Loader2 className="w-4 h-4 text-white animate-spin" />
                </div>
                <div className="flex-1 bg-slate-100 dark:bg-slate-800 px-4 py-3 rounded-2xl rounded-tl-none">
                  <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300 text-sm">
                    <span className="relative flex h-2 w-2">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                    </span>
                    {chatState.currentStage === "rag" &&
                      t("Searching knowledge base...")}
                    {chatState.currentStage === "web" &&
                      t("Searching the web...")}
                    {chatState.currentStage === "generating" &&
                      t("Generating response...")}
                    {!["rag", "web", "generating"].includes(
                      chatState.currentStage,
                    ) && chatState.currentStage}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Input Area - Fixed at bottom */}
          <div className="sticky bottom-0 z-10 border-t border-white/70 dark:border-slate-700 bg-white/90 dark:bg-slate-900/85 px-6 py-4 rounded-b-3xl">
            <div className="max-w-4xl mx-auto relative">
              <input
                ref={inputRef}
                type="text"
                className="w-full px-5 py-3.5 pr-14 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 text-slate-700 dark:text-slate-200"
                placeholder={t("Type your message...")}
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={chatState.isLoading}
              />
              <button
                onClick={handleSend}
                disabled={chatState.isLoading || !inputMessage.trim()}
                className="absolute right-2 top-2 bottom-2 aspect-square bg-blue-600 text-white rounded-lg flex items-center justify-center hover:bg-blue-700 disabled:opacity-50 disabled:hover:bg-blue-600 transition-all"
              >
                {chatState.isLoading ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add to Notebook Modal */}
      
      <AddToNotebookModal
        isOpen={showNotebookModal}
        onClose={() => {
          setShowNotebookModal(false);
          setGeneratedNotebookContent(null);
        }}
        recordType="chat"
        title={generatedNotebookRecord.title}
        userQuery={generatedNotebookRecord.userQuery}
        output={generatedNotebookRecord.output}
        metadata={generatedNotebookRecord.metadata}
        kbName={chatState.enableRag ? chatState.selectedKb : undefined}
      />
    </div>
  );
}
