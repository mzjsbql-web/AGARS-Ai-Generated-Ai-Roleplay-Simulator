"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
import shutil
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: AGARS/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')
project_root_env_example = os.path.join(os.path.dirname(__file__), '../../.env.example')

if not os.path.exists(project_root_env) and os.path.exists(project_root_env_example):
    # 首次运行：从 .env.example 自动创建 .env
    shutil.copy2(project_root_env_example, project_root_env)

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'agars-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # Gemini Safety 设置（仅对 Gemini OpenAI 兼容接口有效）
    # 设为 true 时通过 extra_body 将所有安全类别阈值设为 BLOCK_NONE，避免内容被莫名截断
    LLM_GEMINI_SAFETY_BLOCK_NONE = os.environ.get('LLM_GEMINI_SAFETY_BLOCK_NONE', 'false').lower() == 'true'

    # 是否使用 Google 原生 SDK（auto=根据 URL 自动判断, true=强制使用, false=强制不使用）
    LLM_USE_GOOGLE_SDK = os.environ.get('LLM_USE_GOOGLE_SDK', 'auto').lower()

    # 高性能 LLM 配置（用于叙事正文、图谱查重等高质量任务；不配置则回退到默认 LLM）
    # 支持 PRO、2、3 等后缀，可在 .env 中配置 LLM_API_KEY_PRO / LLM_API_KEY_2 等
    LLM_API_KEY_PRO = os.environ.get('LLM_API_KEY_PRO')
    LLM_BASE_URL_PRO = os.environ.get('LLM_BASE_URL_PRO')
    LLM_MODEL_NAME_PRO = os.environ.get('LLM_MODEL_NAME_PRO')
    
    # Embedding配置（独立于LLM，用于图谱向量化）
    # 如不配置则回退到 LLM 的对应配置
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL') or os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    EMBEDDING_MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'text-embedding-3-small')

    # Zep配置（搜索/模拟仍使用Zep Cloud）
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')

    # FalkorDB配置（Graphiti本地图谱构建）
    FALKORDB_HOST = os.environ.get('FALKORDB_HOST', 'localhost')
    FALKORDB_PORT = int(os.environ.get('FALKORDB_PORT', '6379'))
    FALKORDB_PASSWORD = os.environ.get('FALKORDB_PASSWORD', '')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 1500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 200  # 默认重叠大小（约13%，保留跨块的人物/场景上下文）
    DEFAULT_BATCH_SIZE = 10  # 默认每批处理块数
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # 叙事引擎配置
    NARRATIVE_MAX_NPC_TURNS = int(os.environ.get('NARRATIVE_MAX_NPC_TURNS', '3'))
    NARRATIVE_IMPORTANCE_THRESHOLD = float(os.environ.get('NARRATIVE_IMPORTANCE_THRESHOLD', '0.7'))
    NARRATIVE_ENGINE_TEMPERATURE = float(os.environ.get('NARRATIVE_ENGINE_TEMPERATURE', '0.7'))
    NARRATIVE_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/narratives')
    
    @classmethod
    def get_llm_profiles(cls) -> dict:
        """返回所有可用的 LLM 配置 profile（始终包含 default 和 pro，可扩展 2/3 等）"""
        profiles = {
            "default": {
                "api_key": cls.LLM_API_KEY,
                "base_url": cls.LLM_BASE_URL,
                "model": cls.LLM_MODEL_NAME,
                "configured": True,
            }
        }
        # pro 始终存在（未配置时回退到 default）
        pro_key = os.environ.get('LLM_API_KEY_PRO')
        pro_url = os.environ.get('LLM_BASE_URL_PRO')
        pro_model = os.environ.get('LLM_MODEL_NAME_PRO')
        profiles["pro"] = {
            "api_key": pro_key or cls.LLM_API_KEY,
            "base_url": pro_url or cls.LLM_BASE_URL,
            "model": pro_model or cls.LLM_MODEL_NAME,
            "configured": bool(pro_key or pro_url or pro_model),
        }
        # 支持 2、3 等额外 profile
        for suffix in ['2', '3']:
            env_key = os.environ.get(f'LLM_API_KEY_{suffix}')
            env_url = os.environ.get(f'LLM_BASE_URL_{suffix}')
            env_model = os.environ.get(f'LLM_MODEL_NAME_{suffix}')
            if env_key or env_url or env_model:
                profiles[suffix] = {
                    "api_key": env_key or cls.LLM_API_KEY,
                    "base_url": env_url or cls.LLM_BASE_URL,
                    "model": env_model or cls.LLM_MODEL_NAME,
                    "configured": True,
                }
        return profiles

    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY 未配置")
        return errors

