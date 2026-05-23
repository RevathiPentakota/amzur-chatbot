import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  API_BASE_URL,
  attachmentContentUrl,
  createThread,
  getMcpTools,
  listThreadAttachments,
  listThreadDataFrameSources,
  listThreadRagPdfs,
  runMcpAgent,
  uploadAttachment,
  uploadDataFrame,
  uploadRagPdf,
} from "../lib/api";
import type { AttachmentItem, McpAgentResponse, McpToolDefinition } from "../types";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  toolUsed?: string | null;
  toolInput?: Record<string, unknown> | null;
  toolOutput?: Record<string, unknown> | null;
  reasoning?: string;
  uploads?: UploadedArtifact[];
  toolUsageLabel?: string;
}

type UploadKind = "pdf" | "dataframe" | "attachment";

interface UploadedArtifact {
  id: string;
  kind: UploadKind;
  threadId: number;
  name: string;
  mimeType?: string;
  fileType?: string;
  attachmentId?: number;
  sourceId?: number;
  href?: string;
  status?: "uploaded";
  origin?: "new" | "thread-history";
}

interface PendingUpload {
  localId: string;
  name: string;
  kind: UploadKind;
  progress: number;
  status: "uploading" | "processing" | "uploaded" | "failed";
  error?: string;
  fileTypeHint?: string;
}

let msgId = 0;
function nextId() {
  return ++msgId;
}

function extractThreadId(value: unknown): string | null {
  if (typeof value === "number" && Number.isInteger(value) && value > 0) {
    return String(value);
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (/^\d+$/.test(trimmed) && Number(trimmed) > 0) {
      return trimmed;
    }
  }
  return null;
}

function normalizeImageUrl(rawUrl: string): string {
  const value = rawUrl.trim();
  if (!value) {
    return value;
  }
  if (value.startsWith("sandbox:/")) {
    return `${API_BASE_URL}${value.replace("sandbox:", "")}`;
  }
  if (value.startsWith("/")) {
    return `${API_BASE_URL}${value}`;
  }
  return value;
}

function extractMarkdownImageUrls(text: string): string[] {
  const urls: string[] = [];
  const pattern = /!\[[^\]]*\]\(([^)]+)\)/g;
  let match: RegExpExecArray | null = pattern.exec(text);
  while (match) {
    if (match[1]) {
      urls.push(match[1]);
    }
    match = pattern.exec(text);
  }
  return urls;
}

function extractPlainImageUrls(text: string): string[] {
  const urls: string[] = [];
  const pattern = /(sandbox:\/images\/\d+\/content|\/images\/\d+\/content|https?:\/\/[^\s)]+\/images\/\d+\/content)/g;
  let match: RegExpExecArray | null = pattern.exec(text);
  while (match) {
    if (match[1]) {
      urls.push(match[1]);
    }
    match = pattern.exec(text);
  }
  return urls;
}

function extractToolImageUrls(toolOutput?: Record<string, unknown> | null): string[] {
  if (!toolOutput) {
    return [];
  }

  const urls: string[] = [];
  const direct = toolOutput.image_url;
  if (typeof direct === "string" && direct.trim()) {
    urls.push(direct);
  }

  const images = toolOutput.images;
  if (Array.isArray(images)) {
    for (const item of images) {
      if (typeof item === "string" && item.trim()) {
        urls.push(item);
      }
    }
  }

  return urls;
}

function fileIconFor(item: UploadedArtifact | PendingUpload): string {
  const kind = item.kind;
  if (kind === "pdf") return "📄";
  if (kind === "dataframe") return "📊";
  const ft = (item as UploadedArtifact).fileType;
  const mt = (item as UploadedArtifact).mimeType ?? "";
  if (ft === "image" || mt.startsWith("image/")) return "🖼";
  if (ft === "video" || mt.startsWith("video/")) return "🎬";
  return "📎";
}

function statusLabel(status: PendingUpload["status"]): string {
  if (status === "uploading") return "uploading...";
  if (status === "processing") return "processing...";
  if (status === "uploaded") return "uploaded successfully";
  return "upload failed";
}

function toAttachmentArtifact(item: AttachmentItem): UploadedArtifact {
  return {
    id: `att-${item.file_id ?? item.id}`,
    kind: item.mime_type === "application/pdf" ? "pdf" : "attachment",
    threadId: item.thread_id,
    name: item.filename ?? item.original_filename,
    mimeType: item.mime_type,
    fileType: item.file_type,
    attachmentId: item.file_id ?? item.id,
    href: item.file_url ? normalizeImageUrl(item.file_url) : attachmentContentUrl(item.file_id ?? item.id),
    status: "uploaded",
    origin: "thread-history",
  };
}

function verifyUploadFields(
  response: Record<string, unknown>,
  fallback: { filename: string; thread_id: number; mime_type: string; file_url?: string },
): { filename: string; file_url: string; mime_type: string; thread_id: number } {
  const filename = (typeof response.filename === "string" && response.filename) || fallback.filename;
  const file_url = (typeof response.file_url === "string" && response.file_url) || fallback.file_url || "";
  const mime_type = (typeof response.mime_type === "string" && response.mime_type) || fallback.mime_type;
  const thread_id =
    (typeof response.thread_id === "number" && response.thread_id) || fallback.thread_id;

  const required = { filename, file_url, mime_type, thread_id };
  if (!required.filename || !required.mime_type || !required.thread_id) {
    console.warn("UPLOAD RESPONSE missing required fields", required, response);
  }
  return required;
}

export function MCPAgent() {
  const [tools, setTools] = useState<McpToolDefinition[]>([]);
  const [toolsLoading, setToolsLoading] = useState(true);
  const [toolsError, setToolsError] = useState<string | null>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string>("");
  const [resolvedThreadId, setResolvedThreadId] = useState<string | null>(null);
  const [pendingUploads, setPendingUploads] = useState<PendingUpload[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedArtifact[]>([]);
  const [attachments, setAttachments] = useState<UploadedArtifact[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [expandedMsg, setExpandedMsg] = useState<number | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const lastThreadKeyRef = useRef<string>("");

  const uploading = useMemo(
    () => pendingUploads.some((p) => p.status === "uploading" || p.status === "processing"),
    [pendingUploads],
  );

  const activeArtifacts = useMemo(() => {
    const result = uploadedFiles.length > 0 ? uploadedFiles : attachments;
    console.log("ACTIVE_ARTIFACTS_COMPUTED", {
      uploadedFilesCount: uploadedFiles.length,
      attachmentsCount: attachments.length,
      activeCount: result.length,
      active: result,
    });
    return result;
  }, [attachments, uploadedFiles]);

  const buildFileContext = (items: UploadedArtifact[]): string => {
    if (items.length === 0) {
      return "";
    }
    const lines = items.map((item) => {
      if (item.kind === "pdf") {
        return `- PDF: ${item.name} (use pdf_rag_tool)`;
      }
      if (item.kind === "dataframe") {
        return `- Spreadsheet: ${item.name} (use dataframe_analysis_tool)`;
      }
      if (item.fileType === "video") {
        return `- Video: ${item.name} (use video_analysis_tool)`;
      }
      if (item.fileType === "image") {
        return `- Image: ${item.name} (use image_vision_tool)`;
      }
      return `- Attachment: ${item.name}`;
    });

    return [
      "Uploaded files in current thread:",
      ...lines,
      "Select tools according to file type guidance above.",
    ].join("\n");
  };

  const ensureThread = useCallback(async (): Promise<number> => {
    const parsed = threadId ? parseInt(threadId, 10) : NaN;
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed;
    }

    const created = await createThread();
    const nextId = String(created.id);
    setThreadId(nextId);
    setResolvedThreadId(nextId);
    return created.id;
  }, [threadId]);

  const detectUploadKind = (file: File): UploadKind => {
    const lower = file.name.toLowerCase();
    if (lower.endsWith(".pdf")) {
      return "pdf";
    }
    if (lower.endsWith(".csv") || lower.endsWith(".xlsx") || lower.endsWith(".xls")) {
      return "dataframe";
    }
    return "attachment";
  };

  const removeUploadedArtifact = (artifactId: string) => {
    setUploadedFiles((prev) => prev.filter((item) => item.id !== artifactId));
    setAttachments((prev) => prev.filter((item) => item.id !== artifactId));
  };

  const inferUsageLabel = useCallback(
    (toolName: string | null, toolOutput: Record<string, unknown> | null): string | undefined => {
      if (!toolName) return undefined;
      const byType = (predicate: (item: UploadedArtifact) => boolean) =>
        [...activeArtifacts].reverse().find(predicate);

      let target: UploadedArtifact | undefined;
      if (toolName === "pdf_rag_tool") {
        target = byType((item) => item.kind === "pdf");
      } else if (toolName === "dataframe_analysis_tool") {
        target = byType((item) => item.kind === "dataframe");
      } else if (toolName === "image_vision_tool") {
        target = byType((item) => item.fileType === "image" || (item.mimeType ?? "").startsWith("image/"));
      } else if (toolName === "video_analysis_tool") {
        target = byType((item) => item.fileType === "video" || (item.mimeType ?? "").startsWith("video/"));
      }

      const names = Array.isArray(toolOutput?.analyzed_files)
        ? (toolOutput?.analyzed_files as unknown[]).filter((x): x is string => typeof x === "string")
        : [];
      const fileName = names[0] ?? target?.name;
      if (!fileName) return undefined;
      return `Using: ${fileName} -> ${toolName}`;
    },
    [activeArtifacts],
  );

  const reloadThreadArtifacts = useCallback(async (id: number) => {
    try {
      const [attachmentItems, ragItems, dataframeItems] = await Promise.all([
        listThreadAttachments(id),
        listThreadRagPdfs(id),
        listThreadDataFrameSources(id),
      ]);

      const artifacts: UploadedArtifact[] = [];
      artifacts.push(...attachmentItems.map(toAttachmentArtifact));
      artifacts.push(
        ...ragItems.map((item) => ({
          id: `pdf-${item.file_id ?? item.id}`,
          kind: "pdf" as const,
          threadId: item.thread_id,
          name: item.filename,
          mimeType: "application/pdf",
          href: item.file_url ? normalizeImageUrl(item.file_url) : undefined,
          status: "uploaded" as const,
          origin: "thread-history" as const,
        })),
      );
      artifacts.push(
        ...dataframeItems.map((item) => ({
          id: `df-${item.id}`,
          kind: "dataframe" as const,
          threadId: item.thread_id,
          name: item.filename,
          sourceId: item.id,
          status: "uploaded" as const,
          origin: "thread-history" as const,
        })),
      );

      const unique = new Map<string, UploadedArtifact>();
      for (const item of artifacts) {
        unique.set(item.id, item);
      }
      const loaded = [...unique.values()];
      console.log("RELOAD_ARTIFACTS_LOADED", {
        threadId: id,
        attachmentCount: attachmentItems.length,
        ragCount: ragItems.length,
        dataframeCount: dataframeItems.length,
        totalArtifacts: loaded.length,
        artifacts: loaded,
      });
      setAttachments(loaded);
    } catch (err) {
      console.error("RELOAD_ARTIFACTS_ERROR", err);
      setAttachments([]);
    }
  }, []);

  const handleSelectFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) {
      console.log("UPLOAD_NO_FILES_SELECTED");
      return;
    }

    console.log("UPLOAD_START", { fileCount: files.length, fileNames: Array.from(files).map(f => f.name) });
    setError(null);
    const thread = await ensureThread();
    console.log("UPLOAD_THREAD_ENSURED", { threadId: thread });
    const selected = files;

    const pending: PendingUpload[] = selected.map((file) => {
      const localId = `${Date.now()}-${Math.random()}`;
      return {
        localId,
        name: file.name,
        kind: detectUploadKind(file),
        progress: 0,
        status: "uploading",
        fileTypeHint: file.type,
      };
    });
    setPendingUploads((prev) => [...prev, ...pending]);

    const successful: UploadedArtifact[] = [];

    for (let i = 0; i < selected.length; i += 1) {
      const file = selected[i];
      const pendingItem = pending[i];
      try {
        if (pendingItem.kind === "pdf") {
          console.log("UPLOAD_BEFORE_PDF", { fileName: file.name, threadId: thread });
          const uploaded = await uploadRagPdf(file, thread, (progress) => {
            setPendingUploads((prev) =>
              prev.map((item) =>
                item.localId === pendingItem.localId
                  ? { ...item, progress, status: progress >= 100 ? "processing" : "uploading" }
                  : item,
              ),
            );
          });
          console.log("UPLOAD_AFTER_PDF", { fileName: file.name, response: uploaded });
          const verified = verifyUploadFields(uploaded as unknown as Record<string, unknown>, {
            filename: uploaded.filename,
            thread_id: uploaded.thread_id,
            mime_type: uploaded.mime_type ?? "application/pdf",
            file_url: uploaded.file_url,
          });
          successful.push({
            id: pendingItem.localId,
            kind: "pdf",
            threadId: verified.thread_id,
            name: verified.filename,
            mimeType: verified.mime_type,
            href: verified.file_url ? normalizeImageUrl(verified.file_url) : undefined,
            origin: "new",
          });
        } else if (pendingItem.kind === "dataframe") {
          console.log("UPLOAD_BEFORE_DATAFRAME", { fileName: file.name, threadId: thread });
          const uploaded = await uploadDataFrame(file, thread, (progress) => {
            setPendingUploads((prev) =>
              prev.map((item) =>
                item.localId === pendingItem.localId
                  ? { ...item, progress, status: progress >= 100 ? "processing" : "uploading" }
                  : item,
              ),
            );
          });
          console.log("UPLOAD_AFTER_DATAFRAME", { fileName: file.name, response: uploaded });
          const verified = verifyUploadFields(uploaded as unknown as Record<string, unknown>, {
            filename: uploaded.filename,
            thread_id: uploaded.thread_id,
            mime_type: uploaded.mime_type ?? "application/octet-stream",
            file_url: uploaded.file_url,
          });
          successful.push({
            id: pendingItem.localId,
            kind: "dataframe",
            threadId: verified.thread_id,
            name: verified.filename,
            fileType: uploaded.file_type,
            mimeType: verified.mime_type,
            href: verified.file_url ? normalizeImageUrl(verified.file_url) : undefined,
            origin: "new",
          });
        } else {
          console.log("UPLOAD_BEFORE_ATTACHMENT", { fileName: file.name, threadId: thread });
          const uploaded = await uploadAttachment(file, thread, (progress) => {
            setPendingUploads((prev) =>
              prev.map((item) =>
                item.localId === pendingItem.localId
                  ? { ...item, progress, status: progress >= 100 ? "processing" : "uploading" }
                  : item,
              ),
            );
          });
          console.log("UPLOAD_AFTER_ATTACHMENT", { fileName: file.name, response: uploaded });
          const verified = verifyUploadFields(uploaded as unknown as Record<string, unknown>, {
            filename: uploaded.filename ?? uploaded.original_filename,
            thread_id: uploaded.thread_id,
            mime_type: uploaded.mime_type,
            file_url: uploaded.file_url,
          });
          successful.push({
            id: pendingItem.localId,
            kind: "attachment",
            threadId: verified.thread_id,
            name: verified.filename,
            mimeType: verified.mime_type,
            fileType: uploaded.file_type,
            attachmentId: uploaded.file_id ?? uploaded.id,
            href: verified.file_url ? normalizeImageUrl(verified.file_url) : attachmentContentUrl(uploaded.file_id ?? uploaded.id),
            origin: "new",
          });
        }

        setPendingUploads((prev) =>
          prev.map((item) =>
            item.localId === pendingItem.localId
              ? { ...item, status: "uploaded", progress: 100 }
              : item,
          ),
        );
      } catch (err) {
        console.error("UPLOAD_ERROR", { 
          fileName: file.name, 
          kind: pendingItem.kind, 
          error: err instanceof Error ? err.message : String(err) 
        });
        setPendingUploads((prev) =>
          prev.map((item) =>
            item.localId === pendingItem.localId
              ? {
                  ...item,
                  status: "failed",
                  error: err instanceof Error ? err.message : "Upload failed",
                }
              : item,
          ),
        );
      }
    }

    console.log("UPLOAD_LOOP_COMPLETE", { successCount: successful.length, successful });

    if (successful.length > 0) {
      console.log("UPLOAD_SUCCESS_BEFORE_STATE", {
        successCount: successful.length,
        files: successful,
      });
      setUploadedFiles((prev) => {
        const updated = [...prev, ...successful];
        console.log("UPLOAD_SUCCESS_SET_UPLOADED_FILES", { total: updated.length, files: updated });
        return updated;
      });
      setAttachments((prev) => {
        const updated = [...prev, ...successful];
        console.log("UPLOAD_SUCCESS_SET_ATTACHMENTS", { total: updated.length, files: updated });
        return updated;
      });
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "assistant",
          text: "Files uploaded. Ask a question or press Send to analyze them.",
          uploads: successful,
        },
      ]);
    }
  }, [ensureThread]);

  // ── Load tool list ────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setToolsLoading(true);
    getMcpTools()
      .then((data) => {
        if (!cancelled) setTools(data);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setToolsError(err instanceof Error ? err.message : "Failed to load tools.");
      })
      .finally(() => {
        if (!cancelled) setToolsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  useEffect(() => {
    const activeThread = resolvedThreadId ?? threadId;
    const parsed = activeThread ? parseInt(activeThread, 10) : NaN;
    if (!Number.isInteger(parsed) || parsed <= 0) {
      setAttachments([]);
      return;
    }

    void reloadThreadArtifacts(parsed);
  }, [reloadThreadArtifacts, resolvedThreadId, threadId]);

  useEffect(() => {
    const key = `${resolvedThreadId ?? ""}:${threadId}`;
    if (!lastThreadKeyRef.current) {
      lastThreadKeyRef.current = key;
      return;
    }
    if (lastThreadKeyRef.current !== key) {
      setUploadedFiles([]);
      setPendingUploads([]);
      lastThreadKeyRef.current = key;
    }
  }, [resolvedThreadId, threadId]);

  useEffect(() => {
    console.log("ATTACHMENTS STATE", attachments);
  }, [attachments]);

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if ((text.length === 0 && uploadedFiles.length === 0) || sending || uploading) return;

    const messageText = text || "Please analyze the uploaded files and summarize key insights.";

    const currentThread = await ensureThread();

    const userMsg: Message = {
      id: nextId(),
      role: "user",
      text: messageText,
      uploads: uploadedFiles.length > 0 ? uploadedFiles : undefined,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);
    setError(null);

    try {
      const res: McpAgentResponse = await runMcpAgent({
        message: messageText,
        thread_id: currentThread,
        file_context: buildFileContext(uploadedFiles),
      });

      const serverThreadId =
        extractThreadId(res.tool_output?.thread_id) ??
        extractThreadId(res.tool_input?.thread_id) ??
        null;

      if (serverThreadId) {
        setResolvedThreadId(serverThreadId);
        setThreadId(serverThreadId);
      }

      const assistantMsg: Message = {
        id: nextId(),
        role: "assistant",
        text: res.answer,
        toolUsed: res.tool_used,
        toolInput: res.tool_input ?? null,
        toolOutput: res.tool_output ?? null,
        reasoning: res.reasoning,
        toolUsageLabel: inferUsageLabel(res.tool_used, res.tool_output),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setUploadedFiles([]);
      await reloadThreadArtifacts(currentThread);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setSending(false);
    }
  }, [
    activeArtifacts,
    buildFileContext,
    ensureThread,
    inferUsageLabel,
    input,
    reloadThreadArtifacts,
    sending,
    uploadedFiles,
    uploading,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void sendMessage();
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full bg-slate-900">
      {/* ── Sidebar: tool list ──────────────────────────────────────────── */}
      <aside className="hidden lg:flex flex-col w-72 shrink-0 border-r border-slate-700 bg-slate-800/60 overflow-y-auto">
        <div className="px-4 py-4 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wide">
            Available MCP Tools
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">Discovered from server</p>
        </div>

        {toolsLoading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-slate-400 text-sm">
            <span className="w-4 h-4 border-2 border-slate-600 border-t-indigo-400 rounded-full animate-spin" />
            Loading tools…
          </div>
        ) : toolsError ? (
          <p className="px-4 py-4 text-rose-400 text-sm">{toolsError}</p>
        ) : (
          <ul className="divide-y divide-slate-700/50">
            {tools.map((tool) => (
              <li key={tool.name} className="px-4 py-3 group hover:bg-slate-700/40 transition-colors">
                <p className="text-xs font-mono font-semibold text-indigo-300 group-hover:text-indigo-200">
                  {tool.name}
                </p>
                <p className="text-xs text-slate-400 mt-0.5 leading-relaxed line-clamp-3">
                  {tool.description}
                </p>
                {tool.requires_thread_id && (
                  <span className="mt-1 inline-block text-[10px] bg-amber-900/40 text-amber-300 border border-amber-700 rounded px-1.5 py-0.5">
                    requires thread_id
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </aside>

      {/* ── Main chat area ──────────────────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Header */}
        <div className="shrink-0 px-4 py-3 border-b border-slate-700 bg-slate-800/80 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-base font-bold text-white">MCP Agent Mode</h1>
            <p className="text-xs text-slate-400">
              The agent dynamically selects the right tool for each request
            </p>
            <p className="text-[11px] text-indigo-300 mt-0.5">
              Active thread: {resolvedThreadId ?? "not resolved yet"}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <label className="text-xs text-slate-400 whitespace-nowrap">Thread ID</label>
            <input
              type="number"
              min={1}
              value={threadId}
              onChange={(e) => setThreadId(e.target.value)}
              placeholder="optional"
              className="w-24 rounded-lg bg-slate-700 border border-slate-600 text-sm text-white px-2 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && !sending && (
            <div className="flex flex-col items-center justify-center h-full text-center py-16">
              <div className="w-16 h-16 rounded-2xl bg-indigo-600/20 border border-indigo-600/30 flex items-center justify-center mb-4">
                <span className="text-3xl">🤖</span>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">MCP Agent Ready</h3>
              <p className="text-sm text-slate-400 max-w-sm">
                Ask anything. The agent will discover and invoke the right tool automatically.
              </p>
              <div className="mt-6 grid grid-cols-2 gap-2 max-w-md text-left">
                {[
                  "Query the employee database",
                  "Summarize an uploaded PDF",
                  "Analyze this spreadsheet",
                  "Generate an image of a mountain",
                ].map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setInput(ex)}
                    className="text-xs text-left px-3 py-2 rounded-lg border border-slate-700 hover:border-indigo-600/50 hover:bg-slate-800 text-slate-300 transition-colors"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            (() => {
              const markdownImageSet = new Set(extractMarkdownImageUrls(msg.text));
              const allImageUrls = new Set<string>([
                ...extractMarkdownImageUrls(msg.text),
                ...extractPlainImageUrls(msg.text),
                ...extractToolImageUrls(msg.toolOutput),
              ]);
              const extraInlineImages = [...allImageUrls].filter((url) => !markdownImageSet.has(url));

              return (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-sm"
                    : "bg-slate-800 border border-slate-700 text-slate-100 rounded-bl-sm"
                }`}
              >
                {/* message text */}
                {msg.role === "assistant" ? (
                  <div className="prose prose-invert prose-sm max-w-none prose-p:my-0 prose-pre:my-2 prose-headings:my-1 prose-li:my-0">
                    <ReactMarkdown
                      components={{
                        img: ({ src, alt }) => {
                          if (!src) {
                            return null;
                          }
                          return (
                            <img
                              src={normalizeImageUrl(String(src))}
                              alt={alt ?? "Generated image"}
                              className="my-2 max-w-full rounded-xl border border-slate-700 bg-slate-900 object-contain"
                              loading="lazy"
                            />
                          );
                        },
                      }}
                    >
                      {msg.text}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap">{msg.text}</p>
                )}

                {extraInlineImages.length > 0 && (
                  <div className="mt-2 space-y-2">
                    {extraInlineImages.map((url, index) => (
                      <img
                        key={`${msg.id}-extra-img-${index}`}
                        src={normalizeImageUrl(url)}
                        alt="Generated image"
                        className="max-w-full rounded-xl border border-slate-700 bg-slate-900 object-contain"
                        loading="lazy"
                      />
                    ))}
                  </div>
                )}

                {/* tool execution detail (assistant only) */}
                {msg.role === "assistant" && msg.toolUsed && (
                  <div className="mt-3 border-t border-slate-700/60 pt-2">
                    {msg.toolUsageLabel && (
                      <div className="mb-2 text-[11px] rounded-md border border-indigo-700/50 bg-indigo-900/30 px-2 py-1 text-indigo-200">
                        Using file: {msg.toolUsageLabel.replace("Using: ", "")}
                      </div>
                    )}
                    <button
                      className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
                      onClick={() =>
                        setExpandedMsg((prev) => (prev === msg.id ? null : msg.id))
                      }
                    >
                      <span className="text-[10px] bg-indigo-900/60 text-indigo-300 border border-indigo-700 rounded px-1.5 py-0.5 font-mono">
                        {msg.toolUsed}
                      </span>
                      <span>{expandedMsg === msg.id ? "▲ hide details" : "▼ view details"}</span>
                    </button>

                    {expandedMsg === msg.id && (
                      <div className="mt-2 space-y-2 text-xs text-slate-300">
                        {msg.reasoning && (
                          <p className="text-slate-400 italic">{msg.reasoning}</p>
                        )}
                        {msg.toolInput && (
                          <div>
                            <p className="font-semibold text-slate-400 mb-0.5">Input</p>
                            <pre className="bg-slate-900/60 rounded p-2 overflow-x-auto text-[11px] text-slate-300">
                              {JSON.stringify(msg.toolInput, null, 2)}
                            </pre>
                          </div>
                        )}
                        {msg.toolOutput && (
                          <div>
                            <p className="font-semibold text-slate-400 mb-0.5">Output</p>
                            <pre className="bg-slate-900/60 rounded p-2 overflow-x-auto text-[11px] text-slate-300 max-h-40">
                              {JSON.stringify(msg.toolOutput, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {msg.uploads && msg.uploads.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {msg.uploads.map((file) => (
                      <div
                        key={`${msg.id}-${file.id}`}
                        className="text-xs rounded-md px-2 py-1 bg-slate-900/60 border border-slate-700 text-slate-300"
                      >
                        {(file.fileType === "image" || (file.mimeType ?? "").startsWith("image/")) && file.href && (
                          <img
                            src={file.href}
                            alt={file.name}
                            className="mb-1 max-h-44 w-auto rounded border border-slate-700 object-contain"
                            loading="lazy"
                          />
                        )}
                        {(file.fileType === "video" || (file.mimeType ?? "").startsWith("video/")) && file.href && (
                          <video
                            src={file.href}
                            controls
                            className="mb-1 max-h-52 w-full rounded border border-slate-700 bg-black"
                            preload="metadata"
                          />
                        )}
                        {file.href ? (
                          <a href={file.href} target="_blank" rel="noreferrer" className="hover:text-indigo-300">
                            {file.name}
                          </a>
                        ) : (
                          <span>{file.name}</span>
                        )}
                        <span className="ml-2 text-slate-500">[{file.kind}]</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
              );
            })()
          ))}

          {/* AI thinking indicator */}
          {(sending || uploading) && (
            <div className="flex justify-start">
              <div className="bg-slate-800 border border-slate-700 rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-2 text-slate-400 text-sm">
                <span className="w-3.5 h-3.5 border-2 border-slate-600 border-t-indigo-400 rounded-full animate-spin" />
                {uploading ? "Uploading files…" : "Agent selecting tool and executing…"}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Error banner */}
        {error && (
          <div className="mx-4 mb-2 px-3 py-2 bg-rose-900/30 border border-rose-700 rounded-lg text-rose-300 text-xs">
            {error}
          </div>
        )}

        {/* Input row */}
        <div className="shrink-0 px-4 pb-4 pt-2 border-t border-slate-700">
          {(() => {
            console.log("=== ATTACHMENT RENDER AREA ===", {
              pendingUploadsCount: pendingUploads.length,
              pendingUploads: pendingUploads.map(p => ({ name: p.name, status: p.status, localId: p.localId })),
              uploadedFilesCount: uploadedFiles.length,
              uploadedFiles: uploadedFiles.map(f => ({ id: f.id, name: f.name, kind: f.kind })),
              attachmentsCount: attachments.length,
              attachments: attachments.map(a => ({ id: a.id, name: a.name, kind: a.kind })),
              activeArtifactsCount: activeArtifacts.length,
            });
            return null;
          })()}
          {pendingUploads.length === 0 && activeArtifacts.length === 0 && (
            <div className="mb-2 rounded-lg border border-dashed border-slate-700 bg-slate-800/40 px-3 py-2 text-[11px] text-slate-400">
              No files uploaded yet for this thread.
            </div>
          )}
          {(pendingUploads.length > 0 || activeArtifacts.length > 0) && (
            <div className="mb-2 space-y-1">
              {pendingUploads.map((item) => (
                <div
                  key={item.localId}
                  className="text-xs rounded-lg border border-slate-700 bg-slate-800/70 px-3 py-2 text-slate-300"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate flex items-center gap-1.5">
                      <span>{fileIconFor(item)}</span>
                      <span>{item.name}</span>
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                        item.status === "failed"
                          ? "text-rose-300 border-rose-700 bg-rose-900/30"
                          : item.status === "uploaded"
                            ? "text-emerald-300 border-emerald-700 bg-emerald-900/30"
                            : "text-amber-300 border-amber-700 bg-amber-900/30"
                      }`}
                    >
                      {statusLabel(item.status)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded bg-slate-700 overflow-hidden">
                    <div className="h-full bg-indigo-500" style={{ width: `${item.progress}%` }} />
                  </div>
                  {item.error && <p className="mt-1 text-rose-400">{item.error}</p>}
                </div>
              ))}
              {activeArtifacts.length > 0 && (
                <div>
                  <p className="mb-1 text-[11px] text-slate-400">Uploaded files in this thread</p>
                  <div className="flex flex-wrap gap-1.5">
                    {activeArtifacts.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => removeUploadedArtifact(item.id)}
                        className="text-[11px] rounded-full border border-indigo-600/60 bg-indigo-900/30 px-2 py-0.5 text-indigo-200 hover:bg-indigo-900/50"
                        title="Remove staged file"
                      >
                        {fileIconFor(item)} {item.name} ✓
                        {item.origin === "thread-history" && (
                          <span className="ml-1 rounded-full border border-slate-600 bg-slate-800 px-1.5 py-0 text-[10px] text-slate-300">
                            From thread history
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-2 items-end bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-indigo-500">
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              multiple
              onChange={(e) => {
                const selectedFiles = e.target.files ? Array.from(e.target.files) : [];
                void handleSelectFiles(selectedFiles);
                e.currentTarget.value = "";
              }}
            />
            <button
              type="button"
              disabled={sending || uploading}
              onClick={() => fileInputRef.current?.click()}
              className="shrink-0 px-2.5 py-1.5 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Upload files"
            >
              +
            </button>
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask the MCP agent anything… (Enter to send)"
              disabled={sending}
              className="flex-1 resize-none bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none min-h-6 max-h-32"
              style={{ overflowY: "auto" }}
            />
            <button
              onClick={() => void sendMessage()}
              disabled={sending || uploading || (!input.trim() && activeArtifacts.length === 0)}
              className="shrink-0 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
            >
              Send
            </button>
          </div>
          <p className="mt-1.5 text-[11px] text-slate-500 text-center">
            Shift+Enter for newline · Enter to send
          </p>
        </div>
      </div>
    </div>
  );
}
