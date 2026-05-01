import { useEffect, useMemo, useState } from "react";

import {
  createThread,
  getMessagesByThread,
  getThreads,
  logoutUser,
  removeThread,
  renameThread,
  sendMessage,
} from "../lib/api";

import type { ChatHistoryItem, ThreadItem } from "../types";

interface Message {
  id: string;
  text: string;
  sender: "user" | "bot";
}

export function Chat() {
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getThreads();
        setThreads(data);
        if (data.length > 0) {
          setSelectedThreadId(data[0].id);
        }
      } finally {
        setLoadingThreads(false);
      }
    };

    void load();
  }, []);

  useEffect(() => {
    const loadThreadMessages = async () => {
      if (!selectedThreadId) {
        setMessages([]);
        return;
      }

      setLoadingMessages(true);
      try {
        const history = await getMessagesByThread(selectedThreadId);
        setMessages(mapHistoryToMessages(history));
      } catch {
        setMessages([]);
      } finally {
        setLoadingMessages(false);
      }
    };

    void loadThreadMessages();
  }, [selectedThreadId]);

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) ?? null,
    [threads, selectedThreadId],
  );

  const handleCreateThread = async () => {
    const created = await createThread();
    setThreads((prev) => [created, ...prev]);
    setSelectedThreadId(created.id);
    setMessages([]);
  };

  const handleRenameThread = async (thread: ThreadItem) => {
    const nextTitle = window.prompt("Rename thread", thread.title ?? "");
    if (!nextTitle || !nextTitle.trim()) {
      return;
    }

    const updated = await renameThread(thread.id, { title: nextTitle.trim() });
    setThreads((prev) => prev.map((item) => (item.id === thread.id ? updated : item)));
  };

  const handleDeleteThread = async (thread: ThreadItem) => {
    const ok = window.confirm("Delete this thread and all its messages?");
    if (!ok) {
      return;
    }

    await removeThread(thread.id);
    setThreads((prev) => prev.filter((item) => item.id !== thread.id));

    if (selectedThreadId === thread.id) {
      const remaining = threads.filter((item) => item.id !== thread.id);
      setSelectedThreadId(remaining[0]?.id ?? null);
      if (!remaining.length) {
        setMessages([]);
      }
    }
  };

  const handleSend = async () => {
    if (!input.trim()) return;

    let threadId = selectedThreadId;
    if (!threadId) {
      const created = await createThread();
      setThreads((prev) => [created, ...prev]);
      setSelectedThreadId(created.id);
      threadId = created.id;
    }

    const content = input;
    const userMessage: Message = {
      id: Date.now().toString(),
      text: content,
      sender: "user",
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSending(true);

    try {
      const response = await sendMessage(content, threadId);
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: response.reply,
        sender: "bot",
      };
      setMessages((prev) => [...prev, botMessage]);

      const updatedThreads = await getThreads();
      setThreads(updatedThreads);
    } catch (error) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: error instanceof Error ? error.message : "Failed to get response from bot",
        sender: "bot",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleLogout = async () => {
    try {
      await logoutUser();
    } finally {
      window.location.href = "/login";
    }
  };

  return (
    <div className="min-h-screen bg-slate-100/80 p-4">
      <div className="mx-auto h-[88vh] w-full max-w-6xl overflow-hidden rounded-2xl border border-slate-200/70 bg-white shadow-xl">
        <div className="grid h-full grid-cols-12">
          <aside className="col-span-12 flex flex-col border-b border-slate-200/70 bg-slate-50/90 p-3 md:col-span-4 md:border-b-0 md:border-r">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-700">Threads</h2>
              <button
                onClick={() => {
                  void handleCreateThread();
                }}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-blue-700"
              >
                New
              </button>
            </div>

            <div className="flex-1 space-y-2 overflow-y-auto md:h-[calc(88vh-140px)]">
              {loadingThreads && <p className="text-sm text-slate-500">Loading threads...</p>}

              {!loadingThreads && threads.length === 0 && (
                <p className="text-sm text-slate-500">No threads yet. Create one to start chatting.</p>
              )}

              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`group rounded-xl p-2 transition ${
                    selectedThreadId === thread.id
                      ? "border border-blue-200 bg-blue-50 shadow-sm"
                      : "bg-transparent hover:bg-slate-100"
                  }`}
                >
                  <button
                    onClick={() => setSelectedThreadId(thread.id)}
                    className="w-full text-left"
                  >
                    <p className="truncate text-sm font-medium text-slate-800">
                      {thread.title ?? "Untitled thread"}
                    </p>
                  </button>
                  <div className="mt-1.5 flex gap-2 opacity-0 transition group-hover:opacity-100">
                    <button
                      onClick={() => {
                        void handleRenameThread(thread);
                      }}
                      className="rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-200"
                    >
                      Rename
                    </button>
                    <button
                      onClick={() => {
                        void handleDeleteThread(thread);
                      }}
                      className="rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <button
              onClick={() => {
                void handleLogout();
              }}
              className="mt-3 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-100"
            >
              Logout
            </button>
          </aside>

          <section className="col-span-12 flex h-full flex-col md:col-span-8">
            <div className="border-b border-slate-200/70 bg-white px-4 py-3">
              <h1 className="truncate text-xs font-semibold tracking-wide text-slate-700">
                {selectedThread?.title ?? "amzur chatbot"}
              </h1>
            </div>

            <div className="flex-1 overflow-y-auto bg-slate-50/70 px-4 py-4">
              <div className="mx-auto w-full max-w-2xl space-y-3">
                {loadingMessages && <p className="text-sm text-slate-500">Loading messages...</p>}

                {!loadingMessages && selectedThreadId === null && (
                  <p className="text-sm text-slate-500">Select a thread or create a new one.</p>
                )}

                {!loadingMessages && selectedThreadId !== null && messages.length === 0 && (
                  <p className="text-sm text-slate-500">Start the conversation.</p>
                )}

                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-xl px-4 py-2 text-sm shadow-sm whitespace-pre-wrap wrap-break-word ${
                        msg.sender === "user"
                          ? "bg-blue-600 text-white"
                          : "bg-gray-200 text-slate-800"
                      }`}
                    >
                      {msg.text}
                    </div>
                  </div>
                ))}

                {sending && (
                  <div className="flex justify-start">
                    <div className="max-w-[80%] rounded-xl bg-gray-200 px-4 py-2 text-sm italic text-slate-600 shadow-sm">
                      thinking...
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="sticky bottom-0 border-t border-slate-200/70 bg-white/95 p-3 backdrop-blur">
              <div className="mx-auto flex w-full max-w-2xl items-end gap-2 rounded-full border border-slate-200 bg-white p-1.5 shadow-sm">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Type your message..."
                  disabled={sending || loadingMessages}
                  className="h-11 max-h-28 flex-1 resize-none rounded-full bg-transparent px-4 py-2 text-sm text-slate-800 shadow-sm outline-none focus:ring-2 focus:ring-blue-400"
                />
                <button
                  onClick={() => {
                    void handleSend();
                  }}
                  disabled={sending || loadingMessages || !input.trim()}
                  className="h-10 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sending ? "Sending..." : "Send"}
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function mapHistoryToMessages(history: ChatHistoryItem[]): Message[] {
  const mapped: Message[] = [];

  for (const item of history) {
    mapped.push({
      id: `u-${item.id}`,
      text: item.message,
      sender: "user",
    });
    mapped.push({
      id: `b-${item.id}`,
      text: item.response,
      sender: "bot",
    });
  }

  return mapped;
}
