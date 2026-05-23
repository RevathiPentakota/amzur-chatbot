import asyncio
import logging
import re
import uuid
from pathlib import Path

import gspread
import pandas as pd
from fastapi import UploadFile
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat_message import ChatMessage
from app.models.dataframe_source import DataFrameSource
from app.models.thread import Thread
from app.models.user import User
from app.services.chat_service import chat_service


BLOCKED_PROMPT_PATTERN = re.compile(
    r"\b(import|exec|eval|open\(|__|os\.|subprocess|system\(|rm\s+-rf|write\s+file|delete\s+file)\b",
    re.IGNORECASE,
)


class DataFrameChatService:
    @staticmethod
    def _preview_rows(df: pd.DataFrame, max_rows: int = 5) -> list[dict[str, object | None]]:
        preview_df = df.head(max_rows).copy()
        preview_df = preview_df.where(pd.notnull(preview_df), None)
        return preview_df.to_dict(orient="records")

    @staticmethod
    def _sheet_id_from_input(sheet: str) -> str:
        value = sheet.strip()
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
        if match:
            return match.group(1)
        return value

    @staticmethod
    def _validate_read_only_question(question: str) -> None:
        if BLOCKED_PROMPT_PATTERN.search(question):
            raise ValueError("Unsafe question blocked. Please ask a read-only analysis question.")

    @staticmethod
    async def _ensure_thread(db: AsyncSession, user: User, thread_id: int) -> Thread:
        thread = await db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
        if not thread:
            raise ValueError("Thread not found")
        return thread

    @staticmethod
    async def _save_source(
        db: AsyncSession,
        user: User,
        thread: Thread,
        filename: str,
        file_path: str,
        source_type: str,
        google_sheet_id: str | None = None,
        worksheet_name: str | None = None,
    ) -> DataFrameSource:
        item = DataFrameSource(
            user_id=user.id,
            thread_id=thread.id,
            filename=filename,
            file_path=file_path,
            source_type=source_type,
            google_sheet_id=google_sheet_id,
            worksheet_name=worksheet_name,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @staticmethod
    def _read_local_dataframe(source: DataFrameSource) -> pd.DataFrame:
        path = Path(source.file_path)
        if source.source_type == "csv":
            return pd.read_csv(path)
        if source.source_type == "xlsx":
            return pd.read_excel(path)
        raise ValueError("Unsupported local dataframe source type")

    @staticmethod
    def _read_google_sheet(source: DataFrameSource) -> pd.DataFrame:
        if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
            raise ValueError("Google Sheets service account is not configured.")
        if not source.google_sheet_id:
            raise ValueError("Google sheet metadata is missing sheet id.")

        service_account_path = Path(settings.GOOGLE_SERVICE_ACCOUNT_JSON).expanduser()
        if not service_account_path.exists():
            raise ValueError(
                "Google Sheets service account JSON file was not found. "
                "Please verify GOOGLE_SERVICE_ACCOUNT_JSON in backend/.env."
            )

        try:
            creds = Credentials.from_service_account_file(
                str(service_account_path),
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets.readonly",
                    "https://www.googleapis.com/auth/drive.readonly",
                ],
            )
        except (OSError, PermissionError, ValueError) as exc:
            raise ValueError(
                "Unable to read Google service account credentials file. "
                "Check GOOGLE_SERVICE_ACCOUNT_JSON path and JSON content."
            ) from exc

        try:
            client = gspread.authorize(creds)
            workbook = client.open_by_key(source.google_sheet_id)
            worksheet = workbook.worksheet(source.worksheet_name) if source.worksheet_name else workbook.sheet1
            records = worksheet.get_all_records()
            return pd.DataFrame(records)
        except PermissionError as exc:
            raise ValueError(
                "Google Sheets access denied. Enable Google Sheets API (and Drive API) for the credential project, "
                "wait a few minutes, and ensure the sheet is shared with the service account email."
            ) from exc
        except SpreadsheetNotFound as exc:
            raise ValueError(
                "Google Sheet not found or not shared with the service account email."
            ) from exc
        except WorksheetNotFound as exc:
            raise ValueError("Worksheet name not found in the Google Sheet.") from exc
        except APIError as exc:
            raise ValueError("Google Sheets API error. Please check sheet permissions and URL.") from exc
        except Exception as exc:
            raise ValueError("Invalid Google Sheet URL/ID or inaccessible sheet.") from exc

    def _load_dataframe(self, source: DataFrameSource) -> pd.DataFrame:
        if source.source_type in {"csv", "xlsx"}:
            return self._read_local_dataframe(source)
        if source.source_type == "google_sheet":
            return self._read_google_sheet(source)
        raise ValueError("Unsupported dataframe source type")

    @staticmethod
    async def _latest_source_for_thread(db: AsyncSession, user: User, thread_id: int) -> DataFrameSource:
        source = await db.scalar(
            select(DataFrameSource)
            .where(DataFrameSource.user_id == user.id, DataFrameSource.thread_id == thread_id)
            .order_by(DataFrameSource.created_at.desc(), DataFrameSource.id.desc())
        )
        if not source:
            raise ValueError("No data source found. Upload a CSV/XLSX file or connect a Google Sheet first.")
        return source

    async def list_thread_sources(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
    ) -> list[DataFrameSource]:
        await self._ensure_thread(db, user, thread_id)
        result = await db.scalars(
            select(DataFrameSource)
            .where(DataFrameSource.user_id == user.id, DataFrameSource.thread_id == thread_id)
            .order_by(DataFrameSource.created_at.asc(), DataFrameSource.id.asc())
        )
        return list(result)

    async def upload_file(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        file: UploadFile,
    ) -> tuple[DataFrameSource, list[dict[str, object | None]]]:
        thread = await self._ensure_thread(db, user, thread_id)

        filename = file.filename or "dataset"
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            raise ValueError("Only CSV and XLSX files are supported.")

        folder = Path(settings.UPLOAD_DIR) / str(user.id) / "dataframes"
        folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{suffix}"
        dest = folder / stored_name
        content = await file.read()
        dest.write_bytes(content)

        source_type = "csv" if suffix == ".csv" else "xlsx"
        item = await self._save_source(
            db,
            user,
            thread,
            filename=filename,
            file_path=str(dest),
            source_type=source_type,
        )

        df = self._load_dataframe(item)
        preview = self._preview_rows(df)
        return item, preview

    async def connect_google_sheet(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        sheet: str,
        worksheet_name: str | None = None,
    ) -> tuple[DataFrameSource, list[dict[str, object | None]]]:
        thread = await self._ensure_thread(db, user, thread_id)
        sheet_id = self._sheet_id_from_input(sheet)

        # Validate connectivity before persisting source metadata.
        temp_source = DataFrameSource(
            user_id=user.id,
            thread_id=thread.id,
            filename=f"google_sheet_{sheet_id}",
            file_path=f"gsheet://{sheet_id}",
            source_type="google_sheet",
            google_sheet_id=sheet_id,
            worksheet_name=worksheet_name,
        )
        df = self._read_google_sheet(temp_source)
        preview = self._preview_rows(df)

        item = await self._save_source(
            db,
            user,
            thread,
            filename=f"google_sheet_{sheet_id}",
            file_path=f"gsheet://{sheet_id}",
            source_type="google_sheet",
            google_sheet_id=sheet_id,
            worksheet_name=worksheet_name,
        )
        return item, preview

    @staticmethod
    def _build_persisted_response(answer: str, intermediate_steps: str, preview: list[dict[str, object | None]]) -> str:
        preview_text = str(preview)
        if len(preview_text) > 4000:
            preview_text = preview_text[:4000] + " ...[truncated]"

        return (
            "### Data Analysis Answer\n"
            f"{answer}\n\n"
            "### Intermediate Steps\n"
            "```text\n"
            f"{intermediate_steps}\n"
            "```\n\n"
            "### Table Preview\n"
            "```text\n"
            f"{preview_text}\n"
            "```"
        )

    async def chat(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        question: str,
    ) -> tuple[str, str, list[dict[str, object | None]]]:
        self._validate_read_only_question(question)
        thread = await self._ensure_thread(db, user, thread_id)
        source = await self._latest_source_for_thread(db, user, thread_id)
        df = self._load_dataframe(source)
        preview = self._preview_rows(df)

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0,
            api_key=settings.LITELLM_API_KEY,
            base_url=f"{settings.LITELLM_PROXY_URL.rstrip('/')}/v1",
        )

        agent = create_pandas_dataframe_agent(
            llm,
            df,
            agent_type="tool-calling",
            return_intermediate_steps=True,
            allow_dangerous_code=True,
            max_iterations=8,
            prefix=(
                "You are a read-only data analyst for a pandas DataFrame. "
                "Never modify data, write files, import modules, or execute unsafe operations. "
                "Answer only using the loaded dataframe."
            ),
        )

        response = await asyncio.to_thread(agent.invoke, {"input": question})
        answer = str(response.get("output", "")).strip() or "No answer generated."
        intermediate_steps = str(response.get("intermediate_steps", ""))

        persisted_response = self._build_persisted_response(answer, intermediate_steps, preview)
        item = ChatMessage(
            user_id=user.id,
            thread_id=thread.id,
            message=question,
            response=persisted_response,
        )
        db.add(item)

        if not thread.title:
            thread.title = chat_service.auto_title(question)

        await db.commit()
        logging.info("DataFrame chat completed for thread_id=%s source=%s", thread.id, source.source_type)
        return answer, intermediate_steps, preview


dataframe_chat_service = DataFrameChatService()
