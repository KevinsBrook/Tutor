"use client";

import { useEffect, useRef, useState } from "react";
import {
  Book,
  Bot,
  Database,
  FileText,
  Globe,
  Loader2,
  MessageCircle,
  Paperclip,
  Plus,
  Send,
  Trash2,
  User,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import { useGlobal } from "@/context/GlobalContext";
import { apiUrl } from "@/lib/api";
import { processLatexContent } from "@/lib/latex";
import AddToNotebookModal from "@/components/AddToNotebookModal";

interface KnowledgeBase {
  name: string;
  is_default?: boolean;
}

export default function ChatPage() {
  const {
    chatState,
    setChatState,
    sendChatMessage,
    clearChatHistory,
    newChatSession,
  } = useGlobal();
  const [inputMessage, setInputMessage] = useState("");
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [notebookRecord, setNotebookRecord] = useState<{
    title: string;
    userQuery: string;
    output: string;
    metadata?: Record<string, any>;
  } | null>(null);
  const [showNotebookModal, setShowNotebookModal] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(apiUrl("/api/v1/knowledge/list"))
      .then((res) => res.json())
      .then((data) => {
        const kbList = Array.isArray(data) ? data : [];
        setKbs(kbList);
        if (!chatState.selectedKb && kbList.length > 0) {
          const defaultKb = kbList.find((kb: KnowledgeBase) => kb.is_default);
          setChatState((prev) => ({
            ...prev,
            selectedKb: defaultKb?.name || kbList[0].name,
          }));
        }
      })
      .catch((err) => console.error("Failed to fetch KBs:", err));
  }, []);

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  }, [chatState.messages]);

  const handleSendWithFiles = async (content: string) => {
    const files = [...selectedFiles];
    const form = new FormData();
    form.append("message", content);
    files.forEach((file) => form.append("files", file));
    if (chatState.sessionId) {
      form.append("session_id", chatState.sessionId);
    }

    setChatState((prev) => ({
      ...prev,
      isLoading: true,
      currentStage: "uploading",
      messages: [...prev.messages, { role: "user", content }],
    }));
    setSelectedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    try {
      const res = await fetch(apiUrl("/api/v1/chat/with-files"), {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.message || "文件问答失败");

      setChatState((prev) => ({
        ...prev,
        sessionId: data.session_id || prev.sessionId,
        isLoading: false,
        currentStage: null,
        messages: [
          ...prev.messages,
          {
            role: "assistant",
            content: data.answer || "",
            sources: data.sources,
            isStreaming: false,
          },
        ],
      }));
    } catch (error: any) {
      setChatState((prev) => ({
        ...prev,
        isLoading: false,
        currentStage: null,
        messages: [
          ...prev.messages,
          {
            role: "assistant",
            content: `Error: ${error.message || "文件问答失败"}`,
          },
        ],
      }));
    }
  };

  const handleSend = () => {
    const content = inputMessage.trim();
    if (!content || chatState.isLoading) return;
    if (selectedFiles.length > 0) {
      handleSendWithFiles(content);
    } else {
      sendChatMessage(content);
    }
    setInputMessage("");
  };

  const openNotebookModal = (assistantIndex: number, output: string) => {
    const selectedMessages = chatState.messages.slice(0, assistantIndex + 1);
    const userMessage = [...selectedMessages]
      .reverse()
      .find((message) => message.role === "user");
    const userQuery = userMessage?.content || "智能问答记录";
    const conversationOutput = selectedMessages
      .map((message) => {
        const speaker = message.role === "user" ? "用户" : "助手";
        return `### ${speaker}\n\n${message.content}`;
      })
      .join("\n\n---\n\n");

    setNotebookRecord({
      title: userQuery.slice(0, 100) + (userQuery.length > 100 ? "..." : ""),
      userQuery,
      output: conversationOutput || output,
      metadata: {
        source: "chat",
        save_scope: "conversation_until_selected_message",
        message_count: selectedMessages.length,
        kb_name: chatState.selectedKb || undefined,
        enable_rag: chatState.enableRag,
        enable_web_search: chatState.enableWebSearch,
      },
    });
    setShowNotebookModal(true);
  };

  return (
    <div className="h-[calc(100vh-6rem)] bg-slate-50 px-4 py-4 text-slate-900">
      <div className="mx-auto flex h-full max-w-7xl flex-col gap-4">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-center gap-3">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-sky-100 bg-sky-50 text-sky-700">
                <MessageCircle className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-slate-950">智能问答</h1>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={chatState.selectedKb}
                onChange={(e) =>
                  setChatState((prev) => ({ ...prev, selectedKb: e.target.value }))
                }
                className="h-10 rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none"
              >
                <option value="">不选择知识库</option>
                {kbs.map((kb) => (
                  <option key={kb.name} value={kb.name}>
                    {kb.name}
                    {kb.is_default ? "（默认）" : ""}
                  </option>
                ))}
              </select>

              <button
                onClick={() =>
                  setChatState((prev) => ({ ...prev, enableRag: !prev.enableRag }))
                }
                className={`inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-sm transition ${
                  chatState.enableRag
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-slate-200 bg-white text-slate-600"
                }`}
              >
                <Database className="h-4 w-4" />
                RAG
              </button>

              <button
                onClick={() =>
                  setChatState((prev) => ({
                    ...prev,
                    enableWebSearch: !prev.enableWebSearch,
                  }))
                }
                className={`inline-flex h-10 items-center gap-2 rounded-xl border px-3 text-sm transition ${
                  chatState.enableWebSearch
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-white text-slate-600"
                }`}
              >
                <Globe className="h-4 w-4" />
                联网
              </button>

              <button
                onClick={newChatSession}
                className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 transition hover:bg-slate-50"
              >
                <Plus className="h-4 w-4" />
                新会话
              </button>

              <button
                onClick={clearChatHistory}
                className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 transition hover:bg-slate-50"
              >
                <Trash2 className="h-4 w-4" />
                清空
              </button>
            </div>
          </div>
        </section>

        <section className="flex min-h-0 flex-1 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div ref={messagesContainerRef} className="min-h-0 flex-1 overflow-y-auto p-4">
            {chatState.messages.length === 0 ? (
              <div className="flex h-full items-center justify-center text-center">
                <div>
                  <Bot className="mx-auto h-10 w-10 text-slate-300" />
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {chatState.messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex gap-3 ${
                      message.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {message.role === "assistant" && (
                      <div className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-50 text-sky-700">
                        <Bot className="h-4 w-4" />
                      </div>
                    )}
                    <div
                      className={`max-w-[82%] rounded-2xl px-4 py-3 text-sm leading-6 ${
                        message.role === "user"
                          ? "bg-slate-950 text-white"
                          : "border border-slate-200 bg-slate-50 text-slate-800"
                      }`}
                    >
                      {message.role === "assistant" ? (
                        <>
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[rehypeKatex]}
                          >
                            {processLatexContent(message.content)}
                          </ReactMarkdown>
                          {!message.isStreaming && (
                            <div className="mt-3 flex items-center justify-end border-t border-slate-200 pt-3">
                              <button
                                onClick={() => openNotebookModal(index, message.content)}
                                className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-indigo-600 transition hover:bg-indigo-50"
                              >
                                <Book className="h-3 w-3" />
                                添加到笔记
                              </button>
                            </div>
                          )}
                        </>
                      ) : (
                        <p className="whitespace-pre-wrap">{message.content}</p>
                      )}
                    </div>
                    {message.role === "user" && (
                      <div className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white">
                        <User className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                ))}
                {chatState.isLoading && (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在生成回答...
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="border-t border-slate-200 p-4">
            {selectedFiles.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {selectedFiles.map((file, index) => (
                  <span
                    key={`${file.name}-${file.size}-${index}`}
                    className="inline-flex max-w-[240px] items-center gap-2 rounded-lg border border-sky-100 bg-sky-50 px-2.5 py-1 text-xs text-sky-700"
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{file.name}</span>
                    <button
                      onClick={() =>
                        setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
                      }
                      className="rounded p-0.5 hover:bg-sky-100"
                      aria-label="移除文件"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                accept=".txt,.md,.csv,.json,.pdf,.py,.js,.ts,.html,.css"
                onChange={(e) => {
                  setSelectedFiles(Array.from(e.target.files || []));
                }}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={chatState.isLoading}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Paperclip className="h-4 w-4" />
                输入文件
              </button>
              <input
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                className="h-11 flex-1 rounded-xl border border-slate-200 px-4 text-sm outline-none transition focus:border-sky-300 focus:ring-2 focus:ring-sky-100"
                placeholder="输入你的问题"
                disabled={chatState.isLoading}
              />
              <button
                onClick={handleSend}
                disabled={!inputMessage.trim() || chatState.isLoading}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {chatState.isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                发送
              </button>
            </div>
          </div>
        </section>
      </div>
      {notebookRecord && (
        <AddToNotebookModal
          isOpen={showNotebookModal}
          onClose={() => {
            setShowNotebookModal(false);
            setNotebookRecord(null);
          }}
          recordType="chat"
          title={notebookRecord.title}
          userQuery={notebookRecord.userQuery}
          output={notebookRecord.output}
          metadata={notebookRecord.metadata}
          kbName={chatState.selectedKb}
        />
      )}
    </div>
  );
}
