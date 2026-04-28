"""Pydantic request models used by web routes."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ...constants import LLM_DEFAULTS, WRITING_CONFIG


class CreateNovelRequest(BaseModel):
    novel_type: str = ""
    theme: str = ""
    requirements: str = ""
    protagonist: str = ""
    plot_idea: str = ""
    volume_count: int = 1
    chapters_per_volume: int = 5
    session_id: str = Field(default="", pattern=r"^[A-Za-z0-9_-]{0,64}$")


class ConfirmCreationContractRequest(BaseModel):
    contract_id: str = ""
    approved: bool = True
    session_id: str = Field(default="", pattern=r"^[A-Za-z0-9_-]{0,64}$")
    contract_payload: Dict[str, Any] = Field(default_factory=dict)


class GenerateWorldRequest(BaseModel):
    novel_type: str = ""
    theme: str = ""
    requirements: str = ""


class GenerateOutlineRequest(BaseModel):
    protagonist: str = ""
    plot_idea: str = ""
    volume_count: int = 1
    chapters_per_volume: int = 10


class WriteChapterRequest(BaseModel):
    chapter_number: int = 1
    chapter_index: int = 0
    chapter_outline: str = ""
    chapter_title: str = ""
    existing_content: str = ""
    action: str = "write"
    word_count: int = WRITING_CONFIG.CONTINUE_DEFAULT_WORDS
    enable_trends: bool = False
    trends_platforms: List[str] = Field(default_factory=list)
    trends_query: str = ""


class APIConfigRequest(BaseModel):
    api_base: str
    api_key: str
    model: str = ""


class FetchModelsRequest(BaseModel):
    api_base: str
    api_key: str
    config_id: str = ""


class TestConnectionRequest(BaseModel):
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    config_id: str = ""


class GlobalAPIConfigRequest(BaseModel):
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS


class ShortStoryTimeoutSettingsRequest(BaseModel):
    synopsis: Optional[int] = None
    outline: Optional[int] = None
    chapter: Optional[int] = None
    quality: Optional[int] = None
    coherence: Optional[int] = None
    title: Optional[int] = None
    tags: Optional[int] = None


class LLMTimeoutSettingsRequest(BaseModel):
    connect: Optional[int] = None
    read: Optional[int] = None
    write: Optional[int] = None
    pool: Optional[int] = None


class TimeoutSettingsRequest(BaseModel):
    llm: Optional[LLMTimeoutSettingsRequest] = None
    short_story: Optional[ShortStoryTimeoutSettingsRequest] = None


class AddAPIConfigRequest(BaseModel):
    name: str
    api_base: str
    api_key: str
    models: List[str] = Field(default_factory=list)
    temperature: float = LLM_DEFAULTS.TEMPERATURE
    max_tokens: int = LLM_DEFAULTS.MAX_TOKENS


class UpdateAPIConfigRequest(BaseModel):
    name: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    models: Optional[List[str]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class SetActiveConfigRequest(BaseModel):
    config_id: str
    model: str = ""


class AddModelRequest(BaseModel):
    model: str


class AgentConfigUpdateRequest(BaseModel):
    api_config_id: Optional[str] = None
    api_base: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    use_global: Optional[bool] = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")


class UserInputRequest(BaseModel):
    request_id: str
    user_input: str


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectStateBatchGetRequest(BaseModel):
    keys: List[str] = Field(default_factory=list)


class ProjectStateBatchSetRequest(BaseModel):
    states: Dict[str, Any] = Field(default_factory=dict)


class NovelToScriptSourceChapterRequest(BaseModel):
    chapter_number: int = 1
    title: str = ""
    content: str = ""
    word_count: Optional[int] = None


class NovelToScriptConfigRequest(BaseModel):
    script_style: str = "scene_block_webnovel_script"
    convert_mode: str = "auto"
    scene_density: str = "medium"
    dialogue_ratio: str = "medium"
    keep_voice_style: bool = True
    human_name_strategy: str = "keep_original"


class NovelToScriptConvertRequest(BaseModel):
    source_type: str = "paste"
    source_filename: str = ""
    source_text: str = ""
    source_chapters: List[NovelToScriptSourceChapterRequest] = Field(default_factory=list)
    config: NovelToScriptConfigRequest = Field(default_factory=NovelToScriptConfigRequest)
    api_config_id: str = ""
    model: str = ""
    title: str = ""


class NovelToScriptStateRequest(BaseModel):
    data: Any = None


class NovelToScriptExportRequest(BaseModel):
    title: str = ""
    result: Dict[str, Any] = Field(default_factory=dict)


class NovelToScriptBatchReconvertRequest(BaseModel):
    source_type: str = "paste"
    source_filename: str = ""
    source_text: str = ""
    source_chapters: List[NovelToScriptSourceChapterRequest] = Field(default_factory=list)
    config: NovelToScriptConfigRequest = Field(default_factory=NovelToScriptConfigRequest)
    api_config_id: str = ""
    model: str = ""
    batch_number: int = 1
    existing_batches: List[Dict[str, Any]] = Field(default_factory=list)


class KnowledgeBaseConfigRequest(BaseModel):
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "BAAI/bge-m3"
    siliconflow_embedding_dim: int = 1024
    chunk_size: int = 500
    chunk_overlap: int = 50
    vector_weight: float = 0.7
    fulltext_weight: float = 0.3
    default_top_k: int = 5
    summary_search_enabled: bool = False
    chapter_search_mode: str = "hybrid"


class TestEmbeddingRequest(BaseModel):
    api_base: str = ""
    api_key: str = ""
    model: str = ""


class ImportFileRequest(BaseModel):
    content: str
    filename: str
    category_id: str
    category_key: str = ""
    title: str = ""
    split_mode: str = "auto"


class CreateCategoryRequest(BaseModel):
    name: str
    icon: str = "ri-folder-line"


class ClearKnowledgeBaseRequest(BaseModel):
    clear_all: bool = False
    chapter_ids: List[str] = Field(default_factory=list)


class AuxMemoryCategoryCreateRequest(BaseModel):
    name: str
    description: str = ""
    summary: str = ""
    enabled: bool = True
    user_id: str = ""


class AuxMemoryCategoryUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    enabled: Optional[bool] = None
    user_id: Optional[str] = None


class AuxMemoryItemCreateRequest(BaseModel):
    category_id: str = ""
    summary: str
    details: str = ""
    memory_type: str = "preference"
    score: float = 0.5
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)
    user_id: str = ""
    source_resource_id: str = ""
    extra: Dict[str, Any] = Field(default_factory=dict)


class AuxMemoryItemUpdateRequest(BaseModel):
    category_id: Optional[str] = None
    summary: Optional[str] = None
    details: Optional[str] = None
    memory_type: Optional[str] = None
    score: Optional[float] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None
    user_id: Optional[str] = None
    source_resource_id: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class AuxMemoryItemBatchUpdateRequest(BaseModel):
    item_ids: List[str] = Field(default_factory=list)
    enabled: bool


class AuxMemoryItemBatchDeleteRequest(BaseModel):
    item_ids: List[str] = Field(default_factory=list)


class AuxMemoryItemClearRequest(BaseModel):
    category_id: str = ""
    query: str = ""
    user_id: Optional[str] = None
    enabled_only: bool = False
    memory_type: str = ""


class AuxMemoryRetrieveRequest(BaseModel):
    query: str = ""
    mode: str = "fast"
    top_k: int = 5
    user_id: str = ""
    category_ids: List[str] = Field(default_factory=list)
    where: Dict[str, Any] = Field(default_factory=dict)


class AuxMemoryInjectionPreviewRequest(BaseModel):
    query: str = ""
    mode: str = "fast"
    top_k: int = 5
    user_id: str = ""
    category_ids: List[str] = Field(default_factory=list)
    max_chars: int = 1200
    where: Dict[str, Any] = Field(default_factory=dict)


class AuxMemoryResourceImportRequest(BaseModel):
    content: str
    source_type: str = "manual"
    title: str = ""
    user_id: str = ""
    category_id: str = ""
    min_line_chars: int = 6
    max_items: int = 20
    default_score: float = 0.6


class AuxMemoryRollbackRequest(BaseModel):
    history_id: str


class AuxMemoryTraceRequest(BaseModel):
    item_id: str
    limit: int = 20


class AuxMemoryConfigUpdateRequest(BaseModel):
    injection_enabled: Optional[bool] = None
    injection_mode: Optional[str] = None
    injection_top_k: Optional[int] = None
    injection_max_chars: Optional[int] = None
    auto_classify_enabled: Optional[bool] = None
    auto_summary_enabled: Optional[bool] = None
    auto_summary_top_items: Optional[int] = None


class ContinuousWriteStartRequest(BaseModel):
    story_beginning: str
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    words_per_chapter: int = 2500
    model: str = ""
    api_config_id: str = ""
    enable_trends: bool = False
    trends_platforms: List[str] = Field(default_factory=list)
    trends_query: str = ""
    current_chapter: int = 0
    recovered_chapters: List[dict] = Field(default_factory=list)
    auto_restore: bool = True


class ContinuousWriteContinueRequest(BaseModel):
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    inspiration: str = ""
    model: str = ""
    api_config_id: str = ""
    enable_trends: bool = False
    trends_platforms: List[str] = Field(default_factory=list)


class ContinuousWriteSyncRequest(BaseModel):
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    chapters: List[dict] = Field(default_factory=list)
    current_chapter: int = 0
    deleted_chapters: List[int] = Field(default_factory=list)


class ContinuousWriteRegenerateRequest(BaseModel):
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    chapter_number: int
    inspiration: str = ""
    model: str = ""
    api_config_id: str = ""
    enable_trends: bool = False
    trends_platforms: List[str] = Field(default_factory=list)


class ContinuousWriteInspirationRequest(BaseModel):
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    inspiration: str
    chapter: int = 0


class ContinuousWriteCorrectionRequest(BaseModel):
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    correction: str
    chapter: int = 0


class UpdateInfiniteWriteChapterRequest(BaseModel):
    chapter_index: int
    title: Optional[str] = None
    content: Optional[str] = None


class AddDeadCharacterRequest(BaseModel):
    session_id: str = Field(default="default", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    character_name: str


class RegexReplaceRequest(BaseModel):
    content: str
    pattern: str
    replacement: str
    flags: str = ""


class ContinuousWriteExportRequest(BaseModel):
    title: str = ""
    chapters: List[Dict[str, Any]] = Field(default_factory=list)


class SavePromptRequest(BaseModel):
    content: str


class TrendSearchRequest(BaseModel):
    platform: str = "toutiao"
    category: str = ""
    limit: int = 20


class TrendsConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    auto_refresh: Optional[bool] = None
    refresh_interval: Optional[int] = None
    default_platforms: Optional[List[str]] = None
    show_in_infinite_write: Optional[bool] = None


class TrendsVisibilityRequest(BaseModel):
    show_in_infinite_write: bool = True


class ShortStoryStartRequest(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    source_input: str = ""
    target_total_words: int = 5000
    chapter_word_target: Optional[int] = None
    category: str = "其他"
    tone: str = ""


class ShortStoryWorkflowRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    api_config_id: str = ""
    model: str = ""
    feedback: str = ""


class ShortStorySelectionRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    selection: int


class ShortStoryOutlineConfirmRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    approved: bool = True
    feedback: str = ""


class ShortStoryChapterGenerateRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    chapter_number: int
    api_config_id: str = ""
    model: str = ""


class ShortStoryChapterSaveRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    chapter_number: int
    title: str = ""
    content: str = ""


class ShortStoryReviewCommitRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    report: str = ""
    passed: bool = True
    chapters: List[Dict[str, Any]] = Field(default_factory=list)


class ShortStorySimpleFixRequest(BaseModel):
    workflow: Dict[str, Any] = Field(default_factory=dict)
    report: str = ""
    chapters: List[Dict[str, Any]] = Field(default_factory=list)
