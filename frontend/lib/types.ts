/* ============================================================
   Algorythmos — TypeScript Types (mirrors API schemas)
   ============================================================ */

// ---------- Auth ----------
export interface User {
    id: string;
    email: string;
    name: string;
    picture?: string;
    tenant_id: string;
    role: string;
    created_at: string;
}

export interface ApiKey {
    id: string;
    name: string;
    prefix: string;
    created_at: string;
    last_used_at: string | null;
    is_active: boolean;
}

export interface CreateApiKeyRequest {
    name: string;
}

export interface CreateApiKeyResponse {
    id: string;
    name: string;
    prefix: string;
    raw_key: string;
    created_at: string;
}

// ---------- Health ----------
export interface HealthResponse {
    status: string;
    environment: string;
    database: string;
    redis: string;
    timestamp: string;
}

export interface VersionResponse {
    version: string;
    api_name: string;
    environment: string;
    python_version: string;
}

// ---------- Schemas ----------
export interface FieldDefinition {
    name: string;
    type: "string" | "number" | "date" | "boolean" | "array" | "object";
    description?: string;
    required: boolean;
    default_value?: unknown;
    validation?: Record<string, unknown>;
}

export interface ExtractionSchema {
    schema_id: string;
    name: string;
    description: string;
    fields: FieldDefinition[];
    version: number;
    metadata?: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

export interface CreateSchemaRequest {
    name: string;
    description: string;
    fields: FieldDefinition[];
    metadata?: Record<string, unknown>;
}

export interface UpdateSchemaRequest {
    name?: string;
    description?: string;
    fields?: FieldDefinition[];
    metadata?: Record<string, unknown>;
}

// ---------- Extractors ----------
export interface ExtractorConfig {
    extractor_id: string;
    name: string;
    type: "regex" | "llm" | "template" | "ml" | "rule_based";
    schema_id: string;
    enabled: boolean;
    priority: number;
    rules: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

export interface CreateExtractorRequest {
    name: string;
    type: "regex" | "llm" | "template" | "ml" | "rule_based";
    schema_id: string;
    rules: Record<string, unknown>;
    enabled?: boolean;
    priority?: number;
}

// ---------- Classifiers ----------
export interface ClassifierConfig {
    classifier_id: string;
    name: string;
    type: "keyword" | "ml" | "llm" | "rule_based";
    enabled: boolean;
    categories: string[];
    rules: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

export interface CreateClassifierRequest {
    name: string;
    type: "keyword" | "ml" | "llm" | "rule_based";
    categories: string[];
    rules: Record<string, unknown>;
    enabled?: boolean;
}

// ---------- Splitters ----------
export interface SplitterConfig {
    splitter_id: string;
    name: string;
    type: "page" | "section" | "pattern" | "size";
    enabled: boolean;
    rules: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

export interface CreateSplitterRequest {
    name: string;
    type: "page" | "section" | "pattern" | "size";
    rules: Record<string, unknown>;
    enabled?: boolean;
}

// ---------- Files ----------
export interface FileInfo {
    id: string;
    filename: string;
    content_type: string;
    size_bytes: number;
    storage_path: string;
    status: string;
    metadata?: Record<string, unknown>;
    created_at: string;
    updated_at: string;
}

// ---------- Processor Runs ----------
export interface ProcessorRun {
    id: string;
    processor_name: string;
    status: "queued" | "processing" | "succeeded" | "failed" | "cancelled";
    input_path?: string;
    file_count: number;
    progress: number;
    result?: Record<string, unknown>;
    error?: string;
    processing_time_ms?: number;
    created_at: string;
    updated_at: string;
}

// ---------- Workflows ----------
export interface Workflow {
    id: string;
    name: string;
    description: string;
    steps: WorkflowStep[];
    enabled: boolean;
    created_at: string;
    updated_at: string;
}

export interface WorkflowStep {
    step_id: string;
    processor_id: string;
    name: string;
    order: number;
    config?: Record<string, unknown>;
}

export interface CreateWorkflowRequest {
    name: string;
    description: string;
    steps: Omit<WorkflowStep, "step_id">[];
    enabled?: boolean;
}

// ---------- Evaluation Sets ----------
export interface EvaluationSet {
    id: string;
    name: string;
    description: string;
    target_type: string;
    target_id: string;
    item_count: number;
    created_at: string;
    updated_at: string;
}

export interface CreateEvaluationSetRequest {
    name: string;
    description: string;
    target_type: string;
    target_id: string;
    items?: EvalItem[];
}

export interface EvalItem {
    id: string;
    input_data: Record<string, unknown>;
    expected_output: Record<string, unknown>;
}

// ---------- Parser Runs ----------
export interface ParserRun {
    id: string;
    status: "pending" | "running" | "completed" | "failed";
    file_id?: string;
    output_format: string;
    result?: Record<string, unknown>;
    error?: string;
    processing_time_ms?: number;
    created_at: string;
    updated_at: string;
}

// ---------- Background Jobs ----------
export interface Job {
    job_id: string;
    status: "pending" | "running" | "completed" | "failed";
    input_path: string;
    result?: Record<string, unknown>;
    error?: string;
    webhook_url?: string;
    created_at: string;
}

// ---------- Paginated Response ----------
export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    limit: number;
    offset?: number;
    cursor?: string;
    has_more: boolean;
}

// ---------- LLM ----------
export interface LLMSummaryResponse {
    summary: string;
    word_count: number;
    processing_time_ms: number;
}

export interface LLMEntitiesResponse {
    entities: Array<{
        text: string;
        type: string;
        confidence: number;
    }>;
    processing_time_ms: number;
}

export interface LLMQAResponse {
    answers: Array<{
        question: string;
        answer: string;
        confidence: number;
    }>;
    processing_time_ms: number;
}
