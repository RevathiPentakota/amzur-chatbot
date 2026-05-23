export interface AuthPayload {
	email: string;
	password: string;
}

export interface AuthResponse {
	message: string;
	user: UserInfo;
}

export interface UserInfo {
	id: number;
	email: string;
}

export interface ChatRequest {
	message: string;
	thread_id: number;
	attachment_ids?: number[];
}

export interface ChatResponse {
	reply: string;
	thread_id: number;
}

export interface ChatHistoryItem {
	id: number;
	thread_id: number;
	message: string;
	response: string;
	created_at: string;
	attachments?: AttachmentItem[];
}

export interface ThreadHistoryResponse {
	messages: ChatHistoryItem[];
	images: ImageGenerateResponse[];
}

export interface AttachmentItem {
	id: number;
	file_id?: number;
	user_id: number;
	thread_id: number;
	original_filename: string;
	filename?: string;
	mime_type: string;
	file_type: "image" | "video" | "table" | "code" | "document";
	file_url?: string;
	created_at: string;
}

export interface ThreadItem {
	id: number;
	user_id: number;
	title: string | null;
	created_at: string;
	updated_at: string;
}

export interface ThreadCreatePayload {
	title?: string | null;
}

export interface ThreadUpdatePayload {
	title: string;
}

export interface ImageGenerateRequest {
	prompt: string;
	thread_id?: number;
}

export interface ImageGenerateResponse {
	id: number;
	image_url: string;
	prompt: string;
	thread_id: number | null;
	created_at: string;
}

export interface RagPdfItem {
	id: number;
	file_id?: number;
	user_id: number;
	thread_id: number;
	filename: string;
	file_type?: string;
	mime_type?: string;
	file_url?: string;
	created_at: string;
}

export interface RagChatRequest {
	thread_id: number;
	question: string;
}

export interface RagChatResponse {
	answer: string;
	thread_id: number;
}

export interface SqlChatRequest {
	question: string;
	thread_id: number;
}

export interface SqlChatResponse {
	sql: string;
	result: Array<Record<string, string | number | boolean | null>>;
	answer: string;
}

export interface DataFrameSourceResponse {
	id: number;
	file_id?: number;
	user_id: number;
	thread_id: number;
	filename: string;
	file_type?: string;
	mime_type?: string;
	file_url?: string;
	file_path: string;
	source_type: string;
	google_sheet_id?: string | null;
	worksheet_name?: string | null;
	created_at: string;
	table_preview: Array<Record<string, string | number | boolean | null>>;
}

export interface GoogleSheetConnectRequest {
	thread_id: number;
	sheet: string;
	worksheet_name?: string;
}

export interface DataFrameChatRequest {
	thread_id: number;
	question: string;
}

export interface DataFrameChatResponse {
	answer: string;
	intermediate_steps: string;
	table_preview: Array<Record<string, string | number | boolean | null>>;
}

// ── Research Digest ──────────────────────────────────────────────────────────

export interface ResearchRequest {
	topic: string;
	thread_id: number;
}

export interface ResearchPaper {
	title: string;
	authors: string[];
	abstract: string;
	published: string;
	url: string;
}

export interface ResearchDigestSection {
	title: string;
	content: string;
}

/** Assembled client-side state for a research digest response */
export interface ResearchDigestMessage {
	status: string;
	papers: ResearchPaper[];
	key_findings?: ResearchDigestSection;
	trends?: ResearchDigestSection;
	contradictions?: ResearchDigestSection;
	final_summary?: ResearchDigestSection;
	sources?: ResearchDigestSection;
	done: boolean;
	error?: string;
}

// ── MCP Agent ───────────────────────────────────────────────────────────────

export interface McpToolInputSchema {
	type: string;
	properties: Record<string, { type: string; description?: string; nullable?: boolean }>;
	required?: string[];
}

export interface McpToolDefinition {
	name: string;
	description: string;
	input_schema: McpToolInputSchema;
	output_schema: Record<string, unknown>;
	requires_thread_id: boolean;
}

export interface McpAgentRequest {
	message: string;
	thread_id?: number;
	file_context?: string;
}

export interface McpAgentResponse {
	answer: string;
	tool_used: string | null;
	tool_input: Record<string, unknown> | null;
	tool_output: Record<string, unknown> | null;
	reasoning: string;
}

export interface McpExecuteRequest {
	tool: string;
	input: Record<string, unknown>;
}

export interface McpExecuteResponse {
	status: string;
	result: Record<string, unknown>;
}

// ── Tic Tac Toe ──────────────────────────────────────────────────────────────

export type TicTacToeCell = "X" | "O" | null;
export type TicTacToeBoard = TicTacToeCell[][];

export interface NewGameResponse {
	game_id: string;
	board: TicTacToeBoard;
	current_turn: string;
}

export interface MakeMoveRequest {
	game_id: string;
	row: number;
	col: number;
}

export interface MakeMoveResponse {
	board: TicTacToeBoard;
	player_move: string;
	ai_move: string | null;
	ai_reasoning: string | null;
	winner: string | null;
	game_over: boolean;
	current_turn: string;
}
