"""
语义切分模块

基于 embedding 余弦相似度检测语义断点，将文本切分为语义内聚的 chunk。

算法流程：
1. 将文本按句子边界拆分
2. 对每个句子生成 embedding
3. 计算相邻句子的余弦相似度
4. 在相似度显著下降处标记为断点
5. 按断点分组，合并/拆分以满足目标大小约束
"""

import asyncio
import logging
import re
from typing import List, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)

# ── 句子拆分的标点模式 ──────────────────────────────────────────────
# 中文句末标点 + 英文句末标点（后跟空格或换行）
_SENTENCE_SPLIT_RE = re.compile(
    r'(?<=[。！？\!\?])'           # 中文句号/叹号/问号 或 英文!?（后面直接断）
    r'|(?<=[\.\!\?])(?=\s)'       # 英文句末标点后跟空白
    r'|(?<=\n)'                    # 换行处也断
)


class EmbedderProtocol(Protocol):
    """Embedder 需要实现的接口（兼容 graphiti_core 的 OpenAIEmbedder）"""
    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]: ...


def _split_into_sentences(text: str) -> List[str]:
    """
    将文本按句子边界拆分。

    保留句末标点在句子内。过滤空白句子。
    对于过长的单句（>500字符），在逗号/分号处再拆。
    """
    raw = _SENTENCE_SPLIT_RE.split(text)
    sentences = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        # 过长的句子在逗号/分号处再拆
        if len(s) > 500:
            sub_parts = re.split(r'(?<=[，,；;：:])', s)
            buf = ""
            for part in sub_parts:
                if buf and len(buf) + len(part) > 400:
                    sentences.append(buf.strip())
                    buf = part
                else:
                    buf += part
            if buf.strip():
                sentences.append(buf.strip())
        else:
            sentences.append(s)
    return sentences


def _cosine_similarity_consecutive(embeddings: np.ndarray) -> np.ndarray:
    """计算相邻向量的余弦相似度，返回长度为 n-1 的数组。"""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = embeddings / norms
    # 相邻点积
    sims = np.sum(normed[:-1] * normed[1:], axis=1)
    return sims


def _find_breakpoints(
    similarities: np.ndarray,
    sentence_lengths: List[int],
    target_size: int,
) -> List[int]:
    """
    找到语义断点位置，数量根据 target_size 自适应。

    1. 根据总文本长度和 target_size 估算期望 chunk 数 → 需要的断点数
    2. 选相似度最低的 top-N 个间隙作为断点
    3. 额外保障：相似度极低（< 0.3）的间隙强制加入

    返回的索引表示"在第 i 个句子之后切断"。
    """
    if len(similarities) == 0:
        return []

    total_len = sum(sentence_lengths)
    expected_chunks = max(1, total_len / target_size)
    # 断点数 = 期望 chunk 数 - 1，但至少留 1 个，上限为间隙总数的一半
    n_breakpoints = max(1, min(int(expected_chunks - 1), len(similarities) // 2))

    # 按相似度升序取 top-N
    sorted_indices = np.argsort(similarities)
    selected = set(sorted_indices[:n_breakpoints].tolist())

    # 极低相似度强制加入（话题剧变）
    for i, sim in enumerate(similarities):
        if sim < 0.3:
            selected.add(i)

    return sorted(selected)


def _merge_sentences_to_chunks(
    sentences: List[str],
    breakpoints: List[int],
    target_size: int,
    min_size: int,
    max_size: int,
) -> List[str]:
    """
    按断点将句子合并成 chunk，同时尊重大小约束。

    - 优先在语义断点处切分
    - chunk 过小则与下一组合并
    - chunk 过大则在内部句子边界处再拆
    """
    if not sentences:
        return []

    # 将句子按断点分组
    bp_set = set(breakpoints)
    groups: List[List[str]] = []
    current_group: List[str] = []

    for i, sent in enumerate(sentences):
        current_group.append(sent)
        if i in bp_set or i == len(sentences) - 1:
            groups.append(current_group)
            current_group = []

    # 合并过小的组
    merged: List[List[str]] = []
    buf: List[str] = []
    buf_len = 0

    for group in groups:
        group_len = sum(len(s) for s in group)
        if buf and buf_len + group_len > target_size:
            merged.append(buf)
            buf = group
            buf_len = group_len
        else:
            buf.extend(group)
            buf_len += group_len

    if buf:
        merged.append(buf)

    # 对过大的组在句子边界处再拆
    chunks: List[str] = []
    for group in merged:
        text = "\n".join(group)
        if len(text) <= max_size:
            chunks.append(text)
        else:
            # 贪心按句子累积
            sub_buf = []
            sub_len = 0
            for sent in group:
                if sub_buf and sub_len + len(sent) > target_size:
                    chunks.append("\n".join(sub_buf))
                    sub_buf = [sent]
                    sub_len = len(sent)
                else:
                    sub_buf.append(sent)
                    sub_len += len(sent)
            if sub_buf:
                chunks.append("\n".join(sub_buf))

    # 最后一轮：过小的尾部 chunk 合并到前一个
    if len(chunks) > 1 and len(chunks[-1]) < min_size:
        chunks[-2] = chunks[-2] + "\n" + chunks[-1]
        chunks.pop()

    return chunks


async def semantic_chunk_async(
    text: str,
    embedder: EmbedderProtocol,
    target_size: int = 1500,
) -> List[str]:
    """
    基于 embedding 语义相似度的文本切分。

    Args:
        text: 待切分文本
        embedder: 实现了 create_batch 的 embedder
        target_size: 目标 chunk 大小（字符数），断点数量会自适应此值

    Returns:
        语义切分后的 chunk 列表；None 表示 embedding 失败需降级
    """
    # 短文本不需要切分
    if len(text) <= target_size:
        return [text] if text.strip() else []

    # 1. 拆句
    sentences = _split_into_sentences(text)
    if len(sentences) <= 1:
        return [text] if text.strip() else []

    sentence_lengths = [len(s) for s in sentences]
    logger.info(f"[SemanticChunker] 拆分出 {len(sentences)} 个句子，开始计算 embedding...")

    # 2. 获取 embedding
    try:
        embeddings_list = await embedder.create_batch(sentences)
        embeddings = np.array(embeddings_list, dtype=np.float32)
    except Exception as e:
        logger.warning(f"[SemanticChunker] embedding 调用失败，降级为按长度切分: {e}")
        return None  # 返回 None 表示需要降级

    if len(embeddings) != len(sentences):
        logger.warning("[SemanticChunker] embedding 数量与句子数不匹配，降级")
        return None

    # 3. 计算相邻相似度
    similarities = _cosine_similarity_consecutive(embeddings)

    # 4. 找断点（数量根据 target_size 自适应）
    breakpoints = _find_breakpoints(similarities, sentence_lengths, target_size)
    logger.info(
        f"[SemanticChunker] 相似度范围 [{similarities.min():.3f}, {similarities.max():.3f}], "
        f"断点数: {len(breakpoints)}"
    )

    # 5. 按断点合并成 chunk
    min_size = max(int(target_size * 0.3), 100)
    max_size = int(target_size * 2.0)
    chunks = _merge_sentences_to_chunks(
        sentences, breakpoints,
        target_size=target_size,
        min_size=min_size,
        max_size=max_size,
    )

    logger.info(
        f"[SemanticChunker] 生成 {len(chunks)} 个语义 chunk, "
        f"大小范围: [{min(len(c) for c in chunks)}, {max(len(c) for c in chunks)}]"
    )
    return chunks


def semantic_chunk(
    text: str,
    embedder: EmbedderProtocol,
    loop: asyncio.AbstractEventLoop,
    target_size: int = 1500,
) -> Optional[List[str]]:
    """
    同步包装器，在指定 event loop 中执行语义切分。

    返回 None 表示 embedding 失败，调用方应降级到按长度切分。
    """
    return loop.run_until_complete(
        semantic_chunk_async(text, embedder, target_size)
    )
