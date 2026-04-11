"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  Info,
  Loader2,
  Network,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import cytoscape, { Core, ElementDefinition } from "cytoscape";

import { apiUrl } from "@/lib/api";

interface GraphNode {
  id: string;
  label: string;
  type?: string;
  description?: string;
  degree?: number;
  size?: number;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  weight?: number;
}

interface GraphStats {
  raw_nodes: number;
  raw_edges: number;
  filtered_nodes?: number;
  returned_nodes: number;
  returned_edges: number;
  truncated: boolean;
}

interface GraphResponse {
  kb_name: string;
  rag_provider?: string;
  message?: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
}

interface NodeDetailResponse {
  kb_name: string;
  node: {
    id: string;
    label: string;
    type: string;
    degree: number;
  };
  explanation: string;
  explanation_source: string;
  snippet_count: number;
  chunk_snippets: Array<{ chunk_id: string; excerpt: string }>;
  stats: {
    outgoing: number;
    incoming: number;
    neighbor_count: number;
  };
  related_nodes: Array<{
    id: string;
    label: string;
    type: string;
    relation_count: number;
    degree: number;
  }>;
  llm_error?: string | null;
}

type ColorMode = "degree" | "type";

const NODE_TYPE_COLORS: Record<string, string> = {
  concept: "#0ea5e9",
  dataset: "#22c55e",
  person: "#f97316",
  organization: "#a855f7",
  meta: "#64748b",
  symbol: "#f59e0b",
  entity: "#14b8a6",
};

function getDegreeBand(degree: number): "core" | "hub" | "mid" | "leaf" {
  if (degree >= 12) return "core";
  if (degree >= 7) return "hub";
  if (degree >= 3) return "mid";
  return "leaf";
}

function getDegreeColor(degree: number): string {
  const band = getDegreeBand(degree);
  if (band === "core") return "#ef4444";
  if (band === "hub") return "#3b82f6";
  if (band === "mid") return "#a855f7";
  return "#22c55e";
}

function getNodeTypeText(nodeType?: string): string {
  const mapping: Record<string, string> = {
    concept: "概念",
    dataset: "数据集",
    person: "人物",
    organization: "机构",
    meta: "元信息",
    symbol: "符号",
    entity: "实体",
  };
  return mapping[nodeType || "entity"] || "实体";
}

function getExplanationSourceText(source?: string): string {
  const mapping: Record<string, string> = {
    graph_description: "图谱描述",
    graph_description_zh: "图谱描述（中文化）",
    vdb_entities: "向量库实体内容",
    vdb_entities_zh: "向量库实体内容（中文化）",
    snippet_heuristic: "文本片段摘要",
    snippet_heuristic_zh: "文本片段摘要（中文化）",
    llm_generated: "LLM生成",
    llm_generated_zh: "LLM生成（中文化）",
    none: "无",
  };
  return mapping[source || "none"] || source || "未知";
}

export default function KnowledgeGraphPage() {
  const { t } = useTranslation();
  const params = useParams<{ kbName: string }>();
  const kbName = decodeURIComponent(params.kbName || "");
  const graphContainerRef = useRef<HTMLDivElement | null>(null);
  const cytoscapeRef = useRef<Core | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [search, setSearch] = useState("");

  const [maxNodes, setMaxNodes] = useState(220);
  const [maxEdges, setMaxEdges] = useState(500);
  const [minDegree, setMinDegree] = useState(2);
  const [filterNoise, setFilterNoise] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [colorMode, setColorMode] = useState<ColorMode>("degree");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [focusSelection, setFocusSelection] = useState(true);
  const [useLlmExplanation, setUseLlmExplanation] = useState(true);
  const [nodeDetailLoading, setNodeDetailLoading] = useState(false);
  const [nodeDetails, setNodeDetails] = useState<NodeDetailResponse | null>(null);
  const [nodeDetailError, setNodeDetailError] = useState<string | null>(null);

  const fetchGraph = async () => {
    if (!kbName) {
      setError(t("知识库名称无效。"));
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const query = new URLSearchParams({
        max_nodes: String(maxNodes),
        max_edges: String(maxEdges),
        min_degree: String(minDegree),
        filter_noise: String(filterNoise),
      });

      const res = await fetch(
        apiUrl(`/api/v1/knowledge/${encodeURIComponent(kbName)}/graph?${query.toString()}`),
      );

      if (!res.ok) {
        let detail = t("加载图谱数据失败（HTTP {{status}}）", {
          status: res.status,
        });
        try {
          const payload = await res.json();
          if (payload?.detail) {
            detail = payload.detail;
          }
        } catch {
          // keep default error text
        }
        throw new Error(detail);
      }

      const data = (await res.json()) as GraphResponse;
      setGraphData(data);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : t("加载图谱数据失败。");
      setError(message);
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  };

  const fitGraphView = () => {
    const cy = cytoscapeRef.current;
    if (!cy) return;
    cy.fit(cy.elements(), 70);
  };

  const clearSelection = () => {
    setSelectedNodeId(null);
    setNodeDetails(null);
    setNodeDetailError(null);
  };

  useEffect(() => {
    fetchGraph();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbName, maxNodes, maxEdges, minDegree, filterNoise]);

  const elements = useMemo<ElementDefinition[]>(() => {
    if (!graphData) return [];

    const nodeElements: ElementDefinition[] = graphData.nodes.map((node) => {
      const degree = node.degree ?? 0;
      return {
        data: {
          id: node.id,
          label: node.label || node.id,
          displayLabel:
            degree >= 3
              ? node.label || node.id
              : (node.label || node.id).slice(0, 12),
          type: node.type || "entity",
          description: node.description || "",
          degree,
          degreeBand: getDegreeBand(degree),
          color:
            colorMode === "degree"
              ? getDegreeColor(degree)
              : NODE_TYPE_COLORS[node.type || "entity"] || NODE_TYPE_COLORS.entity,
          size: node.size ?? 20,
        },
      };
    });

    const edgeElements: ElementDefinition[] = graphData.edges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label || "related_to",
        weight: edge.weight ?? 1,
      },
    }));

    return [...nodeElements, ...edgeElements];
  }, [colorMode, graphData]);

  const selectedNodeDetails = useMemo(() => {
    if (!graphData || !selectedNodeId) return null;
    const node = graphData.nodes.find((n) => n.id === selectedNodeId);
    if (!node) return null;

    const outgoing = graphData.edges.filter((e) => e.source === selectedNodeId);
    const incoming = graphData.edges.filter((e) => e.target === selectedNodeId);
    const neighbors = new Map<string, { id: string; count: number }>();
    for (const edge of [...outgoing, ...incoming]) {
      const neighborId = edge.source === selectedNodeId ? edge.target : edge.source;
      const current = neighbors.get(neighborId);
      neighbors.set(neighborId, { id: neighborId, count: (current?.count || 0) + 1 });
    }

    const neighborList = Array.from(neighbors.values())
      .sort((a, b) => b.count - a.count)
      .slice(0, 15)
      .map((item) => {
        const n = graphData.nodes.find((x) => x.id === item.id);
        return { ...item, label: n?.label || item.id, type: n?.type || "entity" };
      });

    const generatedSummary = t("该节点共有 {{degree}} 条关联，其中出边 {{outgoing}} 条、入边 {{incoming}} 条。", {
      degree: node.degree ?? outgoing.length + incoming.length,
      outgoing: outgoing.length,
      incoming: incoming.length,
    });

    return {
      node,
      outgoing,
      incoming,
      neighbors: neighborList,
      summary: node.description?.trim() ? node.description : generatedSummary,
    };
  }, [graphData, selectedNodeId, t]);

  useEffect(() => {
    const fetchNodeDetails = async () => {
      if (!selectedNodeId || !kbName) {
        setNodeDetails(null);
        setNodeDetailError(null);
        return;
      }

      try {
        setNodeDetailLoading(true);
        setNodeDetailError(null);
        const query = new URLSearchParams({
          node_id: selectedNodeId,
          use_llm: String(useLlmExplanation),
          max_neighbors: "20",
        });
        const res = await fetch(
          apiUrl(
            `/api/v1/knowledge/${encodeURIComponent(kbName)}/graph/node-detail?${query.toString()}`,
          ),
        );
        if (!res.ok) {
          let detail = `请求失败（HTTP ${res.status}）`;
          try {
            const payload = await res.json();
            if (payload?.detail) detail = payload.detail;
          } catch {
            // ignore json parse error
          }
          throw new Error(detail);
        }
        const data = (await res.json()) as NodeDetailResponse;
        setNodeDetails(data);
      } catch (err) {
        setNodeDetails(null);
        setNodeDetailError(err instanceof Error ? err.message : "节点详情加载失败。");
      } finally {
        setNodeDetailLoading(false);
      }
    };

    fetchNodeDetails();
  }, [kbName, selectedNodeId, useLlmExplanation]);

  useEffect(() => {
    if (!graphContainerRef.current || !graphData) return;

    if (cytoscapeRef.current) {
      cytoscapeRef.current.destroy();
      cytoscapeRef.current = null;
    }

    const cy = cytoscape({
      container: graphContainerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: "data(displayLabel)",
            "text-wrap": "wrap",
            "text-max-width": "120px",
            "font-size": "10px",
            "background-color": "data(color)",
            "text-valign": "center",
            color: "#0f172a",
            "border-width": 1.2,
            "border-color": "#ccfbf1",
            width: "mapData(size, 18, 56, 18, 56)",
            height: "mapData(size, 18, 56, 18, 56)",
          },
        },
        {
          selector: 'node[degreeBand = "core"]',
          style: { "border-width": 3.2, "border-color": "#fecaca" },
        },
        {
          selector: 'node[degreeBand = "hub"]',
          style: { "border-width": 2.6, "border-color": "#bfdbfe" },
        },
        {
          selector: 'node[degreeBand = "mid"]',
          style: { "border-width": 2.0, "border-color": "#e9d5ff" },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "curve-style": "bezier",
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.7,
            label: showEdgeLabels ? "data(label)" : "",
            "font-size": "8px",
            color: "#475569",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.7,
            "text-background-padding": "1px",
          },
        },
        {
          selector: ".faded",
          style: {
            opacity: 0.12,
          },
        },
        {
          selector: ".highlighted",
          style: {
            opacity: 1,
            "border-width": 2.5,
            "border-color": "#0ea5e9",
            "line-color": "#0ea5e9",
            "target-arrow-color": "#0ea5e9",
          },
        },
        {
          selector: ".selected-node",
          style: {
            "border-width": 4.2,
            "border-color": "#f43f5e",
            "overlay-color": "#fda4af",
            "overlay-opacity": 0.18,
            "overlay-padding": 7,
            "z-index": 999,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        fit: true,
        padding: 55,
        nodeRepulsion: 100000,
        idealEdgeLength: 120,
        edgeElasticity: 120,
        gravity: 0.15,
        numIter: 1800,
        randomize: true,
      },
    });

    cytoscapeRef.current = cy;

    cy.on("tap", "node", (evt) => {
      const nodeId = String(evt.target.id());
      setSelectedNodeId(nodeId);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        setSelectedNodeId(null);
      }
    });

    return () => {
      cy.destroy();
      cytoscapeRef.current = null;
    };
  }, [elements, graphData, showEdgeLabels]);

  useEffect(() => {
    const cy = cytoscapeRef.current;
    if (!cy) return;

    cy.elements().removeClass("selected-node faded highlighted");
    if (!selectedNodeId) return;

    const node = cy.getElementById(selectedNodeId);
    if (!node || node.empty()) return;
    node.addClass("selected-node");

    if (focusSelection) {
      cy.elements().addClass("faded");
      const neighborhood = node.closedNeighborhood();
      neighborhood.removeClass("faded");
      neighborhood.addClass("highlighted");
      cy.animate({
        fit: { eles: neighborhood, padding: 80 },
        duration: 280,
      });
    }
  }, [focusSelection, selectedNodeId]);

  useEffect(() => {
    const cy = cytoscapeRef.current;
    if (!cy) return;

    const keyword = search.trim().toLowerCase();
    cy.elements().removeClass("faded highlighted");

    if (!keyword) return;

    cy.elements().addClass("faded");

    const matchedNodes = cy.nodes().filter((node) => {
      const label = String(node.data("label") || "").toLowerCase();
      const id = String(node.id() || "").toLowerCase();
      return label.includes(keyword) || id.includes(keyword);
    });

    matchedNodes.forEach((node) => {
      const neighborhood = node.closedNeighborhood();
      neighborhood.removeClass("faded");
      neighborhood.addClass("highlighted");
    });

    if (matchedNodes.length > 0) {
      cy.animate({
        center: { eles: matchedNodes[0] },
        zoom: Math.min(cy.zoom() + 0.15, 2.2),
        duration: 300,
      });
    }
  }, [search]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-teal-50 dark:from-slate-950 dark:via-slate-900 dark:to-slate-900 px-4 py-6 md:px-6">
      <div className="mx-auto w-full max-w-7xl space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link
              href="/knowledge"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            >
              <ArrowLeft className="h-4 w-4" />
              {t("返回")}
            </Link>
            <div>
              <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                {t("知识图谱")}
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">{kbName}</p>
            </div>
          </div>

          <button
            onClick={fetchGraph}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            <RefreshCw className="h-4 w-4" />
            {t("刷新")}
          </button>
          <button
            onClick={fitGraphView}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {t("适配视图")}
          </button>
          <button
            onClick={clearSelection}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {t("清除选中")}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto]">
          <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-800">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("搜索节点...")}
              className="w-full bg-transparent text-slate-800 outline-none placeholder:text-slate-400 dark:text-slate-200"
            />
          </label>
          {graphData && (
            <div className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
              <Network className="h-4 w-4" />
              <span>{t("节点 {{count}}", { count: graphData.stats.returned_nodes })}</span>
              <span>·</span>
              <span>{t("边 {{count}}", { count: graphData.stats.returned_edges })}</span>
              {typeof graphData.stats.filtered_nodes === "number" && (
                <>
                  <span>·</span>
                  <span>{t("过滤后 {{count}}", { count: graphData.stats.filtered_nodes })}</span>
                </>
              )}
              {graphData.stats.truncated && (
                <>
                  <span>·</span>
                  <span>{t("已截断以保证性能")}</span>
                </>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-3 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
          <label className="flex min-w-[260px] items-center gap-2">
            <span>{t("节点数量")}</span>
            <input
              type="range"
              min={120}
              max={500}
              step={20}
              value={maxNodes}
              onChange={(e) => setMaxNodes(Number(e.target.value))}
              className="w-full"
            />
            <span>{maxNodes}</span>
          </label>
          <label className="flex min-w-[260px] items-center gap-2">
            <span>{t("边数量")}</span>
            <input
              type="range"
              min={200}
              max={1200}
              step={50}
              value={maxEdges}
              onChange={(e) => setMaxEdges(Number(e.target.value))}
              className="w-full"
            />
            <span>{maxEdges}</span>
          </label>
          <label className="flex min-w-[260px] items-center gap-2">
            <span>{t("最小度数")}</span>
            <input
              type="range"
              min={0}
              max={6}
              step={1}
              value={minDegree}
              onChange={(e) => setMinDegree(Number(e.target.value))}
              className="w-full"
            />
            <span>{minDegree}</span>
          </label>
          <label className="flex min-w-[180px] items-center gap-2">
            <input
              type="checkbox"
              checked={filterNoise}
              onChange={(e) => setFilterNoise(e.target.checked)}
            />
            <span>{t("过滤噪声节点")}</span>
          </label>
          <label className="flex min-w-[180px] items-center gap-2">
            <input
              type="checkbox"
              checked={showEdgeLabels}
              onChange={(e) => setShowEdgeLabels(e.target.checked)}
            />
            <span>{t("显示边标签")}</span>
          </label>
          <label className="flex min-w-[220px] items-center gap-2">
            <span>{t("颜色模式")}</span>
            <select
              value={colorMode}
              onChange={(e) => setColorMode(e.target.value as ColorMode)}
              className="rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-800"
            >
              <option value="degree">{t("按层次（度数）")}</option>
              <option value="type">{t("按节点类型")}</option>
            </select>
          </label>
          <label className="flex min-w-[220px] items-center gap-2">
            <input
              type="checkbox"
              checked={focusSelection}
              onChange={(e) => setFocusSelection(e.target.checked)}
            />
            <span>{t("聚焦选中节点邻域")}</span>
          </label>
          <label className="flex min-w-[220px] items-center gap-2">
            <input
              type="checkbox"
              checked={useLlmExplanation}
              onChange={(e) => setUseLlmExplanation(e.target.checked)}
            />
            <span>{t("解释缺失时用LLM补全")}</span>
          </label>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/80">
          <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
            <span>{t("图例")}：</span>
            {colorMode === "degree" ? (
              <>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#ef4444]" />
                  <span>{t("核心（>=12）")}</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#3b82f6]" />
                  <span>{t("枢纽（7-11）")}</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#a855f7]" />
                  <span>{t("中间层（3-6）")}</span>
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#22c55e]" />
                  <span>{t("叶子（<=2）")}</span>
                </span>
              </>
            ) : (
              Object.entries(NODE_TYPE_COLORS).map(([key, color]) => (
                <span key={key} className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span>{getNodeTypeText(key)}</span>
                </span>
              ))
            )}
          </div>
          {loading ? (
            <div className="flex h-[70vh] items-center justify-center gap-2 text-slate-500 dark:text-slate-400">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span>{t("正在加载图谱数据...")}</span>
            </div>
          ) : error ? (
            <div className="flex h-[70vh] flex-col items-center justify-center gap-3 text-center">
              <AlertCircle className="h-10 w-10 text-red-500" />
              <p className="max-w-2xl text-sm text-slate-600 dark:text-slate-300">{error}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {t(
                  "提示：知识图谱可视化仅支持图谱型RAG提供方（lightrag / raganything / raganything_docling）。",
                )}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {graphData?.message && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                  {graphData.message}
                </div>
              )}
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_340px]">
                <div
                  ref={graphContainerRef}
                  className="h-[70vh] w-full rounded-xl border border-slate-100 bg-white dark:border-slate-800 dark:bg-slate-900"
                />
                <div className="h-[70vh] overflow-y-auto rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-950/40">
                  {selectedNodeDetails ? (
                    <div className="space-y-3 text-xs text-slate-700 dark:text-slate-200">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-semibold">{selectedNodeDetails.node.label}</div>
                          <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                            {getNodeTypeText(selectedNodeDetails.node.type || "entity")} · 度数{" "}
                            {selectedNodeDetails.node.degree ?? 0}
                          </div>
                        </div>
                        <button
                          onClick={() => setSelectedNodeId(null)}
                          className="rounded p-1 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>

                      <div className="rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
                        <div className="mb-1 inline-flex items-center gap-1 text-[11px] font-medium text-slate-500">
                          <Info className="h-3.5 w-3.5" />
                          {t("节点解释")}
                        </div>
                        {nodeDetailLoading ? (
                          <div className="inline-flex items-center gap-1.5 text-slate-500">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            <span>{t("正在生成解释...")}</span>
                          </div>
                        ) : nodeDetailError ? (
                          <div className="text-red-500">{nodeDetailError}</div>
                        ) : nodeDetails?.explanation ? (
                          <div className="space-y-1">
                            <div>{nodeDetails.explanation}</div>
                            <div className="text-[11px] text-slate-500">
                              {t("来源")}：{getExplanationSourceText(nodeDetails.explanation_source)}
                            </div>
                          </div>
                        ) : (
                          <div>{selectedNodeDetails.summary}</div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div className="rounded-lg border border-slate-200 bg-white p-2 text-center dark:border-slate-700 dark:bg-slate-900">
                          <div className="text-[11px] text-slate-500">{t("出边")}</div>
                          <div className="text-base font-semibold">
                            {nodeDetails?.stats?.outgoing ?? selectedNodeDetails.outgoing.length}
                          </div>
                        </div>
                        <div className="rounded-lg border border-slate-200 bg-white p-2 text-center dark:border-slate-700 dark:bg-slate-900">
                          <div className="text-[11px] text-slate-500">{t("入边")}</div>
                          <div className="text-base font-semibold">
                            {nodeDetails?.stats?.incoming ?? selectedNodeDetails.incoming.length}
                          </div>
                        </div>
                      </div>

                      <div className="rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
                        <div className="mb-1 text-[11px] font-medium text-slate-500">
                          {t("相关节点（前15）")}
                        </div>
                        <div className="space-y-1.5">
                          {(nodeDetails?.related_nodes || selectedNodeDetails.neighbors).map((n) => (
                            <button
                              key={n.id}
                              onClick={() => setSelectedNodeId(n.id)}
                              className="flex w-full items-center justify-between rounded px-2 py-1 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
                            >
                              <span className="truncate">{n.label}</span>
                              <span className="ml-2 text-[11px] text-slate-500">
                                ×{"relation_count" in n ? n.relation_count : n.count}
                              </span>
                            </button>
                          ))}
                          {(nodeDetails?.related_nodes?.length || selectedNodeDetails.neighbors.length) ===
                            0 && (
                            <div className="text-[11px] text-slate-500">{t("未找到相关节点。")}</div>
                          )}
                        </div>
                      </div>

                      {nodeDetails?.chunk_snippets?.length ? (
                        <div className="rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900">
                          <div className="mb-1 text-[11px] font-medium text-slate-500">
                            {t("证据片段")}
                          </div>
                          <div className="space-y-2">
                            {nodeDetails.chunk_snippets.slice(0, 3).map((s) => (
                              <div key={s.chunk_id} className="rounded bg-slate-50 p-2 dark:bg-slate-800/60">
                                <div className="mb-1 text-[10px] text-slate-500">{s.chunk_id}</div>
                                <div>{s.excerpt}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-xs text-slate-500 dark:text-slate-400">
                      <Info className="h-5 w-5" />
                      <div>{t("点击任意节点可查看中文解释与相关节点信息。")}</div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
