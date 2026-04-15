"use client";

import { useState, useEffect } from "react";
import {
  BookOpen,
  Plus,
  Trash2,
  Edit3,
  Search,
  Clock,
  FileText,
  Calculator,
  Microscope,
  PenTool,
  ChevronRight,
  ChevronLeft,
  X,
  Check,
  FolderOpen,
  Database,
  Download,
  Upload,
  MessageSquare,
  Loader2
} from "lucide-react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { apiUrl } from "@/lib/api";
import { processLatexContent } from "@/lib/latex";
import { useTranslation } from "react-i18next";

interface NotebookRecord {
  id: string;
  type: "solve" | "question" | "research" | "co_writer" | "chat";
  title: string;
  user_query: string;
  output: string;
  metadata: Record<string, any>;
  created_at: number;
  kb_name?: string;
}

interface Notebook {
  id: string;
  name: string;
  description: string;
  created_at: number;
  updated_at: number;
  records: NotebookRecord[];
  color: string;
  icon: string;
}

interface NotebookSummary {
  id: string;
  name: string;
  description: string;
  created_at: number;
  updated_at: number;
  record_count: number;
  color: string;
  icon: string;
}

const COLORS = [
  "#3B82F6", // blue
  "#8B5CF6", // purple
  "#EC4899", // pink
  "#EF4444", // red
  "#F97316", // orange
  "#EAB308", // yellow
  "#22C55E", // green
  "#14B8A6", // teal
  "#06B6D4", // cyan
  "#6366F1", // indigo
];

const getRecordIcon = (type: string) => {
  switch (type) {
    case "solve":
      return <Calculator className="w-4 h-4" />;
    case "question":
      return <FileText className="w-4 h-4" />;
    case "research":
      return <Microscope className="w-4 h-4" />;
    case "co_writer":
      return <PenTool className="w-4 h-4" />;
    case "chat":
      return <MessageSquare className="w-4 h-4" />;
    default:
      return <FileText className="w-4 h-4" />;
  }
};

const getRecordLabel = (type: string) => {
  switch (type) {
    case "solve":
      return "Solver";
    case "question":
      return "Question";
    case "research":
      return "Research";
    case "co_writer":
      return "Co-Writer";
    case "chat":
      return "Chat";
    default:
      return "Record";
  }
};

const getRecordColor = (type: string) => {
  switch (type) {
    case "solve":
      return "text-blue-500 bg-blue-50 border-blue-200";
    case "question":
      return "text-purple-500 bg-purple-50 border-purple-200";
    case "research":
      return "text-emerald-500 bg-emerald-50 border-emerald-200";
    case "co_writer":
      return "text-amber-500 bg-amber-50 border-amber-200";
    case "chat":
      return "text-cyan-500 bg-cyan-50 border-cyan-200";
    default:
      return "text-slate-500 bg-slate-50 border-slate-200";
  }
};

export default function NotebookPage() {
  const { t } = useTranslation();
  const [regenerateLoading, setRegenerateLoading] = useState(false);
  const [regeneratedData, setRegeneratedData] = useState<any>(null);
  const [notebooks, setNotebooks] = useState<NotebookSummary[]>([]);
  const [selectedNotebook, setSelectedNotebook] = useState<Notebook | null>(
    null,
  );
  const [selectedRecord, setSelectedRecord] = useState<NotebookRecord | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  // Collapse states
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [middleCollapsed, setMiddleCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  // Modal states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(
    null,
  );

  // Form states
  const [newNotebook, setNewNotebook] = useState({
    name: "",
    description: "",
    color: "#3B82F6",
  });
  const [editingNotebook, setEditingNotebook] = useState<{
    id: string;
    name: string;
    description: string;
    color: string;
  } | null>(null);


  // Import modal state
  const [showImportModal, setShowImportModal] = useState(false);
  const [availableNotebooks, setAvailableNotebooks] = useState<
    NotebookSummary[]
  >([]);
  const [importSourceNotebook, setImportSourceNotebook] = useState<string>("");
  const [importSourceRecords, setImportSourceRecords] = useState<
    NotebookRecord[]
  >([]);
  const [selectedImportRecords, setSelectedImportRecords] = useState<
    Set<string>
  >(new Set());
  const [loadingImport, setLoadingImport] = useState(false);

  // Fetch notebooks
  useEffect(() => {
    fetchNotebooks();
  }, []);
  useEffect(() => {
    setRegeneratedData(null);
  }, [selectedRecord?.id]);

  const fetchNotebooks = async () => {
    try {
      const res = await fetch(apiUrl("/api/v1/notebook/list"));
      const data = await res.json();
      setNotebooks(data.notebooks || []);
    } catch (err) {
      console.error("Failed to fetch notebooks:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchNotebookDetail = async (notebookId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/v1/notebook/${notebookId}`));
      const data = await res.json();
      setSelectedNotebook(data);
      setSelectedRecord(null);
    } catch (err) {
      console.error("Failed to fetch notebook detail:", err);
    }
  };

  const handleCreateNotebook = async () => {
    if (!newNotebook.name.trim()) return;

    try {
      const res = await fetch(apiUrl("/api/v1/notebook/create"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newNotebook),
      });
      const data = await res.json();
      if (data.success) {
        fetchNotebooks();
        setShowCreateModal(false);
        setNewNotebook({ name: "", description: "", color: "#3B82F6" });
      }
    } catch (err) {
      console.error("Failed to create notebook:", err);
    }
  };

  const handleUpdateNotebook = async () => {
    if (!editingNotebook || !editingNotebook.name.trim()) return;

    try {
      const res = await fetch(
        apiUrl(`/api/v1/notebook/${editingNotebook.id}`),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: editingNotebook.name,
            description: editingNotebook.description,
            color: editingNotebook.color,
          }),
        },
      );
      const data = await res.json();
      if (data.success) {
        fetchNotebooks();
        if (selectedNotebook?.id === editingNotebook.id) {
          fetchNotebookDetail(editingNotebook.id);
        }
        setShowEditModal(false);
        setEditingNotebook(null);
      }
    } catch (err) {
      console.error("Failed to update notebook:", err);
    }
  };

  const handleDeleteNotebook = async (notebookId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/v1/notebook/${notebookId}`), {
        method: "DELETE",
      });
      const data = await res.json();
      if (data.success) {
        fetchNotebooks();
        if (selectedNotebook?.id === notebookId) {
          setSelectedNotebook(null);
        }
        setShowDeleteConfirm(null);
      }
    } catch (err) {
      console.error("Failed to delete notebook:", err);
    }
  };

  const handleDeleteRecord = async (recordId: string) => {
    if (!selectedNotebook) return;

    try {
      const res = await fetch(
        apiUrl(`/api/v1/notebook/${selectedNotebook.id}/records/${recordId}`),
        {
          method: "DELETE",
        },
      );
      const data = await res.json();
      if (data.success) {
        fetchNotebookDetail(selectedNotebook.id);
        if (selectedRecord?.id === recordId) {
          setSelectedRecord(null);
        }
      }
    } catch (err) {
      console.error("Failed to delete record:", err);
    }
  };

  // Export functions
  const exportAsMarkdown = () => {
    if (!selectedRecord) return;

    const content = `# ${selectedRecord.title}\n\n**Type:** ${selectedRecord.type}\n**Created:** ${new Date(selectedRecord.created_at * 1000).toLocaleString()}\n\n## ${t("User Query")}\n\n${selectedRecord.user_query}\n\n## ${t("Output")}\n\n${selectedRecord.output}`;

    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedRecord.title.replace(/[^a-zA-Z0-9]/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportAsPDF = async () => {
    if (!selectedRecord) return;

    // Use browser print for simple PDF export
    const printContent = `
      <html>
        <head>
          <title>${selectedRecord.title}</title>
          <style>
            body { font-family: system-ui, -apple-system, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
            h1 { color: #1e293b; }
            .meta { color: #64748b; font-size: 14px; margin-bottom: 20px; }
            .section { margin: 20px 0; }
            .section-title { font-size: 12px; text-transform: uppercase; color: #94a3b8; font-weight: 600; margin-bottom: 8px; }
            .query { background: #eff6ff; padding: 16px; border-radius: 8px; }
            .output { background: #f8fafc; padding: 16px; border-radius: 8px; white-space: pre-wrap; }
          </style>
        </head>
        <body>
          <h1>${selectedRecord.title}</h1>
          <div class="meta">${selectedRecord.type.toUpperCase()} • ${new Date(selectedRecord.created_at * 1000).toLocaleString()}</div>
          <div class="section">
            <div class="section-title">${t("User Query")}</div>
            <div class="query">${selectedRecord.user_query}</div>
          </div>
          <div class="section">
            <div class="section-title">${t("Output")}</div>
            <div class="output">${selectedRecord.output}</div>
          </div>
        </body>
      </html>
    `;

    const printWindow = window.open("", "_blank");
    if (printWindow) {
      printWindow.document.write(printContent);
      printWindow.document.close();
      printWindow.print();
    }
  };

  // Import functions
  const openImportModal = async () => {
    if (!selectedNotebook) return;

    setShowImportModal(true);
    setLoadingImport(true);

    try {
      const res = await fetch(apiUrl("/api/v1/notebook/list"));
      const data = await res.json();
      // Filter out current notebook
      const others = (data.notebooks || []).filter(
        (nb: NotebookSummary) =>
          nb.id !== selectedNotebook.id && nb.record_count > 0,
      );
      setAvailableNotebooks(others);
    } catch (err) {
      console.error("Failed to fetch notebooks for import:", err);
    } finally {
      setLoadingImport(false);
    }
  };

  const loadImportSourceRecords = async (notebookId: string) => {
    setImportSourceNotebook(notebookId);
    setLoadingImport(true);

    try {
      const res = await fetch(apiUrl(`/api/v1/notebook/${notebookId}`));
      const data = await res.json();
      setImportSourceRecords(data.records || []);
      setSelectedImportRecords(new Set());
    } catch (err) {
      console.error("Failed to fetch records for import:", err);
    } finally {
      setLoadingImport(false);
    }
  };

  const toggleImportRecord = (recordId: string) => {
    setSelectedImportRecords((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(recordId)) {
        newSet.delete(recordId);
      } else {
        newSet.add(recordId);
      }
      return newSet;
    });
  };

  const handleImportRecords = async () => {
    if (!selectedNotebook || selectedImportRecords.size === 0) return;

    setLoadingImport(true);

    try {
      // Get selected records
      const recordsToImport = importSourceRecords.filter((r) =>
        selectedImportRecords.has(r.id),
      );

      // Add each record to current notebook
      for (const record of recordsToImport) {
        await fetch(apiUrl("/api/v1/notebook/add_record"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            notebook_ids: [selectedNotebook.id],
            record_type: record.type,
            title: `[Imported] ${record.title}`,
            user_query: record.user_query,
            output: record.output,
            metadata: {
              ...record.metadata,
              imported_from: importSourceNotebook,
            },
            kb_name: record.kb_name || null,
          }),
        });
      }

      // Refresh notebook
      fetchNotebookDetail(selectedNotebook.id);
      setShowImportModal(false);
      setImportSourceNotebook("");
      setImportSourceRecords([]);
      setSelectedImportRecords(new Set());
    } catch (err) {
      console.error("Failed to import records:", err);
    } finally {
      setLoadingImport(false);
    }
  };
  const handleRegenerateNote = async () => {
    if (!selectedRecord) return;
  
    const sessionId = selectedRecord.metadata?.session_id;
    if (!sessionId) {
      alert("当前记录没有 session_id，无法重新整理。");
      return;
    }
  
    try {
      setRegenerateLoading(true);
  
      const res = await fetch(apiUrl("/api/v1/notebook/generate-from-chat"), {
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
  
      const data = await res.json();
  
      if (!res.ok) {
        throw new Error(data.detail || "重新整理失败");
      }
  
      setRegeneratedData(data.result);
    } catch (err: any) {
      console.error("Failed to regenerate note:", err);
      alert(err.message || "重新整理失败");
    } finally {
      setRegenerateLoading(false);
    }
  };
  const renderSummary = (summary: any) => {
    if (!summary) return null;
  
    if (typeof summary === "string") {
      return <p className="text-slate-700 dark:text-slate-200">{summary}</p>;
    }
  
    return (
      <div className="space-y-3">
        {Object.entries(summary).map(([key, value], idx) => (
          <div key={`${key}-${idx}`}>
            <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">
              {key}
            </div>
            <div className="text-sm text-slate-700 dark:text-slate-200 leading-6">
              {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
            </div>
          </div>
        ))}
      </div>
    );
  };
  
  const renderOutlineTree = (items: any[], level = 0) => {
    if (!Array.isArray(items) || items.length === 0) return null;
  
    return (
      <ul className={level === 0 ? "space-y-2" : "space-y-1"} style={{ marginLeft: `${level * 16}px` }}>
        {items.map((item, idx) => (
          <li key={`${item?.title || "item"}-${idx}`} className="text-sm text-slate-700 dark:text-slate-200">
            <div className="flex items-start gap-2">
              <span className="mt-1 text-slate-400">•</span>
              <div>
                <div className="font-medium">{item?.title || "未命名节点"}</div>
                {Array.isArray(item?.children) && item.children.length > 0 && (
                  <div className="mt-1">{renderOutlineTree(item.children, level + 1)}</div>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    );
  };
  
  const renderMindmapTree = (node: any, level = 0) => {
    if (!node) return null;
  
    return (
      <div className={`${level > 0 ? "ml-6 mt-2" : ""}`}>
        <div className="flex items-start gap-2">
          <span className="mt-1 text-cyan-500">•</span>
          <div>
            <div className={`text-sm ${level === 0 ? "font-semibold text-slate-900 dark:text-slate-100" : "text-slate-700 dark:text-slate-200"}`}>
              {node?.topic || "未命名主题"}
            </div>
            {Array.isArray(node?.children) && node.children.length > 0 && (
              <div className="mt-1 space-y-1">
                {node.children.map((child: any, idx: number) => (
                  <div key={`${child?.topic || "node"}-${idx}`}>
                    {renderMindmapTree(child, level + 1)}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };
  const buildMindmapFlow = (mindmap: any) => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
  
    if (!mindmap) {
      return { nodes, edges };
    }
  
    let nodeIndex = 0;
    const levelXGap = 220;
    const nodeYGap = 100;
  
    const traverse = (
      node: any,
      depth: number,
      y: number,
      parentId?: string,
    ): number => {
      const id = `node-${nodeIndex++}`;
      const label = node?.topic || "未命名主题";
  
      nodes.push({
        id,
        data: { label },
        position: { x: depth * levelXGap, y },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          borderRadius: 12,
          padding: 10,
          border: "1px solid #cbd5e1",
          background: "#ffffff",
          color: "#0f172a",
          fontSize: 13,
          minWidth: 120,
          textAlign: "center",
        },
      });
  
      if (parentId) {
        edges.push({
          id: `edge-${parentId}-${id}`,
          source: parentId,
          target: id,
          type: "smoothstep",
        });
      }
  
      const children = Array.isArray(node?.children) ? node.children : [];
      if (children.length === 0) {
        return y + nodeYGap;
      }
  
      let currentY = y;
      for (const child of children) {
        currentY = traverse(child, depth + 1, currentY, id);
      }
  
      return currentY;
    };
  
    traverse(mindmap, 0, 0);
  
    return { nodes, edges };
  };

  const filteredNotebooks = notebooks.filter(
    (nb) =>
      nb.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      nb.description.toLowerCase().includes(searchTerm.toLowerCase()),
  );
  const generatedSummary =
    regeneratedData?.summary ?? selectedRecord?.metadata?.generated_summary;
  const generatedOutline =
    regeneratedData?.outline ?? selectedRecord?.metadata?.generated_outline;
  const generatedMindmap =
    regeneratedData?.mindmap ?? selectedRecord?.metadata?.generated_mindmap;
  const mindmapFlow = generatedMindmap ? buildMindmapFlow(generatedMindmap) : { nodes: [], edges: [] };
  return (
    <div
      className="h-[calc(100vh-7rem)] min-h-0 flex gap-4 p-3 animate-fade-in rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/72 shadow-[0_12px_40px_rgba(15,23,42,0.16)] backdrop-blur"
      style={{ justifyContent: "flex-start" }}
    >
      {/* Left Panel: Notebook List */}
      <div
        className={`flex flex-col rounded-2xl border border-rose-200/60 bg-rose-50/45 shadow-[0_10px_30px_rgba(244,63,94,0.16)] dark:border-rose-900/50 dark:bg-rose-950/18 overflow-hidden transition-all duration-300 flex-shrink-0 ${leftCollapsed ? "overflow-hidden" : ""}`}
        style={{
          width: leftCollapsed ? 0 : "288px",
          minWidth: leftCollapsed ? 0 : "288px",
          maxWidth: leftCollapsed ? 0 : "288px",
          opacity: leftCollapsed ? 0 : 1,
        }}
      >
        {/* Header */}
        <div className="p-4 border-b border-slate-100 dark:border-slate-700 bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/30 dark:to-purple-900/30">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
              {t("Notebooks")}
            </h1>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowCreateModal(true)}
                className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-all shadow-md shadow-indigo-500/20"
              >
                <Plus className="w-4 h-4" />
              </button>
              <button
                onClick={() => setLeftCollapsed(true)}
                className="p-2 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg shadow-sm hover:bg-slate-50 dark:hover:bg-slate-600 transition-all"
                title={t("Collapse left panel")}
              >
                <ChevronLeft className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder={t("Search notebooks...")}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none"
            />
          </div>
        </div>

        {/* Notebook List */}
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="p-8 text-center text-slate-400 dark:text-slate-500">
              {t("Loading")}
            </div>
          ) : filteredNotebooks.length === 0 ? (
            <div className="p-8 text-center">
              <FolderOpen className="w-12 h-12 text-slate-200 dark:text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 dark:text-slate-400 text-sm">
                {t("No notebooks yet")}
              </p>
              <p className="text-slate-400 dark:text-slate-500 text-xs mt-1">
                {t("Create your first notebook to get started")}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredNotebooks.map((nb) => (
                <div
                  key={nb.id}
                  onClick={() => fetchNotebookDetail(nb.id)}
                  className={`p-3 rounded-xl cursor-pointer transition-all group ${
                    selectedNotebook?.id === nb.id
                      ? "bg-indigo-50 dark:bg-indigo-900/30 border-2 border-indigo-200 dark:border-indigo-700"
                      : "hover:bg-slate-50 dark:hover:bg-slate-700/50 border-2 border-transparent"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                      style={{
                        backgroundColor: `${nb.color}20`,
                        color: nb.color,
                      }}
                    >
                      <BookOpen className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <h3 className="font-semibold text-slate-900 dark:text-slate-100 truncate text-sm">
                          {nb.name}
                        </h3>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingNotebook({
                                id: nb.id,
                                name: nb.name,
                                description: nb.description,
                                color: nb.color,
                              });
                              setShowEditModal(true);
                            }}
                            className="p-1 hover:bg-slate-200 dark:hover:bg-slate-600 rounded"
                          >
                            <Edit3 className="w-3 h-3 text-slate-500 dark:text-slate-400" />
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setShowDeleteConfirm(nb.id);
                            }}
                            className="p-1 hover:bg-red-100 dark:hover:bg-red-900/40 rounded"
                          >
                            <Trash2 className="w-3 h-3 text-red-500 dark:text-red-400" />
                          </button>
                        </div>
                      </div>
                      {nb.description && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
                          {nb.description}
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-400 dark:text-slate-500">
                        <span className="flex items-center gap-1">
                          <FileText className="w-3 h-3" />
                          {nb.record_count} records
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(nb.updated_at * 1000).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {leftCollapsed && (
        <button
          onClick={() => setLeftCollapsed(false)}
          className="p-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-sm hover:bg-slate-50 dark:hover:bg-slate-700 transition-all self-start mt-4 shrink-0"
          title={t("Expand left panel")}
        >
          <ChevronRight className="w-4 h-4 text-slate-600 dark:text-slate-300" />
        </button>
      )}

      {/* Middle Panel: Records List */}
      <div
        className={`flex flex-col rounded-2xl border border-violet-200/60 bg-violet-50/45 shadow-[0_10px_30px_rgba(139,92,246,0.16)] dark:border-violet-900/50 dark:bg-violet-950/18 overflow-hidden transition-all duration-300 flex-shrink-0 ${middleCollapsed ? "overflow-hidden" : ""}`}
        style={{
          width: middleCollapsed ? 0 : "320px",
          minWidth: middleCollapsed ? 0 : "320px",
          maxWidth: middleCollapsed ? 0 : "320px",
          opacity: middleCollapsed ? 0 : 1,
        }}
      >
        {/* Notebook Header */}
        <div
          className="p-4 border-b border-slate-100 dark:border-slate-700 shrink-0"
          style={{
            backgroundColor: selectedNotebook
              ? `${selectedNotebook.color}10`
              : "transparent",
          }}
        >
          <div className="flex items-center justify-between gap-3">
            {selectedNotebook ? (
              <>
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
                    style={{
                      backgroundColor: `${selectedNotebook.color}20`,
                      color: selectedNotebook.color,
                    }}
                  >
                    <BookOpen className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h2 className="font-bold text-slate-900 dark:text-slate-100 truncate">
                      {selectedNotebook.name}
                    </h2>
                    {selectedNotebook.description && (
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 truncate">
                        {selectedNotebook.description}
                      </p>
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex-1" />
            )}
            <button
              onClick={() => setMiddleCollapsed(true)}
              className="p-2 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg shadow-sm hover:bg-slate-50 dark:hover:bg-slate-600 transition-all shrink-0"
              title={t("Collapse middle panel")}
            >
              <ChevronLeft className="w-4 h-4 text-slate-600 dark:text-slate-300" />
            </button>
          </div>
        </div>

        {selectedNotebook ? (
          <>
            {/* Records List */}
            <div className="flex-1 overflow-y-auto p-3">
              {selectedNotebook.records.length === 0 ? (
                <div className="p-8 text-center">
                  <FileText className="w-12 h-12 text-slate-200 dark:text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-500 dark:text-slate-400 text-sm">
                    {t("No records yet")}
                  </p>
                  <p className="text-slate-400 dark:text-slate-500 text-xs mt-1">
                    {t(
                      "Add records from Solver, Question, Research, or Co-Writer",
                    )}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {selectedNotebook.records.map((record) => (
                    <div
                      key={record.id}
                      onClick={() => setSelectedRecord(record)}
                      className={`p-3 rounded-xl cursor-pointer transition-all group border ${
                        selectedRecord?.id === record.id
                          ? "bg-slate-50 dark:bg-slate-700/50 border-slate-300 dark:border-slate-600"
                          : "hover:bg-slate-50 dark:hover:bg-slate-700/50 border-transparent hover:border-slate-200 dark:hover:border-slate-600"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div
                          className={`p-2 rounded-lg border ${getRecordColor(record.type)}`}
                        >
                          {getRecordIcon(record.type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span
                              className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${getRecordColor(record.type)}`}
                            >
                              {getRecordLabel(record.type)}
                            </span>
                            {record.kb_name && (
                              <span className="text-[10px] text-slate-400 dark:text-slate-500 flex items-center gap-0.5">
                                <Database className="w-3 h-3" />
                                {record.kb_name}
                              </span>
                            )}
                          </div>
                          <h4 className="text-sm font-medium text-slate-900 dark:text-slate-100 line-clamp-1">
                            {record.title}
                          </h4>
                          <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mt-1">
                            {record.user_query}
                          </p>
                          <div className="flex items-center justify-between mt-2">
                            <span className="text-[10px] text-slate-400 dark:text-slate-500">
                              {new Date(
                                record.created_at * 1000,
                              ).toLocaleString()}
                            </span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleDeleteRecord(record.id);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-100 dark:hover:bg-red-900/40 rounded transition-all"
                            >
                              <Trash2 className="w-3 h-3 text-red-500 dark:text-red-400" />
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-400 dark:text-slate-500 p-8">
            <BookOpen className="w-16 h-16 text-slate-200 dark:text-slate-600 mb-4" />
            <p className="text-slate-500 dark:text-slate-400">
              {t("Select a notebook to view records")}
            </p>
          </div>
        )}
      </div>
      {middleCollapsed && (
        <button
          onClick={() => setMiddleCollapsed(false)}
          className="p-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-sm hover:bg-slate-50 dark:hover:bg-slate-700 transition-all self-start mt-4 shrink-0"
          title={t("Expand middle panel")}
        >
          <ChevronRight className="w-4 h-4 text-slate-600 dark:text-slate-300" />
        </button>
      )}

      {/* Right Panel: Record Detail */}
      <div
        className={`flex flex-col rounded-2xl border border-cyan-200/60 bg-cyan-50/45 shadow-[0_10px_30px_rgba(6,182,212,0.16)] dark:border-cyan-900/50 dark:bg-cyan-950/18 overflow-hidden transition-all duration-300 ${rightCollapsed ? "flex-shrink-0 overflow-hidden" : "flex-1"}`}
        style={{
          width: rightCollapsed ? 0 : undefined,
          minWidth: rightCollapsed ? 0 : undefined,
          maxWidth: rightCollapsed ? 0 : undefined,
          opacity: rightCollapsed ? 0 : 1,
          marginLeft: "auto",
          order: 3,
        }}
      >
        {/* Record Header with Action Buttons */}
        <div className="p-4 border-b border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/50 shrink-0">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <button
                onClick={() => setRightCollapsed(true)}
                className="p-2 bg-white dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg shadow-sm hover:bg-slate-50 dark:hover:bg-slate-600 transition-all shrink-0"
                title={t("Collapse right panel")}
              >
                <ChevronRight className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              </button>
              {selectedRecord ? (
                <>
                  <div
                    className={`p-2 rounded-lg border ${getRecordColor(selectedRecord.type)} shrink-0`}
                  >
                    {getRecordIcon(selectedRecord.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h2 className="font-bold text-slate-900 dark:text-slate-100 truncate">
                      {selectedRecord.title}
                    </h2>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${getRecordColor(selectedRecord.type)}`}
                      >
                        {getRecordLabel(selectedRecord.type)}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-500">
                        {new Date(
                          selectedRecord.created_at * 1000,
                        ).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex-1" />
              )}
            </div>

            {/* Action Buttons - Export and History */}
            {selectedRecord && (
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={handleRegenerateNote}
                  disabled={regenerateLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/40 rounded-lg transition-colors disabled:opacity-50"
                  title="重新整理当前笔记"
                >
                 {regenerateLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                 ) : (
                  <PenTool className="w-3.5 h-3.5" />
                 )}
                 重新整理
                </button>
                <button
                  onClick={exportAsMarkdown}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                  title={t("Export as Markdown")}
                >
                  <Download className="w-3.5 h-3.5" />
                  .md
                </button>
                <button
                  onClick={exportAsPDF}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                  title={t("Export as PDF")}
                >
                  <Download className="w-3.5 h-3.5" />
                  .pdf
                </button>
                <button
                  onClick={openImportModal}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 hover:bg-indigo-50 dark:hover:bg-indigo-900/40 rounded-lg transition-colors"
                  title={t("Import records from other notebooks")}
                >
                  <Upload className="w-3.5 h-3.5" />
                  {t("Import")}
                </button>
              </div>
            )}
          </div>
        </div>

        {selectedRecord ? (
          <>
            {/* Record Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {/* User Query */}
              <div className="mb-6">
                <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("User Query")}
                </h3>
                <div className="p-4 bg-blue-50 dark:bg-blue-900/30 rounded-xl border border-blue-100 dark:border-blue-800">
                  <p className="text-slate-700 dark:text-slate-200">
                    {selectedRecord.user_query}
                  </p>
                </div>
              </div>

              {/* Summary */}
              {generatedSummary && (
                <div className="mb-6">
                  <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                    总结
                  </h3>
                  <div className="p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl border border-slate-100 dark:border-slate-600">
                    {renderSummary(generatedSummary)}
                  </div>
                </div>
              )}

              {/* Outline */}
              {generatedOutline && (
                <div className="mb-6">
                  <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                    大纲
                  </h3>
                  <div className="p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl border border-slate-100 dark:border-slate-600">
                    {renderOutlineTree(generatedOutline)}
                  </div>
                </div>
              )}

              {/* Mindmap */}
              {generatedMindmap && (
                <div className="mb-6">
                  <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                    思维导图
                  </h3>
                  <div className="rounded-xl border border-slate-100 dark:border-slate-600 bg-white dark:bg-slate-800 overflow-hidden">
                    <div className="h-[520px]">
                      <ReactFlow
                        nodes={mindmapFlow.nodes}
                        edges={mindmapFlow.edges}
                        fitView
                        nodesDraggable={false}
                        nodesConnectable={false}
                        elementsSelectable={true}
                        panOnDrag
                        zoomOnScroll
                      >
                        <MiniMap />
                        <Controls />
                        <Background gap={16} size={1} />
                      </ReactFlow>
                    </div>
                  </div>
                </div>
              )}

              {/* Raw Output fallback */}
              {!generatedSummary && !generatedOutline && !generatedMindmap && (
                <div>
                  <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                    {t("Output")}
                  </h3>
                  <div className="p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl border border-slate-100 dark:border-slate-600">
                    <div className="prose prose-slate dark:prose-invert max-w-none prose-sm">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                      >
                        {processLatexContent(selectedRecord.output)}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}

              {/* Metadata */}
              {Object.keys(selectedRecord.metadata || {}).length > 0 && (
                <div className="mt-6">
                  <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                    {t("Metadata")}
                  </h3>
                  <div className="p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl border border-slate-100 dark:border-slate-600">
                    <pre className="text-xs text-slate-600 dark:text-slate-300 overflow-x-auto whitespace-pre-wrap">
                      {JSON.stringify(
                        {
                          source_type: selectedRecord.metadata?.source_type,
                          session_id: selectedRecord.metadata?.session_id,
                          message_count: selectedRecord.metadata?.message_count,
                          enable_rag: selectedRecord.metadata?.enable_rag,
                          enable_web_search: selectedRecord.metadata?.enable_web_search,
                        },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              </div>
            )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-400 dark:text-slate-500 p-8">
            <FileText className="w-16 h-16 text-slate-200 dark:text-slate-600 mb-4" />
            <p className="text-slate-500 dark:text-slate-400">
              {t("Select a record to view details")}
            </p>
          </div>
        )}
      </div>
      {rightCollapsed && (
        <button
          onClick={() => setRightCollapsed(false)}
          className="p-2 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-sm hover:bg-slate-50 dark:hover:bg-slate-700 transition-all self-start mt-4 shrink-0"
          title={t("Expand right panel")}
        >
          <ChevronLeft className="w-4 h-4 text-slate-600 dark:text-slate-300" />
        </button>
      )}

      {/* Create Notebook Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-slate-950/35 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in">
          <div className="w-[720px] max-w-[92vw] rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/96 shadow-2xl dark:border-slate-700 dark:bg-slate-900/92 animate-in zoom-in-95">
            <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 dark:text-slate-100">
                {t("Create New Notebook")}
              </h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg"
              >
                <X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
              </button>
            </div>
            <div className="grid gap-5 p-6 md:grid-cols-[1fr_0.7fr]">
              <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Name")}
                </label>
                <input
                  type="text"
                  value={newNotebook.name}
                  onChange={(e) =>
                    setNewNotebook((prev) => ({
                      ...prev,
                      name: e.target.value,
                    }))
                  }
                  placeholder={t("My Notebook")}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Description (Optional)")}
                </label>
                <textarea
                  value={newNotebook.description}
                  onChange={(e) =>
                    setNewNotebook((prev) => ({
                      ...prev,
                      description: e.target.value,
                    }))
                  }
                  placeholder={t("Notes about machine learning...")}
                  rows={3}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none resize-none"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Color")}
                </label>
                <div className="flex gap-2 flex-wrap">
                  {COLORS.map((color) => (
                    <button
                      key={color}
                      onClick={() =>
                        setNewNotebook((prev) => ({ ...prev, color }))
                      }
                      className={`w-8 h-8 rounded-lg transition-all ${
                        newNotebook.color === color
                          ? "ring-2 ring-offset-2 ring-slate-400 dark:ring-slate-500 dark:ring-offset-slate-800 scale-110"
                          : ""
                      }`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
              </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-700 dark:bg-slate-800/60">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  {t("Preview")}
                </p>
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
                  <div
                    className="mb-2 h-2 w-10 rounded-full"
                    style={{ backgroundColor: newNotebook.color }}
                  />
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {newNotebook.name || t("My Notebook")}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-4">
                    {newNotebook.description || t("Description (Optional)")}
                  </p>
                </div>
              </div>
            </div>
            <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex justify-end gap-2">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                {t("Cancel")}
              </button>
              <button
                onClick={handleCreateNotebook}
                disabled={!newNotebook.name.trim()}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                <Plus className="w-4 h-4" />
                {t("Create")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Notebook Modal */}
      {showEditModal && editingNotebook && (
        <div className="fixed inset-0 bg-slate-950/35 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in">
          <div className="w-[720px] max-w-[92vw] rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/96 shadow-2xl dark:border-slate-700 dark:bg-slate-900/92 animate-in zoom-in-95">
            <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 dark:text-slate-100">
                {t("Edit Notebook")}
              </h3>
              <button
                onClick={() => {
                  setShowEditModal(false);
                  setEditingNotebook(null);
                }}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg"
              >
                <X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
              </button>
            </div>
            <div className="grid gap-5 p-6 md:grid-cols-[1fr_0.7fr]">
              <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Name")}
                </label>
                <input
                  type="text"
                  value={editingNotebook.name}
                  onChange={(e) =>
                    setEditingNotebook((prev) =>
                      prev ? { ...prev, name: e.target.value } : null,
                    )
                  }
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Description")}
                </label>
                <textarea
                  value={editingNotebook.description}
                  onChange={(e) =>
                    setEditingNotebook((prev) =>
                      prev ? { ...prev, description: e.target.value } : null,
                    )
                  }
                  rows={3}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none resize-none"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Color")}
                </label>
                <div className="flex gap-2 flex-wrap">
                  {COLORS.map((color) => (
                    <button
                      key={color}
                      onClick={() =>
                        setEditingNotebook((prev) =>
                          prev ? { ...prev, color } : null,
                        )
                      }
                      className={`w-8 h-8 rounded-lg transition-all ${
                        editingNotebook.color === color
                          ? "ring-2 ring-offset-2 ring-slate-400 dark:ring-slate-500 dark:ring-offset-slate-800 scale-110"
                          : ""
                      }`}
                      style={{ backgroundColor: color }}
                    />
                  ))}
                </div>
              </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-700 dark:bg-slate-800/60">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  {t("Preview")}
                </p>
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/50">
                  <div
                    className="mb-2 h-2 w-10 rounded-full"
                    style={{ backgroundColor: editingNotebook.color }}
                  />
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {editingNotebook.name || t("Edit Notebook")}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-4">
                    {editingNotebook.description || t("Description")}
                  </p>
                </div>
              </div>
            </div>
            <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowEditModal(false);
                  setEditingNotebook(null);
                }}
                className="px-4 py-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                {t("Cancel")}
              </button>
              <button
                onClick={handleUpdateNotebook}
                disabled={!editingNotebook.name.trim()}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                <Check className="w-4 h-4" />
                {t("Save Changes")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-slate-950/35 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in">
          <div className="w-[400px] max-w-[92vw] rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/96 shadow-2xl dark:border-slate-700 dark:bg-slate-900/92 animate-in zoom-in-95">
            <div className="p-6 text-center">
              <div className="w-12 h-12 bg-red-100 dark:bg-red-900/40 rounded-full flex items-center justify-center mx-auto mb-4">
                <Trash2 className="w-6 h-6 text-red-600 dark:text-red-400" />
              </div>
              <h3 className="font-bold text-slate-900 dark:text-slate-100 mb-2">
                {t("Delete Notebook?")}
              </h3>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t(
                  "This action cannot be undone. All records in this notebook will be permanently deleted.",
                )}
              </p>
            </div>
            <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex justify-center gap-2 bg-slate-50/60 dark:bg-slate-900/40">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className="px-4 py-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                {t("Cancel")}
              </button>
              <button
                onClick={() => handleDeleteNotebook(showDeleteConfirm)}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
              >
                <Trash2 className="w-4 h-4" />
                {t("Delete")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Import Records Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-slate-950/35 backdrop-blur-sm flex items-center justify-center z-50 animate-in fade-in">
          <div className="w-[860px] max-w-[94vw] max-h-[84vh] rounded-3xl border border-white/60 bg-[color:var(--ui-panel)]/96 shadow-2xl dark:border-slate-700 dark:bg-slate-900/92 flex flex-col animate-in zoom-in-95">
            <div className="p-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between shrink-0">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <Upload className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                {t("Import Records")}
              </h3>
              <button
                onClick={() => {
                  setShowImportModal(false);
                  setImportSourceNotebook("");
                  setImportSourceRecords([]);
                  setSelectedImportRecords(new Set());
                }}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg"
              >
                <X className="w-5 h-5 text-slate-500 dark:text-slate-400" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              <div className="grid gap-4 md:grid-cols-[0.9fr_1.1fr]">
              {/* Source Notebook Selection */}
              <div className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-700 dark:bg-slate-800/60">
                <label className="block text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-2">
                  {t("Source Notebook")}
                </label>
                <select
                  value={importSourceNotebook}
                  onChange={(e) => loadImportSourceRecords(e.target.value)}
                  className="w-full px-4 py-2 border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 rounded-xl focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none"
                >
                  <option value="">{t("Select a notebook...")}</option>
                  {availableNotebooks.map((nb) => (
                    <option key={nb.id} value={nb.id}>
                      {nb.name} ({nb.record_count} records)
                    </option>
                  ))}
                </select>
              </div>

              {/* Records Selection */}
              {importSourceNotebook && (
                <div className="rounded-2xl border border-slate-200 bg-white/80 p-4 dark:border-slate-700 dark:bg-slate-800/60">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                      Select Records ({selectedImportRecords.size} selected)
                    </label>
                    <div className="flex gap-2">
                      <button
                        onClick={() =>
                          setSelectedImportRecords(
                            new Set(importSourceRecords.map((r) => r.id)),
                          )
                        }
                        className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300"
                      >
                        Select All
                      </button>
                      <button
                        onClick={() => setSelectedImportRecords(new Set())}
                        className="text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                      >
                        {t("Clear")}
                      </button>
                    </div>
                  </div>

                  {loadingImport ? (
                    <div className="py-8 text-center text-slate-400 dark:text-slate-500">
                      {t("Loading records...")}
                    </div>
                  ) : importSourceRecords.length === 0 ? (
                    <div className="py-8 text-center text-slate-400 dark:text-slate-500">
                      {t("No records in this notebook")}
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-64 overflow-y-auto">
                      {importSourceRecords.map((record) => (
                        <div
                          key={record.id}
                          onClick={() => toggleImportRecord(record.id)}
                          className={`p-3 rounded-xl cursor-pointer transition-all border ${
                            selectedImportRecords.has(record.id)
                              ? "bg-indigo-50 dark:bg-indigo-900/30 border-indigo-200 dark:border-indigo-700"
                              : "hover:bg-slate-50 dark:hover:bg-slate-700/50 border-slate-200 dark:border-slate-600"
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 ${
                                selectedImportRecords.has(record.id)
                                  ? "bg-indigo-500 border-indigo-500 text-white"
                                  : "border-slate-300 dark:border-slate-500"
                              }`}
                            >
                              {selectedImportRecords.has(record.id) && (
                                <Check className="w-3 h-3" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${getRecordColor(record.type)}`}
                                >
                                  {record.type}
                                </span>
                                <span className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                                  {record.title}
                                </span>
                              </div>
                              <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-1">
                                {record.user_query}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
              </div>
            </div>

            <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex justify-end gap-2 shrink-0">
              <button
                onClick={() => {
                  setShowImportModal(false);
                  setImportSourceNotebook("");
                  setImportSourceRecords([]);
                  setSelectedImportRecords(new Set());
                }}
                className="px-4 py-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleImportRecords}
                disabled={selectedImportRecords.size === 0 || loadingImport}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Upload className="w-4 h-4" />
                Import{" "}
                {selectedImportRecords.size > 0 &&
                  `(${selectedImportRecords.size})`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
