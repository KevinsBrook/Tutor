"use client";

import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Database,
  Globe,
  Loader2,
  MessageCircle,
  Plus,
  Send,
  Trash2,
  User,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import { useGlobal } from "@/context/GlobalContext";
import { apiUrl } from "@/lib/api";
import { processLatexContent } from "@/lib/latex";

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

  const handleSend = () => {
    const content = inputMessage.trim();
    if (!content || chatState.isLoading) return;
    sendChatMessage(content);
    setInputMessage("");
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
                <p className="text-sm text-slate-500">
                  独立问答页面，可结合知识库和联网搜索辅助学习。
                </p>
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
                  <p className="mt-3 text-sm text-slate-500">
                    输入问题开始对话，或先选择课程知识库再提问。
                  </p>
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
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm, remarkMath]}
                          rehypePlugins={[rehypeKatex]}
                        >
                          {processLatexContent(message.content)}
                        </ReactMarkdown>
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
            <div className="flex gap-2">
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
    </div>
  );
}
