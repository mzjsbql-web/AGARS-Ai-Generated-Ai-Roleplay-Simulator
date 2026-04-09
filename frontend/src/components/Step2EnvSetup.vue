<template>
  <div class="env-setup-panel">
    <div class="scroll-container">
      <!-- Step 01: 模拟实例 -->
      <div class="step-card" :class="{ 'active': phase === 0, 'completed': phase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">模拟实例初始化</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 0" class="badge success">已完成</span>
            <span v-else class="badge processing">初始化</span>
          </div>
        </div>
        
        <div class="card-content">
          <p class="api-note">POST /api/simulation/create</p>
          <p class="description">
            新建simulation实例，拉取模拟世界参数模版
          </p>

          <div v-if="simulationId" class="info-card">
            <div class="info-row">
              <span class="info-label">Project ID</span>
              <span class="info-value mono">{{ projectData?.project_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Graph ID</span>
              <span class="info-value mono">{{ projectData?.graph_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Simulation ID</span>
              <span class="info-value mono">{{ simulationId }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">Task ID</span>
              <span class="info-value mono">{{ taskId || '异步任务已完成' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 02: 生成 Agent 人设 -->
      <div class="step-card" :class="{ 'active': phase === 1, 'completed': phase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">生成 Agent 人设</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 1" class="badge success">已完成</span>
            <span v-else-if="phase === 1" class="badge processing">{{ prepareProgress }}%</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            结合上下文，自动调用工具从知识图谱梳理实体与关系，初始化模拟个体，并基于现实种子赋予他们独特的行为与记忆
          </p>

          <!-- Profiles Stats -->
          <div v-if="profiles.length > 0" class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ profiles.length }}</span>
              <span class="stat-label">当前Agent数</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ expectedTotal || '-' }}</span>
              <span class="stat-label">预期Agent总数</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ totalTopicsCount }}</span>
              <span class="stat-label">现实种子当前关联问题数</span>
            </div>
          </div>

          <!-- Profiles List Preview -->
          <div v-if="profiles.length > 0" class="profiles-preview">
            <div class="preview-header">
              <span class="preview-title">已生成的 Agent 人设</span>
              <span v-if="narrativeMode && selectedPlayerUuid" class="narrative-hint">
                已选择玩家角色
              </span>
            </div>
            <div class="profile-search-bar">
              <input
                v-model="profileSearchQuery"
                type="text"
                class="profile-search-input"
                :placeholder="searchNameOnly ? '搜索角色名...' : '搜索角色名、职业、性格...'"
              />
              <button
                class="search-mode-toggle"
                :class="{ active: !searchNameOnly }"
                @click="searchNameOnly = !searchNameOnly"
                :title="searchNameOnly ? '当前：仅搜名称，点击切换全文' : '当前：全文搜索，点击切换仅名称'"
              >{{ searchNameOnly ? '名称' : '全文' }}</button>
              <span v-if="profileSearchQuery" class="profile-search-count">
                {{ filteredProfiles.length }} / {{ profiles.length }}
              </span>
            </div>
            <div class="profiles-list">
              <div
                v-for="profile in filteredProfiles"
                :key="profile.entity_uuid || profile.name"
                class="profile-card"
                :class="{ 'player-selected': narrativeMode && selectedPlayerUuid === profile.entity_uuid }"
                @click="selectProfile(profile)"
              >
                <!-- Narrative mode: player selected indicator (selection moved to Step 03) -->
                <div v-if="narrativeMode && selectedPlayerUuid === profile.entity_uuid" class="player-selected-badge">
                  <span class="player-badge-label">已选</span>
                </div>
                <!-- Narrative mode: edit buttons -->
                <div v-if="narrativeMode" class="profile-btn-group">
                  <div class="profile-edit-btn" @click.stop="openEditProfile(profiles.indexOf(profile))">
                    <span>编辑</span>
                  </div>
                  <div class="profile-delete-btn" @click.stop="deleteProfile(profiles.indexOf(profile))">
                    <span>删除</span>
                  </div>
                </div>
                <div class="profile-header">
                  <span class="profile-realname">{{ narrativeMode ? (profile.name || 'Unknown') : (profile.username || 'Unknown') }}</span>
                  <span v-if="!narrativeMode" class="profile-username">@{{ profile.name || `agent_${idx}` }}</span>
                </div>
                <div v-if="narrativeMode" class="profile-graph-info">
                  <span class="entity-type-badge">{{ profile.entity_type || '未知类型' }}</span>
                  <span class="entity-uuid">{{ (profile.entity_uuid || '').slice(0, 8) }}</span>
                </div>
                <div class="profile-meta">
                  <span class="profile-profession">{{ narrativeMode ? (profile.temperament || profile.personality?.slice(0, 20) || '未知气质') : (profile.profession || '未知职业') }}</span>
                </div>
                <p class="profile-bio">{{ narrativeMode ? (profile.backstory || profile.personality || '暂无档案') : (profile.bio || '暂无简介') }}</p>
                <div v-if="narrativeMode && profile.goals?.length" class="profile-topics">
                  <span
                    v-for="goal in profile.goals.slice(0, 3)"
                    :key="goal"
                    class="topic-tag"
                  >{{ goal }}</span>
                  <span v-if="profile.goals.length > 3" class="topic-more">
                    +{{ profile.goals.length - 3 }}
                  </span>
                </div>
                <div v-else-if="!narrativeMode && profile.interested_topics?.length" class="profile-topics">
                  <span
                    v-for="topic in profile.interested_topics.slice(0, 3)"
                    :key="topic"
                    class="topic-tag"
                  >{{ topic }}</span>
                  <span v-if="profile.interested_topics.length > 3" class="topic-more">
                    +{{ profile.interested_topics.length - 3 }}
                  </span>
                </div>
              </div>
            </div>
            <!-- Narrative mode: add new persona button -->
            <div v-if="narrativeMode" class="add-profile-btn" @click="openAddProfile">
              <span class="add-icon">+</span>
              <span>添加角色</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 03: 生成双平台模拟配置 (OASIS only) -->
      <div v-if="!narrativeMode" class="step-card" :class="{ 'active': phase === 2, 'completed': phase > 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">生成双平台模拟配置</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 2" class="badge success">已完成</span>
            <span v-else-if="phase === 2" class="badge processing">生成中</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            LLM 根据模拟需求与现实种子，智能设置世界时间流速、推荐算法、每个个体的活跃时间段、发言频率、事件触发等参数
          </p>
          
          <!-- Config Preview -->
          <div v-if="simulationConfig" class="config-detail-panel">
            <!-- 时间配置 -->
            <div class="config-block">
              <div class="config-grid">
                <div class="config-item">
                  <span class="config-item-label">模拟时长</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.total_simulation_hours || '-' }} 小时</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">每轮时长</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.minutes_per_round || '-' }} 分钟</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">总轮次</span>
                  <span class="config-item-value">{{ Math.floor((simulationConfig.time_config?.total_simulation_hours * 60 / simulationConfig.time_config?.minutes_per_round)) || '-' }} 轮</span>
                </div>
                <div class="config-item">
                  <span class="config-item-label">每小时活跃</span>
                  <span class="config-item-value">{{ simulationConfig.time_config?.agents_per_hour_min }}-{{ simulationConfig.time_config?.agents_per_hour_max }}</span>
                </div>
              </div>
              <div class="time-periods">
                <div class="period-item">
                  <span class="period-label">高峰时段</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.peak_hours?.join(':00, ') }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.peak_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">工作时段</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.work_hours?.[0] }}:00-{{ simulationConfig.time_config?.work_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.work_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">早间时段</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.morning_hours?.[0] }}:00-{{ simulationConfig.time_config?.morning_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.morning_activity_multiplier }}</span>
                </div>
                <div class="period-item">
                  <span class="period-label">低谷时段</span>
                  <span class="period-hours">{{ simulationConfig.time_config?.off_peak_hours?.[0] }}:00-{{ simulationConfig.time_config?.off_peak_hours?.slice(-1)[0] }}:00</span>
                  <span class="period-multiplier">×{{ simulationConfig.time_config?.off_peak_activity_multiplier }}</span>
                </div>
              </div>
            </div>

            <!-- Agent 配置 -->
            <div class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">Agent 配置</span>
                <span class="config-block-badge">{{ simulationConfig.agent_configs?.length || 0 }} 个</span>
              </div>
              <div class="agents-cards">
                <div 
                  v-for="agent in simulationConfig.agent_configs" 
                  :key="agent.agent_id" 
                  class="agent-card"
                >
                  <!-- 卡片头部 -->
                  <div class="agent-card-header">
                    <div class="agent-identity">
                      <span class="agent-id">Agent {{ agent.agent_id }}</span>
                      <span class="agent-name">{{ agent.entity_name }}</span>
                    </div>
                    <div class="agent-tags">
                      <span class="agent-type">{{ agent.entity_type }}</span>
                      <span class="agent-stance" :class="'stance-' + agent.stance">{{ agent.stance }}</span>
                    </div>
                  </div>
                  
                  <!-- 活跃时间轴 -->
                  <div class="agent-timeline">
                    <span class="timeline-label">活跃时段</span>
                    <div class="mini-timeline">
                      <div 
                        v-for="hour in 24" 
                        :key="hour - 1" 
                        class="timeline-hour"
                        :class="{ 'active': agent.active_hours?.includes(hour - 1) }"
                        :title="`${hour - 1}:00`"
                      ></div>
                    </div>
                    <div class="timeline-marks">
                      <span>0</span>
                      <span>6</span>
                      <span>12</span>
                      <span>18</span>
                      <span>24</span>
                    </div>
                  </div>

                  <!-- 行为参数 -->
                  <div class="agent-params">
                    <div class="param-group">
                      <div class="param-item">
                        <span class="param-label">发帖/时</span>
                        <span class="param-value">{{ agent.posts_per_hour }}</span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">评论/时</span>
                        <span class="param-value">{{ agent.comments_per_hour }}</span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">响应延迟</span>
                        <span class="param-value">{{ agent.response_delay_min }}-{{ agent.response_delay_max }}min</span>
                      </div>
                    </div>
                    <div class="param-group">
                      <div class="param-item">
                        <span class="param-label">活跃度</span>
                        <span class="param-value with-bar">
                          <span class="mini-bar" :style="{ width: (agent.activity_level * 100) + '%' }"></span>
                          {{ (agent.activity_level * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">情感倾向</span>
                        <span class="param-value" :class="agent.sentiment_bias > 0 ? 'positive' : agent.sentiment_bias < 0 ? 'negative' : 'neutral'">
                          {{ agent.sentiment_bias > 0 ? '+' : '' }}{{ agent.sentiment_bias?.toFixed(1) }}
                        </span>
                      </div>
                      <div class="param-item">
                        <span class="param-label">影响力</span>
                        <span class="param-value highlight">{{ agent.influence_weight?.toFixed(1) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 平台配置 -->
            <div class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">推荐算法配置</span>
              </div>
              <div class="platforms-grid">
                <div v-if="simulationConfig.twitter_config" class="platform-card">
                  <div class="platform-card-header">
                    <span class="platform-name">平台 1：广场 / 信息流</span>
                  </div>
                  <div class="platform-params">
                    <div class="param-row">
                      <span class="param-label">时效权重</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.recency_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">热度权重</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.popularity_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">相关性权重</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.relevance_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">病毒阈值</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.viral_threshold }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">回音室强度</span>
                      <span class="param-value">{{ simulationConfig.twitter_config.echo_chamber_strength }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="simulationConfig.reddit_config" class="platform-card">
                  <div class="platform-card-header">
                    <span class="platform-name">平台 2：话题 / 社区</span>
                  </div>
                  <div class="platform-params">
                    <div class="param-row">
                      <span class="param-label">时效权重</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.recency_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">热度权重</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.popularity_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">相关性权重</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.relevance_weight }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">病毒阈值</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.viral_threshold }}</span>
                    </div>
                    <div class="param-row">
                      <span class="param-label">回音室强度</span>
                      <span class="param-value">{{ simulationConfig.reddit_config.echo_chamber_strength }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- LLM 配置推理 -->
            <div v-if="simulationConfig.generation_reasoning" class="config-block">
              <div class="config-block-header">
                <span class="config-block-title">LLM 配置推理</span>
              </div>
              <div class="reasoning-content">
                <div 
                  v-for="(reason, idx) in simulationConfig.generation_reasoning.split('|').slice(0, 2)" 
                  :key="idx" 
                  class="reasoning-item"
                >
                  <p class="reasoning-text">{{ reason.trim() }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 04: 初始激活编排 (OASIS only) -->
      <div v-if="!narrativeMode" class="step-card" :class="{ 'active': phase === 3, 'completed': phase > 3 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">初始激活编排</span>
          </div>
          <div class="step-status">
            <span v-if="phase > 3" class="badge success">已完成</span>
            <span v-else-if="phase === 3" class="badge processing">编排中</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">POST /api/simulation/prepare</p>
          <p class="description">
            基于叙事方向，自动生成初始激活事件与热点话题，引导模拟世界的初始状态
          </p>

          <div v-if="simulationConfig?.event_config" class="orchestration-content">
            <!-- 叙事方向 -->
            <div class="narrative-box">
              <span class="box-label narrative-label">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="special-icon">
                  <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M16.24 7.76L14.12 14.12L7.76 16.24L9.88 9.88L16.24 7.76Z" fill="url(#paint0_linear)" stroke="url(#paint0_linear)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  <defs>
                    <linearGradient id="paint0_linear" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
                      <stop stop-color="#FF5722"/>
                      <stop offset="1" stop-color="#FF9800"/>
                    </linearGradient>
                  </defs>
                </svg>
                叙事引导方向
              </span>
              <p class="narrative-text">{{ simulationConfig.event_config.narrative_direction }}</p>
            </div>

            <!-- 热点话题 -->
            <div class="topics-section">
              <span class="box-label">初始热点话题</span>
              <div class="hot-topics-grid">
                <span v-for="topic in simulationConfig.event_config.hot_topics" :key="topic" class="hot-topic-tag">
                  # {{ topic }}
                </span>
              </div>
            </div>

            <!-- 初始帖子流 -->
            <div class="initial-posts-section">
              <span class="box-label">初始激活序列 ({{ simulationConfig.event_config.initial_posts.length }})</span>
              <div class="posts-timeline">
                <div v-for="(post, idx) in simulationConfig.event_config.initial_posts" :key="idx" class="timeline-item">
                  <div class="timeline-marker"></div>
                  <div class="timeline-content">
                    <div class="post-header">
                      <span class="post-role">{{ post.poster_type }}</span>
                      <span class="post-agent-info">
                        <span class="post-id">Agent {{ post.poster_agent_id }}</span>
                        <span class="post-username">@{{ getAgentUsername(post.poster_agent_id) }}</span>
                      </span>
                    </div>
                    <p class="post-text">{{ post.content }}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Step 05 (OASIS) / Step 03 (Narrative): 准备完成 -->
      <div class="step-card" :class="{ 'active': phase === 4 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">{{ narrativeMode ? '03' : '05' }}</span>
            <span class="step-title">{{ narrativeMode ? '选择角色 & 开始叙事' : '准备完成' }}</span>
          </div>
          <div class="step-status">
            <span v-if="phase >= 4" class="badge processing">进行中</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note">{{ narrativeMode ? 'POST /api/narrative/create' : 'POST /api/simulation/start' }}</p>
          <p class="description">{{ narrativeMode ? '环境已准备完成，请选择你要扮演的角色，然后开始叙事模式' : '模拟环境已准备完成，可以开始运行模拟' }}</p>

          <!-- 叙事模式：角色选择列表 -->
          <div v-if="narrativeMode && profiles.length > 0" class="narrative-player-select">
            <div class="preview-header">
              <span class="preview-title">选择你要扮演的角色</span>
              <span v-if="selectedPlayerUuid" class="narrative-selected-hint">
                已选择: {{ profiles.find(p => p.entity_uuid === selectedPlayerUuid)?.name || '...' }}
              </span>
            </div>
            <div class="profile-search-bar">
              <input
                v-model="playerSearchQuery"
                type="text"
                class="profile-search-input"
                :placeholder="playerSearchNameOnly ? '搜索角色名...' : '搜索角色名、性格、背景...'"
              />
              <button
                class="search-mode-toggle"
                :class="{ active: !playerSearchNameOnly }"
                @click="playerSearchNameOnly = !playerSearchNameOnly"
                :title="playerSearchNameOnly ? '当前：仅搜名称，点击切换全文' : '当前：全文搜索，点击切换仅名称'"
              >{{ playerSearchNameOnly ? '名称' : '全文' }}</button>
              <span v-if="playerSearchQuery" class="profile-search-count">
                {{ filteredPlayerProfiles.length }} / {{ profiles.length }}
              </span>
            </div>
            <div class="profiles-list">
              <div
                v-for="profile in filteredPlayerProfiles"
                :key="profile.entity_uuid || profile.name"
                class="profile-card"
                :class="{ 'player-selected': selectedPlayerUuid === profile.entity_uuid }"
                @click="selectAsPlayer(profile)"
              >
                <div class="player-radio-overlay">
                  <input
                    type="radio"
                    :name="'player-select-final'"
                    :value="profile.entity_uuid"
                    :checked="selectedPlayerUuid === profile.entity_uuid"
                    class="player-radio"
                  />
                  <span class="player-radio-label">扮演</span>
                </div>
                <div class="profile-header">
                  <span class="profile-realname">{{ profile.name || 'Unknown' }}</span>
                </div>
                <div class="profile-meta">
                  <span class="profile-profession">{{ profile.temperament || profile.personality?.slice(0, 20) || '未知气质' }}</span>
                </div>
                <p class="profile-bio">{{ profile.backstory || profile.personality || '暂无档案' }}</p>
                <div v-if="profile.goals?.length" class="profile-topics">
                  <span
                    v-for="goal in profile.goals.slice(0, 3)"
                    :key="goal"
                    class="topic-tag"
                  >{{ goal }}</span>
                  <span v-if="profile.goals.length > 3" class="topic-more">
                    +{{ profile.goals.length - 3 }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- 叙事模式：开篇正文输入 -->
          <div v-if="narrativeMode && phase >= 4" class="narrative-opening-section">
            <div class="preview-header">
              <span class="preview-title">开篇设定</span>
              <div class="opening-mode-switch">
                <button
                  class="mode-btn"
                  :class="{ active: openingMode === 'ai' }"
                  @click="openingMode = 'ai'"
                >AI 生成</button>
                <button
                  class="mode-btn"
                  :class="{ active: openingMode === 'direct' }"
                  @click="openingMode = 'direct'"
                >直接撰写</button>
                <button
                  class="mode-btn"
                  :class="{ active: openingMode === 'continuation' }"
                  @click="openingMode = 'continuation'"
                >小说续写</button>
              </div>
            </div>
            <template v-if="openingMode === 'ai'">
              <p class="opening-hint">描述故事的世界观、初始场景，AI 将据此生成开篇正文（对应变量 <code>{initial_scene}</code>）</p>
              <textarea
                v-model="initialSceneText"
                class="initial-scene-input"
                rows="3"
                placeholder="例如：大宋宣和二年，东京汴梁城外三十里的云台镇，一场暴雨将官道冲断..."
              ></textarea>
            </template>
            <template v-else-if="openingMode === 'direct'">
              <p class="opening-hint">直接撰写开篇正文，将作为叙事的第一段呈现给玩家（第二人称"你"视角）</p>
              <textarea
                v-model="openingDirectText"
                class="initial-scene-input direct-mode"
                rows="6"
                placeholder="你睁开眼，发现自己身处一间昏暗的客栈。窗外暴雨如注，雷声隆隆。空气中弥漫着潮湿的木头气味和隔壁传来的酒香。你隐约记得，自己是为了某件要事才来到这座小镇的..."
              ></textarea>
            </template>
            <template v-else>
              <p class="opening-hint">上传前文文件（pdf / txt / md），系统将自动分块生成摘要；也可直接粘贴前文摘要</p>
              <div class="file-summary-row">
                <label class="file-upload-btn" :class="{ loading: summarizing }">
                  <input
                    type="file"
                    accept=".pdf,.txt,.md,.markdown"
                    style="display:none"
                    @change="handleSummarizeFile"
                    :disabled="summarizing"
                  />
                  {{ summarizing ? '生成中...' : '上传文件生成摘要' }}
                </label>
                <span v-if="summarizeError" class="summarize-error">{{ summarizeError }}</span>
              </div>
              <textarea
                v-model="priorSummaryText"
                class="initial-scene-input direct-mode"
                rows="6"
                :placeholder="summarizing ? '正在处理文件，请稍候...' : '第一章：主角在暴雨夜抵达云台镇，偶遇了神秘的茶馆老板李掌柜。经过一番试探，两人达成秘密协议——主角将协助追查镇上近日发生的离奇失踪案，李掌柜则提供落脚之处和线索...'"
                :disabled="summarizing"
              ></textarea>
              <div class="opening-hint" style="margin-top: 8px;">
                <span style="color: #888;">可选：补充当前世界设定（对应变量 <code>{initial_scene}</code>）</span>
                <textarea
                  v-model="initialSceneText"
                  class="initial-scene-input"
                  rows="2"
                  style="margin-top: 4px;"
                  placeholder="如有新的场景或设定变化，在此补充（可不填）"
                ></textarea>
              </div>
            </template>
          </div>

          <!-- 模拟轮数配置 - OASIS 模式且配置生成完成后才显示 -->
          <div v-if="!narrativeMode && simulationConfig && autoGeneratedRounds" class="rounds-config-section">
            <div class="rounds-header">
              <div class="header-left">
                <span class="section-title">模拟轮数设定</span>
                <span class="section-desc">AGARS 自动规划推演现实 <span class="desc-highlight">{{ simulationConfig?.time_config?.total_simulation_hours || '-' }}</span> 小时，每轮代表现实 <span class="desc-highlight">{{ simulationConfig?.time_config?.minutes_per_round || '-' }}</span> 分钟时间流逝</span>
              </div>
              <label class="switch-control">
                <input type="checkbox" v-model="useCustomRounds">
                <span class="switch-track"></span>
                <span class="switch-label">自定义</span>
              </label>
            </div>
            
            <Transition name="fade" mode="out-in">
              <div v-if="useCustomRounds" class="rounds-content custom" key="custom">
                <div class="slider-display">
                  <div class="slider-main-value">
                    <span class="val-num">{{ customMaxRounds }}</span>
                    <span class="val-unit">轮</span>
                  </div>
                  <div class="slider-meta-info">
                    <span>若Agent规模为100：预计耗时约 {{ Math.round(customMaxRounds * 0.6) }} 分钟</span>
                  </div>
                </div>

                <div class="range-wrapper">
                  <input 
                    type="range" 
                    v-model.number="customMaxRounds" 
                    min="10" 
                    :max="autoGeneratedRounds"
                    step="5"
                    class="minimal-slider"
                    :style="{ '--percent': ((customMaxRounds - 10) / (autoGeneratedRounds - 10)) * 100 + '%' }"
                  />
                  <div class="range-marks">
                    <span>10</span>
                    <span 
                      class="mark-recommend" 
                      :class="{ active: customMaxRounds === 40 }"
                      @click="customMaxRounds = 40"
                      :style="{ position: 'absolute', left: `calc(${(40 - 10) / (autoGeneratedRounds - 10) * 100}% - 30px)` }"
                    >40 (推荐)</span>
                    <span>{{ autoGeneratedRounds }}</span>
                  </div>
                </div>
              </div>
              
              <div v-else class="rounds-content auto" key="auto">
                <div class="auto-info-card">
                  <div class="auto-value">
                    <span class="val-num">{{ autoGeneratedRounds }}</span>
                    <span class="val-unit">轮</span>
                  </div>
                  <div class="auto-content">
                    <div class="auto-meta-row">
                      <span class="duration-badge">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <circle cx="12" cy="12" r="10"></circle>
                          <polyline points="12 6 12 12 16 14"></polyline>
                        </svg>
                        若Agent规模为100：预计耗时 {{ Math.round(autoGeneratedRounds * 0.6) }} 分钟
                      </span>
                    </div>
                    <div class="auto-desc">
                      <p class="highlight-tip" @click="useCustomRounds = true">若首次运行，强烈建议切换至‘自定义模式’减少模拟轮数，以便快速预览效果并降低报错风险 ➝</p>
                    </div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>

          <div class="action-group dual">
            <button
              class="action-btn secondary"
              @click="$emit('go-back')"
            >
              ← 返回图谱构建
            </button>
            <button
              v-if="narrativeMode"
              class="action-btn primary narrative-start-btn"
              :disabled="phase < 4 || !selectedPlayerUuid"
              @click="handleStartNarrative"
            >
              开始叙事模式 ➝
            </button>
            <button
              v-else
              class="action-btn primary"
              :disabled="phase < 4"
              @click="handleStartSimulation"
            >
              开始双世界并行模拟 ➝
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Profile Detail Modal -->
    <Transition name="modal">
      <div v-if="selectedProfile" class="profile-modal-overlay" @click.self="selectedProfile = null">
        <div class="profile-modal">
          <div class="modal-header">
          <div class="modal-header-info">
            <div class="modal-name-row">
              <span class="modal-realname">{{ narrativeMode ? selectedProfile.name : selectedProfile.username }}</span>
              <span v-if="!narrativeMode" class="modal-username">@{{ selectedProfile.name }}</span>
            </div>
            <span class="modal-profession">{{ selectedProfile.profession }}</span>
          </div>
          <button class="close-btn" @click="selectedProfile = null">×</button>
        </div>
        
        <div class="modal-body">
          <!-- 基本信息 -->
          <div class="modal-info-grid">
            <div class="info-item">
              <span class="info-label">事件外显年龄</span>
              <span class="info-value">{{ selectedProfile.age || '-' }} 岁</span>
            </div>
            <div class="info-item">
              <span class="info-label">事件外显性别</span>
              <span class="info-value">{{ { male: '男', female: '女', other: '其他' }[selectedProfile.gender] || selectedProfile.gender }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">国家/地区</span>
              <span class="info-value">{{ selectedProfile.country || '-' }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">事件外显MBTI</span>
              <span class="info-value mbti">{{ selectedProfile.mbti || '-' }}</span>
            </div>
          </div>

          <!-- 简介 -->
          <div class="modal-section">
            <span class="section-label">人设简介</span>
            <p class="section-bio">{{ selectedProfile.bio || '暂无简介' }}</p>
          </div>

          <!-- 关注问题 -->
          <div class="modal-section" v-if="selectedProfile.interested_topics?.length">
            <span class="section-label">关注问题</span>
            <div class="topics-grid">
              <span 
                v-for="topic in selectedProfile.interested_topics" 
                :key="topic" 
                class="topic-item"
              >{{ topic }}</span>
            </div>
          </div>

          <!-- 详细人设 -->
          <div class="modal-section" v-if="selectedProfile.persona">
            <span class="section-label">详细人设背景</span>
            
            <!-- 人设维度概览 -->
            <div class="persona-dimensions">
              <div class="dimension-card">
                <span class="dim-title">事件全景经历</span>
                <span class="dim-desc">在此事件中的完整行为轨迹</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">行为模式侧写</span>
                <span class="dim-desc">经验总结与行事风格偏好</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">独特记忆印记</span>
                <span class="dim-desc">基于现实种子形成的记忆</span>
              </div>
              <div class="dimension-card">
                <span class="dim-title">社会关系网络</span>
                <span class="dim-desc">个体链接与交互图谱</span>
              </div>
            </div>

            <div class="persona-content">
              <p class="section-persona">{{ selectedProfile.persona }}</p>
            </div>
          </div>
        </div>
      </div>
      </div>
    </Transition>

    <!-- Edit Profile Modal (Narrative mode) -->
    <Transition name="modal">
      <div v-if="editingProfile !== null" class="profile-modal-overlay" @click.self="editingProfile = null">
        <div class="profile-modal edit-modal">
          <div class="modal-header">
            <div class="modal-header-info">
              <span class="modal-realname">{{ editingIsNew ? '添加新角色' : '编辑角色' }}</span>
            </div>
            <button class="close-btn" @click="editingProfile = null">×</button>
          </div>
          <div class="modal-body edit-form">
            <!-- 关联已有图谱节点（仅添加新角色时显示） -->
            <div v-if="editingIsNew && narrativeMode && unassignedNodes.length > 0" class="form-group link-node-group">
              <label class="form-label">关联已有图谱节点 <span class="form-hint">（可选，选择后自动填充信息）</span></label>
              <select v-model="selectedNodeUuid" class="form-input" @change="onSelectExistingNode">
                <option value="">不关联，创建新节点</option>
                <option v-for="node in unassignedNodes" :key="node.uuid" :value="node.uuid">
                  {{ node.name }}{{ node.summary ? ' — ' + node.summary.slice(0, 40) : '' }}
                </option>
              </select>
            </div>

            <div class="form-group">
              <label class="form-label">角色名称</label>
              <input type="text" v-model="editForm.name" class="form-input" placeholder="角色名称" />
            </div>

            <!-- ====== 叙事模式表单 ====== -->
            <template v-if="narrativeMode">
              <div class="form-group">
                <label class="form-label">性格特征</label>
                <textarea v-model="editForm.personality" class="form-textarea" rows="2" placeholder="性格特征描述"></textarea>
              </div>
              <div class="form-group">
                <label class="form-label">背景故事</label>
                <textarea v-model="editForm.backstory" class="form-textarea" rows="3" placeholder="角色的背景故事"></textarea>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">气质</label>
                  <input type="text" v-model="editForm.temperament" class="form-input" placeholder="如：沉稳、暴躁、温和" />
                </div>
                <div class="form-group">
                  <label class="form-label">当前位置</label>
                  <input type="text" v-model="editForm.current_location" class="form-input" placeholder="所在地点" />
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">说话风格</label>
                <input type="text" v-model="editForm.speech_style" class="form-input" placeholder="如：文绉绉、粗犷豪迈、阴阳怪气" />
              </div>
              <div class="form-group">
                <label class="form-label">目标 <span class="form-hint">（逗号分隔）</span></label>
                <input type="text" v-model="editForm.goalsStr" class="form-input" placeholder="目标1, 目标2, 目标3" />
              </div>
            </template>

            <!-- ====== OASIS 模式表单 ====== -->
            <template v-else>
              <div class="form-group">
                <label class="form-label">用户名</label>
                <input type="text" v-model="editForm.username" class="form-input" placeholder="用户名" />
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">职业</label>
                  <input type="text" v-model="editForm.profession" class="form-input" placeholder="职业" />
                </div>
                <div class="form-group">
                  <label class="form-label">年龄</label>
                  <input type="number" v-model.number="editForm.age" class="form-input" placeholder="年龄" />
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label">性别</label>
                  <select v-model="editForm.gender" class="form-input">
                    <option value="male">男</option>
                    <option value="female">女</option>
                    <option value="other">其他</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">MBTI</label>
                  <input type="text" v-model="editForm.mbti" class="form-input" placeholder="MBTI类型" />
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">简介</label>
                <textarea v-model="editForm.bio" class="form-textarea" rows="2" placeholder="角色简介"></textarea>
              </div>
              <div class="form-group">
                <label class="form-label">详细人设</label>
                <textarea v-model="editForm.persona" class="form-textarea" rows="4" placeholder="详细人设背景"></textarea>
              </div>
              <div class="form-group">
                <label class="form-label">关注问题 <span class="form-hint">（逗号分隔）</span></label>
                <input type="text" v-model="editForm.topicsStr" class="form-input" placeholder="话题1, 话题2, 话题3" />
              </div>
            </template>

            <div class="form-actions">
              <button class="action-btn secondary" @click="editingProfile = null">取消</button>
              <button class="action-btn primary" @click="saveEditProfile">保存</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Graph Editor Modal -->
    <Transition name="modal">
      <div v-if="graphEditing !== null" class="modal-overlay" @click.self="graphEditing = null">
        <div class="profile-modal graph-editor-modal">
          <div class="modal-header">
            <span class="modal-title">编辑图谱节点</span>
            <button class="modal-close" @click="graphEditing = null">×</button>
          </div>
          <div class="modal-body edit-form">
            <div v-if="graphLoading" class="graph-loading">加载图谱数据中...</div>
            <template v-else>
              <!-- Node Properties -->
              <div class="graph-section-title">节点属性</div>
              <div class="form-group">
                <label class="form-label">名称</label>
                <input type="text" v-model="graphForm.name" class="form-input" />
              </div>
              <div class="form-group">
                <label class="form-label">摘要</label>
                <textarea v-model="graphForm.summary" class="form-textarea" rows="3"></textarea>
              </div>
              <div class="form-group">
                <label class="form-label">类型标签</label>
                <select v-model="graphForm.label" class="form-input">
                  <option v-for="t in allLabelOptions" :key="t" :value="t">{{ t }}</option>
                </select>
              </div>

              <!-- Edges -->
              <div class="graph-section-title">关系边 ({{ graphForm.edges.length }})</div>
              <div v-for="(edge, eIdx) in graphForm.edges" :key="eIdx" class="graph-edge-row">
                <span class="edge-direction">{{ edge.direction === 'outgoing' ? '→' : '←' }}</span>
                <span class="edge-other-name">{{ edge.other_name }}</span>
                <select v-model="edge.rel_type" class="form-input edge-type-select">
                  <option v-for="et in edgeTypeOptions" :key="et" :value="et">{{ et }}</option>
                </select>
                <input type="text" v-model="edge.fact" class="form-input edge-fact" placeholder="事实描述 (fact)" />
                <button class="edge-remove-btn" @click="graphForm.edges.splice(eIdx, 1)">×</button>
              </div>

              <!-- Add Edge -->
              <div class="graph-add-edge">
                <input type="text" v-model="newEdgeTarget" class="form-input edge-target-input" placeholder="目标角色名" />
                <select v-model="newEdgeType" class="form-input edge-type-select">
                  <option v-for="et in edgeTypeOptions" :key="et" :value="et">{{ et }}</option>
                </select>
                <input type="text" v-model="newEdgeFact" class="form-input edge-fact-input" placeholder="事实描述" />
                <button class="edge-add-btn" @click="addGraphEdge">+ 添加边</button>
              </div>

              <div class="form-actions">
                <button class="action-btn secondary" @click="graphEditing = null">取消</button>
                <button class="action-btn primary" :disabled="graphSaving" @click="saveGraphEdits">
                  {{ graphSaving ? '保存中...' : '保存到图谱' }}
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Bottom Info / Logs -->
    <div class="system-logs">
      <div class="log-header">
        <span class="log-title">SYSTEM DASHBOARD</span>
        <span class="log-id">{{ simulationId || 'NO_SIMULATION' }}</span>
      </div>
      <div class="log-content" ref="logContent">
        <div class="log-line" v-for="(log, idx) in systemLogs" :key="idx">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-msg">{{ log.msg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import {
  prepareSimulation,
  getPrepareStatus as getSimPrepareStatus,
  getSimulationProfilesRealtime,
  getSimulationConfig,
  getSimulationConfigRealtime
} from '../api/simulation'
import {
  createNarrative, summarizeFile, getNarrativeSession,
  updateNarrativeProfile, addNarrativeProfile, deleteNarrativeProfile,
  prepareNarrative, getPrepareStatus as getNarrativePrepareStatus, getNarrativeProfiles
} from '../api/narrative'
import { getGraphData, getEntityEdges, createEntityNode, updateEntityEdges, updateEntityNode, deleteEntityNode } from '../api/graph'

const props = defineProps({
  simulationId: String,  // 从父组件传入
  projectData: Object,
  graphData: Object,
  systemLogs: Array,
  narrativeMode: { type: Boolean, default: false },
  narrativeSessionId: String  // Narrative 模式下的 session ID，用于同步后端
})

const emit = defineEmits(['go-back', 'next-step', 'add-log', 'update-status', 'player-selected', 'highlight-graph-node', 'narrative-session-created'])

// State
const phase = ref(0) // 0: 初始化, 1: 生成人设, 2: 生成配置, 3: 完成
const taskId = ref(null)
const prepareProgress = ref(0)
const currentStage = ref('')
const progressMessage = ref('')
const profiles = ref([])
const entityTypes = ref([])
const expectedTotal = ref(null)
const simulationConfig = ref(null)
const selectedProfile = ref(null)
const showProfilesDetail = ref(true)

// 日志去重：记录上一次输出的关键信息
let lastLoggedMessage = ''
let lastLoggedProfileCount = 0
let lastLoggedConfigStage = ''
let narrativeProfileStableCount = 0 // 叙事模式：profiles数量稳定计数器

// 模拟轮数配置
const useCustomRounds = ref(false) // 默认使用自动配置轮数
const customMaxRounds = ref(40)   // 默认推荐40轮

// 叙事模式：本地创建的会话 ID（在 step2 阶段提前创建）
const localNarrativeSessionId = ref(null)
// 获取有效的叙事会话 ID（优先用本地创建的，其次用 prop 传入的）
const effectiveNarrativeSessionId = computed(() => localNarrativeSessionId.value || props.narrativeSessionId || null)

// 叙事模式：玩家角色选择
const selectedPlayerUuid = ref(null)

// Profile 搜索
const profileSearchQuery = ref('')
const playerSearchQuery = ref('')
const searchNameOnly = ref(true)  // true=仅名称, false=全文搜索
const playerSearchNameOnly = ref(true)  // 选择列表：true=仅名称, false=全文搜索
const initialSceneText = ref('')
const openingMode = ref('ai')
const openingDirectText = ref('')
const priorSummaryText = ref('')
const summarizing = ref(false)
const summarizeError = ref('')

const handleSummarizeFile = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  // reset input so same file can be re-selected
  event.target.value = ''

  summarizing.value = true
  summarizeError.value = ''
  priorSummaryText.value = ''
  addLog(`正在处理文件：${file.name}`)
  try {
    const res = await summarizeFile(file)
    if (res.success && res.data?.summary) {
      priorSummaryText.value = res.data.summary
      addLog(`摘要生成完成（共 ${res.data.chunk_count} 个分块）`)
    } else {
      summarizeError.value = res.error || '摘要生成失败'
      addLog(`摘要生成失败：${summarizeError.value}`)
    }
  } catch (err) {
    summarizeError.value = err.message
    addLog(`摘要生成异常：${err.message}`)
  } finally {
    summarizing.value = false
  }
}

// 叙事模式：编辑/添加人设
const editingProfile = ref(null) // index or 'new'
const editingIsNew = ref(false)
const unassignedNodes = ref([])    // 图谱中无 profile 的节点列表
const selectedNodeUuid = ref('')   // 新增 profile 时选中的已有节点 UUID
const saving = ref(false)
const editForm = ref({
  name: '',
  username: '',
  profession: '',
  age: null,
  gender: 'male',
  mbti: '',
  bio: '',
  persona: '',
  topicsStr: '',
  // 叙事模式专用字段
  personality: '',
  backstory: '',
  goalsStr: '',
  speech_style: '',
  temperament: '',
  current_location: ''
})

// 图谱编辑器
const graphEditing = ref(null) // profile index or null
const graphLoading = ref(false)
const graphSaving = ref(false)
const graphForm = ref({
  name: '',
  summary: '',
  label: '',
  edges: []  // [{other_name, edge_name, fact, direction, other_uuid}]
})

// 图谱边类型选项（从 ontology 读取）
const edgeTypeOptions = computed(() => {
  const types = (props.projectData?.ontology?.edge_types || []).map(et => et.name)
  if (!types.includes('RELATES_TO')) types.push('RELATES_TO')
  return types
})

// 图谱标签选项（去重）
const allLabelOptions = computed(() => {
  const s = new Set(entityTypes.value)
  s.add('Person')
  s.add('Organization')
  return Array.from(s)
})

// Watch stage to update phase
watch(currentStage, (newStage) => {
  if (newStage === '生成Agent人设' || newStage === 'generating_profiles') {
    phase.value = 1
  } else if (newStage === '生成模拟配置' || newStage === 'generating_config') {
    if (props.narrativeMode) {
      // 叙事模式不需要配置生成，直接跳到完成
      phase.value = 4
      addLog('叙事模式：跳过配置生成，环境准备完成')
      emit('update-status', 'completed')
    } else {
      phase.value = 2
      // 进入配置生成阶段，开始轮询配置
      if (!configTimer) {
        addLog('开始生成双平台模拟配置...')
        startConfigPolling()
      }
    }
  } else if (newStage === '准备模拟脚本' || newStage === 'copying_scripts') {
    phase.value = props.narrativeMode ? 4 : 2
  }
})

// 从配置中计算自动生成的轮数（不使用硬编码默认值）
const autoGeneratedRounds = computed(() => {
  if (!simulationConfig.value?.time_config) {
    return null // 配置未生成时返回 null
  }
  const totalHours = simulationConfig.value.time_config.total_simulation_hours
  const minutesPerRound = simulationConfig.value.time_config.minutes_per_round
  if (!totalHours || !minutesPerRound) {
    return null // 配置数据不完整时返回 null
  }
  const calculatedRounds = Math.floor((totalHours * 60) / minutesPerRound)
  // 确保最大轮数不小于40（推荐值），避免滑动条范围异常
  return Math.max(calculatedRounds, 40)
})

// Polling timer
let pollTimer = null
let profilesTimer = null
let configTimer = null

// Computed
const displayProfiles = computed(() => {
  if (showProfilesDetail.value) {
    return profiles.value
  }
  return profiles.value.slice(0, 6)
})

// 根据agent_id获取对应的username
const getAgentUsername = (agentId) => {
  if (profiles.value && profiles.value.length > agentId && agentId >= 0) {
    const profile = profiles.value[agentId]
    return profile?.username || `agent_${agentId}`
  }
  return `agent_${agentId}`
}

// Profile 搜索过滤
const filteredProfiles = computed(() => {
  const q = profileSearchQuery.value.trim().toLowerCase()
  if (!q) return profiles.value
  if (searchNameOnly.value) {
    return profiles.value.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.username || '').toLowerCase().includes(q)
    )
  }
  return profiles.value.filter(p =>
    (p.name || '').toLowerCase().includes(q) ||
    (p.username || '').toLowerCase().includes(q) ||
    (p.profession || '').toLowerCase().includes(q) ||
    (p.temperament || '').toLowerCase().includes(q) ||
    (p.personality || '').toLowerCase().includes(q) ||
    (p.backstory || '').toLowerCase().includes(q)
  )
})

const filteredPlayerProfiles = computed(() => {
  const q = playerSearchQuery.value.trim().toLowerCase()
  if (!q) return profiles.value
  if (playerSearchNameOnly.value) {
    return profiles.value.filter(p =>
      (p.name || '').toLowerCase().includes(q) ||
      (p.username || '').toLowerCase().includes(q)
    )
  }
  return profiles.value.filter(p =>
    (p.name || '').toLowerCase().includes(q) ||
    (p.username || '').toLowerCase().includes(q) ||
    (p.temperament || '').toLowerCase().includes(q) ||
    (p.personality || '').toLowerCase().includes(q) ||
    (p.backstory || '').toLowerCase().includes(q)
  )
})

// 计算所有人设的关联问题总数
const totalTopicsCount = computed(() => {
  return profiles.value.reduce((sum, p) => {
    return sum + (p.interested_topics?.length || 0)
  }, 0)
})

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

// 处理开始模拟按钮点击
const handleStartSimulation = () => {
  // 构建传递给父组件的参数
  const params = {}
  
  if (useCustomRounds.value) {
    // 用户自定义轮数，传递 max_rounds 参数
    params.maxRounds = customMaxRounds.value
    addLog(`开始模拟，自定义轮数: ${customMaxRounds.value} 轮`)
  } else {
    // 用户选择保持自动生成的轮数，不传递 max_rounds 参数
    addLog(`开始模拟，使用自动配置轮数: ${autoGeneratedRounds.value} 轮`)
  }
  
  emit('next-step', params)
}

const truncateBio = (bio) => {
  if (bio.length > 80) {
    return bio.substring(0, 80) + '...'
  }
  return bio
}

const selectProfile = (profile) => {
  if (props.narrativeMode) {
    // narrative 模式下直接进入编辑，不显示空的社交档案 modal
    const idx = profiles.value.indexOf(profile)
    if (idx >= 0) openEditProfile(idx)
    emit('highlight-graph-node', profile.entity_uuid)
  } else {
    selectedProfile.value = profile
  }
}

const selectAsPlayer = (profile) => {
  selectedPlayerUuid.value = profile.entity_uuid
  emit('player-selected', profile.entity_uuid)
  addLog(`已选择玩家角色: ${profile.username || profile.name}`)
}

const openEditProfile = (idx) => {
  const p = profiles.value[idx]
  editingProfile.value = idx
  editingIsNew.value = false
  editForm.value = {
    name: p.name || '',
    username: p.username || '',
    profession: p.profession || '',
    age: p.age || null,
    gender: p.gender || 'male',
    mbti: p.mbti || '',
    bio: p.bio || '',
    persona: p.persona || '',
    topicsStr: (p.interested_topics || []).join(', '),
    // 叙事模式字段
    personality: p.personality || '',
    backstory: p.backstory || '',
    goalsStr: (p.goals || []).join(', '),
    speech_style: p.speech_style || '',
    temperament: p.temperament || '',
    current_location: p.current_location || ''
  }
}

const openAddProfile = async () => {
  editingProfile.value = 'new'
  editingIsNew.value = true
  selectedNodeUuid.value = ''
  editForm.value = {
    name: '',
    username: '',
    profession: '',
    age: null,
    gender: 'male',
    mbti: '',
    bio: '',
    persona: '',
    topicsStr: '',
    personality: '',
    backstory: '',
    goalsStr: '',
    speech_style: '',
    temperament: '',
    current_location: ''
  }

  // 加载图谱中尚无 profile 的节点
  const graphId = props.projectData?.graph_id
  if (graphId) {
    try {
      const res = await getGraphData(graphId)
      if (res.success && res.data?.nodes) {
        const existingUuids = new Set(profiles.value.map(p => p.entity_uuid))
        unassignedNodes.value = res.data.nodes.filter(n =>
          n.uuid && n.name && !existingUuids.has(n.uuid)
        )
      }
    } catch (err) {
      console.error('Failed to load unassigned nodes:', err)
      unassignedNodes.value = []
    }
  }
}

const onSelectExistingNode = () => {
  const uuid = selectedNodeUuid.value
  if (!uuid) return
  const node = unassignedNodes.value.find(n => n.uuid === uuid)
  if (node) {
    editForm.value.name = node.name || ''
    editForm.value.backstory = node.summary || ''
    // 尝试推导 entity_type
    const labels = node.labels || []
    const customLabel = labels.find(l => l !== 'Entity' && l !== 'Node')
    if (customLabel) editForm.value.profession = customLabel
  }
}

const saveEditProfile = async () => {
  const form = editForm.value
  const topics = form.topicsStr.split(/[,，]/).map(t => t.trim()).filter(Boolean)
  const goals = form.goalsStr.split(/[,，]/).map(t => t.trim()).filter(Boolean)
  const graphId = props.projectData?.graph_id
  const isNarrative = props.narrativeMode

  saving.value = true

  if (editingIsNew.value) {
    // ---- 添加新角色 ----
    let realUuid = `custom_${Date.now()}`

    if (selectedNodeUuid.value) {
      // 关联已有图谱节点，复用其 UUID
      realUuid = selectedNodeUuid.value
      addLog(`关联已有图谱节点: ${form.name}`)
    } else if (graphId) {
      // 创建新 FalkorDB 节点
      const summaryText = isNarrative
        ? (form.backstory || form.personality || '').substring(0, 500)
        : (form.bio || form.persona || '').substring(0, 500)
      try {
        const res = await createEntityNode(graphId, {
          name: form.name,
          entity_type: 'Person',
          summary: summaryText
        })
        if (res.success && res.data?.entity_uuid) {
          realUuid = res.data.entity_uuid
          addLog(`FalkorDB 节点已创建: ${form.name}`)
        }
      } catch (err) {
        addLog(`FalkorDB 创建节点失败: ${err.message}`)
      }
    }

    // 2) 立即加入前端列表并关闭弹窗（不等后端同步）
    const newProfile = {
      entity_uuid: realUuid,
      entity_type: '角色',
      name: form.name,
      username: form.username || form.name,
      profession: form.profession,
      age: form.age,
      gender: form.gender,
      mbti: form.mbti,
      bio: form.bio,
      persona: form.persona,
      interested_topics: topics,
      // 叙事模式字段
      personality: form.personality,
      backstory: form.backstory,
      goals: goals,
      speech_style: form.speech_style,
      temperament: form.temperament,
      current_location: form.current_location,
      source_entity_uuid: null
    }
    profiles.value.push(newProfile)
    addLog(`已手动添加角色: ${form.name}`)

    // 先关弹窗，让用户立刻看到新角色
    saving.value = false
    editingProfile.value = null

    // 3) 异步同步到叙事后端（不阻塞 UI）
    if (isNarrative && effectiveNarrativeSessionId.value) {
      const profileData = {
        name: form.name,
        username: form.username || form.name,
        personality: form.personality,
        backstory: form.backstory,
        goals: goals,
        speech_style: form.speech_style,
        temperament: form.temperament,
        current_location: form.current_location,
        entity_type: '角色',
        entity_uuid: realUuid
      }
      addNarrativeProfile(effectiveNarrativeSessionId.value, profileData).then(res => {
        if (res.success && res.data?.entity_uuid) {
          // 用后端返回的 UUID 更新（如果后端创建了新节点）
          const p = profiles.value.find(x => x.entity_uuid === realUuid)
          if (p && res.data.entity_uuid !== realUuid) {
            p.entity_uuid = res.data.entity_uuid
          }
          addLog(`角色已同步到叙事后端: ${form.name}`)
        }
      }).catch(err => {
        addLog(`叙事后端同步失败: ${err.message}`)
      })
    }
    return  // 已在上面关闭弹窗，直接返回
  } else {
    // ---- 编辑已有角色 ----
    const idx = editingProfile.value
    const p = profiles.value[idx]
    p.name = form.name
    if (isNarrative) {
      p.personality = form.personality
      p.backstory = form.backstory
      p.goals = goals
      p.speech_style = form.speech_style
      p.temperament = form.temperament
      p.current_location = form.current_location
    } else {
      p.username = form.username
      p.profession = form.profession
      p.age = form.age
      p.gender = form.gender
      p.mbti = form.mbti
      p.bio = form.bio
      p.persona = form.persona
      p.interested_topics = topics
    }
    addLog(`已编辑角色: ${form.name}`)

    // 叙事模式额外同步到后端 session
    if (isNarrative && effectiveNarrativeSessionId.value) {
      try {
        const profileData = {
          name: form.name,
          personality: form.personality,
          backstory: form.backstory,
          goals: goals,
          speech_style: form.speech_style,
          temperament: form.temperament,
          current_location: form.current_location
        }
        await updateNarrativeProfile(effectiveNarrativeSessionId.value, p.entity_uuid, profileData)
        addLog(`角色更新已同步到叙事后端: ${form.name}`)
      } catch (err) {
        addLog(`叙事后端同步失败: ${err.message}`)
      }
    }
  }

  saving.value = false
  editingProfile.value = null
}

// ---- 图谱编辑器 ----
const newEdgeTarget = ref('')
const newEdgeFact = ref('')
const newEdgeType = ref('RELATES_TO')

const openGraphEditor = async (idx) => {
  const p = profiles.value[idx]
  const graphId = props.projectData?.graph_id
  const entityUuid = p.entity_uuid

  if (!graphId || !entityUuid || entityUuid.startsWith('custom_')) {
    addLog(`该角色不在图谱中（UUID: ${entityUuid}）`)
    return
  }

  graphEditing.value = idx
  graphLoading.value = true
  graphForm.value = { name: '', summary: '', label: '', edges: [] }
  newEdgeTarget.value = ''
  newEdgeFact.value = ''

  try {
    const res = await getEntityEdges(graphId, entityUuid)
    if (res.success && res.data) {
      const d = res.data
      graphForm.value.name = d.node?.name || p.name || ''
      graphForm.value.summary = d.node?.summary || ''
      graphForm.value.label = d.node?.label || p.entity_type || 'Person'
      graphForm.value.edges = (d.edges || []).map(e => ({
        other_name: e.other_name || '',
        other_uuid: e.other_uuid || '',
        rel_type: e.rel_type || 'RELATES_TO',
        edge_name: e.edge_name || '',
        fact: e.fact || '',
        direction: e.direction || 'outgoing'
      }))
    }
  } catch (err) {
    addLog(`加载图谱数据失败: ${err.message}`)
  } finally {
    graphLoading.value = false
  }
}

const addGraphEdge = () => {
  const target = newEdgeTarget.value.trim()
  const fact = newEdgeFact.value.trim()
  if (!target || !fact) return
  graphForm.value.edges.push({
    other_name: target,
    other_uuid: '',
    rel_type: newEdgeType.value || 'RELATES_TO',
    edge_name: fact.substring(0, 50),
    fact: fact,
    direction: 'outgoing'
  })
  newEdgeTarget.value = ''
  newEdgeFact.value = ''
  newEdgeType.value = 'RELATES_TO'
}

const saveGraphEdits = async () => {
  const idx = graphEditing.value
  if (idx === null) return
  const p = profiles.value[idx]
  const graphId = props.projectData?.graph_id
  const entityUuid = p.entity_uuid
  if (!graphId || !entityUuid) return

  graphSaving.value = true
  try {
    // 1. 更新节点属性
    await updateEntityNode(graphId, entityUuid, {
      name: graphForm.value.name,
      summary: graphForm.value.summary,
      label: graphForm.value.label
    })

    // 2. 更新边
    const relationships = graphForm.value.edges.map(e => ({
      name: e.other_name,
      rel_type: e.rel_type || 'RELATES_TO',
      relation: e.fact
    }))
    await updateEntityEdges(graphId, entityUuid, { relationships })

    addLog(`图谱已更新: ${graphForm.value.name}`)
    graphEditing.value = null
  } catch (err) {
    addLog(`图谱保存失败: ${err.message}`)
  } finally {
    graphSaving.value = false
  }
}

const deleteProfile = async (idx) => {
  const p = profiles.value[idx]
  if (!p) return
  if (!confirm(`确定删除角色「${p.name}」？`)) return

  const graphId = props.projectData?.graph_id
  const entityUuid = p.entity_uuid
  const isGraphNode = graphId && entityUuid && !entityUuid.startsWith('custom_')

  // 询问是否同时删除图谱节点
  const alsoDeleteNode = isGraphNode && confirm(
    `是否同时删除图谱中「${p.name}」的节点及关联边？\n\n` +
    `[确定] 删除节点（不可恢复）\n[取消] 仅移除角色，保留图谱节点`
  )

  // 1) 从前端列表移除
  profiles.value.splice(idx, 1)
  addLog(`已删除角色: ${p.name}` + (alsoDeleteNode ? '（含图谱节点）' : '（保留图谱节点）'))

  // 如果是已选玩家角色，清除选择
  if (selectedPlayerUuid.value === entityUuid) {
    selectedPlayerUuid.value = ''
  }

  // 2) 仅在用户选择时删 FalkorDB 节点+边
  if (alsoDeleteNode) {
    deleteEntityNode(graphId, entityUuid).catch(err => {
      addLog(`FalkorDB 节点删除失败: ${err.message}`)
    })
  }

  // 3) 同步到叙事后端（传入 keep_node 参数）
  if (props.narrativeMode && effectiveNarrativeSessionId.value) {
    deleteNarrativeProfile(effectiveNarrativeSessionId.value, entityUuid, !alsoDeleteNode).catch(err => {
      addLog(`叙事后端删除失败: ${err.message}`)
    })
  }
}

const handleStartNarrative = () => {
  if (!selectedPlayerUuid.value) {
    addLog('请先选择一个角色作为玩家角色')
    return
  }
  const scene = initialSceneText.value.trim() || '一个充满未知与冒险的世界'
  const directText = openingMode.value === 'direct' ? openingDirectText.value.trim() : ''
  const priorSummary = openingMode.value === 'continuation' ? priorSummaryText.value.trim() : ''
  addLog(`开始叙事模式，玩家角色 UUID: ${selectedPlayerUuid.value}`)
  emit('next-step', {
    narrativeMode: true,
    playerEntityUuid: selectedPlayerUuid.value,
    initialScene: scene,
    openingText: directText || undefined,
    priorSummary: priorSummary || undefined,
    narrativeSessionId: effectiveNarrativeSessionId.value
  })
}

// 自动开始准备模拟
const startPrepareSimulation = async () => {
  // 叙事模式走专用准备流程
  if (props.narrativeMode) {
    await startPrepareNarrative()
    return
  }

  if (!props.simulationId) {
    addLog('错误：缺少 simulationId')
    emit('update-status', 'error')
    return
  }

  // 标记第一步完成，开始第二步
  phase.value = 1
  addLog(`模拟实例已创建: ${props.simulationId}`)
  addLog('正在准备模拟环境...')
  emit('update-status', 'processing')

  try {
    const res = await prepareSimulation({
      simulation_id: props.simulationId,
      use_llm_for_profiles: true,
      parallel_profile_count: 5
    })

    if (res.success && res.data) {
      if (res.data.already_prepared) {
        addLog('检测到已有完成的准备工作，直接使用')
        await loadPreparedData()
        return
      }

      taskId.value = res.data.task_id
      addLog(`准备任务已启动`)
      addLog(`  └─ Task ID: ${res.data.task_id}`)

      // 立即设置预期Agent总数（从prepare接口返回值获取）
      if (res.data.expected_entities_count) {
        expectedTotal.value = res.data.expected_entities_count
        addLog(`从Zep图谱读取到 ${res.data.expected_entities_count} 个实体`)
        if (res.data.entity_types && res.data.entity_types.length > 0) {
          addLog(`  └─ 实体类型: ${res.data.entity_types.join(', ')}`)
        }
      }

      addLog('开始轮询准备进度...')
      // 开始轮询进度
      startPolling()
      // 开始实时获取 Profiles
      startProfilesPolling()
    } else {
      addLog(`准备失败: ${res.error || '未知错误'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    addLog(`准备异常: ${err.message}`)
    emit('update-status', 'error')
  }
}

// 叙事模式专用准备流程
const startPrepareNarrative = async () => {
  phase.value = 1
  emit('update-status', 'processing')

  // 1) 如果已有叙事会话（从历史进入），先尝试加载已有数据，避免重新生成
  let sessionId = effectiveNarrativeSessionId.value
  if (sessionId) {
    addLog(`检测到已有叙事会话: ${sessionId}，正在恢复...`)
    try {
      // 加载已有 profiles
      const profilesRes = await getNarrativeProfiles(sessionId)
      if (profilesRes.success && profilesRes.data?.profiles?.length > 0) {
        profiles.value = (profilesRes.data.profiles || []).map((p, idx) => ({
          ...p,
          entity_uuid: p.entity_uuid || `agent_${idx}`
        }))
        const types = new Set()
        profiles.value.forEach(p => { if (p.entity_type) types.add(p.entity_type) })
        entityTypes.value = Array.from(types)
        addLog(`已恢复 ${profiles.value.length} 个角色档案`)
      }

      // 加载会话状态，恢复文本框内容
      const sessionRes = await getNarrativeSession(sessionId)
      if (sessionRes.success && sessionRes.data) {
        const s = sessionRes.data
        if (s.initial_scene) initialSceneText.value = s.initial_scene
        if (s.opening_text) {
          openingMode.value = 'direct'
          openingDirectText.value = s.opening_text
        } else if (s.prior_summary) {
          openingMode.value = 'continuation'
          priorSummaryText.value = s.prior_summary
        }
        // 如果 player 已选过（非 pending），恢复选择
        if (s.player_entity_uuid && s.player_entity_uuid !== 'pending') {
          selectedPlayerUuid.value = s.player_entity_uuid
        }
      }

      // 有 profiles 就直接进入完成态，不重新生成
      if (profiles.value.length > 0) {
        phase.value = 4
        emit('update-status', 'completed')
        addLog('叙事环境已恢复，可继续配置')
        return
      }

      addLog('未找到已有角色档案，开始重新生成...')
    } catch (err) {
      addLog(`恢复已有会话失败，重新生成: ${err.message}`)
    }
  }

  // 2) 如果还没有叙事会话，先创建一个（player_entity_uuid 稍后在用户选择角色时更新）
  if (!sessionId) {
    addLog('正在创建叙事会话...')
    try {
      const createRes = await createNarrative({
        project_id: props.projectData?.project_id,
        graph_id: props.projectData?.graph_id,
        player_entity_uuid: 'pending',
        simulation_id: props.simulationId || ''
      })
      if (createRes.success && createRes.data?.session_id) {
        sessionId = createRes.data.session_id
        localNarrativeSessionId.value = sessionId
        emit('narrative-session-created', sessionId)
        addLog(`叙事会话已创建: ${sessionId}`)
      } else {
        addLog(`创建叙事会话失败: ${createRes.error || '未知错误'}`)
        emit('update-status', 'error')
        return
      }
    } catch (err) {
      addLog(`创建叙事会话异常: ${err.message}`)
      emit('update-status', 'error')
      return
    }
  }

  // 3) 调用 prepare 生成角色档案
  addLog(`叙事会话: ${sessionId}`)
  addLog('正在准备叙事环境（生成角色档案）...')

  try {
    const res = await prepareNarrative({
      session_id: sessionId,
      parallel_count: 3
    })

    if (res.success && res.data) {
      taskId.value = res.data.task_id
      addLog(`叙事准备任务已启动`)
      addLog(`  └─ Task ID: ${res.data.task_id}`)

      // 开始轮询进度（使用 narrative API）
      startPolling()
      // 开始实时获取 Profiles（使用 narrative API）
      startProfilesPolling()
    } else {
      addLog(`准备失败: ${res.error || '未知错误'}`)
      emit('update-status', 'error')
    }
  } catch (err) {
    addLog(`准备异常: ${err.message}`)
    emit('update-status', 'error')
  }
}

const startPolling = () => {
  pollTimer = setInterval(pollPrepareStatus, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startProfilesPolling = () => {
  profilesTimer = setInterval(fetchProfilesRealtime, 3000)
}

const stopProfilesPolling = () => {
  if (profilesTimer) {
    clearInterval(profilesTimer)
    profilesTimer = null
  }
}

const pollPrepareStatus = async () => {
  if (!taskId.value && !props.simulationId && !effectiveNarrativeSessionId.value) return

  try {
    // 叙事模式使用叙事 API 轮询
    const res = props.narrativeMode
      ? await getNarrativePrepareStatus({
          task_id: taskId.value,
          session_id: effectiveNarrativeSessionId.value
        })
      : await getSimPrepareStatus({
          task_id: taskId.value,
          simulation_id: props.simulationId
        })
    
    if (res.success && res.data) {
      const data = res.data
      
      // 更新进度
      prepareProgress.value = data.progress || 0
      progressMessage.value = data.message || ''
      
      // 解析阶段信息并输出详细日志
      if (data.progress_detail) {
        currentStage.value = data.progress_detail.current_stage_name || ''
        
        // 输出详细进度日志（避免重复）
        const detail = data.progress_detail
        const logKey = `${detail.current_stage}-${detail.current_item}-${detail.total_items}`
        if (logKey !== lastLoggedMessage && detail.item_description) {
          lastLoggedMessage = logKey
          const stageInfo = `[${detail.stage_index}/${detail.total_stages}]`
          if (detail.total_items > 0) {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.current_item}/${detail.total_items} - ${detail.item_description}`)
          } else {
            addLog(`${stageInfo} ${detail.current_stage_name}: ${detail.item_description}`)
          }
        }
      } else if (data.message) {
        // 从消息中提取阶段
        const match = data.message.match(/\[(\d+)\/(\d+)\]\s*([^:]+)/)
        if (match) {
          currentStage.value = match[3].trim()
        }
        // 输出消息日志（避免重复）
        if (data.message !== lastLoggedMessage) {
          lastLoggedMessage = data.message
          addLog(data.message)
        }
      }
      
      // 检查是否完成
      if (data.status === 'completed' || data.status === 'ready' || data.already_prepared) {
        addLog('✓ 准备工作已完成')
        stopPolling()
        stopProfilesPolling()
        await loadPreparedData()
      } else if (data.status === 'failed') {
        addLog(`✗ 准备失败: ${data.error || '未知错误'}`)
        stopPolling()
        stopProfilesPolling()
        // 叙事模式：即使后端配置生成失败，只要有人设就可以继续
        if (props.narrativeMode && profiles.value.length > 0) {
          addLog('叙事模式：人设已就绪，可以继续')
          phase.value = 4
          emit('update-status', 'completed')
        }
      }
    }
  } catch (err) {
    console.warn('轮询状态失败:', err)
  }
}

const fetchProfilesRealtime = async () => {
  // 叙事模式使用叙事 API 获取 profiles
  if (props.narrativeMode) {
    if (!effectiveNarrativeSessionId.value) return
    try {
      const res = await getNarrativeProfiles(effectiveNarrativeSessionId.value)
      if (res.success && res.data) {
        const prevCount = profiles.value.length
        profiles.value = (res.data.profiles || []).map((p, idx) => ({
          ...p,
          entity_uuid: p.entity_uuid || `agent_${idx}`
        }))

        const types = new Set()
        profiles.value.forEach(p => {
          if (p.entity_type) types.add(p.entity_type)
        })
        entityTypes.value = Array.from(types)

        const currentCount = profiles.value.length
        if (currentCount > 0 && currentCount !== lastLoggedProfileCount) {
          narrativeProfileStableCount = 0
          lastLoggedProfileCount = currentCount
          const latestProfile = profiles.value[currentCount - 1]
          const profileName = latestProfile?.name || `Agent_${currentCount}`
          if (currentCount === 1) {
            addLog(`开始生成角色档案...`)
          }
          addLog(`→ 角色档案 ${currentCount}: ${profileName}`)
        } else if (currentCount > 0 && phase.value < 4) {
          narrativeProfileStableCount++
          if (narrativeProfileStableCount >= 3) {
            addLog(`✓ 检测到 ${currentCount} 个角色档案已稳定生成`)
            phase.value = 4
            stopProfilesPolling()
            addLog('叙事模式：环境准备完成，请选择角色')
            emit('update-status', 'completed')
          }
        }
      }
    } catch (err) {
      console.warn('获取叙事 Profiles 失败:', err)
    }
    return
  }

  if (!props.simulationId) return

  try {
    const res = await getSimulationProfilesRealtime(props.simulationId, 'reddit')

    if (res.success && res.data) {
      const prevCount = profiles.value.length
      // Normalize: ensure entity_uuid is always set (fallback to source_entity_uuid, then user_id)
      profiles.value = (res.data.profiles || []).map((p, idx) => ({
        ...p,
        entity_uuid: p.entity_uuid || p.source_entity_uuid || `user_${p.user_id ?? idx}`
      }))
      // 只有当 API 返回有效值时才更新，避免覆盖已有的有效值
      if (res.data.total_expected) {
        expectedTotal.value = res.data.total_expected
      }
      
      // 提取实体类型
      const types = new Set()
      profiles.value.forEach(p => {
        if (p.entity_type) types.add(p.entity_type)
      })
      entityTypes.value = Array.from(types)
      
      // 输出 Profile 生成进度日志（仅当数量变化时）
      const currentCount = profiles.value.length
      if (currentCount > 0 && currentCount !== lastLoggedProfileCount) {
        narrativeProfileStableCount = 0 // 数量变化，重置稳定计数
        lastLoggedProfileCount = currentCount
        const total = expectedTotal.value || '?'
        const latestProfile = profiles.value[currentCount - 1]
        const profileName = latestProfile?.name || latestProfile?.username || `Agent_${currentCount}`
        if (currentCount === 1) {
          addLog(`开始生成Agent人设...`)
        }
        addLog(`→ Agent人设 ${currentCount}/${total}: ${profileName} (${latestProfile?.profession || '未知职业'})`)

        // 如果全部生成完成（有预期总数且达到）
        if (expectedTotal.value && currentCount >= expectedTotal.value) {
          addLog(`✓ 全部 ${currentCount} 个Agent人设生成完成`)
          // 叙事模式：人设生成完成后直接跳到完成阶段（不需要等配置生成）
          if (props.narrativeMode && phase.value < 4) {
            phase.value = 4
            stopProfilesPolling()
            addLog('叙事模式：环境准备完成，请选择角色')
            emit('update-status', 'completed')
          }
        }
      } else if (currentCount > 0 && props.narrativeMode && phase.value < 4) {
        // 叙事模式备用检测：profiles数量连续3次轮询未变化（约9秒），说明已全部生成
        narrativeProfileStableCount++
        if (narrativeProfileStableCount >= 3) {
          addLog(`✓ 检测到 ${currentCount} 个Agent人设已稳定生成`)
          phase.value = 4
          stopProfilesPolling()
          addLog('叙事模式：环境准备完成，请选择角色')
          emit('update-status', 'completed')
        }
      }
    }
  } catch (err) {
    console.warn('获取 Profiles 失败:', err)
  }
}

// 配置轮询
const startConfigPolling = () => {
  configTimer = setInterval(fetchConfigRealtime, 2000)
}

const stopConfigPolling = () => {
  if (configTimer) {
    clearInterval(configTimer)
    configTimer = null
  }
}

const fetchConfigRealtime = async () => {
  if (!props.simulationId) return
  
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    
    if (res.success && res.data) {
      const data = res.data
      
      // 输出配置生成阶段日志（避免重复）
      if (data.generation_stage && data.generation_stage !== lastLoggedConfigStage) {
        lastLoggedConfigStage = data.generation_stage
        if (data.generation_stage === 'generating_profiles') {
          addLog('正在生成Agent人设配置...')
        } else if (data.generation_stage === 'generating_config') {
          addLog('正在调用LLM生成模拟配置参数...')
        }
      }
      
      // 如果配置已生成
      if (data.config_generated && data.config) {
        simulationConfig.value = data.config
        addLog('✓ 模拟配置生成完成')
        
        // 显示详细配置摘要
        if (data.summary) {
          addLog(`  ├─ Agent数量: ${data.summary.total_agents}个`)
          addLog(`  ├─ 模拟时长: ${data.summary.simulation_hours}小时`)
          addLog(`  ├─ 初始帖子: ${data.summary.initial_posts_count}条`)
          addLog(`  ├─ 热点话题: ${data.summary.hot_topics_count}个`)
          addLog(`  └─ 平台配置: Twitter ${data.summary.has_twitter_config ? '✓' : '✗'}, Reddit ${data.summary.has_reddit_config ? '✓' : '✗'}`)
        }
        
        // 显示时间配置详情
        if (data.config.time_config) {
          const tc = data.config.time_config
          addLog(`时间配置: 每轮${tc.minutes_per_round}分钟, 共${Math.floor((tc.total_simulation_hours * 60) / tc.minutes_per_round)}轮`)
        }
        
        // 显示事件配置
        if (data.config.event_config?.narrative_direction) {
          const narrative = data.config.event_config.narrative_direction
          addLog(`叙事方向: ${narrative.length > 50 ? narrative.substring(0, 50) + '...' : narrative}`)
        }
        
        stopConfigPolling()
        phase.value = 4
        addLog('✓ 环境搭建完成，可以开始模拟')
        emit('update-status', 'completed')
      }
    }
  } catch (err) {
    console.warn('获取 Config 失败:', err)
  }
}

const loadPreparedData = async () => {
  phase.value = 2
  addLog('正在加载已有配置数据...')

  // 最后获取一次 Profiles
  await fetchProfilesRealtime()
  addLog(`已加载 ${profiles.value.length} 个Agent人设`)

  // 叙事模式不需要配置，直接完成
  if (props.narrativeMode) {
    addLog('叙事模式：跳过配置加载，环境准备完成')
    phase.value = 4
    emit('update-status', 'completed')
    return
  }

  // 获取配置（使用实时接口）
  try {
    const res = await getSimulationConfigRealtime(props.simulationId)
    if (res.success && res.data) {
      if (res.data.config_generated && res.data.config) {
        simulationConfig.value = res.data.config
        addLog('✓ 模拟配置加载成功')

        // 显示详细配置摘要
        if (res.data.summary) {
          addLog(`  ├─ Agent数量: ${res.data.summary.total_agents}个`)
          addLog(`  ├─ 模拟时长: ${res.data.summary.simulation_hours}小时`)
          addLog(`  └─ 初始帖子: ${res.data.summary.initial_posts_count}条`)
        }

        addLog('✓ 环境搭建完成，可以开始模拟')
        phase.value = 4
        emit('update-status', 'completed')
      } else {
        // 配置尚未生成，开始轮询
        addLog('配置生成中，开始轮询等待...')
        startConfigPolling()
      }
    }
  } catch (err) {
    addLog(`加载配置失败: ${err.message}`)
    emit('update-status', 'error')
  }
}

// Scroll log to bottom
const logContent = ref(null)
watch(() => props.systemLogs?.length, () => {
  nextTick(() => {
    if (logContent.value) {
      logContent.value.scrollTop = logContent.value.scrollHeight
    }
  })
})

onMounted(() => {
  // 自动开始准备流程
  if (props.simulationId) {
    addLog('Step2 环境搭建初始化')
    if (props.narrativeMode && !props.projectData?.project_id) {
      // 叙事模式需要 projectData 才能创建会话，等待 projectData 加载
      const unwatch = watch(() => props.projectData, (val) => {
        if (val?.project_id) {
          unwatch()
          startPrepareSimulation()
        }
      }, { immediate: true })
    } else {
      startPrepareSimulation()
    }
  }
})

onUnmounted(() => {
  stopPolling()
  stopProfilesPolling()
  stopConfigPolling()
})
</script>

<style scoped>
.env-setup-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FAFAFA;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Step Card */
.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.3s ease;
  position: relative;
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }
.badge.accent { background: #E3F2FD; color: #1565C0; }

.card-content {
  /* No extra padding - uses step-card's padding */
}

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

/* Action Section */
.action-section {
  margin-top: 16px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn.primary {
  background: #000;
  color: #FFF;
}

.action-btn.primary:hover:not(:disabled) {
  opacity: 0.8;
}

.action-btn.secondary {
  background: #F5F5F5;
  color: #333;
}

.action-btn.secondary:hover:not(:disabled) {
  background: #E5E5E5;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-group {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.action-group.dual {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.action-group.dual .action-btn {
  width: 100%;
}

/* Info Card */
.info-card {
  background: #F5F5F5;
  border-radius: 6px;
  padding: 16px;
  margin-top: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed #E0E0E0;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  font-size: 12px;
  color: #666;
}

.info-value {
  font-size: 13px;
  font-weight: 500;
}

.info-value.mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
}

/* Stats Grid */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

/* Profiles Preview */
.profiles-preview {
  margin-top: 20px;
  border-top: 1px solid #E5E5E5;
  padding-top: 16px;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.preview-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.profile-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.profile-search-input {
  flex: 1;
  height: 30px;
  padding: 0 10px;
  border: 1px solid #DDD;
  border-radius: 4px;
  font-size: 13px;
  color: #333;
  outline: none;
  background: #FAFAFA;
}

.profile-search-input:focus {
  border-color: #999;
  background: #FFF;
}

.search-mode-toggle {
  height: 30px;
  padding: 0 10px;
  border: 1px solid #DDD;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
  background: #FAFAFA;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}
.search-mode-toggle:hover {
  border-color: #999;
  background: #F0F0F0;
}
.search-mode-toggle.active {
  border-color: #7C3AED;
  color: #7C3AED;
  background: #F5F0FF;
}

.profile-search-count {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

.profiles-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.profiles-list::-webkit-scrollbar {
  width: 4px;
}

.profiles-list::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.profiles-list::-webkit-scrollbar-thumb:hover {
  background: #CCC;
}

.profile-card {
  background: #FAFAFA;
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.profile-card:hover {
  border-color: #999;
  background: #FFF;
}

.profile-card.player-selected {
  border-color: #1565C0;
  background: #E3F2FD;
  box-shadow: 0 0 0 2px rgba(21, 101, 192, 0.2);
}

.player-radio-overlay {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  z-index: 1;
}

.player-radio {
  width: 16px;
  height: 16px;
  accent-color: #1565C0;
  cursor: pointer;
}

.player-radio-label {
  font-size: 11px;
  font-weight: 600;
  color: #1565C0;
}

.player-selected-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
}

.player-badge-label {
  font-size: 11px;
  font-weight: 600;
  color: #FFF;
  background: #1565C0;
  padding: 2px 8px;
  border-radius: 4px;
}

.narrative-hint {
  font-size: 12px;
  font-weight: 600;
  color: #1565C0;
  background: #E3F2FD;
  padding: 2px 8px;
  border-radius: 4px;
}

.narrative-player-select {
  margin-bottom: 20px;
}

.narrative-selected-hint {
  font-size: 12px;
  font-weight: 600;
  color: #1565C0;
  background: #E3F2FD;
  padding: 2px 8px;
  border-radius: 4px;
}

.narrative-opening-section {
  margin-bottom: 20px;
}
.opening-mode-switch {
  display: flex;
  gap: 4px;
  background: #F3F4F6;
  border-radius: 6px;
  padding: 2px;
}
.mode-btn {
  padding: 4px 12px;
  font-size: 12px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #6B7280;
  cursor: pointer;
  transition: all 0.2s;
}
.mode-btn.active {
  background: #FFF;
  color: #1565C0;
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0,0,0,0.08);
}
.opening-hint {
  font-size: 11px;
  color: #6B7280;
  margin: 6px 0 0;
}
.initial-scene-input.direct-mode {
  min-height: 120px;
}
.initial-scene-input {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #1F2937;
  background: #FAFAFA;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
  margin-top: 8px;
  box-sizing: border-box;
}
.initial-scene-input:focus {
  outline: none;
  border-color: #1565C0;
  background: #FFF;
}
.initial-scene-input::placeholder {
  color: #9CA3AF;
  font-size: 12px;
}

.file-summary-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 6px 0 4px;
}

.file-upload-btn {
  display: inline-block;
  padding: 6px 14px;
  border: 1px solid #1565C0;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #1565C0;
  background: #FFF;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.file-upload-btn:hover { background: #E3F2FD; }
.file-upload-btn.loading {
  color: #999;
  border-color: #CCC;
  cursor: not-allowed;
}

.summarize-error {
  font-size: 11px;
  color: #D32F2F;
}

.narrative-start-btn {
  background: #1565C0 !important;
}
.narrative-start-btn:hover:not(:disabled) {
  background: #0D47A1 !important;
}

.profile-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.profile-realname {
  font-size: 14px;
  font-weight: 700;
  color: #000;
}

.profile-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #999;
}

.profile-graph-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.entity-type-badge {
  font-size: 10px;
  font-weight: 600;
  color: #FFF;
  background: #7B2D8E;
  padding: 1px 7px;
  border-radius: 8px;
  letter-spacing: 0.3px;
}

.entity-uuid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  background: #F5F5F5;
  padding: 1px 5px;
  border-radius: 3px;
}

.rel-count {
  font-size: 10px;
  color: #888;
}

.profile-meta {
  margin-bottom: 8px;
}

.profile-profession {
  font-size: 11px;
  color: #666;
  background: #F0F0F0;
  padding: 2px 8px;
  border-radius: 3px;
}

.profile-bio {
  font-size: 12px;
  color: #444;
  line-height: 1.6;
  margin: 0 0 10px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.profile-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.topic-tag {
  font-size: 10px;
  color: #1565C0;
  background: #E3F2FD;
  padding: 2px 8px;
  border-radius: 10px;
}

.topic-more {
  font-size: 10px;
  color: #999;
  padding: 2px 6px;
}

/* Config Preview */
/* Config Detail Panel */
.config-detail-panel {
  margin-top: 16px;
}

.config-block {
  margin-top: 16px;
  border-top: 1px solid #E5E5E5;
  padding-top: 12px;
}

.config-block:first-child {
  margin-top: 0;
  border-top: none;
  padding-top: 0;
}

.config-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.config-block-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.config-block-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  background: #F1F5F9;
  color: #475569;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Config Grid */
.config-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.config-item {
  background: #F9F9F9;
  padding: 12px 14px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-item-label {
  font-size: 11px;
  color: #94A3B8;
}

.config-item-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 16px;
  font-weight: 600;
  color: #1E293B;
}

/* Time Periods */
.time-periods {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.period-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #F9F9F9;
  border-radius: 6px;
}

.period-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748B;
  min-width: 70px;
}

.period-hours {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #475569;
  flex: 1;
}

.period-multiplier {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  color: #6366F1;
  background: #EEF2FF;
  padding: 2px 6px;
  border-radius: 4px;
}

/* Agents Cards */
.agents-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 4px;
}

.agents-cards::-webkit-scrollbar {
  width: 4px;
}

.agents-cards::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.agents-cards::-webkit-scrollbar-thumb:hover {
  background: #CCC;
}

.agent-card {
  background: #F9F9F9;
  border: 1px solid #E5E5E5;
  border-radius: 6px;
  padding: 14px;
  transition: all 0.2s ease;
}

.agent-card:hover {
  border-color: #999;
  background: #FFF;
}

/* Agent Card Header */
.agent-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid #F1F5F9;
}

.agent-identity {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.agent-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #94A3B8;
}

.agent-name {
  font-size: 14px;
  font-weight: 600;
  color: #1E293B;
}

.agent-tags {
  display: flex;
  gap: 6px;
}

.agent-type {
  font-size: 10px;
  color: #64748B;
  background: #F1F5F9;
  padding: 2px 8px;
  border-radius: 4px;
}

.agent-stance {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
}

.stance-neutral {
  background: #F1F5F9;
  color: #64748B;
}

.stance-supportive {
  background: #DCFCE7;
  color: #16A34A;
}

.stance-opposing {
  background: #FEE2E2;
  color: #DC2626;
}

.stance-observer {
  background: #FEF3C7;
  color: #D97706;
}

/* Agent Timeline */
.agent-timeline {
  margin-bottom: 14px;
}

.timeline-label {
  display: block;
  font-size: 10px;
  color: #94A3B8;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.mini-timeline {
  display: flex;
  gap: 2px;
  height: 16px;
  background: #F8FAFC;
  border-radius: 4px;
  padding: 3px;
}

.timeline-hour {
  flex: 1;
  background: #E2E8F0;
  border-radius: 2px;
  transition: all 0.2s;
}

.timeline-hour.active {
  background: linear-gradient(180deg, #6366F1, #818CF8);
}

.timeline-marks {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: #94A3B8;
}

/* Agent Params */
.agent-params {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-group {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.param-item .param-label {
  font-size: 10px;
  color: #94A3B8;
}

.param-item .param-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.param-value.with-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mini-bar {
  height: 4px;
  background: linear-gradient(90deg, #6366F1, #A855F7);
  border-radius: 2px;
  min-width: 4px;
  max-width: 40px;
}

.param-value.positive {
  color: #16A34A;
}

.param-value.negative {
  color: #DC2626;
}

.param-value.neutral {
  color: #64748B;
}

.param-value.highlight {
  color: #6366F1;
}

/* Platforms Grid */
.platforms-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.platform-card {
  background: #F9F9F9;
  padding: 14px;
  border-radius: 6px;
}

.platform-card-header {
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #E5E5E5;
}

.platform-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.platform-params {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.param-label {
  font-size: 12px;
  color: #64748B;
}

.param-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: #1E293B;
}

/* Reasoning Content */
.reasoning-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reasoning-item {
  padding: 12px 14px;
  background: #F9F9F9;
  border-radius: 6px;
}

.reasoning-text {
  font-size: 13px;
  color: #555;
  line-height: 1.7;
  margin: 0;
}

/* Profile Modal */
.profile-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.profile-modal {
  background: #FFF;
  border-radius: 16px;
  width: 90%;
  max-width: 600px;
  max-height: 85vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 24px;
  background: #FFF;
  border-bottom: 1px solid #F0F0F0;
}

.modal-header-info {
  flex: 1;
}

.modal-name-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.modal-realname {
  font-size: 20px;
  font-weight: 700;
  color: #000;
}

.modal-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #999;
}

.modal-profession {
  font-size: 12px;
  color: #666;
  background: #F5F5F5;
  padding: 4px 10px;
  border-radius: 4px;
  display: inline-block;
  font-weight: 500;
}

.close-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: none;
  color: #999;
  border-radius: 50%;
  font-size: 24px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: color 0.2s;
  padding: 0;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

/* 基本信息网格 */
.modal-info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px 16px;
  margin-bottom: 32px;
  padding: 0;
  background: transparent;
  border-radius: 0;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 11px;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.info-value {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.info-value.mbti {
  font-family: 'JetBrains Mono', monospace;
  color: #FF5722;
}

/* 模块区域 */
.modal-section {
  margin-bottom: 28px;
}

.section-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.section-bio {
  font-size: 14px;
  color: #333;
  line-height: 1.6;
  margin: 0;
  padding: 16px;
  background: #F9F9F9;
  border-radius: 6px;
  border-left: 3px solid #E0E0E0;
}

/* 话题标签 */
.topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.topic-item {
  font-size: 11px;
  color: #1565C0;
  background: #E3F2FD;
  padding: 4px 10px;
  border-radius: 12px;
  transition: all 0.2s;
  border: none;
}

.topic-item:hover {
  background: #BBDEFB;
  color: #0D47A1;
}

/* 详细人设 */
.persona-dimensions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.dimension-card {
  background: #F8F9FA;
  padding: 12px;
  border-radius: 6px;
  border-left: 3px solid #DDD;
  transition: all 0.2s;
}

.dimension-card:hover {
  background: #F0F0F0;
  border-left-color: #999;
}

.dim-title {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #333;
  margin-bottom: 4px;
}

.dim-desc {
  display: block;
  font-size: 10px;
  color: #888;
  line-height: 1.4;
}

.persona-content {
  max-height: none;
  overflow: visible;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
}

.persona-content::-webkit-scrollbar {
  width: 4px;
}

.persona-content::-webkit-scrollbar-thumb {
  background: #DDD;
  border-radius: 2px;
}

.section-persona {
  font-size: 13px;
  color: #555;
  line-height: 1.8;
  margin: 0;
  text-align: justify;
}

/* System Logs */
.system-logs {
  background: #000;
  color: #DDD;
  padding: 16px;
  font-family: 'JetBrains Mono', monospace;
  border-top: 1px solid #222;
  flex-shrink: 0;
}

.log-header {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid #333;
  padding-bottom: 8px;
  margin-bottom: 8px;
  font-size: 10px;
  color: #888;
}

.log-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 80px; /* Approx 4 lines visible */
  overflow-y: auto;
  padding-right: 4px;
}

.log-content::-webkit-scrollbar {
  width: 4px;
}

.log-content::-webkit-scrollbar-thumb {
  background: #333;
  border-radius: 2px;
}

.log-line {
  font-size: 11px;
  display: flex;
  gap: 12px;
  line-height: 1.5;
}

.log-time {
  color: #666;
  min-width: 75px;
}

.log-msg {
  color: #CCC;
  word-break: break-all;
}

/* Spinner */
.spinner-sm {
  width: 16px;
  height: 16px;
  border: 2px solid #E5E5E5;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
/* Orchestration Content */
.orchestration-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 16px;
}

.box-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.narrative-box {
  background: #FFFFFF;
  padding: 20px 24px;
  border-radius: 12px;
  border: 1px solid #EEF2F6;
  box-shadow: 0 4px 24px rgba(0,0,0,0.03);
  transition: all 0.3s ease;
}

.narrative-box .box-label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #666;
  font-size: 13px;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  font-weight: 600;
}

.special-icon {
  filter: drop-shadow(0 2px 4px rgba(255, 87, 34, 0.2));
  transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.narrative-box:hover .special-icon {
  transform: rotate(180deg);
}

.narrative-text {
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  color: #334155;
  line-height: 1.8;
  margin: 0;
  text-align: justify;
  letter-spacing: 0.01em;
}

.topics-section {
  background: #FFF;
}

.hot-topics-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hot-topic-tag {
  font-size: 12px;
  color:rgba(255, 86, 34, 0.88);
  background: #FFF3E0;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.hot-topic-more {
  font-size: 11px;
  color: #999;
  padding: 4px 6px;
}

.initial-posts-section {
  border-top: 1px solid #EAEAEA;
  padding-top: 16px;
}

.posts-timeline {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-left: 8px;
  border-left: 2px solid #F0F0F0;
  margin-top: 12px;
}

.timeline-item {
  position: relative;
  padding-left: 20px;
}

.timeline-marker {
  position: absolute;
  left: 0;
  top: 14px;
  width: 12px;
  height: 2px;
  background: #DDD;
}

.timeline-content {
  background: #F9F9F9;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #EEE;
}

.post-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.post-role {
  font-size: 11px;
  font-weight: 700;
  color: #333;
  text-transform: uppercase;
}

.post-agent-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.post-id,
.post-username {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #666;
  line-height: 1;
  vertical-align: baseline;
}

.post-username {
  margin-right: 6px;
}

.post-text {
  font-size: 12px;
  color: #555;
  line-height: 1.5;
  margin: 0;
}

/* 模拟轮数配置样式 */
.rounds-config-section {
  margin: 24px 0;
  padding-top: 24px;
  border-top: 1px solid #EAEAEA;
}

.rounds-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #1E293B;
}

.section-desc {
  font-size: 12px;
  color: #94A3B8;
}

.desc-highlight {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: #1E293B;
  background: #F1F5F9;
  padding: 1px 6px;
  border-radius: 4px;
  margin: 0 2px;
}

/* Switch Control */
.switch-control {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px 4px 4px;
  border-radius: 20px;
  transition: background 0.2s;
}

.switch-control:hover {
  background: #F8FAFC;
}

.switch-control input {
  display: none;
}

.switch-track {
  width: 36px;
  height: 20px;
  background: #E2E8F0;
  border-radius: 10px;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
}

.switch-track::after {
  content: '';
  position: absolute;
  left: 2px;
  top: 2px;
  width: 16px;
  height: 16px;
  background: #FFF;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  transition: transform 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
}

.switch-control input:checked + .switch-track {
  background: #000;
}

.switch-control input:checked + .switch-track::after {
  transform: translateX(16px);
}

.switch-label {
  font-size: 12px;
  font-weight: 500;
  color: #64748B;
}

.switch-control input:checked ~ .switch-label {
  color: #1E293B;
}

/* Slider Content */
.rounds-content {
  animation: fadeIn 0.3s ease;
}

.slider-display {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
}

.slider-main-value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.val-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 24px;
  font-weight: 700;
  color: #000;
}

.val-unit {
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.slider-meta-info {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #64748B;
  background: #F1F5F9;
  padding: 4px 8px;
  border-radius: 4px;
}

.range-wrapper {
  position: relative;
  padding: 0 2px;
}

.minimal-slider {
  -webkit-appearance: none;
  width: 100%;
  height: 4px;
  background: #E2E8F0;
  border-radius: 2px;
  outline: none;
  background-image: linear-gradient(#000, #000);
  background-size: var(--percent, 0%) 100%;
  background-repeat: no-repeat;
  cursor: pointer;
}

.minimal-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #FFF;
  border: 2px solid #000;
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(0,0,0,0.1);
  transition: transform 0.1s;
  margin-top: -6px; /* Center thumb */
}

.minimal-slider::-webkit-slider-thumb:hover {
  transform: scale(1.1);
}

.minimal-slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 2px;
}

.range-marks {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #94A3B8;
  position: relative;
}

.mark-recommend {
  cursor: pointer;
  transition: color 0.2s;
  position: relative;
}

.mark-recommend:hover {
  color: #000;
}

.mark-recommend.active {
  color: #000;
  font-weight: 600;
}

.mark-recommend::after {
  content: '';
  position: absolute;
  top: -12px;
  left: 50%;
  transform: translateX(-50%);
  width: 1px;
  height: 4px;
  background: #CBD5E1;
}

/* Auto Info */
.auto-info-card {
  display: flex;
  align-items: center;
  gap: 24px;
  background: #F8FAFC;
  padding: 16px 20px;
  border-radius: 8px;
}

.auto-value {
  display: flex;
  flex-direction: row;
  align-items: baseline;
  gap: 4px;
  padding-right: 24px;
  border-right: 1px solid #E2E8F0;
}

.auto-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  justify-content: center;
}

.auto-meta-row {
  display: flex;
  align-items: center;
}

.duration-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 500;
  color: #64748B;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  padding: 3px 8px;
  border-radius: 6px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}

.auto-desc {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.auto-desc p {
  margin: 0;
  font-size: 13px;
  color: #64748B;
  line-height: 1.5;
}

.highlight-tip {
  margin-top: 4px !important;
  font-size: 12px !important;
  color: #000 !important;
  font-weight: 500;
  cursor: pointer;
}

.highlight-tip:hover {
  text-decoration: underline;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Modal Transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .profile-modal {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .profile-modal {
  transition: all 0.3s ease-in;
}

.modal-enter-from .profile-modal,
.modal-leave-to .profile-modal {
  transform: scale(0.95) translateY(10px);
  opacity: 0;
}

/* Profile Button Group */
.profile-btn-group {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 1;
  display: flex;
  gap: 4px;
}

.profile-edit-btn,
.profile-graph-btn,
.profile-delete-btn {
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.profile-edit-btn {
  color: #666;
  background: #F5F5F5;
}

.profile-edit-btn:hover {
  color: #FF5722;
  background: #FFF3E0;
}

.profile-graph-btn {
  color: #1565C0;
  background: #E3F2FD;
}

.profile-graph-btn:hover {
  color: #0D47A1;
  background: #BBDEFB;
}

.profile-delete-btn {
  color: #999;
  background: #F5F5F5;
}

.profile-delete-btn:hover {
  color: #D32F2F;
  background: #FFEBEE;
}

/* Graph Editor */
.graph-editor-modal {
  max-width: 560px;
}

.graph-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #333;
  margin: 12px 0 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid #EEE;
}

.graph-loading {
  text-align: center;
  padding: 30px;
  color: #999;
  font-size: 13px;
}

.graph-edge-row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}

.edge-direction {
  width: 20px;
  text-align: center;
  font-size: 14px;
  color: #999;
  flex-shrink: 0;
}

.edge-other-name {
  width: 100px;
  font-size: 12px;
  font-weight: 600;
  color: #333;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.edge-fact {
  flex: 1;
}

.edge-remove-btn {
  width: 24px;
  height: 24px;
  border: 1px solid #EEE;
  border-radius: 4px;
  background: none;
  cursor: pointer;
  color: #999;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.edge-remove-btn:hover {
  color: #F44336;
  border-color: #F44336;
  background: #FFF5F5;
}

.graph-add-edge {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 6px;
}

.edge-target-input {
  width: 100px;
  flex-shrink: 0;
}

.edge-type-select {
  width: 130px;
  flex-shrink: 0;
  font-size: 11px;
}

.edge-fact-input {
  flex: 1;
}

.edge-add-btn {
  padding: 4px 10px;
  border: 1px dashed #DDD;
  border-radius: 4px;
  background: none;
  cursor: pointer;
  font-size: 11px;
  color: #999;
  white-space: nowrap;
  transition: all 0.2s;
}

.edge-add-btn:hover {
  border-color: #1565C0;
  color: #1565C0;
}

/* Add Profile Button */
.add-profile-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 16px;
  border: 2px dashed #DDD;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #999;
  transition: all 0.2s;
  margin-top: 4px;
}

.add-profile-btn:hover {
  border-color: #FF5722;
  color: #FF5722;
  background: #FFF8F5;
}

.add-icon {
  font-size: 18px;
  font-weight: 300;
}

/* Edit Form Styles */
.edit-modal .modal-body {
  max-height: 60vh;
  overflow-y: auto;
}

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.link-node-group {
  background: #F8F6FF;
  border: 1px dashed #C4B5FD;
  border-radius: 6px;
  padding: 10px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #333;
}

.form-hint {
  font-weight: 400;
  color: #999;
}

.form-input {
  padding: 8px 12px;
  border: 1px solid #DDD;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  transition: border-color 0.2s;
  background: #FAFAFA;
}

.form-input:focus {
  outline: none;
  border-color: #FF5722;
  background: #FFF;
}

.form-textarea {
  padding: 8px 12px;
  border: 1px solid #DDD;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  background: #FAFAFA;
}

.form-textarea:focus {
  outline: none;
  border-color: #FF5722;
  background: #FFF;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid #F0F0F0;
}
</style>
