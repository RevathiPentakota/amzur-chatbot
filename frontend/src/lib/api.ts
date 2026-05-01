export const API_BASE_URL = "http://localhost:8000";

import type {
  AuthPayload,
  AuthResponse,
  ChatHistoryItem,
  ThreadCreatePayload,
  ThreadItem,
  ThreadUpdatePayload,
  ChatResponse,
} from "../types";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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

export async function getMessagesByThread(threadId: number): Promise<ChatHistoryItem[]> {
  return api<ChatHistoryItem[]>(`/chat/thread/${threadId}/messages`, {
    method: "GET",
  });
}

export async function sendMessage(message: string, threadId: number): Promise<ChatResponse> {
  return api<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, thread_id: threadId }),
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
