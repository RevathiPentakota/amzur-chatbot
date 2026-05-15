import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import {
  attachmentContentUrl,
  createThread,
  generateImage,
  generatedImageUrl,
  getMessagesByThread,
  listThreadRagPdfs,
  ragChat,
  ragPdfContentUrl,
  getThreads,
  logoutUser,
  removeThread,
  renameThread,
  sendMessage,
  sqlChat,
  uploadRagPdf,
  uploadAttachment,
} from "../lib/api";

import type {
  AttachmentItem,
  ChatHistoryItem,
  RagPdfItem,
  ThreadItem,
  ImageGenerateResponse,
  SqlChatResponse,
} from "../types";

interface Message {
  id: string;
  text: string;
  sender: "user" | "bot";
  attachments?: AttachmentItem[];
  generatedImageId?: number;
  generatedImagePrompt?: string;
  sqlQuery?: string;
  sqlResult?: SqlChatResponse["result"];
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
  const [ragPdfs, setRagPdfs] = useState<RagPdfItem[]>([]);
  const [ragUploading, setRagUploading] = useState(false);
  const [ragUploadProgress, setRagUploadProgress] = useState(0);
  const [usePdfRag, setUsePdfRag] = useState(false);
  const [chatMode, setChatMode] = useState<"chat" | "sql">("chat");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pdfInputRef = useRef<HTMLInputElement | null>(null);

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
        const response = await getMessagesByThread(selectedThreadId);
        setMessages(mapHistoryToMessages(response.messages, response.images));
        const pdfs = await listThreadRagPdfs(selectedThreadId);
        setRagPdfs(pdfs);
        setUsePdfRag(pdfs.length > 0);
      } catch {
        setMessages([]);
        setRagPdfs([]);
        setUsePdfRag(false);
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
    const isSqlMode = chatMode === "sql";
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

    if ((isSqlMode && !hasText) || (!isSqlMode && !hasText && readyAttachments.length === 0) || uploading || hasUploadErrors) {
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
      if (isSqlMode) {
        const sqlResponse = await sqlChat({ question: content, thread_id: threadId });
        const botMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: sqlResponse.answer,
          sender: "bot",
          sqlQuery: sqlResponse.sql,
          sqlResult: sqlResponse.result,
        };
        setMessages((prev) => [...prev, botMessage]);
        const updatedThreads = await getThreads();
        setThreads(updatedThreads);
        return;
      }

      const useRagPath = usePdfRag && ragPdfs.length > 0 && readyAttachments.length === 0 && Boolean(content);
      if (useRagPath) {
        const response = await ragChat({ thread_id: threadId, question: content });
        const botMessage: Message = {
          id: (Date.now() + 1).toString(),
          text: response.answer,
          sender: "bot",
        };
        setMessages((prev) => [...prev, botMessage]);
      } else {
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
      }
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

  const handleSelectRagPdf = async (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }

    const file = files[0];
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          text: "Only PDF files are supported for RAG upload.",
          sender: "bot",
        },
      ]);
      return;
    }

    let threadId = selectedThreadId;
    if (!threadId) {
      const created = await createThread();
      setThreads((prev) => [created, ...prev]);
      setSelectedThreadId(created.id);
      threadId = created.id;
    }

    setRagUploading(true);
    setRagUploadProgress(0);
    try {
      const uploaded = await uploadRagPdf(file, threadId, (progress) => setRagUploadProgress(progress));
      setRagPdfs((prev) => [...prev, uploaded]);
      setUsePdfRag(true);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          text: `PDF uploaded and indexed: ${uploaded.filename}. Ask your questions in PDF mode.`,
          sender: "bot",
        },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          text: error instanceof Error ? error.message : "PDF upload failed.",
          sender: "bot",
        },
      ]);
    } finally {
      setRagUploading(false);
      setRagUploadProgress(0);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <div className="flex h-full w-full overflow-hidden">
        <div className="flex h-full w-full">
          <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
            <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-3">
              <span className="text-[13px] font-semibold tracking-wide text-slate-500 uppercase">Threads</span>
              <button
                onClick={() => {
                  void handleCreateThread();
                }}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-700"
              >
                + New
              </button>
            </div>

            <div className="flex-1 space-y-0.5 overflow-y-auto px-2 py-2">
              {loadingThreads && <p className="text-sm text-slate-500">Loading threads...</p>}

              {!loadingThreads && threads.length === 0 && (
                <p className="text-sm text-slate-500">No threads yet. Create one to start chatting.</p>
              )}

              {threads.map((thread) => (
                <div
                  key={thread.id}
                  className={`group flex items-center justify-between rounded-lg px-3 py-2 transition-colors ${
                    selectedThreadId === thread.id
                      ? "bg-blue-50 text-blue-700"
                      : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  <button
                    onClick={() => setSelectedThreadId(thread.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className={`truncate text-[13px] font-medium ${
                      selectedThreadId === thread.id ? "text-blue-700" : "text-slate-700"
                    }`}>
                      {thread.title ?? "Untitled thread"}
                    </p>
                  </button>
                  <div className="ml-1 flex shrink-0 gap-1 opacity-0 transition group-hover:opacity-100">
                    <button
                      onClick={() => {
                        void handleRenameThread(thread);
                      }}
                      className="rounded p-1 text-xs text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                      title="Rename"
                    >
                      ✎
                    </button>
                    <button
                      onClick={() => {
                        void handleDeleteThread(thread);
                      }}
                      className="rounded p-1 text-xs text-slate-400 hover:bg-red-50 hover:text-red-600"
                      title="Delete"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="shrink-0 border-t border-slate-100 p-3">
              <button
                onClick={() => {
                  void handleLogout();
                }}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] font-medium text-slate-600 transition hover:bg-slate-100"
              >
                Logout
              </button>
            </div>
          </aside>

          <section className="flex min-w-0 flex-1 flex-col">
            <div className="flex shrink-0 items-center border-b border-slate-200 bg-white px-6 py-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-blue-500"></div>
                <h1 className="truncate text-[14px] font-semibold text-slate-800">
                  {selectedThread?.title ?? "amzur chatbot"}
                </h1>
              </div>
              <div className="ml-4 inline-flex rounded-full border border-slate-200 bg-slate-50 p-0.5">
                <button
                  type="button"
                  onClick={() => setChatMode("chat")}
                  className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                    chatMode === "chat" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  Chat
                </button>
                <button
                  type="button"
                  onClick={() => setChatMode("sql")}
                  className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                    chatMode === "sql" ? "bg-blue-600 text-white" : "text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  Database Chat
                </button>
              </div>
              {usePdfRag && ragPdfs.length > 0 && (
                <span className="ml-3 rounded-full bg-indigo-100 px-2 py-0.5 text-[11px] font-medium text-indigo-700">PDF QA</span>
              )}
              {chatMode === "sql" && (
                <span className="ml-3 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">Read-only SQL</span>
              )}
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto bg-gray-50 px-4 py-6">
              <div className="mx-auto w-full max-w-3xl space-y-4 pb-4">
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
                      className={`max-w-[78%] min-w-0 rounded-2xl px-5 py-3 text-[14px] leading-relaxed shadow-sm ${
                        msg.sender === "user"
                          ? "bg-blue-600 text-white"
                          : "border border-slate-200 bg-white text-slate-800"
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
                          <p className="text-xs text-slate-400 italic">Generated: {msg.generatedImagePrompt}</p>
                          <img
                            src={generatedImageUrl(msg.generatedImageId)}
                            alt={msg.generatedImagePrompt}
                            className="max-h-80 rounded-xl border border-slate-200 object-contain"
                          />
                        </div>
                      ) : msg.sqlQuery ? (
                        <div className="space-y-3">
                          <div>
                            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Generated SQL</p>
                            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
                              <code>{msg.sqlQuery}</code>
                            </pre>
                          </div>
                          <SqlResultTable rows={msg.sqlResult ?? []} />
                          <div>
                            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Explanation</p>
                            <p className="whitespace-pre-wrap text-sm text-slate-800">{msg.text}</p>
                          </div>
                        </div>
                      ) : (
                        <div className="prose prose-sm max-w-none text-slate-800
                          prose-p:my-1 prose-p:leading-relaxed
                          prose-ul:my-1 prose-ul:pl-4
                          prose-ol:my-1 prose-ol:pl-4
                          prose-li:my-0.5
                          prose-strong:font-semibold prose-strong:text-slate-900
                          prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-xs prose-code:text-slate-700
                          prose-pre:my-2 prose-pre:overflow-x-auto prose-pre:rounded-xl prose-pre:bg-slate-800 prose-pre:p-4 prose-pre:text-xs prose-pre:text-slate-100
                          prose-headings:my-2 prose-headings:font-semibold prose-headings:text-slate-900
                          prose-blockquote:border-l-2 prose-blockquote:border-slate-300 prose-blockquote:pl-3 prose-blockquote:italic prose-blockquote:text-slate-600
                        ">
                          <ReactMarkdown>{msg.text}</ReactMarkdown>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {sending && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-[13px] italic text-slate-400 shadow-sm">
                      thinking…
                    </div>
                  </div>
                )}

                {generatingImage && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-[13px] italic text-slate-400 shadow-sm">
                      Generating image…
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
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
              <input
                ref={pdfInputRef}
                type="file"
                className="hidden"
                accept="application/pdf,.pdf"
                onChange={(e) => {
                  void handleSelectRagPdf(e.target.files);
                  e.currentTarget.value = "";
                }}
              />

              {ragPdfs.length > 0 && (
                <div className="mx-auto mb-2 w-full max-w-3xl rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-semibold uppercase tracking-wide text-indigo-500">PDFs:</span>
                    {ragPdfs.map((pdf) => (
                      <a
                        key={pdf.id}
                        href={ragPdfContentUrl(pdf.id)}
                        target="_blank"
                        rel="noreferrer"
                        className="rounded-md bg-white px-2 py-0.5 text-xs font-medium text-indigo-700 shadow-sm hover:bg-indigo-100"
                      >
                        {pdf.filename}
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {pendingAttachments.length > 0 && (
                <div className="mx-auto mb-2 w-full max-w-3xl space-y-1.5">
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
                <div className="mx-auto mb-2 w-full max-w-3xl rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  One or more attachments failed. Remove failed files and try again.
                </div>
              )}

              <div className="mx-auto flex w-full max-w-3xl items-end gap-1.5 rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-sm focus-within:border-blue-400 focus-within:ring-1 focus-within:ring-blue-100">
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={chatMode === "sql" || sending || loadingMessages || preparingUpload || generatingImage || ragUploading}
                    title="Attach file"
                    className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                      <path fillRule="evenodd" d="M15.621 4.379a3 3 0 0 0-4.242 0l-7 7a1.5 1.5 0 0 0 2.122 2.121l7-7a.5.5 0 0 1 .707.708l-7 7a2.5 2.5 0 0 1-3.536-3.536l7-7a4.5 4.5 0 0 1 6.364 6.364l-7 7a6.5 6.5 0 0 1-9.192-9.192l7-7a.75.75 0 0 1 1.06 1.061l-7 7A5 5 0 0 0 11 17.5l7-7a3 3 0 0 0 0-4.243Z" clipRule="evenodd" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    onClick={() => pdfInputRef.current?.click()}
                    disabled={chatMode === "sql" || sending || loadingMessages || ragUploading || generatingImage}
                    title="Upload PDF for RAG"
                    className="rounded-lg px-2 py-1.5 text-[11px] font-semibold text-indigo-500 transition hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    PDF
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowImagePrompt((v) => !v)}
                    disabled={chatMode === "sql" || sending || loadingMessages || generatingImage}
                    title="Generate image with AI"
                    className="rounded-lg p-2 text-slate-400 transition hover:bg-purple-50 hover:text-purple-600 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                      <path fillRule="evenodd" d="M1 5.25A2.25 2.25 0 0 1 3.25 3h13.5A2.25 2.25 0 0 1 19 5.25v9.5A2.25 2.25 0 0 1 16.75 17H3.25A2.25 2.25 0 0 1 1 14.75v-9.5Zm1.5 5.81v3.69c0 .414.336.75.75.75h13.5a.75.75 0 0 0 .75-.75v-2.69l-2.22-2.219a.75.75 0 0 0-1.06 0l-1.91 1.909-.48-.48a.75.75 0 0 0-1.06 0L6.53 11.06l-4.03-4.03v4.03Zm3.5-5.81a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z" clipRule="evenodd" />
                    </svg>
                  </button>
                </div>
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder={chatMode === "sql" ? "Ask a database question in plain English..." : "Message..."}
                  disabled={sending || loadingMessages}
                  rows={1}
                  className="max-h-32 min-h-9 flex-1 resize-none bg-transparent py-1.5 text-[14px] text-slate-800 placeholder-slate-400 outline-none"
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
                    || ragUploading
                    || pendingAttachments.some((item) => item.uploading)
                    || pendingAttachments.some((item) => Boolean(item.error))
                    || (chatMode === "sql"
                      ? !input.trim()
                      : (!input.trim() && pendingAttachments.filter((item) => typeof item.id === "number").length === 0))
                  }
                  className="shrink-0 self-end rounded-xl bg-blue-600 px-4 py-2 text-[13px] font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {sending
                    ? "Sending…"
                    : preparingUpload || pendingAttachments.some((item) => item.uploading)
                      ? "Uploading…"
                      : "Send"}
                </button>
              </div>

              {ragPdfs.length > 0 && (
                <div className="mx-auto mt-2 flex w-full max-w-3xl items-center gap-3 px-1 text-xs">
                  <span className="font-medium text-indigo-600">PDF QA mode</span>
                  <button
                    type="button"
                    onClick={() => setUsePdfRag((v) => !v)}
                    className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
                      usePdfRag ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                    }`}
                  >
                    {usePdfRag ? "On" : "Off"}
                  </button>
                </div>
              )}

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
                <div className="mx-auto mt-1.5 w-full max-w-3xl px-1 text-xs font-medium text-blue-600">
                  {preparingUpload
                    ? "Preparing upload..."
                    : `Uploading ${pendingAttachments.filter((item) => item.uploading).length} file(s)...`}
                </div>
              )}

              {ragUploading && (
                <div className="mx-auto mt-1.5 w-full max-w-3xl px-1 text-xs font-medium text-indigo-600">
                  Processing PDF... {ragUploadProgress}%
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function mapHistoryToMessages(
  history: ChatHistoryItem[],
  images: ImageGenerateResponse[] = []
): Message[] {
  const mapped: Message[] = [];

  // Combine messages and images into a single chronological array
  const allItems: Array<{ type: "message" | "image"; item: ChatHistoryItem | ImageGenerateResponse; date: Date }> = [];

  for (const item of history) {
    allItems.push({
      type: "message",
      item,
      date: new Date(item.created_at),
    });
  }

  for (const image of images) {
    allItems.push({
      type: "image",
      item: image,
      date: new Date(image.created_at),
    });
  }

  // Sort by date (ascending, oldest first)
  allItems.sort((a, b) => a.date.getTime() - b.date.getTime());

  // Convert to Message array
  for (const entry of allItems) {
    if (entry.type === "message") {
      const msg = entry.item as ChatHistoryItem;
      mapped.push({
        id: `u-${msg.id}`,
        text: msg.message,
        sender: "user",
        attachments: msg.attachments ?? [],
      });
      mapped.push({
        id: `b-${msg.id}`,
        text: msg.response,
        sender: "bot",
      });
    } else {
      const img = entry.item as ImageGenerateResponse;
      mapped.push({
        id: `img-${img.id}`,
        text: `[Generated Image: ${img.prompt}]`,
        sender: "bot",
        generatedImageId: img.id,
        generatedImagePrompt: img.prompt,
      });
    }
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

function SqlResultTable({ rows }: { rows: Array<Record<string, string | number | boolean | null>> }) {
  if (!rows.length) {
    return <p className="text-xs text-slate-500">No rows returned.</p>;
  }

  const columns = Object.keys(rows[0]);

  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Results</p>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              {columns.map((column) => (
                <th key={column} className="px-3 py-2 font-semibold">{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`sql-row-${index}`} className="border-t border-slate-100">
                {columns.map((column) => (
                  <td key={`${index}-${column}`} className="px-3 py-2 text-slate-800">
                    {row[column] === null ? "NULL" : String(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
