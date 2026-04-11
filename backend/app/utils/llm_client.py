"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import time
import logging
from typing import Optional, Dict, Any, List

from openai import OpenAI

from ..config import Config
from .llm_monitor import monitor

logger = logging.getLogger('agars.llm_client')

# ============================================================
# Profile-based LLM client factory（模块级，延迟初始化）
# ============================================================
_client_cache: Dict[str, 'LLMClient'] = {}


def get_client(profile: str = "default", model_override: str = "") -> 'LLMClient':
    """根据 profile 名称（和可选的模型覆盖）返回 LLMClient（单例缓存）"""
    cache_key = f"{profile}:{model_override}" if model_override else profile
    if cache_key not in _client_cache:
        profiles = Config.get_llm_profiles()
        cfg = profiles.get(profile) or profiles["default"]
        _client_cache[cache_key] = LLMClient(
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model=model_override or cfg["model"],
        )
    return _client_cache[cache_key]


def get_client_for_prompt(key: str) -> 'LLMClient':
    """根据 prompt key 的独立 API 配置返回 LLMClient（有覆盖则用覆盖，否则用全局默认）"""
    from ..services.prompt_config import get_api_config
    cfg = get_api_config(key)
    api_key = cfg['api_key']
    base_url = cfg['base_url']
    model = cfg['model']

    if not api_key and not base_url and not model:
        # 无任何覆盖，直接用全局默认
        return get_client("default")

    # 有部分覆盖：未填的字段回退到全局 default
    default_profiles = Config.get_llm_profiles()
    default_cfg = default_profiles["default"]
    cache_key = f"custom:{api_key or ''}:{base_url or ''}:{model or ''}"
    if cache_key not in _client_cache:
        _client_cache[cache_key] = LLMClient(
            api_key=api_key or default_cfg["api_key"],
            base_url=base_url or default_cfg["base_url"],
            model=model or default_cfg["model"],
        )
    return _client_cache[cache_key]


class LLMClient:
    """LLM客户端（带超时和重试）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        self.safety_block_none = Config.LLM_GEMINI_SAFETY_BLOCK_NONE
        self._genai_client = None  # 延迟初始化原生 Gemini 客户端

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    def _is_gemini_url(self) -> bool:
        """判断是否使用 Google 原生 SDK（根据配置或 URL 自动判断）"""
        mode = Config.LLM_USE_GOOGLE_SDK  # 'auto', 'true', 'false'
        if mode == 'true':
            return True
        if mode == 'false':
            return False
        return 'generativelanguage.googleapis.com' in (self.base_url or '')

    def _chat_gemini_native(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict] = None,
    ) -> tuple:
        """
        使用原生 google-genai SDK 调用 Gemini，支持 safety_settings BLOCK_NONE。

        Returns:
            (response_text, actual_messages) — 响应文本 + 包装后实际发送的消息列表（供日志记录）
        """
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError(
                "未安装 google-genai，请运行: pip install google-genai\n"
                "或在全局配置中关闭「禁用 Gemini Safety Filter」选项"
            )

        if self._genai_client is None:
            self._genai_client = genai.Client(api_key=self.api_key)

        # 将 OpenAI 格式消息转换为 Gemini 原生格式
        system_instruction = None
        user_parts = []
        for msg in messages:
            role = msg['role']
            content = msg['content']
            if role == 'system':
                system_instruction = content
            elif role in ('user', 'assistant'):
                user_parts.append((role, content))

        from ..services.prompt_config import PROMPT_DEFAULTS, _overrides
        wrapper_key = 'content_wrapper_llm'
        _ov = _overrides.get(wrapper_key, {})
        _df = PROMPT_DEFAULTS.get(wrapper_key, {})
        wrap_messages = _ov.get('messages', _df.get('messages', []))

        wrapped = bool(wrap_messages)
        if wrap_messages:
            combined = '\n\n'.join(c for _, c in user_parts)
            contents = []
            for wm in wrap_messages:
                role = wm.get('role', 'user')
                text = wm.get('content', '').replace('{user_content}', combined)
                if role == 'system_instruction':
                    system_instruction = text
                else:
                    gemini_role = 'model' if role in ('assistant', 'model') else role
                    contents.append(types.Content(role=gemini_role, parts=[types.Part(text=text)]))
        else:
            contents = []
            for role, content in user_parts:
                gemini_role = 'model' if role == 'assistant' else role
                contents.append(types.Content(role=gemini_role, parts=[types.Part(text=content)]))

        # 构建实际发送的消息列表（供 monitor 日志记录）
        actual_messages = []
        if system_instruction:
            actual_messages.append({"role": "system", "content": system_instruction})
        for c in contents:
            role_str = 'assistant' if c.role == 'model' else c.role
            text = c.parts[0].text if c.parts else ''
            actual_messages.append({"role": role_str, "content": text})
        if wrapped:
            actual_messages.append({"_wrapped": True})

        config_kwargs: Dict[str, Any] = dict(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if self.safety_block_none:
            config_kwargs['safety_settings'] = [
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_CIVIC_INTEGRITY', threshold='BLOCK_NONE'),
            ]
        if system_instruction:
            config_kwargs['system_instruction'] = system_instruction
        if response_format and response_format.get('type') == 'json_object':
            config_kwargs['response_mime_type'] = 'application/json'

        config = types.GenerateContentConfig(**config_kwargs)

        chunks = []
        last_chunk = None
        for chunk in self._genai_client.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        ):
            last_chunk = chunk
            if chunk.text:
                chunks.append(chunk.text)

        # 空响应时输出诊断信息
        if not chunks and last_chunk is not None:
            diag_parts = []
            # 检查 prompt 级别的拦截
            pf = getattr(last_chunk, 'prompt_feedback', None)
            if pf:
                br = getattr(pf, 'block_reason', None)
                if br:
                    diag_parts.append(f"prompt_block_reason={br}")
                sr = getattr(pf, 'safety_ratings', None)
                if sr:
                    diag_parts.append(f"prompt_safety={sr}")
            # 检查 candidate 级别的拦截
            candidates = getattr(last_chunk, 'candidates', None)
            if candidates:
                for i, c in enumerate(candidates):
                    fr = getattr(c, 'finish_reason', None)
                    sr = getattr(c, 'safety_ratings', None)
                    if fr:
                        diag_parts.append(f"candidate[{i}].finish_reason={fr}")
                    if sr:
                        diag_parts.append(f"candidate[{i}].safety={sr}")
            elif candidates is not None:
                diag_parts.append("candidates=[]（无候选结果）")
            logger.warning(f"Gemini 原生 SDK 返回空内容，诊断: {'; '.join(diag_parts) or '无额外信息'}")

        return ''.join(chunks), actual_messages

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        max_retries: int = 3
    ) -> str:
        """
        发送聊天请求（带重试）

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            max_retries: 最大重试次数

        Returns:
            模型响应文本
        """
        # Google AI Studio → 始终走原生 SDK 路径
        use_gemini_native = self._is_gemini_url()

        # OpenAI 路径也支持 wrapper
        actual_messages = messages
        if not use_gemini_native:
            from ..services.prompt_config import PROMPT_DEFAULTS, _overrides
            wk = 'content_wrapper_llm'
            wm = _overrides.get(wk, {}).get('messages', PROMPT_DEFAULTS.get(wk, {}).get('messages', []))
            if wm:
                system_parts = [m['content'] for m in messages if m['role'] == 'system']
                user_parts = [m['content'] for m in messages if m['role'] in ('user', 'assistant')]
                combined = '\n\n'.join(user_parts)
                actual_messages = []
                if system_parts:
                    actual_messages.append({'role': 'system', 'content': '\n\n'.join(system_parts)})
                for w in wm:
                    role = w.get('role', 'user')
                    # 角色映射：model → assistant, system_instruction → system
                    if role in ('model', 'assistant'):
                        role = 'assistant'
                    elif role == 'system_instruction':
                        role = 'system'
                    actual_messages.append({'role': role, 'content': w.get('content', '').replace('{user_content}', combined)})

        kwargs = {
            "model": self.model,
            "messages": actual_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        last_error = None
        log_messages = messages  # 默认记录原始消息，Gemini 路径会替换为包装后的
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                if use_gemini_native:
                    content, log_messages = self._chat_gemini_native(messages, temperature, max_tokens, response_format)
                else:
                    log_messages = actual_messages
                    chunks = []
                    with self.client.chat.completions.create(**kwargs, stream=True) as stream:
                        for chunk in stream:
                            delta = chunk.choices[0].delta.content if chunk.choices else None
                            if delta:
                                chunks.append(delta)
                    content = "".join(chunks)
                if not content.strip():
                    raise ValueError("LLM 返回空内容")
                duration_ms = (time.time() - start_time) * 1000
                monitor.log_full(source="LLMClient", model=self.model, messages=log_messages, kwargs={"temperature": temperature, "max_tokens": max_tokens}, response=content, duration_ms=duration_ms)
                return content
            except Exception as e:
                last_error = e
                wait = 2 * (attempt + 1)
                logger.warning(f"LLM调用失败 (attempt {attempt+1}/{max_retries}): {str(e)[:100]}，{wait}秒后重试")
                if attempt < max_retries - 1:
                    time.sleep(wait)

        duration_ms = (time.time() - start_time) * 1000
        monitor.log_full(source="LLMClient", model=self.model, messages=log_messages, kwargs={"temperature": temperature, "max_tokens": max_tokens}, duration_ms=duration_ms, error=str(last_error))
        raise last_error

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON

        通过在 prompt 中要求返回 JSON，兼容不支持 response_format 的 API。

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            解析后的JSON对象
        """
        # 在最后一条消息后追加 JSON 格式要求
        patched_messages = []
        for msg in messages:
            patched_messages.append(dict(msg))

        # 给 system 消息追加 JSON 约束，如果没有 system 则插入一条
        json_instruction = "\n\n【重要】请只返回合法的 JSON 对象，不要包含 ```json 代码块标记或任何其他非 JSON 文本。"
        has_system = False
        for msg in patched_messages:
            if msg["role"] == "system":
                msg["content"] += json_instruction
                has_system = True
                break
        if not has_system:
            patched_messages.insert(0, {"role": "system", "content": json_instruction.strip()})

        response = self.chat(
            messages=patched_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        extracted = self._extract_json(response)
        try:
            return json.loads(extracted)
        except json.JSONDecodeError as e:
            # 尝试用 json_repair 修复常见 LLM 输出问题（缺逗号、多余逗号等）
            try:
                from json_repair import repair_json
                repaired = repair_json(extracted, return_objects=True)
                if isinstance(repaired, dict):
                    logger.warning(f"JSON自动修复成功（原始错误: {e}）")
                    return repaired
            except Exception:
                pass
            # 判断是否因 max_tokens 截断导致 JSON 不完整
            stripped = response.strip()
            truncated = stripped and not stripped.endswith(('}', ']', '"'))
            hint = "（响应被 max_tokens 截断，请提高 max_tokens）" if truncated else ""
            logger.error(f"JSON解析失败{hint}: {e}\nLLM原始响应 (前1500字): {response[:1500]!r}")
            raise

    @staticmethod
    def _extract_json(text: str) -> str:
        """从 LLM 响应中提取 JSON，处理 CoT 推理文字、markdown 代码块（含截断情况）"""
        import re
        text = text.strip()
        # 0. 检测并截断重复闭合括号的病态输出（如 "\n}\n}\n}\n}..."）
        #    某些模型在 json_object 模式下 max_tokens 过大时会产生此问题
        repeat_match = re.search(r'(\n\s*\}\s*){5,}', text)
        if repeat_match:
            # 保留到重复段起始位置 + 一个闭合括号
            text = text[:repeat_match.start()] + '\n}'
            logger.warning(f"检测到重复闭合括号病态输出，已截断至 {len(text)} 字符")
        # 1. 优先匹配完整的 ```json ... ``` 或 ``` ... ``` 代码块
        m = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 2. 处理截断的代码块（只有开头 ``` 没有结尾 ```）
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        # 3. 找第一个 { 并用括号计数匹配对应的结尾 }（防止 LLM 在 JSON 后追加文字）
        start = text.find('{')
        if start != -1:
            depth = 0
            in_string = False
            escape = False
            for i, ch in enumerate(text[start:], start):
                if escape:
                    escape = False
                    continue
                if ch == '\\' and in_string:
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
        return text

