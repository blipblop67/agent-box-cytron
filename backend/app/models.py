from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    visibility: str = Field(default="shared", pattern="^(shared|private)$")


class KnowledgeBaseOut(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    visibility: str
    created_at: float
    document_count: int = 0


class DocumentOut(BaseModel):
    id: str
    kb_id: str
    filename: str
    content_type: str | None
    size_bytes: int | None
    status: str
    error_message: str | None
    chunk_count: int
    uploaded_by: str
    created_at: float


class QueryRequest(BaseModel):
    query: str
    top_k: int | None = None


class ChunkResult(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    text: str
    score: float


class QueryResponse(BaseModel):
    kb_id: str
    query: str
    results: list[ChunkResult]


class DriveFileOut(BaseModel):
    id: str
    name: str
    mimeType: str
    modifiedTime: str | None = None
    size: str | None = None
    webViewLink: str | None = None


class DriveFileContent(BaseModel):
    name: str
    mime_type: str
    content: str


class DriveFileCreate(BaseModel):
    name: str
    content: str
    mime_type: str = "text/plain"
    folder_id: str | None = None


class DriveFileUpdate(BaseModel):
    content: str
    mime_type: str = "text/plain"


class FlowNode(BaseModel):
    id: str
    type: str
    position: dict
    data: dict = {}


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str


class FlowGraph(BaseModel):
    nodes: list[FlowNode] = []
    edges: list[FlowEdge] = []


class FlowCreate(BaseModel):
    name: str
    description: str = ""
    visibility: str = Field(default="shared", pattern="^(shared|private)$")


class FlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    visibility: str | None = Field(default=None, pattern="^(shared|private)$")
    graph: FlowGraph | None = None


class FlowOut(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    visibility: str
    graph: FlowGraph
    published: bool
    created_at: float
    updated_at: float


class FlowSummaryOut(BaseModel):
    id: str
    name: str
    description: str
    owner_id: str
    visibility: str
    node_count: int
    created_at: float
    updated_at: float


class FlowRunRequest(BaseModel):
    input: str = ""


class FlowRunTraceStep(BaseModel):
    node_id: str
    type: str
    input: str
    output: str | None
    error: str | None


class FlowRunResponse(BaseModel):
    output: str
    trace: list[FlowRunTraceStep]


class FlowPublishResponse(BaseModel):
    api_key: str
    run_url: str


class SettingsOut(BaseModel):
    llm_provider: str
    openrouter_model: str
    openrouter_key_configured: bool
    ollama_base_url: str
    ollama_model: str
    google_client_id: str
    google_client_secret_configured: bool
    google_email_redirect_uri: str
    google_drive_redirect_uri: str
    google_calendar_redirect_uri: str
    google_sheets_redirect_uri: str
    google_oauth_redirect_warning: str | None
    google_service_account_configured: bool
    google_service_account_email: str
    web_search_key_configured: bool
    youtube_key_configured: bool
    smtp_host: str
    smtp_port: str
    smtp_username: str
    smtp_from_address: str
    smtp_use_tls: bool
    smtp_password_configured: bool
    duckdns_subdomain: str
    duckdns_token_configured: bool
    duckdns_configured: bool
    duckdns_last_updated_ip: str
    duckdns_last_updated_at: float | None
    duckdns_last_error: str
    smtp_configured: bool


class SettingsUpdate(BaseModel):
    llm_provider: str | None = Field(default=None, pattern="^(openrouter|ollama)$")
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    web_search_api_key: str | None = None
    youtube_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str | None = None
    smtp_use_tls: bool | None = None
    google_service_account_key: str | None = None
    duckdns_subdomain: str | None = None
    duckdns_token: str | None = None


class TestImpersonationRequest(BaseModel):
    impersonate: str
    scope: str = "gmail"  # "gmail" | "sheets" | "drive" | "calendar"


class ScheduleCreate(BaseModel):
    trigger_type: str = Field(pattern="^(interval|daily)$")
    interval_minutes: int | None = None
    daily_time: str | None = None  # "HH:MM", 24-hour
    input_text: str = ""


class ScheduleUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None
    daily_time: str | None = None
    input_text: str | None = None


class ScheduleOut(BaseModel):
    id: str
    flow_id: str
    trigger_type: str
    interval_minutes: int | None
    daily_time: str | None
    input_text: str
    enabled: bool
    created_by: str
    created_at: float
    last_run_at: float | None
    last_run_status: str | None


class ScheduleRunOut(BaseModel):
    id: str
    schedule_id: str
    flow_id: str
    started_at: float
    status: str
    output: str | None
    error_message: str | None


class TemplateSummary(BaseModel):
    id: str
    name: str
    description: str
    node_count: int


class TemplateUse(BaseModel):
    name: str | None = None


class TelegramBotCreate(BaseModel):
    name: str
    bot_token: str
    visibility: str = Field(default="shared", pattern="^(shared|private)$")


class TelegramBotUpdate(BaseModel):
    name: str | None = None
    visibility: str | None = Field(default=None, pattern="^(shared|private)$")


class TelegramBotOut(BaseModel):
    id: str
    name: str
    owner_id: str
    visibility: str
    bot_username: str | None
    chat_linked: bool
    created_at: float


class TelegramSendRequest(BaseModel):
    text: str


class TelegramTriggerCreate(BaseModel):
    bot_id: str


class TelegramTriggerUpdate(BaseModel):
    enabled: bool


class TelegramTriggerOut(BaseModel):
    id: str
    flow_id: str
    bot_id: str
    bot_name: str
    conversation_id: str
    enabled: bool
    created_by: str
    created_at: float


class TelegramTriggerRunOut(BaseModel):
    id: str
    incoming_text: str
    reply_text: str | None
    status: str
    error_message: str | None
    started_at: float


class UpdateConfigRequest(BaseModel):
    repo: str
    branch: str = "main"


class UpdateStatus(BaseModel):
    repo: str
    branch: str
    current_version: str
    latest_version: str | None = None
    update_available: bool | None = None
    latest_message: str | None = None
    latest_date: str | None = None
    configured: bool
    error: str | None = None


class UpdateApplyResult(BaseModel):
    updated_to: str
    auto_restarting: bool


class AuthRequest(BaseModel):
    name: str
    password: str


class AuthUser(BaseModel):
    id: str
    name: str
    role: str
    email: str | None = None


class AuthResponse(BaseModel):
    token: str
    user: AuthUser


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    name: str


class TestEmailRequest(BaseModel):
    to_address: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UpdateEmailRequest(BaseModel):
    email: str | None = None


class AdminPasswordResetRequest(BaseModel):
    new_password: str


class PersonalSettingsOut(BaseModel):
    google_client_id: str
    google_client_secret_configured: bool
    google_email_redirect_uri: str
    google_drive_redirect_uri: str
    google_calendar_redirect_uri: str
    google_sheets_redirect_uri: str
    google_oauth_redirect_warning: str | None
    openrouter_model: str
    openrouter_key_configured: bool
    web_search_key_configured: bool
    youtube_key_configured: bool


class PersonalSettingsUpdate(BaseModel):
    google_client_id: str | None = None
    google_client_secret: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    web_search_api_key: str | None = None
    youtube_api_key: str | None = None


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ConversationOut(BaseModel):
    id: str
    flow_id: str
    title: str
    created_at: float
    updated_at: float


class ConversationMessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: float


class ConversationDetailOut(ConversationOut):
    messages: list[ConversationMessageOut]


class ConversationSendMessage(BaseModel):
    content: str


class ConversationSendResponse(BaseModel):
    user_message: ConversationMessageOut
    assistant_message: ConversationMessageOut
    trace: list[FlowRunTraceStep]


class ExtractedTextOut(BaseModel):
    filename: str
    content: str
