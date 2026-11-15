"""
Слой LangGraph: граф диалога.

Модули:
    - state: TypedDict состояния графа;
    - prompts: промпты узлов;
    - nodes: узлы графа;
    - dialogue_graph: сборка StateGraph;
    - vector_store_reader: чтение чанков из векторного хранилища;
    - service: RAGService — единственная точка входа для API.
"""
