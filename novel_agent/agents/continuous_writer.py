# -*- coding: utf-8 -*-
"""
鏃犻檺缁啓Agent
鐢ㄤ簬鏍规嵁鐢ㄦ埛鎻愪緵鐨勬晠浜嬪紑澶存垨鐏垫劅杩涜缁啓鍒涗綔
姣忕珷瀹屾垚鍚庤嚜鍔ㄥ瓨鍏ョ煡璇嗗簱锛岄槻姝㈠墽鎯呴噸澶嶅拰璁惧畾鍐茬獊

澧炲己鍔熻兘锛?
- 浼氳瘽鎸佷箙鍖栵細鏈嶅姟閲嶅惎鍚庡彲鎭㈠缁啓
- 妯″瀷鍒囨崲淇濇寔杩炶疮锛氭崲妯″瀷鍚庤嚜鍔ㄤ紶閫掑畬鏁翠笂涓嬫枃
- 绔犺妭杩炶疮鎬т繚璇侊細閫氳繃鎸佷箙鍖栫殑鍓ф儏鎽樿纭繚涓€鑷存€?
- SeekDB 浼樺寲锛氬姩鎬佹悳绱㈡潈閲嶃€佹櫤鑳介噸鎺掑簭銆佷笂涓嬫枃鍘嬬缉
"""
from __future__ import annotations

import asyncio
import logging
import time
import re
import json
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass, field

from .base_agent import BaseAgent
from .session_store import get_session_store, SessionState
from ..agent_config import AgentModelConfig

# 寤惰繜瀵煎叆鍓ф儏绾︽潫妯″潡锛岄伩鍏嶅惊鐜緷璧?
PlotConstraintStore = None
ContentValidator = None
PostGenerationProcessor = None

def get_plot_constraint_store(knowledge_base):
    """鑾峰彇鍓ф儏绾︽潫瀛樺偍瀹炰緥"""
    global PlotConstraintStore
    if PlotConstraintStore is None:
        from ..knowledge_base.logic_layer.plot_constraints import PlotConstraintStore as PCS
        PlotConstraintStore = PCS
    return PlotConstraintStore(knowledge_base)

def get_content_validator(constraint_store, knowledge_base):
    """鑾峰彇鍐呭楠岃瘉鍣ㄥ疄渚?"""
    global ContentValidator, PostGenerationProcessor
    if ContentValidator is None:
        from .content_validator import ContentValidator as CV, PostGenerationProcessor as PGP
        ContentValidator = CV
        PostGenerationProcessor = PGP
    return ContentValidator(constraint_store, knowledge_base), PostGenerationProcessor

logger = logging.getLogger(__name__)


@dataclass
class CharacterState:
    """瑙掕壊鐘舵€佽拷韪?"""
    name: str
    is_alive: bool = True
    status: str = "姝ｅ父"
    location: str = ""
    last_chapter: int = 0
    notes: List[str] = field(default_factory=list)


@dataclass
class PlotPoint:
    """鍓ф儏瑕佺偣杩借釜"""
    chapter: int
    description: str
    importance: str = "normal"
    resolved: bool = False


@dataclass
class ContinuousWriteConfig:
    """鏃犻檺缁啓閰嶇疆"""
    words_per_chapter: int = 2500
    min_words: int = 2000
    max_words: int = 4000
    auto_save_to_kb: bool = True
    check_consistency: bool = True
    context_chapters: int = 3
    kb_search_top_k: int = 5
    kb_summary_top_k: int = 3
    pause_for_user_input: bool = True
    enable_trends_search: bool = False
    trends_platforms: List[str] = field(default_factory=lambda: ["toutiao", "douyin"])
    trends_limit: int = 5


class ContinuousWriter(BaseAgent):
    """
    鏃犻檺缁啓Agent
    
    鏍稿績鍔熻兘锛?
    1. 鏍规嵁鐢ㄦ埛鎻愪緵鐨勬晠浜嬪紑澶存垨鐏垫劅杩涜缁啓
    2. 姣忕珷鍩轰簬鍓嶄竴绔犲唴瀹圭户缁画鍐?
    3. 姣忓畬鎴愪竴绔犺嚜鍔ㄥ悜閲忓寲瀛樺叆鐭ヨ瘑搴?
    4. 閫氳繃鐭ヨ瘑搴撴绱㈤槻姝㈠墽鎯呴噸澶嶅拰璁惧畾鍐茬獊
    5. 鏀寔鐢ㄦ埛闅忔椂鍔犲叆鐏垫劅鍜岀籂姝ｅ墽鎯?
    
    澧炲己鍔熻兘锛?
    6. 浼氳瘽鎸佷箙鍖?- 鏈嶅姟閲嶅惎鍚庤嚜鍔ㄦ仮澶?
    7. 妯″瀷鍒囨崲杩炶疮鎬?- 鎹㈡ā鍨嬫椂鑷姩浼犻€掑畬鏁翠笂涓嬫枃
    8. 璺ㄧ珷鑺備竴鑷存€?- 閫氳繃鎸佷箙鍖栫姸鎬佺‘淇濆墽鎯呰繛璐?
    """
    
    def __init__(
        self,
        model_config: Optional[AgentModelConfig] = None,
        write_config: Optional[ContinuousWriteConfig] = None,
        knowledge_base = None,
        session_id: str = "default",
        project_id: str = "",
        **kwargs
    ):
        """鍒濆鍖栨棤闄愮画鍐橝gent"""
        super().__init__(
            name="ContinuousWriter",
            prompt_file="continuous_writer.md",
            model_config=model_config,
            **kwargs
        )
        
        self.write_config = write_config or ContinuousWriteConfig()
        self.knowledge_base = knowledge_base
        
        # 浼氳瘽鏍囪瘑
        self._session_id = session_id
        self._project_id = project_id
        self._session_store = get_session_store()
        self._session_state: Optional[SessionState] = None
        
        self._is_running = False
        self._should_stop = False
        self._waiting_for_input = False
        self._current_chapter = 0
        
        self._written_chapters: List[Dict[str, Any]] = []
        self._story_beginning: str = ""
        self._user_inspirations: List[Dict[str, Any]] = []
        self._recovered_chapters: List[Dict[str, Any]] = []  # 鎭㈠鐨勭珷鑺傛暟鎹?
        self._corrections: List[Dict[str, Any]] = []
        
        self._characters: Dict[str, CharacterState] = {}
        self._plot_points: List[PlotPoint] = []
        self._dead_characters: List[str] = []
        
        self._trends_enabled: bool = False
        self._trends_query: str = ""
        self._cached_trends: List[Dict[str, Any]] = []
        
        # 褰撳墠浣跨敤鐨勬ā鍨嬪悕绉帮紙鐢ㄤ簬杩借釜妯″瀷鍒囨崲锛?
        self._current_model: str = ""
        
        # 鍓ф儏绾︽潫瀛樺偍锛堝湪璁剧疆鐭ヨ瘑搴撴椂鍒濆鍖栵級
        self._constraint_store = None
        
        # 鍐呭楠岃瘉鍣紙鍚庡鐞嗛獙璇侊級
        self._content_validator = None
        self._post_processor = None
        
        # 楠岃瘉閰嶇疆
        self._enable_post_validation = True  # 鏄惁鍚敤鍚庡鐞嗛獙璇?
        self._auto_fix_violations = True  # 鏄惁鑷姩淇杩濊
        self._max_regeneration_attempts = 2  # 鏈€澶ч噸鏂扮敓鎴愭鏁?
        
        # 楂樼骇妫€绱㈤厤缃?
        self._use_advanced_search = True  # 浣跨敤澧炲己鐨勭煡璇嗗簱鎼滅储
        self._use_dynamic_weights = True  # 鍔ㄦ€佽皟鏁存悳绱㈡潈閲?
        self._use_reranking = True  # 鍚敤缁撴灉閲嶆帓搴?
        self._use_context_compression = True  # 鍚敤涓婁笅鏂囧帇缂?
        
    def _get_default_prompt(self) -> str:
        """鑾峰彇榛樿绯荤粺鎻愮ず璇?"""
        return """# 鏃犻檺缁啓Agent

浣犳槸灏忚椤圭洰鐨勯暱绋嬬画鍐橝gent锛岃礋璐ｅ杞繛缁垱浣滃苟淇濇寔璺ㄦā鍨嬭繛璐€?
## 宸ヤ綔妯″紡

### 妯″紡 CW1锛氳捣绔狅紙start锛?- 寤虹珛浜虹墿銆佸啿绐佸拰鍙欎簨鑺傚锛岀珷鏈粰鍑虹画鍐欓挬瀛愩€?
### 妯″紡 CW2锛氱画绔狅紙continue锛岄粯璁わ級
- 鍦ㄤ笂涓€绔犲熀纭€涓婃帹杩涳紝涓嶉噸澶嶅墠鏂囷紝涓嶅師鍦扮┖杞€?
### 妯″紡 CW3锛氶噸鐢熸垚锛坮egenerate锛?- 淇濇寔绔犺妭鐩爣涓庝簨瀹炰笉鍙橈紝閲嶅啓琛ㄨ揪涓庢帹杩涜矾寰勩€?
### 妯″紡 CW4锛氱籂姝ｆ墽琛岋紙correct / inspiration锛?- 涓嬩竴绔犱紭鍏堣惤瀹炵敤鎴风籂姝ｄ笌鐏垫劅銆?
## 瀛楁暟涓庝竴鑷存€х‖绾︽潫锛堟渶楂樹紭鍏堢骇锛?
1. 涓ユ牸鎺у埗鍦ㄧ洰鏍囧瓧鏁扮殑姝ｈ礋15%鑼冨洿鍐呫€?2. 宸叉浜¤鑹蹭笉寰椾互娲讳汉鐘舵€佸洖褰掞紙鍥炲繂/闂洖闄ゅ锛夈€?3. 涓嶇牬鍧忔棦鏈変笘鐣岃銆佽鑹茶瀹氥€佹椂闂寸嚎銆?4. 妯″瀷鍒囨崲鍚庝紭鍏堥伒瀹堝巻鍙蹭笂涓嬫枃涓庢寔涔呭寲鐘舵€併€?
## 绾跨▼瑙勫垯

- 鏀嚎鎺ㄨ繘鏃堕渶淇濈暀鍥炰富绾跨嚎绱€?- 鏀嚎涓嶅彲鏃犻檺寤堕暱锛岃揪鍒扮洰鏍囧悗鍥炴敹銆?- 蹇呰鏃跺彲浣跨敤闅愯棌娉ㄩ噴锛?  - `<!-- PLOT_THREAD:return_main -->`
  - `<!-- PLOT_THREAD:switch:subplot_a -->`
  - `<!-- PLOT_THREAD:complete -->`
"""
    
    async def execute(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """鎵ц缁啓浠诲姟"""
        action = input_data.get("action", "continue")
        
        if input_data.get("trends_query"):
            self._trends_enabled = True
            self._trends_query = input_data.get("trends_query", "")
        if input_data.get("trends_platforms"):
            self.write_config.trends_platforms = input_data.get("trends_platforms")
        
        if action == "start":
            return await self._start_new_story(input_data, context)
        elif action == "continue":
            return await self._continue_writing(input_data, context)
        elif action == "add_inspiration":
            return self._add_inspiration(input_data)
        elif action == "correct":
            return self._add_correction(input_data)
        elif action == "stop":
            return self._stop_writing()
        elif action == "status":
            return self._get_status()
        elif action == "get_chapter":
            return self._get_chapter(input_data.get("chapter_number", 1))
        elif action == "enable_trends":
            return self._enable_trends(input_data)
        elif action == "disable_trends":
            return self._disable_trends()
        elif action == "regenerate":
            return await self._regenerate_chapter(input_data, context)
        else:
            return {"success": False, "error": f"鏈煡鍔ㄤ綔: {action}"}
    
    def _load_or_create_session(self, story_beginning: str = "") -> SessionState:
        """
        鍔犺浇鎴栧垱寤烘寔涔呭寲浼氳瘽
        
        杩欐槸纭繚鎹㈡ā鍨嬪悗淇濇寔杩炶疮鎬х殑鍏抽敭
        """
        # 灏濊瘯浠庢寔涔呭寲瀛樺偍鍔犺浇
        state = self._session_store.load(self._session_id, self._project_id)
        
        if state:
            # 鎭㈠宸叉湁浼氳瘽
            logger.info(f"[{self.name}] Recovered persisted session at chapter {state.current_chapter}")
            
            # 鍚屾鍐呭瓨鐘舵€?
            self._story_beginning = state.story_beginning
            self._current_chapter = state.current_chapter
            self._written_chapters = state.chapters.copy()
            self._dead_characters = state.dead_characters.copy()
            self._user_inspirations = state.inspirations.copy()
            self._corrections = state.corrections.copy()
            
            return state
        
        # 鍒涘缓鏂颁細璇?
        state = SessionState(
            session_id=self._session_id,
            project_id=self._project_id,
            story_beginning=story_beginning,
            words_per_chapter=self.write_config.words_per_chapter,
            trends_enabled=self._trends_enabled,
            trends_platforms=self.write_config.trends_platforms
        )
        
        self._session_store.save(state)
        logger.info(f"[{self.name}] Created new persisted session")
        return state
    
    def _sync_to_session(self):
        """
        灏嗗唴瀛樼姸鎬佸悓姝ュ埌鎸佷箙鍖栦細璇?
        
        姣忔绔犺妭瀹屾垚鍚庤皟鐢紝纭繚鏁版嵁涓嶄涪澶?
        """
        if not self._session_state:
            return
        
        self._session_state.story_beginning = self._story_beginning
        self._session_state.current_chapter = self._current_chapter
        self._session_state.chapters = self._written_chapters.copy()
        self._session_state.dead_characters = self._dead_characters.copy()
        self._session_state.inspirations = self._user_inspirations.copy()
        self._session_state.corrections = self._corrections.copy()
        self._session_state.is_running = self._is_running
        self._session_state.last_model = self._current_model
        
        self._session_store.save(self._session_state)
    
    def _get_model_switch_context(self) -> str:
        """
        鑾峰彇妯″瀷鍒囨崲鏃剁殑棰濆涓婁笅鏂?
        
        褰撴娴嬪埌妯″瀷鍒囨崲鏃讹紝鎻愪緵鏇磋缁嗙殑涓婁笅鏂囦互纭繚杩炶疮鎬?
        """
        if not self._session_state:
            return ""
        
        last_model = self._session_state.last_model
        if last_model and last_model != self._current_model:
            logger.info(f"[{self.name}] 妫€娴嬪埌妯″瀷鍒囨崲: {last_model} -> {self._current_model}")
            
            # 鏋勫缓澧炲己鐨勬ā鍨嬪垏鎹笂涓嬫枃
            context_parts = []
            
            # 1. 鍩虹浼氳瘽鎽樿
            session_summary = self._session_state.get_context_summary(max_chapters=5)
            context_parts.append(session_summary)
            
            # 2. 浠庣煡璇嗗簱鑾峰彇鍏抽敭绾︽潫锛堜娇鐢ㄩ珮绾ф悳绱級
            if self.knowledge_base and self._use_advanced_search:
                try:
                    # 鑾峰彇鎵€鏈夋椿璺冪殑涓ラ噸绾︽潫
                    critical_constraints = self.knowledge_base.get_active_constraints()
                    if critical_constraints:
                        context_parts.append("\n[閲嶈鍓ф儏绾︽潫]")
                        for c in critical_constraints[:10]:
                            context_parts.append(f"- {c.title}")
                    
                    # 鑾峰彇姝讳骸瑙掕壊
                    dead_chars = self.knowledge_base.get_dead_characters()
                    if dead_chars:
                        context_parts.append("\n[宸叉浜¤鑹瞉")
                        context_parts.append(", ".join(dead_chars))
                        
                except Exception as e:
                    logger.warning(f"[{self.name}] 鑾峰彇鐭ヨ瘑搴撶害鏉熷け璐? {e}")
            
            # 3. 鏈€鍚庝竴绔犵殑瀹屾暣鍐呭锛堢‘淇濈画鍐欒繛璐級
            if self._written_chapters:
                last_ch = self._written_chapters[-1]
                last_content = last_ch.get('content', '')
                if last_content:
                    context_parts.append("\n[涓婁竴绔犲畬鏁村唴瀹筣")
                    context_parts.append(
                        f"第{last_ch.get('chapter_number')}章 {last_ch.get('title', '')}"
                    )
                    # 鎻愪緵鏇村鍐呭浠ョ‘淇濊繛璐?
                    context_parts.append(last_content[-2000:] if len(last_content) > 2000 else last_content)
            
            return "\n".join(context_parts)
        
        return ""
    
    async def _start_new_story(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """寮€濮嬫柊鏁呬簨鎴栨仮澶嶅凡鏈夋晠浜?"""
        story_beginning = input_data.get("content", "")
        if not story_beginning:
            return {"success": False, "error": "璇锋彁渚涙晠浜嬪紑澶存垨鐏垫劅"}
        
        current_chapter = input_data.get("current_chapter", 0)
        is_recovery = current_chapter > 0
        
        self._is_running = True
        self._should_stop = False
        
        # 鑾峰彇褰撳墠妯″瀷鍚嶇О
        if self.model_config:
            self._current_model = self.model_config.model
        
        # 灏濊瘯浠庢寔涔呭寲瀛樺偍鎭㈠锛堜紭鍏堢骇鏈€楂橈級
        self._session_state = self._load_or_create_session(story_beginning)
        
        # 濡傛灉鎸佷箙鍖栦細璇濇湁鏁版嵁锛屼紭鍏堜娇鐢?
        if self._session_state.chapters:
            logger.info(f"[{self.name}] Using persisted chapters: {len(self._session_state.chapters)}")
            is_recovery = True
            self._current_chapter = self._session_state.current_chapter
            self._story_beginning = self._session_state.story_beginning
            self._written_chapters = self._session_state.chapters.copy()
            self._dead_characters = self._session_state.dead_characters.copy()
            self._user_inspirations = self._session_state.inspirations.copy()
            self._corrections = self._session_state.corrections.copy()
        elif is_recovery:
            # 浠庡墠绔紶鍏ョ殑鏁版嵁鎭㈠锛堝吋瀹规棫閫昏緫锛?
            self._current_chapter = current_chapter
            if not self._story_beginning:
                self._story_beginning = story_beginning
            
            # 鎭㈠绔犺妭鏁版嵁 - 鍏抽敭淇锛氱‘淇濆悗缁珷鑺傛湁涓婁笅鏂?
            recovered_chapters = input_data.get("recovered_chapters", [])
            if recovered_chapters and isinstance(recovered_chapters, list):
                self._written_chapters = []
                for ch in recovered_chapters:
                    if isinstance(ch, dict) and ch.get("content"):
                        self._written_chapters.append({
                            "chapter_number": ch.get("chapter_number", len(self._written_chapters) + 1),
                            "title": ch.get("title", f"第{ch.get('chapter_number', len(self._written_chapters) + 1)}章"),
                            "content": ch.get("content", ""),
                            "word_count": ch.get("word_count", len(ch.get("content", "")))
                        })
                logger.info(f"[{self.name}] 浠庡墠绔仮澶?{len(self._written_chapters)} 绔犺妭鏁版嵁")
                
                # 鍚屾鍒版寔涔呭寲瀛樺偍
                self._session_state.chapters = self._written_chapters.copy()
                self._session_state.current_chapter = current_chapter
                self._session_store.save(self._session_state)
            else:
                # 濡傛灉娌℃湁瀹屾暣绔犺妭鏁版嵁锛屽皢 story_beginning 浣滀负铏氭嫙鐨勭涓€绔?
                logger.warning(f"[{self.name}] 鎭㈠浼氳瘽浣嗘棤瀹屾暣绔犺妭鏁版嵁锛屼娇鐢ㄥ紑澶存枃鏈綔涓轰笂涓嬫枃")
            
            logger.info(f"[{self.name}] 鎭㈠浼氳瘽锛氬綋鍓嶇珷鑺?{current_chapter}")
        else:
            self._current_chapter = 0
            self._written_chapters = []
            self._story_beginning = story_beginning
            self._user_inspirations = []
            self._corrections = []
            self._characters = {}
            self._plot_points = []
            self._dead_characters = []
            
            # 鏇存柊鎸佷箙鍖栦細璇?
            self._session_state.story_beginning = story_beginning
            self._session_store.save(self._session_state)
            
            logger.info(f"[{self.name}] 寮€濮嬫柊鏁呬簨")
        
        return await self._write_chapter(input_data, context)
    
    async def _continue_writing(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """缁х画缁啓涓嬩竴绔?"""
        if not self._is_running and not self._written_chapters:
            return {"success": False, "error": "璇峰厛寮€濮嬩竴涓柊鏁呬簨"}
        
        self._is_running = True
        self._should_stop = False
        
        extra_inspiration = input_data.get("content", "")
        if extra_inspiration:
            self._add_inspiration({"content": extra_inspiration, "chapter": self._current_chapter + 1})
        
        return await self._write_chapter(input_data, context)
    
    async def _regenerate_chapter(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """閲嶆柊鐢熸垚鎸囧畾绔犺妭锛堥粯璁や粠璇ョ珷璧烽噸寤猴級"""
        chapter_number = int(input_data.get("chapter_number", 0) or 0)
        if chapter_number <= 0:
            return {"success": False, "error": "invalid chapter number"}
        
        target_index = None
        for idx, ch in enumerate(self._written_chapters):
            if ch.get("chapter_number") == chapter_number:
                target_index = idx
                break
        
        if target_index is None:
            return {"success": False, "error": f"chapter {chapter_number} not found"}
        
        self._is_running = True
        self._should_stop = False
        
        removed = self._written_chapters[target_index:]
        removed_numbers = [ch.get("chapter_number") for ch in removed if ch.get("chapter_number")]
        
        self._written_chapters = self._written_chapters[:target_index]
        self._current_chapter = chapter_number - 1
        
        # 娓呯悊琚Щ闄ょ珷鑺傜殑鐏垫劅鍜岀籂姝?
        self._user_inspirations = [i for i in self._user_inspirations if i.get("chapter", 0) < chapter_number]
        self._corrections = [c for c in self._corrections if c.get("chapter", 0) < chapter_number]
        
        # 鍚屾鐭ヨ瘑搴撳垹闄わ紙濡傛灉鍚敤锛?
        if removed_numbers and self.knowledge_base:
            for num in removed_numbers:
                try:
                    self.knowledge_base.delete_chapter(f"chapter_{num}")
                except Exception as e:
                    logger.warning(f"[{self.name}] 鍒犻櫎鐭ヨ瘑搴撶珷鑺傚け璐? chapter_{num}, {e}")
        
        # 鍚屾浼氳瘽
        self._sync_to_session()
        
        extra_inspiration = input_data.get("content", "")
        if extra_inspiration:
            self._add_inspiration({"content": extra_inspiration, "chapter": chapter_number})
        
        return await self._write_chapter(input_data, context)
    
    async def _write_chapter(
        self,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """鍐欎竴涓珷鑺?"""
        self._current_chapter += 1
        chapter_number = self._current_chapter
        
        await self.notify_progress(f"正在创作第{chapter_number}章...", 0)
        
        # 妫€娴嬫ā鍨嬪垏鎹紝鑾峰彇棰濆涓婁笅鏂?
        model_switch_context = self._get_model_switch_context()
        
        await self.notify_progress("姝ｅ湪璇诲彇鐭ヨ瘑搴?..", 10)
        kb_summaries = await self._retrieve_summaries_from_knowledge_base()
        
        await self.notify_progress("姝ｅ湪妫€绱㈢浉鍏冲墽鎯?..", 20)
        kb_context = await self._retrieve_from_knowledge_base(chapter_number)
        
        trends_data = []
        if self._trends_enabled:
            await self.notify_progress("姝ｅ湪鎼滅储鐑偣...", 30)
            trends_data = await self._search_trends()
        
        recent_chapters = self._get_recent_chapters()
        chapter_inspirations = [i for i in self._user_inspirations if i.get("chapter") == chapter_number]
        chapter_corrections = [c for c in self._corrections if c.get("chapter") == chapter_number]
        
        await self.notify_progress("姝ｅ湪鏋勫缓鎻愮ず...", 40)
        
        prompt = self._build_chapter_prompt(
            chapter_number=chapter_number,
            story_beginning=self._story_beginning if chapter_number == 1 else "",
            recent_chapters=recent_chapters,
            kb_context=kb_context,
            kb_summaries=kb_summaries,
            trends_data=trends_data,
            inspirations=chapter_inspirations,
            corrections=chapter_corrections,
            model_switch_context=model_switch_context  # 鏂板锛氭ā鍨嬪垏鎹笂涓嬫枃
        )
        
        start_time = time.time()
        
        try:
            response = await self.call_llm([
                {"role": "user", "content": prompt}
            ])
            
            chapter_data = self._parse_chapter_response(response, chapter_number)
            chapter_data["model_used"] = self._current_model  # 璁板綍浣跨敤鐨勬ā鍨?
            duration = time.time() - start_time
            
            logger.info(
                f"[{self.name}] Completed chapter {chapter_number}: "
                f"{chapter_data['word_count']} words, model={self._current_model}"
            )
            
            # 鍚庡鐞嗛獙璇侊紙闄ゆ彁绀鸿瘝绾︽潫澶栫殑绗簩閬撻槻绾匡級
            validation_result = None
            if self._enable_post_validation and self._content_validator:
                await self.notify_progress("姝ｅ湪楠岃瘉鍐呭涓€鑷存€?..", 85)
                
                content = chapter_data["content"]
                validation_result = self._content_validator.validate(
                    content,
                    chapter_number,
                    auto_fix=self._auto_fix_violations
                )
                
                if validation_result.auto_fixed and validation_result.fixed_content:
                    # 搴旂敤鑷姩淇
                    chapter_data["content"] = validation_result.fixed_content
                    chapter_data["word_count"] = len(re.sub(r'\s+', '', validation_result.fixed_content))
                    chapter_data["auto_fixed"] = True
                    logger.info(f"[{self.name}] 搴旂敤鑷姩淇")
                
                if validation_result.has_critical:
                    # 瀛樺湪涓ラ噸杩濊锛岃褰曡鍛?
                    chapter_data["validation_warnings"] = [
                        v.description for v in validation_result.violations
                    ]
                    logger.warning(f"[{self.name}] Detected {len(validation_result.violations)} validation violations")
            
            self._update_character_states(chapter_data)
            self._written_chapters.append(chapter_data)
            
            # 鍚屾鍒版寔涔呭寲瀛樺偍锛堝叧閿細纭繚鏁版嵁涓嶄涪澶憋級
            self._sync_to_session()
            
            if self.write_config.auto_save_to_kb:
                await self._save_to_knowledge_base(chapter_data)
            
            await self.notify_progress(f"第{chapter_number}章创作完成", 100, {"chapter": chapter_data})
            
            result = {
                "success": True,
                "chapter": chapter_data,
                "waiting_for_input": self.write_config.pause_for_user_input,
                "message": "绔犺妭鍒涗綔瀹屾垚",
                "session_id": self._session_id,
                "persisted": True  # 鏍囪宸叉寔涔呭寲
            }
            
            # 娣诲姞楠岃瘉缁撴灉
            if validation_result:
                result["validation"] = {
                    "passed": validation_result.is_valid,
                    "auto_fixed": validation_result.auto_fixed,
                    "warnings": [v.description for v in validation_result.violations] if validation_result.violations else []
                }
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.name}] 鍒涗綔澶辫触: {e}")
            self._current_chapter -= 1
            return {"success": False, "chapter_number": chapter_number, "error": str(e)}
    
    def _build_chapter_prompt(
        self,
        chapter_number: int,
        story_beginning: str,
        recent_chapters: List[Dict[str, Any]],
        kb_context: Dict[str, Any],
        kb_summaries: List[Dict[str, Any]] = None,
        trends_data: List[Dict[str, Any]] = None,
        inspirations: List[Dict[str, Any]] = None,
        corrections: List[Dict[str, Any]] = None,
        model_switch_context: str = ""  # 鏂板锛氭ā鍨嬪垏鎹㈡椂鐨勯澶栦笂涓嬫枃
    ) -> str:
        """鏋勫缓绔犺妭缁啓鎻愮ず璇?"""
        parts = []
        inspirations = inspirations or []
        corrections = corrections or []
        kb_summaries = kb_summaries or []
        trends_data = trends_data or []
        
        # 妯″瀷鍒囨崲鏃讹紝娣诲姞瀹屾暣鐨勬晠浜嬩笂涓嬫枃
        if model_switch_context:
            parts.append("[閲嶈鎻愮ず锛氭ā鍨嬪凡鍒囨崲锛岃浠旂粏闃呰浠ヤ笅瀹屾暣涓婁笅鏂嘳")
            parts.append(model_switch_context)
            parts.append("")
        
        if kb_summaries:
            parts.append("[鍓ф儏鎬荤粨]")
            for s in kb_summaries:
                parts.append(f"{s.get('chapter_range', '')}: {s.get('content', '')}")
            parts.append("")
        
        if story_beginning:
            parts.append(f"[鏁呬簨寮€澶碷\n{story_beginning}\n")
        
        if trends_data:
            parts.append("[热点融合要求]")
            parts.append("请从热点候选中选择 1-2 条与当前剧情最契合的内容进行改编融入。")
            parts.append("不要原样照抄热点标题，不要写成新闻播报，要转化为角色动机/冲突/事件触发。")
            parts.append("")
            parts.append("[热点候选]")
            trend_candidates = self._select_balanced_trend_candidates(trends_data, limit=5)
            for t in trend_candidates:
                title = (t.get("title") or "").strip()
                if not title:
                    continue
                platform = (t.get("platform") or "").strip()
                hot = (t.get("hot") or "").strip()
                source = f"[{platform}]" if platform else ""
                heat = f"（热度:{hot}）" if hot else ""
                parts.append(f"- {source}{title}{heat}")
            parts.append("")
        if kb_context.get("relevant_content"):
            parts.append("[鐭ヨ瘑搴撲俊鎭痌")
            for item in kb_context["relevant_content"]:
                parts.append(f"- {item}")
            parts.append("")
        
        # 宸叉浜¤鑹诧紙浠庣煡璇嗗簱鍜屽唴瀛樹腑鍚堝苟锛?
        all_dead = set(self._dead_characters)
        if kb_context.get("dead_characters"):
            all_dead.update(kb_context["dead_characters"])
        
        if all_dead:
            parts.append("[宸叉浜¤鑹?- 缁濆绂佹澶嶆椿锛乚")
            parts.append("浠ヤ笅瑙掕壊宸插湪涔嬪墠鐨勭珷鑺備腑姝讳骸锛岀粷瀵逛笉鑳借浠栦滑浠ユ椿浜鸿韩浠藉嚭鐜帮細")
            for char in sorted(all_dead):
                parts.append(f"  鉂?{char}")
            parts.append("")
        
        # 鍓ф儏绾︽潫锛堜粠鐭ヨ瘑搴撴绱級
        if kb_context.get("plot_constraints"):
            parts.append("[閲嶈鍓ф儏绾︽潫]")
            for constraint in kb_context["plot_constraints"][:5]:
                doc = constraint.get("document", "")
                if doc:
                    # 鍙彁鍙栧叧閿俊鎭?
                    lines = doc.split("\n")[:10]
                    for line in lines:
                        if line.strip() and not line.startswith("==="):
                            parts.append(f"  {line}")
            parts.append("")
        
        # 澧炲己鍓嶆儏鍥為【锛氭彁渚涙洿璇︾粏鐨勭珷鑺傚唴瀹?
        if recent_chapters:
            parts.append("[鍓嶆儏鍥為【]")
            for ch in recent_chapters:
                ch_num = ch.get('chapter_number')
                title = ch.get('title', '')
                summary = ch.get('summary', '')[:300]  # 澧炲姞鎽樿闀垮害
                parts.append(f"第{ch_num}章 {title}:")
                parts.append(f"  {summary}...")
            parts.append("")
            
            # 鏈€鍚庝竴绔犵殑瀹屾暣鍐呭锛堢‘淇濈画鍐欒繛璐級
            if recent_chapters:
                last_chapter = recent_chapters[-1]
                last_content = last_chapter.get('content', '')
                if last_content:
                    # 鎻愪緵鏈€鍚?000瀛椾綔涓虹洿鎺ヤ笂涓嬫枃
                    parts.append("[涓婁竴绔犵粨灏撅紙璇风洿鎺ョ画鍐欙級]")
                    parts.append(last_content[-1000:])
                    parts.append("")
        
        if inspirations:
            parts.append("[鐏垫劅]")
            for insp in inspirations:
                parts.append(f"- {insp.get('content', '')}")
            parts.append("")
        
        if corrections:
            parts.append("[绾犳]")
            for corr in corrections:
                parts.append(f"- {corr.get('content', '')}")
            parts.append("")
        
        target = self.write_config.words_per_chapter
        min_w = int(target * 0.90)
        max_w = int(target * 1.10)
        
        parts.append(f"[字数限制] {min_w}-{max_w}字，目标{target}字")
        parts.append(f"[任务] 请创作第{chapter_number}章")
        parts.append("[注意] 请保持与前文剧情连贯，不要重复已有内容，不要让已死亡角色复活")
        
        return "\n".join(parts)
    
    def _parse_chapter_response(self, response: str, chapter_number: int) -> Dict[str, Any]:
        """瑙ｆ瀽LLM鍝嶅簲"""
        title_match = re.search(r'#\s*绗琝d+绔燶s*(.+?)(?:\n|$)', response)
        title = title_match.group(1).strip() if title_match else f"第{chapter_number}章"
        
        content = response
        chapter_info = {}
        
        info_match = re.search(r'---\n.+?(.*?)(?:$|\n---)', response, re.DOTALL)
        if info_match:
            content = response[:info_match.start()].strip()
        
        if title_match:
            content = content[title_match.end():].strip()
        
        word_count = len(re.sub(r'\s+', '', content))
        
        target = self.write_config.words_per_chapter
        max_w = int(target * 1.15)
        
        if word_count > max_w:
            logger.warning(f"[{self.name}] 瀛楁暟瓒呮爣: {word_count} > {max_w}")
            content = self._smart_truncate(content, max_w)
            word_count = len(re.sub(r'\s+', '', content))
        
        summary = content[:200] + "..." if len(content) > 200 else content
        
        return {
            "chapter_number": chapter_number,
            "title": title,
            "content": content,
            "word_count": word_count,
            "summary": summary,
            **chapter_info
        }
    
    def _smart_truncate(self, content: str, max_words: int) -> str:
        """鏅鸿兘鎴柇"""
        current = len(re.sub(r'\s+', '', content))
        if current <= max_words:
            return content
        
        paragraphs = content.split('\n\n')
        result = []
        total = 0
        
        for para in paragraphs:
            para_words = len(re.sub(r'\s+', '', para))
            if total + para_words <= max_words:
                result.append(para)
                total += para_words
            else:
                break
        
        return '\n\n'.join(result).strip() or content[:max_words * 2]
    
    def _update_character_states(self, chapter_data: Dict[str, Any]) -> None:
        """鏇存柊瑙掕壊鐘舵€?"""
        pass
    
    async def _retrieve_from_knowledge_base(self, chapter_number: int) -> Dict[str, Any]:
        """
        浠庣煡璇嗗簱妫€绱紙澧炲己鐗堬級
        
        浣跨敤 SeekDB 浼樺寲鐨勯珮绾ф悳绱㈠姛鑳斤細
        - 鍔ㄦ€佹潈閲嶈皟鏁?
        - 鏅鸿兘閲嶆帓搴?
        - 涓婁笅鏂囧帇缂?
        """
        if not self.knowledge_base:
            return {"relevant_content": [], "plot_constraints": [], "dead_characters": [], "writing_context": {}}
        
        result = {
            "relevant_content": [],
            "plot_constraints": [],
            "dead_characters": [],
            "writing_context": {}
        }
        
        try:
            # 鏋勫缓鏌ヨ
            recent = ""
            if self._written_chapters:
                recent = self._written_chapters[-1].get("content", "")[:500]
            elif self._story_beginning:
                recent = self._story_beginning[:500]
            
            if recent and self._use_advanced_search:
                # 浣跨敤楂樼骇鎼滅储锛堝弬鑰?SeekDB 浼樺寲锛?
                try:
                    # 鑾峰彇鍐欎綔涓婁笅鏂囷紙涓€绔欏紡鑾峰彇鎵€鏈夌浉鍏充俊鎭級
                    writing_context = self.knowledge_base.get_context_for_writing(
                        query=recent,
                        current_chapter=chapter_number,
                        max_tokens=2000,
                        include_constraints=True
                    )
                    result["writing_context"] = writing_context
                    
                    # 鎻愬彇鐩稿叧鍐呭
                    for item in writing_context.get("relevant_content", []):
                        content = item.get("content", "")[:200]
                        if content:
                            result["relevant_content"].append(content)
                    
                    # 鎻愬彇绾︽潫
                    for constraint in writing_context.get("constraints", []):
                        result["plot_constraints"].append({
                            "type": constraint.get("type"),
                            "description": constraint.get("description"),
                            "entities": constraint.get("entities", [])
                        })
                    
                    # 姝讳骸瑙掕壊
                    result["dead_characters"] = writing_context.get("dead_characters", [])
                    
                    logger.debug(f"[{self.name}] 楂樼骇鎼滅储瀹屾垚锛宼oken浼拌: {writing_context.get('total_tokens_estimate', 0)}")
                    
                except AttributeError:
                    # 鐭ヨ瘑搴撲笉鏀寔楂樼骇鎼滅储锛屼娇鐢ㄥ熀纭€鎼滅储
                    logger.debug(f"[{self.name}] 鐭ヨ瘑搴撲笉鏀寔楂樼骇鎼滅储锛屽洖閫€鍒板熀纭€妯″紡")
                    self._use_advanced_search = False
            
            # 鍩虹鎼滅储锛堜綔涓哄悗澶囨垨楂樼骇鎼滅储涓嶅彲鐢ㄦ椂锛?
            if not self._use_advanced_search and recent:
                resp = self.knowledge_base.search(query=recent, top_k=self.write_config.kb_search_top_k)
                result["relevant_content"] = [r.document[:200] for r in resp.results if r.metadata.get("type") != "plot_constraints"]
            
            # 妫€绱㈠墽鎯呯害鏉燂紙鍏抽敭锛氶槻姝㈣鑹插娲荤瓑闂锛?
            if self._constraint_store:
                constraints = self._constraint_store.search_constraints(
                    query=recent[:200] if recent else "",
                    top_k=5
                )
                # 鍚堝苟绾︽潫
                for c in constraints:
                    if c not in result["plot_constraints"]:
                        result["plot_constraints"].append(c)
                
                # 鑾峰彇鎵€鏈夋浜¤鑹插垪琛?
                dead_chars = self._constraint_store.get_death_constraints()
                for char in dead_chars:
                    if char not in result["dead_characters"]:
                        result["dead_characters"].append(char)
                
                # 鍚屾鍒板唴瀛樼姸鎬?
                for char in result["dead_characters"]:
                    if char not in self._dead_characters:
                        self._dead_characters.append(char)
                        logger.info(f"[{self.name}] 浠庣煡璇嗗簱鍚屾姝讳骸瑙掕壊: {char}")
                
        except Exception as e:
            logger.warning(f"[{self.name}] 鐭ヨ瘑搴撴绱㈠け璐? {e}")
        
        return result
    
    async def _retrieve_summaries_from_knowledge_base(self) -> List[Dict[str, Any]]:
        """浠庣煡璇嗗簱妫€绱㈡€荤粨"""
        if not self.knowledge_base:
            return []
        
        try:
            resp = self.knowledge_base.search(
                query="鍓ф儏鎬荤粨",
                top_k=self.write_config.kb_summary_top_k
            )
            return [{"chapter_range": "", "content": r.document[:500]} for r in resp.results]
        except Exception as e:
            logger.debug(f"[{self.name}] 妫€绱㈠墽鎯呮€荤粨澶辫触: {e}")
        
        return []

    def _select_balanced_trend_candidates(
        self,
        trends_data: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """按平台轮询挑选热点，避免单个平台占满候选位。"""
        if not trends_data or limit <= 0:
            return []

        platform_buckets: Dict[str, List[Dict[str, Any]]] = {}
        platform_order: List[str] = []

        for trend in trends_data:
            platform = (trend.get("platform") or "").strip().lower()
            if platform not in platform_buckets:
                platform_buckets[platform] = []
                platform_order.append(platform)
            platform_buckets[platform].append(trend)

        merged: List[Dict[str, Any]] = []
        cursor = {platform: 0 for platform in platform_order}
        while len(merged) < limit:
            appended = False
            for platform in platform_order:
                idx = cursor[platform]
                items = platform_buckets.get(platform, [])
                if idx >= len(items):
                    continue
                merged.append(items[idx])
                cursor[platform] = idx + 1
                appended = True
                if len(merged) >= limit:
                    break
            if not appended:
                break

        return merged

    @staticmethod
    def _extract_trend_tool_error(result: Any) -> str:
        if result is None:
            return ""
        if hasattr(result, "content") and result.content:
            first = result.content[0]
            text = getattr(first, "text", "")
            if isinstance(text, str):
                return text.strip()
        return ""

    def _build_trend_tool_candidates(self, platform: str) -> List[str]:
        normalized = (platform or "").strip().lower()
        if not normalized:
            return []

        candidates: List[str] = []

        def _add(tool_name: str) -> None:
            if tool_name and tool_name not in candidates:
                candidates.append(tool_name)

        mapped = self._get_trend_tool_name(normalized)
        _add(mapped)

        modern = f"get_{normalized}_trending"
        _add(modern)
        _add(modern.replace("_", "-"))

        if mapped:
            _add(mapped.replace("_", "-"))

        return candidates
    
    async def _search_trends(self) -> List[Dict[str, Any]]:
        """鎼滅储鐑偣"""
        trends: List[Dict[str, Any]] = []

        def _extract_tag(text: str, tag: str) -> str:
            if not text:
                return ""
            match = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
            return (match.group(1).strip() if match else "")

        def _strip_xml(text: str) -> str:
            if not text:
                return ""
            return re.sub(r"<[^>]+>", "", text).strip()

        def _parse_trend_payload(payload: Any) -> List[Dict[str, str]]:
            rows: List[Dict[str, str]] = []
            if payload is None:
                return rows

            if isinstance(payload, list):
                for item in payload:
                    rows.extend(_parse_trend_payload(item))
                return rows

            if isinstance(payload, dict):
                for key in ("data", "list", "items", "result"):
                    value = payload.get(key)
                    if isinstance(value, list):
                        rows.extend(_parse_trend_payload(value))
                        return rows

                title_val = payload.get("title") or payload.get("name") or payload.get("content") or ""
                if isinstance(title_val, (dict, list)):
                    rows.extend(_parse_trend_payload(title_val))
                    return rows

                title_text = str(title_val or "").strip()
                title = _extract_tag(title_text, "title") or _strip_xml(title_text) or title_text
                if title:
                    hot_val = payload.get("hot") or payload.get("hotValue") or payload.get("heat") or payload.get("popularity") or payload.get("score") or ""
                    url_val = payload.get("url") or payload.get("link") or ""
                    rows.append(
                        {
                            "title": str(title),
                            "hot": str(hot_val or ""),
                            "url": str(url_val or ""),
                        }
                    )
                return rows

            if isinstance(payload, str):
                text = payload.strip()
                if not text:
                    return rows
                try:
                    parsed = json.loads(text)
                    rows.extend(_parse_trend_payload(parsed))
                    return rows
                except json.JSONDecodeError:
                    title = _extract_tag(text, "title") or _strip_xml(text) or text
                    if title:
                        rows.append(
                            {
                                "title": str(title),
                                "hot": _extract_tag(text, "popularity"),
                                "url": _extract_tag(text, "link"),
                            }
                        )
                return rows

            return rows

        try:
            selected_platforms: List[str] = []
            for platform in self.write_config.trends_platforms:
                normalized = (platform or "").strip().lower()
                if normalized and normalized not in selected_platforms:
                    selected_platforms.append(normalized)

            total_limit = int(self.write_config.trends_limit or 0)
            if not selected_platforms or total_limit <= 0:
                self._cached_trends = []
                return []

            seen_titles = set()
            platform_trends: Dict[str, List[Dict[str, Any]]] = {
                platform: [] for platform in selected_platforms
            }

            for platform in selected_platforms:
                try:
                    result = None
                    tool_candidates = self._build_trend_tool_candidates(platform)
                    used_tool = ""

                    for tool_name in tool_candidates:
                        try:
                            # 优先尝试以“类方法方式”调用，兼容测试中无 self 的猴补方法签名
                            try:
                                call_impl = getattr(BaseAgent, "use_skill")  # type: ignore[name-defined]
                                call_result = call_impl("trends_search", tool_name, limit=total_limit)  # type: ignore[misc]
                            except TypeError:
                                # 回退到实例方法调用
                                call_result = self.use_skill("trends_search", tool_name, limit=total_limit)
                        except Exception as call_error:
                            logger.debug(
                                f"[{self.name}] 热点工具调用异常({platform}, {tool_name}): {call_error}"
                            )
                            continue

                        # 检查 Skill 调用结果
                        if not call_result or not call_result.get("success"):
                            error_msg = call_result.get("error", "") if call_result else "unknown error"
                            lowered_error = error_msg.lower()
                            if "not found" in lowered_error:
                                logger.debug(
                                    f"[{self.name}] 热点工具不存在，尝试下一个候选: platform={platform}, tool={tool_name}"
                                )
                                continue
                            logger.debug(
                                f"[{self.name}] 热点工具调用失败({platform}, {tool_name}): {error_msg}"
                            )
                            call_result = None

                        if call_result and call_result.get("success"):
                            result = call_result
                            used_tool = tool_name
                            break

                    if result is None:
                        logger.debug(f"[{self.name}] 未获取到平台热点({platform})，候选工具: {tool_candidates}")
                        continue

                    # 处理 Skill 返回的数据
                    if result and result.get("data"):
                        data_items = result.get("data", [])
                        for item in data_items:
                            title = (item.get("title") or "").strip()
                            if not title or title in seen_titles:
                                continue
                            seen_titles.add(title)
                            platform_trends[platform].append(
                                {
                                    "title": title,
                                    "hot": (item.get("hot") or item.get("hotValue") or item.get("热度") or ""),
                                    "url": item.get("url", ""),
                                    "platform": platform,
                                }
                            )
                            if len(platform_trends[platform]) >= total_limit:
                                break

                    logger.debug(
                        f"[{self.name}] 平台热点获取成功: platform={platform}, tool={used_tool}, count={len(platform_trends[platform])}"
                    )
                except Exception as platform_error:
                    logger.debug(f"[{self.name}] 鑾峰彇骞冲彴鐑偣澶辫触({platform}): {platform_error}")
                    continue

            merged_candidates: List[Dict[str, Any]] = []
            for platform in selected_platforms:
                merged_candidates.extend(platform_trends.get(platform, []))
            trends = self._select_balanced_trend_candidates(merged_candidates, limit=total_limit)
            self._cached_trends = trends
        except Exception as e:
            logger.error(f"[{self.name}] 鐑偣鎼滅储澶辫触: {e}")
        return trends
    
    def _get_trend_tool_name(self, platform: str) -> str:
        """鑾峰彇鐑偣宸ュ叿鍚?"""
        platform = (platform or "").strip().lower()
        m = {
            "douban": "get_douban_rank",
            "weread": "get_weread_rank",
            "zhihu": "get_zhihu_trending",
            "gcores": "get_gcores_new",
            "toutiao": "get_toutiao_trending",
            "netease": "get_netease_news_trending",
            "tencent": "get_tencent_news_trending",
            "thepaper": "get_thepaper_trending",
            "bilibili": "get_bilibili_rank",
            "douyin": "get_douyin_trending",
            "weibo": "get_weibo_trending",
            "36kr": "get_36kr_trending",
            "sspai": "get_sspai_rank",
            "ifanr": "get_ifanr_news",
            "juejin": "get_juejin_article_rank",
            "smzdm": "get_smzdm_rank",
        }
        return m.get(platform, f"get_{platform}_trending")
    
    async def _save_to_knowledge_base(self, chapter_data: Dict[str, Any]) -> None:
        """瀛樺叆鐭ヨ瘑搴撳苟鑷姩鎻愬彇鍓ф儏绾︽潫"""
        if not self.knowledge_base:
            return
        
        try:
            # 瀛樺偍绔犺妭鍐呭
            self.knowledge_base.add_chapter(
                chapter_id=f"chapter_{chapter_data['chapter_number']}",
                title=chapter_data["title"],
                content=chapter_data["content"],
                chapter_number=chapter_data["chapter_number"],
                metadata={
                    "word_count": chapter_data["word_count"],
                    "model_used": self._current_model
                }
            )
            
            # 鑷姩鎻愬彇骞跺瓨鍌ㄥ墽鎯呯害鏉燂紙鍏抽敭锛氱‘淇濊鑹叉浜＄瓑淇℃伅琚褰曪級
            if self._constraint_store:
                constraints = self._constraint_store.extract_and_store(
                    content=chapter_data["content"],
                    chapter_id=f"chapter_{chapter_data['chapter_number']}",
                    chapter_number=chapter_data["chapter_number"],
                    title=chapter_data["title"]
                )
                
                # 鏇存柊鍐呭瓨涓殑姝讳骸瑙掕壊鍒楄〃
                for constraint in constraints:
                    if constraint.constraint_type == "character_death":
                        for entity in constraint.entities:
                            if entity not in self._dead_characters:
                                self._dead_characters.append(entity)
                                logger.info(f"[{self.name}] 妫€娴嬪埌瑙掕壊姝讳骸: {entity}")
                
                if constraints:
                    logger.info(f"[{self.name}] Extracted {len(constraints)} plot constraints")
            
        except Exception as e:
            logger.error(f"[{self.name}] 瀛樺偍澶辫触: {e}")
    
    def _add_inspiration(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """娣诲姞鐏垫劅"""
        content = input_data.get("content", "")
        if not content:
            return {"success": False, "error": "鐏垫劅鍐呭涓嶈兘涓虹┖"}
        
        chapter = input_data.get("chapter", self._current_chapter + 1)
        self._user_inspirations.append({"content": content, "chapter": chapter, "added_at": time.time()})
        
        # 鍚屾鍒版寔涔呭寲瀛樺偍
        self._sync_to_session()
        
        return {"success": True, "message": "inspiration added"}
    
    def _add_correction(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """娣诲姞绾犳"""
        content = input_data.get("content", "")
        if not content:
            return {"success": False, "error": "绾犳鍐呭涓嶈兘涓虹┖"}
        
        chapter = input_data.get("chapter", self._current_chapter + 1)
        self._corrections.append({"content": content, "chapter": chapter, "added_at": time.time()})
        
        # 鍚屾鍒版寔涔呭寲瀛樺偍
        self._sync_to_session()
        
        return {"success": True, "message": "correction added"}
    
    def _add_dead_character(self, character_name: str) -> Dict[str, Any]:
        """娣诲姞姝讳骸瑙掕壊"""
        if character_name and character_name not in self._dead_characters:
            self._dead_characters.append(character_name)
            self._sync_to_session()
            logger.info(f"[{self.name}] 璁板綍瑙掕壊姝讳骸: {character_name}")
        return {"success": True, "dead_characters": self._dead_characters}
    
    def _stop_writing(self) -> Dict[str, Any]:
        """鍋滄缁啓"""
        self._is_running = False
        self._should_stop = True
        
        # 鍚屾鍒版寔涔呭寲瀛樺偍
        self._sync_to_session()
        
        return {
            "success": True,
            "message": "continuous writing stopped",
            "total_chapters": len(self._written_chapters),
            "total_words": sum(ch.get("word_count", 0) for ch in self._written_chapters),
            "session_id": self._session_id,
            "persisted": True
        }
    
    def _get_status(self) -> Dict[str, Any]:
        """鑾峰彇鐘舵€?"""
        return {
            "success": True,
            "is_running": self._is_running,
            "current_chapter": self._current_chapter,
            "total_chapters": len(self._written_chapters),
            "total_words": sum(ch.get("word_count", 0) for ch in self._written_chapters),
            "dead_characters": self._dead_characters,
            "trends_enabled": self._trends_enabled,
            "session_id": self._session_id,
            "last_model": self._current_model,
            "persisted": self._session_state is not None
        }
    
    def _enable_trends(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """鍚敤鐑偣"""
        self._trends_enabled = True
        self._trends_query = input_data.get("query", "")
        if input_data.get("platforms"):
            self.write_config.trends_platforms = input_data.get("platforms")
        return {"success": True, "message": "trends fusion enabled"}
    
    def _disable_trends(self) -> Dict[str, Any]:
        """绂佺敤鐑偣"""
        self._trends_enabled = False
        self._trends_query = ""
        self._cached_trends = []
        return {"success": True, "message": "trends fusion disabled"}
    
    def _get_chapter(self, chapter_number: int) -> Dict[str, Any]:
        """鑾峰彇绔犺妭"""
        for ch in self._written_chapters:
            if ch.get("chapter_number") == chapter_number:
                return {"success": True, "chapter": ch}
        return {"success": False, "error": f"chapter {chapter_number} not found"}
    
    def _apply_client_sync(
        self,
        chapters: List[Dict[str, Any]],
        current_chapter: int,
        deleted_chapters: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """鍚屾鍓嶇绔犺妭鍒楄〃鍒板悗绔細璇?"""
        normalized = [ch for ch in chapters if isinstance(ch, dict)]
        normalized.sort(key=lambda x: x.get("chapter_number", 0))
        
        self._written_chapters = normalized
        
        if current_chapter > 0:
            self._current_chapter = current_chapter
        else:
            last_num = 0
            if normalized:
                last_num = max([c.get("chapter_number", 0) for c in normalized] or [0])
            self._current_chapter = last_num
        
        deleted_chapters = deleted_chapters or []
        if deleted_chapters and self.knowledge_base:
            for num in deleted_chapters:
                try:
                    self.knowledge_base.delete_chapter(f"chapter_{num}")
                except Exception as e:
                    logger.warning(f"[{self.name}] 鍒犻櫎鐭ヨ瘑搴撶珷鑺傚け璐? chapter_{num}, {e}")
        
        self._user_inspirations = [
            i for i in self._user_inspirations if i.get("chapter", 0) <= self._current_chapter + 1
        ]
        self._corrections = [
            c for c in self._corrections if c.get("chapter", 0) <= self._current_chapter + 1
        ]
        
        self._sync_to_session()
        
        return {
            "success": True,
            "message": "session synchronized",
            "current_chapter": self._current_chapter,
            "total_chapters": len(self._written_chapters)
        }
    
    def _get_recent_chapters(self) -> List[Dict[str, Any]]:
        """鑾峰彇鏈€杩戠珷鑺?"""
        return self._written_chapters[-self.write_config.context_chapters:]
    
    def get_all_chapters(self) -> List[Dict[str, Any]]:
        """鑾峰彇鎵€鏈夌珷鑺?"""
        return self._written_chapters.copy()
    
    def set_knowledge_base(self, kb) -> None:
        """璁剧疆鐭ヨ瘑搴?"""
        self.knowledge_base = kb
        
        # 鍒濆鍖栧墽鎯呯害鏉熷瓨鍌?
        if kb:
            try:
                self._constraint_store = get_plot_constraint_store(kb)
                logger.info(f"[{self.name}] Knowledge base and plot constraint store initialized")
                
                # 浠庣煡璇嗗簱鍔犺浇宸叉湁鐨勬浜¤鑹?
                dead_chars = self._constraint_store.get_death_constraints()
                for char in dead_chars:
                    if char not in self._dead_characters:
                        self._dead_characters.append(char)
                
                if self._dead_characters:
                    logger.info(f"[{self.name}] Loaded dead-character constraints: {len(self._dead_characters)}")
                
                # 鍒濆鍖栧唴瀹归獙璇佸櫒锛堝悗澶勭悊楠岃瘉锛?
                self._content_validator, _ = get_content_validator(self._constraint_store, kb)
                self._content_validator.load_constraints()
                logger.info(f"[{self.name}] 鍐呭楠岃瘉鍣ㄥ凡閰嶇疆")
                
            except Exception as e:
                logger.warning(f"[{self.name}] 鍓ф儏绾︽潫瀛樺偍鍒濆鍖栧け璐? {e}")
                self._constraint_store = None
                self._content_validator = None
        else:
            self._constraint_store = None
            self._content_validator = None
            logger.info(f"[{self.name}] 鐭ヨ瘑搴撳凡閰嶇疆")
    
    def set_session_id(self, session_id: str, project_id: str = "") -> None:
        """璁剧疆浼氳瘽ID锛堢敤浜庢寔涔呭寲锛?"""
        self._session_id = session_id
        self._project_id = project_id
        logger.info(f"[{self.name}] 浼氳瘽ID璁剧疆涓? {session_id}")
    
    def set_model(self, model: str) -> None:
        """璁剧疆褰撳墠妯″瀷锛堢敤浜庤拷韪ā鍨嬪垏鎹級"""
        if model != self._current_model:
            logger.info(f"[{self.name}] 妯″瀷鍒囨崲: {self._current_model} -> {model}")
        self._current_model = model
    
    def get_session_context(self) -> Dict[str, Any]:
        """
        鑾峰彇浼氳瘽涓婁笅鏂囷紙渚涘閮ㄤ娇鐢級
        
        杩斿洖纭繚杩炶疮鎬ф墍闇€鐨勬墍鏈変俊鎭?
        """
        if self._session_state:
            return self._session_store.get_context_for_continuation(
                self._session_id,
                self._project_id
            )
        
        return {
            "session_id": self._session_id,
            "current_chapter": self._current_chapter,
            "story_beginning": self._story_beginning,
            "dead_characters": self._dead_characters,
            "last_model": self._current_model,
            "recent_chapters": self._get_recent_chapters()
        }
    
    def configure_advanced_search(
        self,
        use_advanced: bool = True,
        use_dynamic_weights: bool = True,
        use_reranking: bool = True,
        use_context_compression: bool = True
    ) -> None:
        """
        閰嶇疆楂樼骇鎼滅储閫夐」
        
        Args:
            use_advanced: 鏄惁浣跨敤楂樼骇鎼滅储
            use_dynamic_weights: 鏄惁浣跨敤鍔ㄦ€佹潈閲?
            use_reranking: 鏄惁浣跨敤閲嶆帓搴?
            use_context_compression: 鏄惁浣跨敤涓婁笅鏂囧帇缂?
        """
        self._use_advanced_search = use_advanced
        self._use_dynamic_weights = use_dynamic_weights
        self._use_reranking = use_reranking
        self._use_context_compression = use_context_compression
        logger.info(
            f"[{self.name}] 楂樼骇鎼滅储閰嶇疆鏇存柊: "
            f"advanced={use_advanced}, "
            f"dynamic_weights={use_dynamic_weights}, "
            f"reranking={use_reranking}, "
            f"compression={use_context_compression}"
        )
    
    async def recover_from_model_switch(self) -> Dict[str, Any]:
        """
        浠庢ā鍨嬪垏鎹腑鎭㈠
        
        褰撴娴嬪埌妯″瀷鍒囨崲鏃讹紝涓诲姩鍔犺浇瀹屾暣涓婁笅鏂囦互纭繚杩炶疮鎬?
        
        Returns:
            鎭㈠缁撴灉锛屽寘鍚姞杞界殑涓婁笅鏂囦俊鎭?
        """
        result = {
            "success": True,
            "model_switched": False,
            "context_loaded": False,
            "dead_characters": [],
            "constraints": [],
            "recent_chapters_count": 0
        }
        
        if not self._session_state:
            result["message"] = "session state not found"
            return result
        
        last_model = self._session_state.last_model
        if not last_model or last_model == self._current_model:
            result["message"] = "鏈娴嬪埌妯″瀷鍒囨崲"
            return result
        
        result["model_switched"] = True
        logger.info(f"[{self.name}] 妫€娴嬪埌妯″瀷鍒囨崲锛屽紑濮嬫仮澶嶄笂涓嬫枃: {last_model} -> {self._current_model}")
        
        try:
            # 1. 浠庢寔涔呭寲瀛樺偍鎭㈠鍩虹鐘舵€?
            self._story_beginning = self._session_state.story_beginning
            self._current_chapter = self._session_state.current_chapter
            self._written_chapters = self._session_state.chapters.copy()
            self._dead_characters = self._session_state.dead_characters.copy()
            self._user_inspirations = self._session_state.inspirations.copy()
            self._corrections = self._session_state.corrections.copy()
            
            result["recent_chapters_count"] = len(self._written_chapters)
            
            # 2. 浠庣煡璇嗗簱鍚屾鏈€鏂扮害鏉?
            if self.knowledge_base:
                try:
                    # 鑾峰彇娲昏穬绾︽潫
                    constraints = self.knowledge_base.get_active_constraints()
                    result["constraints"] = [c.title for c in constraints[:5]]
                    
                    # 鍚屾姝讳骸瑙掕壊
                    dead_chars = self.knowledge_base.get_dead_characters()
                    for char in dead_chars:
                        if char not in self._dead_characters:
                            self._dead_characters.append(char)
                    
                    result["dead_characters"] = self._dead_characters.copy()
                    
                except Exception as e:
                    logger.warning(f"[{self.name}] 浠庣煡璇嗗簱鎭㈠绾︽潫澶辫触: {e}")
            
            result["context_loaded"] = True
            result["message"] = (
                f"context recovered after model switch, loaded {result['recent_chapters_count']} chapters"
            )
            
            # 鏇存柊浼氳瘽涓殑妯″瀷淇℃伅
            self._session_state.last_model = self._current_model
            self._session_store.save(self._session_state)
            
        except Exception as e:
            logger.error(f"[{self.name}] 妯″瀷鍒囨崲鎭㈠澶辫触: {e}")
            result["success"] = False
            result["message"] = f"鎭㈠澶辫触: {e}"
        
        return result


