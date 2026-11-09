"""Чанкинг Markdown-документов по смыслу."""

import logging
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


logger = logging.getLogger(__name__)


# Маппинг префикса имени файла → тип документа.
# Попадает в метаданные чанка и позволяет фильтровать поиск (VectorStoreReader, filter_dict).
# Порядок важен: более специфичные префиксы должны идти раньше общих.
DOC_TYPE_MAP: tuple[tuple[str, str], ...] = (
    ("neoflex_ru_projects", "project"),
    ("neoflex_ru_industries", "industry"),
    ("neoflex_ru_services", "service"),
    ("neoflex_ru_platforms", "platform"),
    ("neoflex_ru_news", "news"),
    ("neoflex_ru_publications", "publication"),
    ("neoflex_ru_about_partners", "partners"),
    ("neoflex_ru_about_history", "history"),
    ("neoflex_ru_about_career", "career"),
    ("neoflex_ru_about_company", "company"),
    ("neoflex_ru_contacts", "contacts"),
    ("neoflex_ru", "home"),
)


def get_doc_type(document_name: str) -> str:
    """
    Определяет тип документа по имени файла.

    :param document_name: Имя файла без расширения.
    :return: Тип документа или "other".
    """
    for prefix, doc_type in DOC_TYPE_MAP:
        if document_name.startswith(prefix):
            return doc_type
    return "other"


class DocumentChunker:
    """Чанкер Markdown-документов по смыслу."""

    def __init__(
        self,
        chunk_size: int = 2000,
        chunk_overlap: int = 300,
        min_chunk_len: int = 150,
        min_final_len: int = 50,
    ) -> None:
        """
        Инициализация чанкера.

        :param chunk_size: Целевой размер чанка в символах.
        :param chunk_overlap: Перекрытие между чанками.
        :param min_chunk_len: Минимальная длина чанка до склейки.
        :param min_final_len: Минимальная длина чанка после склейки.
        """
        self._chunk_size = chunk_size
        self._min_chunk_len = min_chunk_len
        self._min_final_len = min_final_len
        self._header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        self._size_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", " ", ""],
        )

    def chunk(self, documents: list[Document]) -> list[Document]:
        """
        Разбивает документы на чанки с метаданными.

        :param documents: Список Document-объектов (Markdown).
        :return: Список чанков с обогащёнными метаданными.
        """
        all_chunks: list[Document] = []
        for document in documents:
            chunks = self._merge_short_chunks(self._split_document(document))
            self._add_metadata(chunks, document)
            all_chunks.extend(chunks)

        logger.info("Всего чанков после обработки: %d", len(all_chunks))
        return all_chunks

    def _split_document(self, document: Document) -> list[Document]:
        """
        Разбивает один документ по заголовкам, затем по размеру.

        :param document: Document-объект.
        :return: Список чанков.
        """
        final_chunks: list[Document] = []
        for chunk in self._header_splitter.split_text(document.page_content):
            if len(chunk.page_content) <= self._chunk_size:
                final_chunks.append(chunk)
            else:
                final_chunks.extend(self._size_splitter.split_documents([chunk]))
        return final_chunks

    @staticmethod
    def _add_metadata(chunks: list[Document], document: Document) -> None:
        """
        Проставляет чанкам метаданные документа, раздела и стабильный node_id.

        :param chunks: Чанки одного документа (после склейки).
        :param document: Исходный документ.
        """
        document_name = document.metadata["document_name"]
        doc_type = get_doc_type(document_name)

        for index, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "source": document.metadata["source"],
                    "title": document.metadata.get("title", ""),
                    "document_name": document_name,
                    "doc_type": doc_type,
                    "section": chunk.metadata.get("h2", ""),
                    "subsection": chunk.metadata.get("h3", ""),
                    "node_id": f"{document_name}:{index}",
                }
            )

    def _merge_short_chunks(self, chunks: list[Document]) -> list[Document]:
        """
        Склеивает короткие чанки с соседями.

        Короткий чанк приклеивается к предыдущему, а если предыдущего нет —
        к следующему. Если файл целиком из одного короткого чанка —
        он остаётся, но отбрасывается на этапе MIN_FINAL_LEN.

        :param chunks: Список чанков.
        :return: Список чанков после склейки.
        """
        merged: list[Document] = []
        for i, chunk in enumerate(chunks):
            if len(chunk.page_content.strip()) >= self._min_chunk_len:
                merged.append(chunk)
            elif merged:
                # Приклеиваем к предыдущему.
                merged[-1].page_content += "\n\n" + chunk.page_content
            elif i + 1 < len(chunks):
                # Приклеиваем к следующему.
                chunks[i + 1].page_content = chunk.page_content + "\n\n" + chunks[i + 1].page_content
            else:
                # Файл целиком из одного короткого чанка — оставляем как есть,
                # отфильтруется на следующем шаге.
                merged.append(chunk)

        # Отбрасываем слишком короткие после склейки.
        return [c for c in merged if len(c.page_content.strip()) >= self._min_final_len]