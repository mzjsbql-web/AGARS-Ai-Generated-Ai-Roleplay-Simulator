"""
兼容第三方 OpenAI API 代理的 LLM Client

使用 strict: False，不需要 OpenAI strict mode 的约束（additionalProperties/全字段required）。
主要修补内容：
1. 内联展开 $ref/$defs（Google AI Studio 不支持）
2. 移除 title（Google AI Studio 不接受）
3. 将 anyOf: [X, null] 转为 nullable: true（Gemini 不支持 type: null）
4. 移除 default（部分 API 不接受）
"""

import asyncio
import copy
import json
import logging
import time as _time
import typing
from typing import Any

import openai
from pydantic import BaseModel
from openai.types.chat import ChatCompletionMessageParam

logger = logging.getLogger('agars.llm_compat')

from graphiti_core.llm_client.openai_generic_client import (
    OpenAIGenericClient,
    DEFAULT_MODEL,
)
from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, ModelSize
from graphiti_core.llm_client.errors import RateLimitError
from graphiti_core.prompts.models import Message

from ..utils.llm_monitor import monitor


# wrapper messages 中 role 的统一映射
# 用户在配置里写 user/assistant/model 均可，代码按目标 SDK 自动转换
def _map_role_to_gemini(role: str) -> str:
    """assistant → model（Gemini 原生 SDK 用 model）"""
    return 'model' if role in ('assistant', 'model') else role

def _map_role_to_openai(role: str) -> str:
    """model → assistant, system_instruction → system（OpenAI 兼容端点）"""
    if role in ('model', 'assistant'):
        return 'assistant'
    if role == 'system_instruction':
        return 'system'
    return role

def _get_wrapper_messages(wrapper_key: str) -> list:
    """从 prompt_config 读取 wrapper 的 messages 数组"""
    from .prompt_config import PROMPT_DEFAULTS, _overrides
    _ov = _overrides.get(wrapper_key, {})
    _df = PROMPT_DEFAULTS.get(wrapper_key, {})
    return _ov.get('messages', _df.get('messages', []))


def _fix_schema(schema: dict) -> dict:
    """
    递归修补 JSON Schema：移除 default（部分 API 不接受），处理 $defs 和嵌套结构。
    不添加 additionalProperties 也不覆盖 required——strict: False 下无需这两项约束，
    强加反而会导致 Gemini 服务端拒绝模型的合法输出（message=None）。
    """
    if not isinstance(schema, dict):
        return schema

    # 处理 $defs（Pydantic 把嵌套模型放在这里）
    if '$defs' in schema:
        for def_name, def_schema in schema['$defs'].items():
            _fix_schema(def_schema)

    # 递归处理每个 property，仅移除 default
    for prop_schema in schema.get('properties', {}).values():
        prop_schema.pop('default', None)
        _fix_schema(prop_schema)

    # 处理 array 的 items
    if 'items' in schema and isinstance(schema['items'], dict):
        _fix_schema(schema['items'])

    # 处理 anyOf / oneOf
    for combiner in ('anyOf', 'oneOf'):
        if combiner in schema:
            for sub_schema in schema[combiner]:
                if isinstance(sub_schema, dict):
                    _fix_schema(sub_schema)

    return schema


def _inline_refs(node: dict, defs: dict) -> dict:
    """递归内联 $ref 引用。"""
    if not isinstance(node, dict):
        return node

    if '$ref' in node:
        ref = node['$ref']
        if ref.startswith('#/$defs/'):
            def_name = ref[len('#/$defs/'):]
            if def_name in defs:
                resolved = copy.deepcopy(defs[def_name])
                # 合并 $ref 节点上的其他字段（如有）
                for k, v in node.items():
                    if k != '$ref':
                        resolved[k] = v
                return _inline_refs(resolved, defs)
        return node

    result = {}
    for key, value in node.items():
        if key in ('$defs', 'title'):
            continue  # 移除 $defs 和 title（API 不需要）
        elif isinstance(value, dict):
            result[key] = _inline_refs(value, defs)
        elif isinstance(value, list):
            result[key] = [
                _inline_refs(item, defs) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def _resolve_refs(schema: dict) -> dict:
    """
    将 JSON Schema 中的 $ref 引用内联展开，消除 $defs。
    Google AI Studio 等不支持 $ref，需要完全展开后再发送。
    """
    defs = schema.get('$defs', {})
    return _inline_refs(schema, defs)


def _convert_nullable(node: dict) -> dict:
    """
    将 anyOf: [schema, {type: "null"}] 转换为 {...schema, nullable: true}。

    Gemini API 的合法 type 只有 string/number/integer/boolean/object/array，
    不支持 type: "null"。Pydantic 对 Optional 字段（str | None）生成的
    anyOf: [{type: "string"}, {type: "null"}] 需要转成 OpenAPI 3.0 的
    nullable: true 形式才能被 Gemini 接受。
    """
    if not isinstance(node, dict):
        return node

    if 'anyOf' in node:
        any_of = node['anyOf']
        null_schemas = [s for s in any_of if isinstance(s, dict) and s.get('type') == 'null']
        non_null_schemas = [s for s in any_of if not (isinstance(s, dict) and s.get('type') == 'null')]

        if null_schemas and len(non_null_schemas) == 1:
            # anyOf: [oneSchema, null] → 展开为顶层 + nullable: true
            result = {k: v for k, v in node.items() if k != 'anyOf'}
            for k, v in non_null_schemas[0].items():
                if k not in result:
                    result[k] = v
            result['nullable'] = True
            return _convert_nullable(result)
        elif null_schemas:
            # anyOf 有多个非 null 项 + null → 保留 anyOf，移除 null 项，加 nullable
            result = {k: v for k, v in node.items() if k != 'anyOf'}
            result['anyOf'] = [_convert_nullable(s) for s in non_null_schemas]
            result['nullable'] = True
            return result

    result = {}
    for key, value in node.items():
        if isinstance(value, dict):
            result[key] = _convert_nullable(value)
        elif isinstance(value, list):
            result[key] = [
                _convert_nullable(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class CompatOpenAIClient(OpenAIGenericClient):
    """OpenAIGenericClient with schema fix for third-party API proxies."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 默认 read timeout 是 600s，API 代理偶尔无响应会导致 asyncio.gather 永久挂起
        self.client = self.client.with_options(timeout=60.0)
        import os
        self._disable_json_schema = os.environ.get('LLM_DISABLE_JSON_SCHEMA', 'false').lower() == 'true'
        # Gemini 内容过滤：OpenAI 兼容端点不支持 safety_settings，
        # 遇到 content_filter 时降级到原生 google-genai SDK 重试
        from ..config import Config
        _mode = Config.LLM_USE_GOOGLE_SDK  # 'auto', 'true', 'false'
        if _mode == 'true':
            self._is_gemini = True
        elif _mode == 'false':
            self._is_gemini = False
        else:
            self._is_gemini = 'generativelanguage.googleapis.com' in str(self.client.base_url or '')
        self._safety_block_none = os.environ.get('LLM_GEMINI_SAFETY_BLOCK_NONE', 'false').lower() == 'true'
        self._genai_client = None  # 按需初始化

    async def _call_gemini_native(
        self,
        messages: list[Message],
        model_name: str,
        response_model: type[BaseModel] | None = None,
    ) -> str:
        """用原生 google-genai SDK 调用，支持 safety_settings BLOCK_NONE + 结构化输出。"""
        from google import genai
        from google.genai import types

        if self._genai_client is None:
            self._genai_client = genai.Client(api_key=self.client.api_key)

        system_instruction = None
        user_parts = []
        for m in messages:
            if m.role == 'system':
                system_instruction = m.content
            elif m.role == 'user':
                user_parts.append(m.content)

        combined_user_text = '\n\n'.join(user_parts)

        wrapper_key = 'content_wrapper_graph'
        wrap_messages = _get_wrapper_messages(wrapper_key)

        if wrap_messages:
            contents = []
            for msg in wrap_messages:
                role = msg.get('role', 'user')
                text = msg.get('content', '').replace('{user_content}', combined_user_text)
                if role == 'system_instruction':
                    # system_instruction 是 Gemini 的特殊参数，不放入 contents
                    system_instruction = text
                else:
                    contents.append(types.Content(
                        role=_map_role_to_gemini(role),
                        parts=[types.Part(text=text)],
                    ))
        else:
            contents = [
                types.Content(role='user', parts=[types.Part(text=combined_user_text)]),
            ]

        # 记录实际发送内容到 monitor，方便前端面板调试
        _sent_messages = [
            {'role': 'system', 'content': system_instruction or ''},
        ] + [
            {'role': c.role, 'content': c.parts[0].text} for c in contents
        ]
        monitor.log_full(
            source='CompatOpenAIClient.gemini_native',
            model=model_name,
            messages=_sent_messages,
            kwargs={'wrapper': wrapper_key, 'has_schema': response_model is not None},
        )

        config_kwargs: dict[str, Any] = dict(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            response_mime_type='application/json',
        )
        if self._safety_block_none:
            config_kwargs['safety_settings'] = [
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_CIVIC_INTEGRITY', threshold='BLOCK_NONE'),
            ]
        if system_instruction:
            config_kwargs['system_instruction'] = system_instruction
        # 传清理后的 JSON Schema 字典（不传 Pydantic 类，避免动态模型/default 等兼容问题）
        if response_model is not None:
            config_kwargs['response_json_schema'] = _convert_nullable(
                _resolve_refs(_fix_schema(response_model.model_json_schema()))
            )

        config = types.GenerateContentConfig(**config_kwargs)

        def _sync_call():
            resp = self._genai_client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            if resp.text:
                return resp.text

            # 诊断空响应原因
            candidates = resp.candidates or []
            if candidates:
                c = candidates[0]
                reason = getattr(c, 'finish_reason', None)
                logger.warning(f'原生SDK返回空text: finish_reason={reason}')
            else:
                feedback = getattr(resp, 'prompt_feedback', None)
                block_reason = getattr(feedback, 'block_reason', None) if feedback else None
                logger.warning(f'原生SDK返回无candidates: block_reason={block_reason}')
                # PROHIBITED_CONTENT 是 Google 绝对策略，BLOCK_NONE 无法覆盖，重试无意义
                if block_reason and 'PROHIBITED_CONTENT' in str(block_reason):
                    logger.warning('PROHIBITED_CONTENT: 跳过此 chunk，返回空结果')
                    return '{}'
            return ''

        return await asyncio.to_thread(_sync_call)

    async def _call_openai_compat(
        self,
        messages: list[Message],
        model_name: str,
        response_model: type[BaseModel] | None,
    ) -> str:
        """通过 OpenAI 兼容端点调用，返回原始 JSON 字符串。"""
        wrap_messages = _get_wrapper_messages('content_wrapper_graph')

        openai_messages: list[ChatCompletionMessageParam] = []
        if wrap_messages:
            system_parts = []
            user_parts = []
            for m in messages:
                if m.role == 'system':
                    system_parts.append(m.content)
                elif m.role == 'user':
                    user_parts.append(m.content)
            if system_parts:
                openai_messages.append({'role': 'system', 'content': '\n\n'.join(system_parts)})
            combined = '\n\n'.join(user_parts)
            for wm in wrap_messages:
                role = _map_role_to_openai(wm.get('role', 'user'))
                text = wm.get('content', '').replace('{user_content}', combined)
                openai_messages.append({'role': role, 'content': text})
        else:
            for m in messages:
                if m.role == 'user':
                    openai_messages.append({'role': 'user', 'content': m.content})
                elif m.role == 'system':
                    openai_messages.append({'role': 'system', 'content': m.content})

        response_format: dict[str, Any] = {'type': 'json_object'}
        if response_model is not None and not self._disable_json_schema:
            # OpenAI 兼容端点：只做 $ref 展开和 default 清理，保留标准 anyOf null 语义
            # _convert_nullable 仅用于 Gemini 原生路径（Gemini 不支持 type: null）
            json_schema = _resolve_refs(_fix_schema(response_model.model_json_schema()))
            response_format = {
                'type': 'json_schema',
                'json_schema': {
                    'name': getattr(response_model, '__name__', 'structured_response'),
                    'schema': json_schema,
                    'strict': False,
                },
            }

        response = await self.client.chat.completions.create(
            model=model_name,
            messages=openai_messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format=response_format,  # type: ignore[arg-type]
        )
        if not response.choices:
            raise ValueError(f'LLM返回无choices: {response}')
        choice = response.choices[0]
        if choice.message is None:
            raise ValueError(f'LLM返回空消息(message=None): finish_reason={choice.finish_reason}')
        return choice.message.content or ''

    @property
    def _use_gemini_native(self) -> bool:
        """Google AI Studio 始终走原生 SDK"""
        return self._is_gemini

    async def _generate_response(
        self,
        messages: list[Message],
        response_model: type[BaseModel] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        model_size: ModelSize = ModelSize.medium,
    ) -> dict[str, typing.Any]:
        for m in messages:
            m.content = self._clean_input(m.content)

        model_name = self.model or DEFAULT_MODEL
        schema_name = getattr(response_model, '__name__', 'json_object') if response_model else 'json_object'
        logger.info(f'LLM请求: model={model_name}, schema={schema_name}')

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                _start = _time.time()
                if self._use_gemini_native:
                    result = await self._call_gemini_native(messages, model_name, response_model)
                else:
                    result = await self._call_openai_compat(messages, model_name, response_model)
                _dur = (_time.time() - _start) * 1000
                if not result:
                    raise ValueError('LLM返回空内容')
                parsed = json.loads(result)
                _keys = list(parsed.keys()) if isinstance(parsed, dict) else f'[list len={len(parsed)}]'
                logger.info(f'LLM响应: schema={schema_name}, keys={_keys}, len={len(result)}')
                monitor.log_full(source="CompatOpenAIClient", model=model_name, messages=[{"role": m.role, "content": m.content} for m in messages], kwargs={"schema": schema_name}, response=result, duration_ms=_dur)
                return parsed
            except openai.RateLimitError as e:
                logger.error(f'LLM速率限制: {e}')
                raise RateLimitError from e
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 10 * (attempt + 1)
                    logger.warning(f'LLM请求失败，{wait}s后重试 ({attempt+1}/3): {e}')
                    await asyncio.sleep(wait)
                else:
                    logger.error(f'LLM请求失败: {e}')
                    monitor.log_full(source="CompatOpenAIClient", model=model_name, messages=[{"role": m.role, "content": m.content} for m in messages], error=str(e))

        raise last_error  # type: ignore[misc]
