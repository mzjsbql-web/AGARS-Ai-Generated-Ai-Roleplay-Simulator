"""
API路由模块
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)
narrative_bp = Blueprint('narrative', __name__)
settings_bp = Blueprint('settings', __name__)
monitor_bp = Blueprint('monitor', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import narrative  # noqa: E402, F401
from . import settings  # noqa: E402, F401
from . import monitor  # noqa: E402, F401

