import asyncio
import json
import logging
import re
from dataclasses import dataclass

from langchain_classic.chains.sql_database.query import create_sql_query_chain
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import generated_image  # noqa: F401
from app.models.chat_message import ChatMessage
from app.models.thread import Thread
from app.models.user import User
from app.services.chat_service import chat_service


UNSAFE_KEYWORDS = ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER")
UNSAFE_PATTERN = re.compile(r"\b(" + "|".join(UNSAFE_KEYWORDS) + r")\b", re.IGNORECASE)


@dataclass
class SqlChatResult:
    sql: str
    result: list[dict[str, object | None]]
    answer: str


class ReadOnlySQLDatabase(SQLDatabase):
    @staticmethod
    def _assert_read_only(command: str) -> None:
        if UNSAFE_PATTERN.search(command):
            raise ValueError("Only read-only SQL queries are allowed.")

    def run(self, command, fetch="all", include_columns=False, *args, **kwargs):  # type: ignore[override]
        query = command if isinstance(command, str) else str(command)
        self._assert_read_only(query)
        return super().run(command, fetch=fetch, include_columns=include_columns, *args, **kwargs)

    def run_no_throw(self, command, fetch="all", include_columns=False, *args, **kwargs):  # type: ignore[override]
        query = command if isinstance(command, str) else str(command)
        self._assert_read_only(query)
        return super().run_no_throw(command, fetch=fetch, include_columns=include_columns, *args, **kwargs)


class SqlChatService:
    def __init__(self) -> None:
        self._sync_database_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2", 1)
        self._db = ReadOnlySQLDatabase.from_uri(self._sync_database_url)
        self._llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0,
            api_key=settings.LITELLM_API_KEY,
            base_url=f"{settings.LITELLM_PROXY_URL.rstrip('/')}/v1",
        )
        self._agent_executor = create_sql_agent(
            llm=self._llm,
            db=self._db,
            agent_type="tool-calling",
            verbose=False,
            return_intermediate_steps=True,
            prefix=(
                "You are a PostgreSQL SQL assistant. Generate and execute ONLY read-only SQL "
                "queries. Never use INSERT, UPDATE, DELETE, DROP, TRUNCATE, or ALTER."
            ),
        )
        self._sql_query_chain = create_sql_query_chain(self._llm, self._db)

    @staticmethod
    def _assert_safe_prompt(question: str) -> None:
        if UNSAFE_PATTERN.search(question):
            raise ValueError(
                "Unsafe request blocked. Only read-only questions are allowed. "
                "Please ask a SELECT-style question."
            )

    @staticmethod
    def _clean_sql(sql_text: str) -> str:
        cleaned = str(sql_text).strip()

        # Remove markdown code fences and language hints no matter where they appear.
        cleaned = re.sub(r"```(?:sql|plaintext|text)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace("```", "")

        # Some SQL chains return labels like SQLQuery/SQLResult/Answer.
        if re.search(r"(?i)sqlquery:\s*", cleaned):
            cleaned = re.split(r"(?i)sqlquery:\s*", cleaned, maxsplit=1)[1]
        if re.search(r"(?i)sqlresult:\s*", cleaned):
            cleaned = re.split(r"(?i)sqlresult:\s*", cleaned, maxsplit=1)[0]
        if re.search(r"(?i)answer:\s*", cleaned):
            cleaned = re.split(r"(?i)answer:\s*", cleaned, maxsplit=1)[0]

        cleaned = re.sub(r"(?i)^query:\s*", "", cleaned).strip()

        # Keep only the first SQL statement, dropping any extra commentary.
        # Handle CTEs separately so plain English starting with "with ..." is not accepted.
        sql_match = re.search(r"(?is)\bwith\b[\s\S]*?\bselect\b[\s\S]*?(?:;|$)", cleaned)
        if not sql_match:
            sql_match = re.search(r"(?is)\bselect\b[\s\S]*?(?:;|$)", cleaned)
        if not sql_match:
            sql_match = re.search(r"(?is)\bshow\b[\s\S]*?(?:;|$)", cleaned)
        if not sql_match:
            sql_match = re.search(r"(?is)\bexplain\b[\s\S]*?(?:;|$)", cleaned)
        if sql_match:
            cleaned = sql_match.group(0)

        cleaned = cleaned.strip().rstrip(";")
        return cleaned

    @staticmethod
    def _looks_like_read_sql(sql_text: str) -> bool:
        normalized = sql_text.strip().lower()
        if normalized.startswith("with"):
            return "select" in normalized
        return (
            normalized.startswith("select")
            or normalized.startswith("show")
            or normalized.startswith("explain")
        )

    @staticmethod
    def _extract_sql(intermediate_steps: list) -> str:
        for step in intermediate_steps:
            if not isinstance(step, tuple) or len(step) < 1:
                continue
            action = step[0]
            tool_name = getattr(action, "tool", "")
            if "sql_db_query" not in str(tool_name):
                continue

            tool_input = getattr(action, "tool_input", "")
            if isinstance(tool_input, dict):
                sql_candidate = str(tool_input.get("query", "")).strip()
            else:
                sql_candidate = str(tool_input).strip()

            if sql_candidate:
                return sql_candidate

        raise ValueError("Could not determine generated SQL query from agent output.")

    async def _execute_sql(
        self,
        db_session: AsyncSession,
        sql_query: str,
    ) -> list[dict[str, object | None]]:
        rows = await db_session.execute(text(sql_query))
        return [dict(row) for row in rows.mappings().all()]

    @staticmethod
    def _build_persisted_response(
        sql_query: str,
        query_result: list[dict[str, object | None]],
        answer: str,
    ) -> str:
        result_json = json.dumps(query_result, default=str, ensure_ascii=True)
        if len(result_json) > 6000:
            result_json = result_json[:6000] + " ...[truncated]"

        return (
            "### Generated SQL\n"
            "```sql\n"
            f"{sql_query}\n"
            "```\n\n"
            "### SQL Result\n"
            "```json\n"
            f"{result_json}\n"
            "```\n\n"
            "### Explanation\n"
            f"{answer}"
        )

    async def _persist_sql_chat(
        self,
        db_session: AsyncSession,
        user: User,
        thread: Thread,
        question: str,
        sql_query: str,
        query_result: list[dict[str, object | None]],
        answer: str,
    ) -> None:
        persisted_response = self._build_persisted_response(sql_query, query_result, answer)
        db_item = ChatMessage(
            user_id=user.id,
            thread_id=thread.id,
            message=question,
            response=persisted_response,
        )
        db_session.add(db_item)

        if not thread.title:
            thread.title = chat_service.auto_title(question)

        await db_session.commit()

    async def ask(
        self,
        db_session: AsyncSession,
        user: User,
        thread_id: int,
        question: str,
    ) -> SqlChatResult:
        if "postgresql" not in settings.DATABASE_URL.lower():
            raise ValueError("NL-to-SQL is configured for PostgreSQL only.")

        self._assert_safe_prompt(question)

        thread = await db_session.scalar(
            select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id)
        )
        if not thread:
            raise ValueError("Thread not found")

        response = await asyncio.to_thread(
            self._agent_executor.invoke,
            {"input": question},
        )
        intermediate_steps = response.get("intermediate_steps", [])
        try:
            generated_sql = self._clean_sql(self._extract_sql(intermediate_steps))
        except ValueError:
            logging.info("SQL extraction from intermediate steps failed; using SQL query chain fallback")
            generated_sql = self._clean_sql(
                await asyncio.to_thread(self._sql_query_chain.invoke, {"question": question})
            )

        if not self._looks_like_read_sql(generated_sql):
            raise ValueError(
                "Could not generate a valid read-only SQL query. Please rephrase your question."
            )

        ReadOnlySQLDatabase._assert_read_only(generated_sql)

        # Log generated SQL only (never secrets).
        logging.info("NL-to-SQL generated query: %s", generated_sql)

        try:
            query_result = await self._execute_sql(db_session, generated_sql)
        except SQLAlchemyError as exc:
            logging.warning("Generated SQL execution failed: %s", str(exc)[:200])
            raise ValueError(
                "Generated SQL was invalid for this database schema. Please rephrase your question."
            ) from exc

        answer = str(response.get("output", "")).strip() or "Query executed successfully."

        await self._persist_sql_chat(
            db_session=db_session,
            user=user,
            thread=thread,
            question=question,
            sql_query=generated_sql,
            query_result=query_result,
            answer=answer,
        )

        return SqlChatResult(sql=generated_sql, result=query_result, answer=answer)


sql_chat_service = SqlChatService()
