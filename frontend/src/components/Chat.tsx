import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import {
  attachmentContentUrl,
  createThread,
  generateImage,
  generatedImageUrl,
  getMessagesByThread,
  getThreads,
  logoutUser,
  removeThread,
  renameThread,
  sendMessage,
  uploadAttachment,
} from "../lib/api";

import type { AttachmentItem, ChatHistoryItem, ThreadItem } from "../types";

interface Message {
  id: string;
  text: string;
  sender: "user" | "bot";
  attachments?: AttachmentItem[];
  generatedImageId?: number;
  generatedImagePrompt?: string;
}

interface PendingAttachment {
  localId: string;
  localFile?: File;
  original_filename: string;
  mime_type: string;
  file_type: AttachmentItem["file_type"] | null;
  id?: number;
  thread_id?: number;
  user_id?: number;
  created_at?: string;
  uploadProgress: number;
  uploading: boolean;
  error?: string;
  localPreviewUrl?: string;
}

export function Chat() {
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loadingThreads, setLoadingThreads] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [preparingUpload, setPreparingUpload] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [showImagePrompt, setShowImagePrompt] = useState(false);
  const [imagePrompt, setImagePrompt] = useState("");
  const [generatingImage, setGeneratingImage] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

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
    const hasText = Boolean(input.trim());
    const uploading = pendingAttachments.some((item) => item.uploading);
    const hasUploadErrors = pendingAttachments.some((item) => Boolean(item.error));
    const readyAttachments = pendingAttachments.filter(
      (item): item is PendingAttachment & { id: number } =>
        typeof item.id === "number" && !item.uploading,
    );
    const unresolvedAttachments = pendingAttachments.filter(
      (item) => !item.uploading && !item.error && typeof item.id !== "number",
    );

    if ((!hasText && readyAttachments.length === 0) || uploading || hasUploadErrors) {
      return;
    }

    if (unresolvedAttachments.length > 0) {
      const warnMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: "Attachment upload is not finished yet. Please wait a moment and try again.",
        sender: "bot",
      };
      setMessages((prev) => [...prev, warnMessage]);
      return;
    }

    let threadId = selectedThreadId;
    if (!threadId) {
      const created = await createThread();
      setThreads((prev) => [created, ...prev]);
      setSelectedThreadId(created.id);
      threadId = created.id;
    }

    const content = input.trim();
    const messageAttachments: AttachmentItem[] = readyAttachments.map((item) => ({
        id: item.id,
        user_id: item.user_id ?? 0,
        thread_id: item.thread_id ?? threadId,
        original_filename: item.original_filename,
        mime_type: item.mime_type,
        file_type: item.file_type ?? "document",
        created_at: item.created_at ?? new Date().toISOString(),
      }));

    const userMessage: Message = {
      id: Date.now().toString(),
      text: content || "(attachment)",
      sender: "user",
      attachments: messageAttachments,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSending(true);

    try {
      const attachmentIds = readyAttachments.map((item) => item.id);
      const response = await sendMessage(
        content || "Please process the uploaded attachment(s).",
        threadId,
        attachmentIds,
      );
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: response.reply,
        sender: "bot",
      };
      setMessages((prev) => [...prev, botMessage]);
      setPendingAttachments([]);

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

  const ensureThreadForAttachment = async (): Promise<number> => {
    if (selectedThreadId) {
      return selectedThreadId;
    }

    const created = await createThread();
    setThreads((prev) => [created, ...prev]);
    setSelectedThreadId(created.id);
    return created.id;
  };

  const handleSelectAttachments = async (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }

    const filesToUpload = Array.from(files).map((file) => {
      const localId = `${Date.now()}-${Math.random()}`;
      const previewUrl = file.type.startsWith("image/") || file.type.startsWith("video/")
        ? URL.createObjectURL(file)
        : undefined;
      return {
        file,
        localId,
        pending: {
          localId,
          localFile: file,
          original_filename: file.name,
          mime_type: file.type || "application/octet-stream",
          file_type: null,
          uploadProgress: 0,
          uploading: true,
          localPreviewUrl: previewUrl,
        } satisfies PendingAttachment,
      };
    });

    setPendingAttachments((prev) => [...prev, ...filesToUpload.map((item) => item.pending)]);

    let threadId: number;
    setPreparingUpload(true);
    try {
      threadId = await ensureThreadForAttachment();
    } finally {
      setPreparingUpload(false);
    }

    for (const itemToUpload of filesToUpload) {
      try {
        const uploaded = await uploadAttachment(itemToUpload.file, threadId, (progress) => {
          setPendingAttachments((prev) =>
            prev.map((item) =>
              item.localId === itemToUpload.localId ? { ...item, uploadProgress: progress } : item,
            ),
          );
        });

        setPendingAttachments((prev) =>
          prev.map((item) =>
            item.localId === itemToUpload.localId
              ? {
                  ...item,
                  id: uploaded.id,
                  user_id: uploaded.user_id,
                  thread_id: uploaded.thread_id,
                  file_type: uploaded.file_type,
                  created_at: uploaded.created_at,
                  uploadProgress: 100,
                  uploading: false,
                }
              : item,
          ),
        );
      } catch (error) {
        setPendingAttachments((prev) =>
          prev.map((item) =>
            item.localId === itemToUpload.localId
              ? {
                  ...item,
                  uploading: false,
                  error: error instanceof Error ? error.message : "Upload failed",
                }
              : item,
          ),
        );
      }
    }
  };

  const removePendingAttachment = (localId: string) => {
    setPendingAttachments((prev) => {
      const next = prev.filter((item) => item.localId !== localId);
      const removed = prev.find((item) => item.localId === localId);
      if (removed?.localPreviewUrl) {
        URL.revokeObjectURL(removed.localPreviewUrl);
      }
      return next;
    });
  };

  const retryPendingAttachment = async (localId: string) => {
    const target = pendingAttachments.find((item) => item.localId === localId);
    if (!target?.localFile) {
      setPendingAttachments((prev) =>
        prev.map((item) =>
          item.localId === localId
            ? { ...item, error: "Retry unavailable. Please attach the file again." }
            : item,
        ),
      );
      return;
    }

    const threadId = target.thread_id ?? (await ensureThreadForAttachment());

    setPendingAttachments((prev) =>
      prev.map((item) =>
        item.localId === localId
          ? { ...item, uploading: true, uploadProgress: 0, error: undefined, thread_id: threadId }
          : item,
      ),
    );

    try {
      const uploaded = await uploadAttachment(target.localFile, threadId, (progress) => {
        setPendingAttachments((prev) =>
          prev.map((item) =>
            item.localId === localId ? { ...item, uploadProgress: progress } : item,
          ),
        );
      });

      setPendingAttachments((prev) =>
        prev.map((item) =>
          item.localId === localId
            ? {
                ...item,
                id: uploaded.id,
                user_id: uploaded.user_id,
                thread_id: uploaded.thread_id,
                file_type: uploaded.file_type,
                created_at: uploaded.created_at,
                uploadProgress: 100,
                uploading: false,
                error: undefined,
              }
            : item,
        ),
      );
    } catch (error) {
      setPendingAttachments((prev) =>
        prev.map((item) =>
          item.localId === localId
            ? {
                ...item,
                uploading: false,
                error: error instanceof Error ? error.message : "Upload failed",
              }
            : item,
        ),
      );
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

  const handleGenerateImage = async () => {
    if (!imagePrompt.trim() || generatingImage) return;

    let threadId = selectedThreadId;
    if (!threadId) {
      const created = await createThread();
      setThreads((prev) => [created, ...prev]);
      setSelectedThreadId(created.id);
      threadId = created.id;
    }

    const prompt = imagePrompt.trim();
    setImagePrompt("");
    setShowImagePrompt(false);
    setGeneratingImage(true);

    const userMsg: Message = {
      id: Date.now().toString(),
      text: `Generate image: ${prompt}`,
      sender: "user",
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const result = await generateImage({ prompt, thread_id: threadId });
      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        text: "",
        sender: "bot",
        generatedImageId: result.id,
        generatedImagePrompt: result.prompt,
      };
      setMessages((prev) => [...prev, botMsg]);
      const updatedThreads = await getThreads();
      setThreads(updatedThreads);
    } catch (error) {
      const errMsg: Message = {
        id: (Date.now() + 1).toString(),
        text: error instanceof Error ? error.message : "Image generation failed.",
        sender: "bot",
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setGeneratingImage(false);
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

          <section className="col-span-12 flex h-full min-h-0 flex-col md:col-span-8">
            <div className="border-b border-slate-200/70 bg-white px-4 py-3">
              <h1 className="truncate text-xs font-semibold tracking-wide text-slate-700">
                {selectedThread?.title ?? "amzur chatbot"}
              </h1>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto bg-slate-50/70 px-4 py-4">
              <div className="mx-auto w-full max-w-2xl space-y-3 pb-2">
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
                      className={`max-w-[80%] min-w-0 overflow-hidden wrap-break-word rounded-xl px-4 py-2 text-sm shadow-sm ${
                        msg.sender === "user"
                          ? "bg-blue-600 text-white"
                          : "bg-gray-200 text-slate-800"
                      }`}
                    >
                      {msg.sender === "user" ? (
                        <div className="space-y-2">
                          <span className="whitespace-pre-wrap">{msg.text}</span>
                          {msg.attachments && msg.attachments.length > 0 && (
                            <div className="space-y-2">
                              {msg.attachments.map((attachment) => (
                                <AttachmentPreview key={attachment.id} attachment={attachment} compact />
                              ))}
                            </div>
                          )}
                        </div>
                      ) : msg.generatedImageId ? (
                        <div className="space-y-2">
                          <p className="text-xs text-slate-500 italic">Generated: {msg.generatedImagePrompt}</p>
                          <img
                            src={generatedImageUrl(msg.generatedImageId)}
                            alt={msg.generatedImagePrompt}
                            className="max-h-80 rounded-lg border border-slate-300 object-contain"
                          />
                        </div>
                      ) : (
                        <div className="prose prose-sm max-w-none
                          prose-p:my-1 prose-p:leading-relaxed
                          prose-ul:my-1 prose-ul:pl-4
                          prose-ol:my-1 prose-ol:pl-4
                          prose-li:my-0.5
                          prose-strong:font-semibold
                          prose-code:rounded prose-code:bg-slate-300 prose-code:px-1 prose-code:text-xs
                          prose-pre:my-2 prose-pre:overflow-x-auto prose-pre:rounded-lg prose-pre:bg-slate-700 prose-pre:p-3 prose-pre:text-xs prose-pre:text-slate-100
                          prose-headings:my-1 prose-headings:font-semibold
                          prose-blockquote:border-l-2 prose-blockquote:border-slate-400 prose-blockquote:pl-3 prose-blockquote:italic
                        ">
                          <ReactMarkdown>{msg.text}</ReactMarkdown>
                        </div>
                      )}
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

                {generatingImage && (
                  <div className="flex justify-start">
                    <div className="max-w-[80%] rounded-xl bg-gray-200 px-4 py-2 text-sm italic text-slate-600 shadow-sm">
                      Generating image...
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="border-t border-slate-200/70 bg-white/95 p-3 backdrop-blur">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                accept="image/*,video/*,.csv,.xls,.xlsx,.txt,.md,.json,.py,.js,.ts,.tsx,.jsx,.java,.c,.cpp,.cs,.go,.rs,.sql,.pdf,.doc,.docx,.tex"
                onChange={(e) => {
                  void handleSelectAttachments(e.target.files);
                  e.currentTarget.value = "";
                }}
              />

              {pendingAttachments.length > 0 && (
                <div className="mx-auto mb-2 w-full max-w-2xl space-y-2">
                  {pendingAttachments.map((item) => (
                    <div
                      key={item.localId}
                      className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-xs font-medium text-slate-700">{item.original_filename}</p>
                        <p className="text-[11px] text-slate-500">
                          {item.uploading
                            ? `Uploading ${item.uploadProgress}%`
                            : item.error
                              ? item.error
                              : "Uploaded"}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {item.error && (
                          <button
                            type="button"
                            onClick={() => {
                              void retryPendingAttachment(item.localId);
                            }}
                            className="rounded-md bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-200"
                          >
                            Retry
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => removePendingAttachment(item.localId)}
                          className="rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-200"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {pendingAttachments.some((item) => Boolean(item.error)) && (
                <div className="mx-auto mb-2 w-full max-w-2xl rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  One or more attachments failed to upload. Remove failed files and try attaching again.
                </div>
              )}

              <div className="mx-auto flex w-full max-w-2xl items-end gap-2 rounded-full border border-slate-200 bg-white p-1.5 shadow-sm">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={sending || loadingMessages || preparingUpload || generatingImage}
                  className="h-10 rounded-full border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Attach
                </button>
                <button
                  type="button"
                  onClick={() => setShowImagePrompt((v) => !v)}
                  disabled={sending || loadingMessages || generatingImage}
                  title="Generate image with AI"
                  className="h-10 rounded-full border border-slate-200 px-3 text-sm font-medium text-slate-700 transition hover:bg-purple-50 hover:border-purple-300 hover:text-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  🖼
                </button>
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
                  disabled={
                    sending
                    || loadingMessages
                    || preparingUpload
                    || generatingImage
                    || pendingAttachments.some((item) => item.uploading)
                    || pendingAttachments.some((item) => Boolean(item.error))
                    || (!input.trim() && pendingAttachments.filter((item) => typeof item.id === "number").length === 0)
                  }
                  className="h-10 rounded-full bg-blue-600 px-5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {sending
                    ? "Sending..."
                    : preparingUpload || pendingAttachments.some((item) => item.uploading)
                      ? "Uploading..."
                      : "Send"}
                </button>
              </div>

              {showImagePrompt && (
                <div className="mx-auto mt-2 w-full max-w-2xl rounded-2xl border border-purple-200 bg-purple-50 p-3 shadow-sm">
                  <p className="mb-2 text-xs font-semibold text-purple-700">Describe the image you want to generate</p>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={imagePrompt}
                      onChange={(e) => setImagePrompt(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void handleGenerateImage();
                        if (e.key === "Escape") setShowImagePrompt(false);
                      }}
                      placeholder="e.g. A sunset over mountain peaks..."
                      autoFocus
                      className="flex-1 rounded-xl border border-purple-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:ring-2 focus:ring-purple-400"
                    />
                    <button
                      type="button"
                      onClick={() => void handleGenerateImage()}
                      disabled={!imagePrompt.trim() || generatingImage}
                      className="rounded-xl bg-purple-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {generatingImage ? "Generating..." : "Generate"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowImagePrompt(false)}
                      className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {(preparingUpload || pendingAttachments.some((item) => item.uploading)) && (
                <div className="mx-auto mt-2 w-full max-w-2xl px-2 text-xs font-medium text-blue-700">
                  {preparingUpload
                    ? "Preparing upload..."
                    : `Uploading ${pendingAttachments.filter((item) => item.uploading).length} file(s)...`}
                </div>
              )}
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
      attachments: item.attachments ?? [],
    });
    mapped.push({
      id: `b-${item.id}`,
      text: item.response,
      sender: "bot",
    });
  }

  return mapped;
}

function AttachmentPreview({
  attachment,
  compact = false,
}: {
  attachment: AttachmentItem;
  compact?: boolean;
}) {
  const source = attachmentContentUrl(attachment.id);

  if (attachment.file_type === "image") {
    return (
      <img
        src={source}
        alt={attachment.original_filename}
        className={`rounded-lg border border-white/30 object-cover ${compact ? "max-h-44" : "max-h-56"}`}
      />
    );
  }

  if (attachment.file_type === "video") {
    return (
      <video
        src={source}
        controls
        className={`rounded-lg border border-white/30 ${compact ? "max-h-44" : "max-h-56"}`}
      />
    );
  }

  return (
    <a
      href={source}
      target="_blank"
      rel="noreferrer"
      className="inline-flex rounded-lg bg-white/20 px-2 py-1 text-xs font-medium text-inherit underline"
    >
      {attachment.original_filename}
    </a>
  );
}
