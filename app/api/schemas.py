"""Схемы запроса и ответа API."""

from pydantic import BaseModel, ConfigDict, Field

# Лимиты защищают приложение от огромных входов: question попадает в промпт и в запрос
# к хранилищу, session_id — ключ истории (thread_id) и часть каждой строки лога.
SESSION_ID_MAX_LEN = 128
QUESTION_MAX_LEN = 4000
# Только безопасные символы: перевод строки в session_id позволил бы подделывать строки лога.
SESSION_ID_PATTERN = r"^[\w.:-]+$"


class ChatRequest(BaseModel):
    """Запрос к чат-боту."""

    # Пробелы по краям убираются до проверки длины, поэтому вопрос из одних пробелов
    # не проходит валидацию и не уходит в модель.
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(
        min_length=1,
        max_length=SESSION_ID_MAX_LEN,
        pattern=SESSION_ID_PATTERN,
        description="Идентификатор сессии: буквы, цифры, '_', '.', ':', '-'",
        examples=["abc123"],
    )
    question: str = Field(
        min_length=1,
        max_length=QUESTION_MAX_LEN,
        examples=["Какие решения на основе ИИ создаёт Neoflex?"],
    )


class SourceDocumentOut(BaseModel):
    """Источник ответа. Поля совпадают с state.SourceDocument."""

    source: str
    snippet: str


class ChatResponse(BaseModel):
    """Ответ чат-бота. Поля совпадают с service.RAGAnswer."""

    answer: str
    source_documents: list[SourceDocumentOut]
    session_id: str
