"""
业务服务模块
延迟导入：避免重量级依赖（graphiti_core 等）在模块加载时立即拉入，
使得轻量级子模块（prompt_config、narrative_engine_config、preset_manager 等）
可以在这些依赖未安装时正常工作。
"""

import importlib as _importlib

__all__ = [
    'OntologyGenerator',
    'GraphBuilderService',
    'TextProcessor',
    'ZepEntityReader',
    'EntityNode',
    'FilteredEntities',
    'OasisProfileGenerator',
    'OasisAgentProfile',
    'SimulationManager',
    'SimulationState',
    'SimulationStatus',
    'SimulationConfigGenerator',
    'SimulationParameters',
    'AgentActivityConfig',
    'TimeSimulationConfig',
    'EventConfig',
    'PlatformConfig',
    'SimulationRunner',
    'SimulationRunState',
    'RunnerStatus',
    'AgentAction',
    'RoundSummary',
    'ZepGraphMemoryUpdater',
    'ZepGraphMemoryManager',
    'AgentActivity',
    'SimulationIPCClient',
    'SimulationIPCServer',
    'IPCCommand',
    'IPCResponse',
    'CommandType',
    'CommandStatus',
]

# 名称 → (子模块, 属性名) 的映射
_LAZY_IMPORTS = {
    'OntologyGenerator':        ('.ontology_generator', 'OntologyGenerator'),
    'GraphBuilderService':      ('.graph_builder', 'GraphBuilderService'),
    'TextProcessor':            ('.text_processor', 'TextProcessor'),
    'ZepEntityReader':          ('.zep_entity_reader', 'ZepEntityReader'),
    'EntityNode':               ('.zep_entity_reader', 'EntityNode'),
    'FilteredEntities':         ('.zep_entity_reader', 'FilteredEntities'),
    'OasisProfileGenerator':    ('.oasis_profile_generator', 'OasisProfileGenerator'),
    'OasisAgentProfile':        ('.oasis_profile_generator', 'OasisAgentProfile'),
    'SimulationManager':        ('.simulation_manager', 'SimulationManager'),
    'SimulationState':          ('.simulation_manager', 'SimulationState'),
    'SimulationStatus':         ('.simulation_manager', 'SimulationStatus'),
    'SimulationConfigGenerator': ('.simulation_config_generator', 'SimulationConfigGenerator'),
    'SimulationParameters':     ('.simulation_config_generator', 'SimulationParameters'),
    'AgentActivityConfig':      ('.simulation_config_generator', 'AgentActivityConfig'),
    'TimeSimulationConfig':     ('.simulation_config_generator', 'TimeSimulationConfig'),
    'EventConfig':              ('.simulation_config_generator', 'EventConfig'),
    'PlatformConfig':           ('.simulation_config_generator', 'PlatformConfig'),
    'SimulationRunner':         ('.simulation_runner', 'SimulationRunner'),
    'SimulationRunState':       ('.simulation_runner', 'SimulationRunState'),
    'RunnerStatus':             ('.simulation_runner', 'RunnerStatus'),
    'AgentAction':              ('.simulation_runner', 'AgentAction'),
    'RoundSummary':             ('.simulation_runner', 'RoundSummary'),
    'ZepGraphMemoryUpdater':    ('.zep_graph_memory_updater', 'ZepGraphMemoryUpdater'),
    'ZepGraphMemoryManager':    ('.zep_graph_memory_updater', 'ZepGraphMemoryManager'),
    'AgentActivity':            ('.zep_graph_memory_updater', 'AgentActivity'),
    'SimulationIPCClient':      ('.simulation_ipc', 'SimulationIPCClient'),
    'SimulationIPCServer':      ('.simulation_ipc', 'SimulationIPCServer'),
    'IPCCommand':               ('.simulation_ipc', 'IPCCommand'),
    'IPCResponse':              ('.simulation_ipc', 'IPCResponse'),
    'CommandType':              ('.simulation_ipc', 'CommandType'),
    'CommandStatus':            ('.simulation_ipc', 'CommandStatus'),
}


def __getattr__(name):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        module = _importlib.import_module(module_path, __name__)
        value = getattr(module, attr)
        # 缓存到模块全局，后续访问不再走 __getattr__
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

