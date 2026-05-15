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
