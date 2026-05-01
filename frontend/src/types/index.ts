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
