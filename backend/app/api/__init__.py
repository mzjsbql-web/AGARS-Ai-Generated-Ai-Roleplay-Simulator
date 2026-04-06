"""
API路由模块
蓝图导入使用 try/except 隔离，单个模块的依赖缺失不会拖垮其他蓝图
（例如新设备首次运行、graphiti_core 未安装时，设置页面仍可用）
"""

import logging
from flask import Blueprint

_logger = logging.getLogger('agars.api')

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
narrative_bp = Blueprint('narrative', __name__)
settings_bp = Blueprint('settings', __name__)
monitor_bp = Blueprint('monitor', __name__)

_modules = ['graph', 'simulation', 'report', 'narrative', 'settings', 'monitor']
for _mod_name in _modules:
    try:
        __import__(f'{__name__}.{_mod_name}')
    except Exception as _e:
        _logger.warning(f"API 模块 {_mod_name} 加载失败（部分功能不可用）: {_e}")

