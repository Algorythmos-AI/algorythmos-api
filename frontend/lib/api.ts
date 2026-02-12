/* ============================================================
   Algorythmos — API Client  (Enterprise-grade)
   ---
   Fixed: X-Tenant-ID header, detailed error messages,
   proper auth flow for all request types.
   ============================================================ */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://api.algorythmos.fr/api";

/** Default tenant ID — can be overridden in localStorage */
const DEFAULT_TENANT_ID = "default";

class ApiError extends Error {
    status: number;
    code: string;
    data: unknown;
    constructor(status: number, message: string, code?: string, data?: unknown) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.code = code || "UNKNOWN_ERROR";
        this.data = data;
    }
}

/**
 * Build auth headers for ALL request types.
 * Includes X-API-Key AND X-Tenant-ID (both required by backend).
 */
function getAuthHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};

    if (typeof window !== "undefined") {
        // API Key (required for all authenticated endpoints)
        const apiKey = localStorage.getItem("alg_api_key");
        if (apiKey) {
            headers["X-API-Key"] = apiKey;
        }

        // Bearer token (alternative auth method)
        const token = localStorage.getItem("alg_id_token");
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }

        // Tenant ID (REQUIRED by backend — was missing before!)
        const tenantId = localStorage.getItem("alg_tenant_id") || DEFAULT_TENANT_ID;
        headers["X-Tenant-ID"] = tenantId;
    }

    return headers;
}

/**
 * Parse API error response into a human-readable message.
 */
function parseErrorMessage(status: number, data: unknown): { message: string; code: string } {
    if (data && typeof data === "object") {
        const d = data as Record<string, unknown>;

        // FastAPI structured error: { detail: { code, message } }
        if (d.detail && typeof d.detail === "object") {
            const detail = d.detail as Record<string, unknown>;
            return {
                message: String(detail.message || detail.msg || JSON.stringify(d.detail)),
                code: String(detail.code || "API_ERROR"),
            };
        }
        // FastAPI string detail: { detail: "string" }
        if (typeof d.detail === "string") {
            return { message: d.detail, code: "API_ERROR" };
        }
        // Validation errors: { detail: [{ msg, loc, type }] }
        if (Array.isArray(d.detail)) {
            const msgs = d.detail.map((e: Record<string, unknown>) =>
                `${(e.loc as string[] || []).join(".")}: ${e.msg}`
            ).join("; ");
            return { message: msgs || "Validation error", code: "VALIDATION_ERROR" };
        }
    }

    // Status code based fallback
    const statusMessages: Record<number, string> = {
        400: "Bad request — check your input",
        401: "Unauthorized — please set your API key in Settings → API Keys",
        403: "Forbidden — you don't have access to this resource",
        404: "Not found",
        413: "File too large",
        415: "Unsupported file type — only PDFs are accepted",
        422: "Processing failed — the document could not be parsed",
        429: "Rate limit exceeded — please try again later",
        500: "Internal server error",
        503: "Service unavailable — the API is not configured or down",
    };

    return {
        message: statusMessages[status] || `Request failed with status ${status}`,
        code: "HTTP_ERROR",
    };
}

/**
 * Core request function with proper auth and error handling.
 */
async function request<T>(
    path: string,
    options: RequestInit = {}
): Promise<T> {
    const url = `${API_BASE}${path}`;
    const authHeaders = getAuthHeaders();
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...authHeaders,
        ...(options.headers as Record<string, string> || {}),
    };

    const res = await fetch(url, {
        ...options,
        headers,
    });

    if (!res.ok) {
        let data: unknown;
        try {
            data = await res.json();
        } catch {
            try {
                data = await res.text();
            } catch {
                data = null;
            }
        }
        const { message, code } = parseErrorMessage(res.status, data);
        throw new ApiError(res.status, message, code, data);
    }

    // 204 No Content
    if (res.status === 204) return undefined as T;

    return res.json();
}

/**
 * Multipart (FormData) request with proper auth headers.
 * Does NOT set Content-Type (browser sets it with boundary).
 */
async function multipartRequest<T>(
    path: string,
    formData: FormData,
    method = "POST"
): Promise<T> {
    const url = `${API_BASE}${path}`;
    const authHeaders = getAuthHeaders();
    // Remove Content-Type — browser will set multipart/form-data with boundary
    delete authHeaders["Content-Type"];

    const res = await fetch(url, {
        method,
        headers: authHeaders,
        body: formData,
    });

    if (!res.ok) {
        let data: unknown;
        try {
            data = await res.json();
        } catch {
            try {
                data = await res.text();
            } catch {
                data = null;
            }
        }
        const { message, code } = parseErrorMessage(res.status, data);
        throw new ApiError(res.status, message, code, data);
    }

    if (res.status === 204) return undefined as T;
    return res.json();
}

// ---------- Health ----------
export const health = {
    check: () => request<{ status: string }>("/alg/healthz"),
    version: () => request<{ version: string; environment: string }>("/version"),
};

// ---------- Auth ----------
export const auth = {
    createApiKey: (name: string) =>
        request<{ id: string; raw_key: string; prefix: string }>("/auth/api-keys", {
            method: "POST",
            body: JSON.stringify({ name }),
        }),
    listApiKeys: () =>
        request<{ items: Array<{ id: string; name: string; prefix: string; is_active: boolean; created_at: string; last_used_at: string | null }> }>(
            "/auth/api-keys"
        ),
    revokeApiKey: (id: string) =>
        request<void>(`/auth/api-keys/${id}`, { method: "DELETE" }),
};

// ---------- Schemas ----------
export const schemas = {
    list: (limit = 20, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/schemas?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/schemas/${id}`),
    create: (data: unknown) =>
        request<unknown>("/schemas", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/schemas/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/schemas/${id}`, { method: "DELETE" }),
};

// ---------- Extractors ----------
export const extractors = {
    list: (limit = 20, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/extractors?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/extractors/${id}`),
    create: (data: unknown) =>
        request<unknown>("/extractors", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/extractors/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/extractors/${id}`, { method: "DELETE" }),
};

// ---------- Classifiers ----------
export const classifiers = {
    list: (limit = 20, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/classifiers?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/classifiers/${id}`),
    create: (data: unknown) =>
        request<unknown>("/classifiers", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/classifiers/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/classifiers/${id}`, { method: "DELETE" }),
};

// ---------- Splitters ----------
export const splitters = {
    list: (limit = 20, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/splitters?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/splitters/${id}`),
    create: (data: unknown) =>
        request<unknown>("/splitters", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/splitters/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/splitters/${id}`, { method: "DELETE" }),
};

// ---------- Files ----------
export const files = {
    list: (limit = 50, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/files?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/files/${id}`),
    upload: async (file: File, metadata?: Record<string, unknown>) => {
        const formData = new FormData();
        formData.append("file", file);
        if (metadata) formData.append("metadata", JSON.stringify(metadata));
        return multipartRequest<unknown>("/files", formData);
    },
    delete: (id: string) =>
        request<void>(`/files/${id}`, { method: "DELETE" }),
};

// ---------- Processor Runs ----------
export const processorRuns = {
    list: (processorName: string, limit = 20, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/processors/${processorName}/runs?limit=${limit}&offset=${offset}`
        ),
    get: (processorName: string, runId: string) =>
        request<unknown>(`/processors/${processorName}/runs/${runId}`),
    create: async (processorName: string, pdfFiles: File[], providerHint?: string) => {
        const formData = new FormData();
        pdfFiles.forEach((f) => formData.append("files", f));
        if (providerHint) formData.append("provider_hint", providerHint);
        return multipartRequest<unknown>(`/processors/${processorName}/runs`, formData);
    },
};

// ---------- Extract (core feature) ----------
export const extract = {
    upload: async (pdfFiles: File[], providerHint?: string, debug = false) => {
        const formData = new FormData();
        pdfFiles.forEach((f) => formData.append("files", f));

        const params = new URLSearchParams();
        if (providerHint) params.set("provider_hint", providerHint);
        if (debug) params.set("debug", "true");

        const qs = params.toString();
        return multipartRequest<unknown>(`/extract/upload${qs ? `?${qs}` : ""}`, formData);
    },
};

// ---------- Parse ----------
export const parse = {
    sync: (data: unknown) =>
        request<unknown>("/parse", { method: "POST", body: JSON.stringify(data) }),
    async: (data: unknown) =>
        request<unknown>("/parse/async", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    getRun: (runId: string) => request<unknown>(`/parse/runs/${runId}`),
    listRuns: (limit = 20, offset = 0) =>
        request<{ items: unknown[]; total: number }>(
            `/parse/runs?limit=${limit}&offset=${offset}`
        ),
};

// ---------- Workflows ----------
export const workflows = {
    list: (limit = 50, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/workflows?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/workflows/${id}`),
    create: (data: unknown) =>
        request<unknown>("/workflows", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/workflows/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/workflows/${id}`, { method: "DELETE" }),
    execute: (id: string, data?: unknown) =>
        request<unknown>(`/workflows/${id}/execute`, {
            method: "POST",
            body: data ? JSON.stringify(data) : undefined,
        }),
};

// ---------- Evaluation Sets ----------
export const evaluationSets = {
    list: (limit = 50, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/evaluation-sets?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/evaluation-sets/${id}`),
    create: (data: unknown) =>
        request<unknown>("/evaluation-sets", {
            method: "POST",
            body: JSON.stringify(data),
        }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/evaluation-sets/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/evaluation-sets/${id}`, { method: "DELETE" }),
    run: (id: string) =>
        request<unknown>(`/evaluation-sets/${id}/run`, { method: "POST" }),
};

// ---------- LLM ----------
export const llm = {
    summarize: (text: string, maxLength = 500, style = "concise") =>
        request<{ summary: string }>("/llm/summarize", {
            method: "POST",
            body: JSON.stringify({ text, max_length: maxLength, style }),
        }),
    extractEntities: (text: string, entityTypes?: string[]) =>
        request<{ entities: Array<{ text: string; type: string; confidence: number }> }>(
            "/llm/entities",
            { method: "POST", body: JSON.stringify({ text, entity_types: entityTypes }) }
        ),
    answerQuestions: (text: string, questions: string[]) =>
        request<{ answers: Array<{ question: string; answer: string }> }>(
            "/llm/qa",
            { method: "POST", body: JSON.stringify({ text, questions }) }
        ),
};

// ---------- Processors (CRUD) ----------
export const processors = {
    list: (limit = 50, offset = 0) =>
        request<{ items: unknown[]; total: number; has_more: boolean }>(
            `/processors?limit=${limit}&offset=${offset}`
        ),
    get: (id: string) => request<unknown>(`/processors/${id}`),
    create: (data: unknown) =>
        request<unknown>("/processors", { method: "POST", body: JSON.stringify(data) }),
    update: (id: string, data: unknown) =>
        request<unknown>(`/processors/${id}`, {
            method: "PUT",
            body: JSON.stringify(data),
        }),
    delete: (id: string) =>
        request<void>(`/processors/${id}`, { method: "DELETE" }),
};

export { ApiError };
