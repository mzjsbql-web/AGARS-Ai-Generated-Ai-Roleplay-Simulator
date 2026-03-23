"""
叙事引擎配置中心
管理叙事引擎的可配置参数，支持 JSON 持久化
"""

import os
import json
from typing import Dict, Any, Optional

from ..utils.logger import get_logger

logger = get_logger('agars.narrative_engine_config')

# ============================================================
# 默认值定义
# ============================================================

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "previous_narrative_count": {
        "label": "前情段落数",
        "description": "正文/选项可读的前情叙事段落数量",
        "default": 3,
        "min": 1,
        "max": 10,
    },
    "previous_narrative_max_chars": {
        "label": "前情最大字数",
        "description": "前情回顾文本的最大字符数",
        "default": 1500,
        "min": 500,
        "max": 5000,
    },
    "events_text_count": {
        "label": "玩家场景全局事件数",
        "description": "玩家场景可读的全局事件数量",
        "default": 15,
        "min": 5,
        "max": 50,
    },
    "npc_global_events_count": {
        "label": "NPC全局事件数",
        "description": "NPC可读的全局事件数量",
        "default": 10,
        "min": 5,
        "max": 30,
    },
    "npc_own_actions_count": {
        "label": "NPC自身行动数",
        "description": "NPC可读的自身历史行动数量",
        "default": 5,
        "min": 1,
        "max": 15,
    },
}

# ============================================================
# JSON 持久化
# ============================================================

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'narrative_engine_config.json'
)

_overrides: Dict[str, Any] = {}


def _load_overrides():
    global _overrides
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                _overrides = json.load(f)
            logger.info(f"已加载叙事引擎配置: {len(_overrides)} 项")
    except Exception as e:
        logger.warning(f"加载叙事引擎配置失败: {e}")
        _overrides = {}


def _save_overrides():
    try:
        with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(_overrides, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存叙事引擎配置失败: {e}")


_load_overrides()

# ============================================================
# 公共 API
# ============================================================


def get_setting(key: str) -> Any:
    """获取单个配置值（用户覆盖优先，否则默认值）"""
    if key in _overrides:
        return _overrides[key]
    default_def = DEFAULTS.get(key)
    if default_def:
        return default_def["default"]
    raise ValueError(f"未知的配置 key: {key}")


def list_settings() -> list:
    """列出所有配置（用于设置页面）"""
    result = []
    for key, meta in DEFAULTS.items():
        result.append({
            "key": key,
            "label": meta["label"],
            "description": meta["description"],
            "value": _overrides.get(key, meta["default"]),
            "default": meta["default"],
            "min": meta["min"],
            "max": meta["max"],
            "is_modified": key in _overrides,
        })
    return result


def update_setting(key: str, value: Any):
    """更新单个配置"""
    if key not in DEFAULTS:
        raise ValueError(f"未知的配置 key: {key}")
    meta = DEFAULTS[key]
    value = int(value)
    if value < meta["min"] or value > meta["max"]:
        raise ValueError(f"{key} 的值必须在 {meta['min']}-{meta['max']} 之间，当前: {value}")
    _overrides[key] = value
    _save_overrides()
    logger.info(f"叙事引擎配置已更新: {key} = {value}")


def reset_setting(key: Optional[str] = None):
    """重置配置到默认值"""
    if key:
        _overrides.pop(key, None)
    else:
        _overrides.clear()
    _save_overrides()
    logger.info(f"叙事引擎配置已重置: {key or '全部'}")
