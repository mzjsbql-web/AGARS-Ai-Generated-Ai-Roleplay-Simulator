"""
Preset 管理器
支持将当前 prompt 配置 + 叙事引擎配置导出为 preset，以及从 preset 导入恢复。
Preset 以 JSON 文件存储在 backend/presets/ 目录下。
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List

from ..utils.logger import get_logger

logger = get_logger('agars.preset_manager')

# ============================================================
# 路径
# ============================================================

_PRESETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'presets'
)

# 确保目录存在
os.makedirs(_PRESETS_DIR, exist_ok=True)


# ============================================================
# Preset 文件格式
# ============================================================
# {
#   "id": "uuid",
#   "name": "My Preset",
#   "description": "...",
#   "created_at": 1700000000,
#   "updated_at": 1700000000,
#   "is_default": false,
#   "prompts": { ... },             # prompts_config.json 的内容
#   "narrative_engine": { ... }     # narrative_engine_config.json 的内容
# }


def _preset_path(preset_id: str) -> str:
    """安全获取 preset 文件路径"""
    # 防止路径穿越
    safe_id = os.path.basename(preset_id)
    return os.path.join(_PRESETS_DIR, f'{safe_id}.json')


def _read_preset(preset_id: str) -> Optional[Dict[str, Any]]:
    path = _preset_path(preset_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"读取 preset 失败 [{preset_id}]: {e}")
        return None


def _write_preset(data: Dict[str, Any]):
    path = _preset_path(data['id'])
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_current_prompts_overrides() -> Dict[str, Any]:
    """读取当前 prompts_config.json"""
    from .prompt_config import _CONFIG_PATH
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _get_current_ne_overrides() -> Dict[str, Any]:
    """读取当前 narrative_engine_config.json"""
    from .narrative_engine_config import _CONFIG_PATH
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _apply_prompts_overrides(data: Dict[str, Any]):
    """将 preset 中的 prompts 覆盖写入并重载"""
    from .prompt_config import _CONFIG_PATH, _load_overrides
    with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _load_overrides()


def _apply_ne_overrides(data: Dict[str, Any]):
    """将 preset 中的叙事引擎覆盖写入并重载"""
    from .narrative_engine_config import _CONFIG_PATH, _load_overrides
    with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _load_overrides()


# ============================================================
# 默认 preset 初始化
# ============================================================

_DEFAULT_PRESET_ID = 'default'


def _ensure_default_preset():
    """确保存在一个 default preset（所有覆盖为空 = 纯默认值）"""
    path = _preset_path(_DEFAULT_PRESET_ID)
    if not os.path.exists(path):
        _write_preset({
            'id': _DEFAULT_PRESET_ID,
            'name': '默认配置',
            'description': '系统默认配置，未做任何自定义修改',
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
            'is_default': True,
            'prompts': {},
            'narrative_engine': {},
        })
        logger.info("已创建默认 preset")


_ensure_default_preset()


# ============================================================
# 公共 API
# ============================================================


def list_presets() -> List[Dict[str, Any]]:
    """列出所有 preset（摘要信息，不含完整配置数据）"""
    result = []
    for fname in os.listdir(_PRESETS_DIR):
        if not fname.endswith('.json'):
            continue
        preset_id = fname[:-5]
        data = _read_preset(preset_id)
        if data:
            result.append({
                'id': data['id'],
                'name': data.get('name', preset_id),
                'description': data.get('description', ''),
                'created_at': data.get('created_at', 0),
                'updated_at': data.get('updated_at', 0),
                'is_default': data.get('is_default', False),
            })
    # 默认 preset 排最前，其余按更新时间倒序
    result.sort(key=lambda x: (not x['is_default'], -x['updated_at']))
    return result


def get_preset(preset_id: str) -> Optional[Dict[str, Any]]:
    """获取单个 preset 的完整数据"""
    return _read_preset(preset_id)


def create_preset(name: str, description: str = '') -> Dict[str, Any]:
    """将当前设置导出为新 preset"""
    preset_id = uuid.uuid4().hex[:12]
    now = int(time.time())
    data = {
        'id': preset_id,
        'name': name,
        'description': description,
        'created_at': now,
        'updated_at': now,
        'is_default': False,
        'prompts': _get_current_prompts_overrides(),
        'narrative_engine': _get_current_ne_overrides(),
    }
    _write_preset(data)
    logger.info(f"Preset 已创建: {name} ({preset_id})")
    return data


def update_preset(preset_id: str, name: Optional[str] = None,
                  description: Optional[str] = None) -> Dict[str, Any]:
    """更新 preset 的元信息，并用当前配置覆盖其内容"""
    data = _read_preset(preset_id)
    if not data:
        raise ValueError(f"Preset 不存在: {preset_id}")
    if data.get('is_default'):
        raise ValueError("默认 preset 不可修改")

    if name is not None:
        data['name'] = name
    if description is not None:
        data['description'] = description
    data['updated_at'] = int(time.time())
    # 用当前设置覆盖
    data['prompts'] = _get_current_prompts_overrides()
    data['narrative_engine'] = _get_current_ne_overrides()
    _write_preset(data)
    logger.info(f"Preset 已更新: {data['name']} ({preset_id})")
    return data


def delete_preset(preset_id: str):
    """删除 preset"""
    data = _read_preset(preset_id)
    if not data:
        raise ValueError(f"Preset 不存在: {preset_id}")
    if data.get('is_default'):
        raise ValueError("默认 preset 不可删除")
    path = _preset_path(preset_id)
    os.remove(path)
    logger.info(f"Preset 已删除: {data.get('name', preset_id)} ({preset_id})")


def apply_preset(preset_id: str):
    """应用 preset，将其配置写入当前环境"""
    data = _read_preset(preset_id)
    if not data:
        raise ValueError(f"Preset 不存在: {preset_id}")

    _apply_prompts_overrides(data.get('prompts', {}))
    _apply_ne_overrides(data.get('narrative_engine', {}))
    logger.info(f"Preset 已应用: {data.get('name', preset_id)} ({preset_id})")


def import_preset(preset_data: Dict[str, Any]) -> Dict[str, Any]:
    """从导入的 JSON 数据创建 preset"""
    # 验证必要字段
    if 'name' not in preset_data:
        raise ValueError("导入的 preset 缺少 name 字段")

    # 生成新 ID，避免冲突
    preset_id = uuid.uuid4().hex[:12]
    now = int(time.time())
    data = {
        'id': preset_id,
        'name': preset_data['name'],
        'description': preset_data.get('description', ''),
        'created_at': preset_data.get('created_at', now),
        'updated_at': now,
        'is_default': False,
        'prompts': preset_data.get('prompts', {}),
        'narrative_engine': preset_data.get('narrative_engine', {}),
    }
    _write_preset(data)
    logger.info(f"Preset 已导入: {data['name']} ({preset_id})")
    return data


def export_preset(preset_id: str) -> Dict[str, Any]:
    """导出 preset 为可分享的 JSON 数据"""
    data = _read_preset(preset_id)
    if not data:
        raise ValueError(f"Preset 不存在: {preset_id}")
    # 导出时移除内部 ID，导入时会重新生成
    export = {
        'name': data['name'],
        'description': data.get('description', ''),
        'created_at': data.get('created_at', 0),
        'prompts': data.get('prompts', {}),
        'narrative_engine': data.get('narrative_engine', {}),
    }
    return export
