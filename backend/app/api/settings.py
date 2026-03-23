"""
设置 API 路由 — Prompt 配置管理 & 叙事引擎配置
"""

import os

from flask import request, jsonify

from . import settings_bp
from ..config import Config
from ..services.prompt_config import list_prompts, update_prompt, reset_prompt, PROMPT_DEFAULTS, PROMPT_VARIABLES
from ..services.narrative_engine_config import (
    list_settings as ne_list_settings,
    update_setting as ne_update_setting,
    reset_setting as ne_reset_setting,
    DEFAULTS as NE_DEFAULTS,
)
from ..utils.logger import get_logger

# .env 文件路径（backend/app/api/ 向上三级到项目根）
_ENV_FILE = os.path.realpath(os.path.join(os.path.dirname(__file__), '../../../.env'))

# 允许前端读写的 .env 键
_ENV_KEYS = [
    'LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL_NAME',
    'LLM_GEMINI_SAFETY_BLOCK_NONE', 'LLM_USE_GOOGLE_SDK',
    'EMBEDDING_API_KEY', 'EMBEDDING_BASE_URL', 'EMBEDDING_MODEL_NAME',
    'ZEP_API_KEY',
    'FALKORDB_HOST', 'FALKORDB_PORT', 'FALKORDB_PASSWORD',
]


def _write_env(updates: dict):
    """将 updates 中的 key=value 写入 .env 文件，保留注释和其他行不变。"""
    lines = []
    updated_keys = set()
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE, 'r', encoding='utf-8') as f:
            raw_lines = f.readlines()
        for line in raw_lines:
            stripped = line.rstrip('\r\n')
            if stripped and not stripped.startswith('#'):
                eq_idx = stripped.find('=')
                if eq_idx > 0:
                    key = stripped[:eq_idx].strip()
                    if key in updates:
                        lines.append(f'{key}={updates[key]}\n')
                        updated_keys.add(key)
                        continue
            lines.append(line if line.endswith('\n') else line + '\n')
    # 追加 .env 中不存在的新 key
    for key, val in updates.items():
        if key not in updated_keys:
            lines.append(f'{key}={val}\n')
    with open(_ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def _reload_config():
    """将 os.environ 的最新值同步回 Config 类属性。"""
    Config.LLM_API_KEY = os.environ.get('LLM_API_KEY')
    Config.LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    Config.LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    Config.LLM_GEMINI_SAFETY_BLOCK_NONE = os.environ.get('LLM_GEMINI_SAFETY_BLOCK_NONE', 'false').lower() == 'true'
    Config.LLM_USE_GOOGLE_SDK = os.environ.get('LLM_USE_GOOGLE_SDK', 'auto').lower()
    Config.EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY')
    Config.EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL') or os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    Config.EMBEDDING_MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'text-embedding-3-small')
    Config.ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    Config.FALKORDB_HOST = os.environ.get('FALKORDB_HOST', 'localhost')
    Config.FALKORDB_PORT = int(os.environ.get('FALKORDB_PORT', '6379'))
    Config.FALKORDB_PASSWORD = os.environ.get('FALKORDB_PASSWORD', '')

logger = get_logger('agars.api.settings')


@settings_bp.route('/prompts', methods=['GET'])
def get_all_prompts():
    """获取所有 prompt 配置"""
    try:
        prompts = list_prompts()
        return jsonify({"success": True, "data": prompts})
    except Exception as e:
        logger.error(f"获取 prompt 配置失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route('/prompt-variables', methods=['GET'])
def get_prompt_variables():
    """获取 Prompt 变量参考表（按 narrative / oasis / common 分类）"""
    return jsonify({"success": True, "data": PROMPT_VARIABLES})


@settings_bp.route('/prompts/<key>', methods=['PUT'])
def update_single_prompt(key):
    """更新单个 prompt"""
    try:
        if key not in PROMPT_DEFAULTS:
            return jsonify({"success": False, "error": f"未知的 prompt: {key}"}), 404

        data = request.get_json()
        system = data.get('system')
        template = data.get('template')
        temperature = data.get('temperature')
        max_tokens = data.get('max_tokens')
        api_key = data.get('api_key')
        base_url = data.get('base_url')
        model = data.get('model')
        messages = data.get('messages')  # 扩展字段：多轮对话数组

        if all(v is None for v in [system, template, temperature, max_tokens, api_key, base_url, model, messages]):
            return jsonify({"success": False, "error": "需要提供至少一个字段"}), 400

        update_prompt(key, system=system, template=template, temperature=temperature,
                      max_tokens=max_tokens, api_key=api_key, base_url=base_url, model=model,
                      messages=messages)

        return jsonify({"success": True, "message": f"已更新: {key}"})

    except Exception as e:
        logger.error(f"更新 prompt 失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route('/llm-profiles', methods=['GET'])
def get_llm_profiles():
    """获取所有可用的 LLM 配置 profile（从 .env 读取）"""
    try:
        profiles = Config.get_llm_profiles()
        result = []
        for name, cfg in profiles.items():
            result.append({
                "name": name,
                "model": cfg.get("model", ""),
                "base_url": cfg.get("base_url", ""),
                "has_key": bool(cfg.get("api_key")),
                "configured": cfg.get("configured", False),
            })
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.error(f"获取 LLM profile 失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route('/prompts/reset', methods=['POST'])
def reset_prompts():
    """重置 prompt 到默认值"""
    try:
        data = request.get_json() or {}
        key = data.get('key')  # None = 重置全部
        reset_prompt(key)
        return jsonify({"success": True, "message": f"已重置: {key or '全部'}"})
    except Exception as e:
        logger.error(f"重置 prompt 失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 叙事引擎配置
# ============================================================

@settings_bp.route('/narrative-engine', methods=['GET'])
def get_narrative_engine_settings():
    """获取叙事引擎所有配置"""
    try:
        settings = ne_list_settings()
        return jsonify({"success": True, "data": settings})
    except Exception as e:
        logger.error(f"获取叙事引擎配置失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route('/narrative-engine/<key>', methods=['PUT'])
def update_narrative_engine_setting(key):
    """更新单个叙事引擎配置"""
    try:
        if key not in NE_DEFAULTS:
            return jsonify({"success": False, "error": f"未知的配置: {key}"}), 404
        data = request.get_json()
        value = data.get('value')
        if value is None:
            return jsonify({"success": False, "error": "需要提供 value"}), 400
        ne_update_setting(key, value)
        return jsonify({"success": True, "message": f"已更新: {key}"})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error(f"更新叙事引擎配置失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route('/narrative-engine/reset', methods=['POST'])
def reset_narrative_engine_settings():
    """重置叙事引擎配置"""
    try:
        data = request.get_json() or {}
        key = data.get('key')
        ne_reset_setting(key)
        return jsonify({"success": True, "message": f"已重置: {key or '全部'}"})
    except Exception as e:
        logger.error(f"重置叙事引擎配置失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# 全局 API 配置（直接读写 .env）
# ============================================================

@settings_bp.route('/fetch-models', methods=['POST'])
def fetch_models():
    """通过指定的 base_url 和 api_key 拉取可用模型列表"""
    try:
        data = request.get_json() or {}
        base_url = (data.get('base_url') or '').strip() or Config.LLM_BASE_URL
        api_key = (data.get('api_key') or '').strip() or Config.LLM_API_KEY or 'placeholder'

        import openai as _openai
        client = _openai.OpenAI(api_key=api_key, base_url=base_url, timeout=10.0)
        models_page = client.models.list()
        model_ids = sorted([m.id for m in models_page.data])
        return jsonify({"success": True, "data": model_ids})
    except Exception as e:
        logger.error(f"拉取模型列表失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@settings_bp.route('/env-config', methods=['GET'])
def get_env_config():
    """读取 .env 中的基础 API 配置当前值"""
    try:
        data = {k: os.environ.get(k, '') for k in _ENV_KEYS}
        return jsonify({"success": True, "data": data})
    except Exception as e:
        logger.error(f"读取 env 配置失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@settings_bp.route('/env-config', methods=['POST'])
def update_env_config():
    """将基础 API 配置写入 .env，并热更新运行中的 Config"""
    try:
        body = request.get_json() or {}
        updates = {k: str(v) for k, v in body.items() if k in _ENV_KEYS}
        if not updates:
            return jsonify({"success": False, "error": "没有有效的配置项"}), 400

        _write_env(updates)

        # 热更新 os.environ
        for k, v in updates.items():
            os.environ[k] = v

        # 同步回 Config 类属性
        _reload_config()

        # 清空 LLMClient 缓存，让新配置立即生效
        from ..utils.llm_client import _client_cache
        _client_cache.clear()

        return jsonify({"success": True, "message": "已保存，新配置立即生效"})
    except Exception as e:
        logger.error(f"更新 env 配置失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500
