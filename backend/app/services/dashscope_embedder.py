"""
阿里云 DashScope 兼容的 Embedder

DashScope 的 embedding API 限制单次请求最多 10 条输入，
本模块继承 OpenAIEmbedder 并在 create_batch 中自动分批。
"""

from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

DASHSCOPE_MAX_BATCH_SIZE = 10


class DashScopeEmbedder(OpenAIEmbedder):
    """OpenAIEmbedder wrapper that respects DashScope's batch size limit of 10."""

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        if len(input_data_list) <= DASHSCOPE_MAX_BATCH_SIZE:
            return await super().create_batch(input_data_list)

        # Split into chunks of DASHSCOPE_MAX_BATCH_SIZE
        all_embeddings = []
        for i in range(0, len(input_data_list), DASHSCOPE_MAX_BATCH_SIZE):
            batch = input_data_list[i:i + DASHSCOPE_MAX_BATCH_SIZE]
            embeddings = await super().create_batch(batch)
            all_embeddings.extend(embeddings)
        return all_embeddings
