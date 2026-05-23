export const API_BASE_URL = "http://localhost:8000";
const REQUEST_TIMEOUT_MS = 60000;

import type {
  AttachmentItem,
  AuthPayload,
  AuthResponse,
  ChatHistoryItem,
  ImageGenerateRequest,
  ImageGenerateResponse,
  RagChatRequest,
  RagChatResponse,
  RagPdfItem,
  ThreadCreatePayload,
  ThreadItem,
  ThreadUpdatePayload,
  ChatResponse,
  ThreadHistoryResponse,
  SqlChatRequest,
  SqlChatResponse,
  DataFrameSourceResponse,
  GoogleSheetConnectRequest,
  DataFrameChatRequest,
  DataFrameChatResponse,
  ResearchRequest,
} from "../types";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const headers = new Headers(init?.headers ?? {});
  const isFormData = init?.body instanceof FormData;
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      credentials: "include",
      headers,
      signal: controller.signal,
      ...init,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const data = await res.json();
      if (typeof data?.detail === "string") {
        detail = data.detail;
      }
    } catch {
      // Keep fallback message when response body is not JSON.
    }
    throw new Error(`Request failed: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function registerUser(payload: AuthPayload): Promise<AuthResponse> {
  return api<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginUser(payload: AuthPayload): Promise<AuthResponse> {
  return api<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutUser(): Promise<{ message: string }> {
  return api<{ message: string }>("/auth/logout", {
    method: "POST",
  });
}

export async function getChatHistory(): Promise<ChatHistoryItem[]> {
  return api<ChatHistoryItem[]>("/chat/history", {
    method: "GET",
  });
}

export async function getMessagesByThread(threadId: number): Promise<ThreadHistoryResponse> {
  return api<ThreadHistoryResponse>(`/chat/thread/${threadId}/messages`, {
    method: "GET",
  });
}

export async function sendMessage(
  message: string,
  threadId: number,
  attachmentIds: number[] = [],
): Promise<ChatResponse> {
  return api<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, thread_id: threadId, attachment_ids: attachmentIds }),
  });
}

export function attachmentContentUrl(attachmentId: number): string {
  return `${API_BASE_URL}/chat/attachments/${attachmentId}/content`;
}

export async function listThreadAttachments(threadId: number): Promise<AttachmentItem[]> {
  return api<AttachmentItem[]>(`/chat/thread/${threadId}/attachments`, {
    method: "GET",
  });
}

export function uploadAttachment(
  file: File,
  threadId: number,
  onProgress?: (progress: number) => void,
): Promise<AttachmentItem> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("thread_id", String(threadId));
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/chat/upload`, true);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) {
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      onProgress(percent);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as AttachmentItem);
        } catch {
          reject(new Error("Failed to parse upload response"));
        }
        return;
      }

      try {
        const parsed = JSON.parse(xhr.responseText) as { detail?: string };
        reject(new Error(parsed.detail ?? `Upload failed (${xhr.status})`));
      } catch {
        reject(new Error(`Upload failed (${xhr.status})`));
      }
    };

    xhr.onerror = () => reject(new Error("Upload request failed"));
    xhr.send(formData);
  });
}

export async function getThreads(): Promise<ThreadItem[]> {
  return api<ThreadItem[]>("/threads", { method: "GET" });
}

export async function createThread(
  payload: ThreadCreatePayload = {},
): Promise<ThreadItem> {
  return api<ThreadItem>("/threads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function renameThread(
  threadId: number,
  payload: ThreadUpdatePayload,
): Promise<ThreadItem> {
  return api<ThreadItem>(`/threads/${threadId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function removeThread(threadId: number): Promise<{ message: string }> {
  return api<{ message: string }>(`/threads/${threadId}`, { method: "DELETE" });
}

export function googleLoginUrl(): string {
  return `${API_BASE_URL}/auth/google/login`;
}

export async function generateImage(
  payload: ImageGenerateRequest,
): Promise<ImageGenerateResponse> {
  return api<ImageGenerateResponse>("/images/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function generatedImageUrl(imageId: number): string {
  return `${API_BASE_URL}/images/${imageId}/content`;
}

export function ragPdfContentUrl(pdfId: number): string {
  return `${API_BASE_URL}/rag/pdfs/${pdfId}/content`;
}

export async function listThreadRagPdfs(threadId: number): Promise<RagPdfItem[]> {
  return api<RagPdfItem[]>(`/rag/thread/${threadId}/pdfs`, {
    method: "GET",
  });
}

export async function ragChat(payload: RagChatRequest): Promise<RagChatResponse> {
  return api<RagChatResponse>("/rag/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function sqlChat(payload: SqlChatRequest): Promise<SqlChatResponse> {
  return api<SqlChatResponse>("/sql/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function uploadDataFrame(
  file: File,
  threadId: number,
  onProgress?: (progress: number) => void,
): Promise<DataFrameSourceResponse> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("thread_id", String(threadId));
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/dataframe/upload`, true);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) {
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      onProgress(percent);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as DataFrameSourceResponse);
        } catch {
          reject(new Error("Failed to parse dataframe upload response"));
        }
        return;
      }

      try {
        const parsed = JSON.parse(xhr.responseText) as { detail?: string };
        reject(new Error(parsed.detail ?? `Dataframe upload failed (${xhr.status})`));
      } catch {
        reject(new Error(`Dataframe upload failed (${xhr.status})`));
      }
    };

    xhr.onerror = () => reject(new Error("Dataframe upload request failed"));
    xhr.send(formData);
  });
}

export async function connectGoogleSheet(
  payload: GoogleSheetConnectRequest,
): Promise<DataFrameSourceResponse> {
  return api<DataFrameSourceResponse>("/dataframe/google-sheet", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function dataframeChat(payload: DataFrameChatRequest): Promise<DataFrameChatResponse> {
  return api<DataFrameChatResponse>("/dataframe/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listThreadDataFrameSources(threadId: number): Promise<DataFrameSourceResponse[]> {
  return api<DataFrameSourceResponse[]>(`/dataframe/thread/${threadId}/sources`, {
    method: "GET",
  });
}

export function uploadRagPdf(
  file: File,
  threadId: number,
  onProgress?: (progress: number) => void,
): Promise<RagPdfItem> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append("thread_id", String(threadId));
    formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/rag/upload-pdf`, true);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (event) => {
      if (!onProgress || !event.lengthComputable) {
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      onProgress(percent);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as RagPdfItem);
        } catch {
          reject(new Error("Failed to parse PDF upload response"));
        }
        return;
      }

      try {
        const parsed = JSON.parse(xhr.responseText) as { detail?: string };
        reject(new Error(parsed.detail ?? `PDF upload failed (${xhr.status})`));
      } catch {
        reject(new Error(`PDF upload failed (${xhr.status})`));
      }
    };

    xhr.onerror = () => reject(new Error("PDF upload request failed"));
    xhr.send(formData);
  });
}

/**
 * Opens a Server-Sent Events connection to /research/digest and calls the
 * provided callbacks as each named event arrives. Returns a cleanup function.
 */
export function streamResearchDigest(
  payload: ResearchRequest,
  callbacks: {
    onStatus?: (msg: string) => void;
    onPapers?: (papers: unknown[]) => void;
    onSection?: (event: string, title: string, content: string) => void;
    onSources?: (title: string, content: string) => void;
    onDone?: () => void;
    onError?: (msg: string) => void;
  },
): () => void {
  const ctrl = new AbortController();

  void (async () => {
    let resp: Response;
    try {
      resp = await fetch(`${API_BASE_URL}/research/digest`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: ctrl.signal,
      });
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        callbacks.onError?.(err instanceof Error ? err.message : "Network error");
      }
      return;
    }

    if (!resp.ok) {
      let detail = `${resp.status} ${resp.statusText}`;
      try {
        const data = await resp.json() as { detail?: string };
        if (typeof data?.detail === "string") detail = data.detail;
      } catch { /* ignore */ }
      callbacks.onError?.(detail);
      return;
    }

    const reader = resp.body?.getReader();
    if (!reader) { callbacks.onError?.("No response body"); return; }
    const decoder = new TextDecoder();
    let buf = "";

    // eslint-disable-next-line no-constant-condition
    while (true) {
      let done = false;
      let value: Uint8Array | undefined;
      try {
        ({ done, value } = await reader.read());
      } catch {
        break;
      }
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      // Process complete SSE events (separated by \n\n)
      const parts = buf.split("\n\n");
      buf = parts.pop() ?? "";  // keep incomplete tail

      for (const part of parts) {
        const lines = part.trim().split("\n");
        let eventName = "";
        let dataStr = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) eventName = line.slice(7).trim();
          else if (line.startsWith("data: ")) dataStr = line.slice(6).trim();
        }
        if (!eventName || !dataStr) continue;

        let parsed: Record<string, unknown>;
        try {
          parsed = JSON.parse(dataStr) as Record<string, unknown>;
        } catch {
          continue;
        }

        if (eventName === "status") {
          callbacks.onStatus?.(String(parsed.message ?? ""));
        } else if (eventName === "papers") {
          callbacks.onPapers?.((parsed.papers as unknown[]) ?? []);
        } else if (eventName === "sources") {
          callbacks.onSources?.(String(parsed.title ?? "Sources"), String(parsed.content ?? ""));
        } else if (eventName === "done") {
          callbacks.onDone?.();
        } else if (eventName === "error") {
          callbacks.onError?.(String(parsed.message ?? "Unknown error"));
        } else {
          // key_findings, trends, contradictions, final_summary
          callbacks.onSection?.(eventName, String(parsed.title ?? ""), String(parsed.content ?? ""));
        }
      }
    }
  })();

  return () => ctrl.abort();
}

// ── MCP Agent ───────────────────────────────────────────────────────────────

import type { McpAgentRequest, McpAgentResponse, McpExecuteRequest, McpExecuteResponse, McpToolDefinition } from "../types";

export async function getMcpTools(): Promise<McpToolDefinition[]> {
  return api<McpToolDefinition[]>("/mcp/tools", { method: "GET" });
}

export async function runMcpAgent(payload: McpAgentRequest): Promise<McpAgentResponse> {
  return api<McpAgentResponse>("/mcp/agent", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function executeMcpTool(payload: McpExecuteRequest): Promise<McpExecuteResponse> {
  return api<McpExecuteResponse>("/mcp/execute", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Tic Tac Toe ──────────────────────────────────────────────────────────────

import type { NewGameResponse, MakeMoveRequest, MakeMoveResponse } from "../types";

export async function newTicTacToeGame(): Promise<NewGameResponse> {
  return api<NewGameResponse>("/tic-tac-toe/new", { method: "POST" });
}

export async function makeTicTacToeMove(
  payload: MakeMoveRequest,
): Promise<MakeMoveResponse> {
  return api<MakeMoveResponse>("/tic-tac-toe/move", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
