import asyncio
import logging
import uuid
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.pdf_document import PdfDocument
from app.models.thread import Thread
from app.models.user import User


class RagService:
    @staticmethod
    def _format_citations(docs: list) -> str:
        seen: set[str] = set()
        lines: list[str] = []

        for doc in docs:
            meta = doc.metadata or {}
            filename = str(meta.get("filename") or meta.get("source") or "document.pdf")

            page_label = meta.get("page_label")
            if page_label is not None:
                ref = f"{filename} (page {page_label})"
            else:
                page_index = meta.get("page")
                if isinstance(page_index, int):
                    ref = f"{filename} (page {page_index + 1})"
                else:
                    ref = filename

            if ref in seen:
                continue
            seen.add(ref)
            lines.append(f"- {ref}")

        if not lines:
            return ""
        return "\n\nSources:\n" + "\n".join(lines)

    @staticmethod
    def _collection_name(user_id: int, thread_id: int) -> str:
        return f"rag_u{user_id}_t{thread_id}"

    @staticmethod
    def _embeddings() -> OpenAIEmbeddings:
        return OpenAIEmbeddings(
            model=settings.LITELLM_EMBEDDING_MODEL,
            api_key=settings.LITELLM_API_KEY,
            base_url=f"{settings.LITELLM_PROXY_URL.rstrip('/')}/v1",
        )

    async def upload_pdf(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        filename: str,
        file_bytes: bytes,
    ) -> PdfDocument:
        thread = await db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
        if not thread:
            raise ValueError("Thread not found")

        upload_dir = Path(settings.UPLOAD_DIR) / str(user.id) / str(thread_id) / "rag"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"{uuid.uuid4().hex}_{filename}"
        dest.write_bytes(file_bytes)

        record = PdfDocument(
            user_id=user.id,
            thread_id=thread_id,
            filename=filename,
            file_path=str(dest),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        await asyncio.to_thread(self._index_pdf, user.id, thread_id, record.id, record.filename, record.file_path)
        return record

    def _index_pdf(
        self,
        user_id: int,
        thread_id: int,
        pdf_id: int,
        filename: str,
        file_path: str,
    ) -> None:
        loader = PyPDFLoader(file_path)
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)
        chunks = splitter.split_documents(docs)

        for chunk in chunks:
            chunk.metadata = {
                **(chunk.metadata or {}),
                "user_id": user_id,
                "thread_id": thread_id,
                "pdf_id": pdf_id,
                "filename": filename,
            }

        vectorstore = Chroma(
            collection_name=self._collection_name(user_id, thread_id),
            embedding_function=self._embeddings(),
            persist_directory=settings.CHROMA_PERSIST_DIR,
        )
        vectorstore.add_documents(chunks)
        try:
            vectorstore.persist()
        except Exception:
            pass

    async def ask(
        self,
        db: AsyncSession,
        user: User,
        thread_id: int,
        question: str,
    ) -> str:
        thread = await db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
        if not thread:
            raise ValueError("Thread not found")

        vectorstore = await asyncio.to_thread(
            Chroma,
            collection_name=self._collection_name(user.id, thread_id),
            embedding_function=self._embeddings(),
            persist_directory=settings.CHROMA_PERSIST_DIR,
        )

        docs = await asyncio.to_thread(vectorstore.similarity_search, question, 4)
        if not docs:
            return "I could not find relevant content in the uploaded PDF for this question."

        context = "\n\n".join(d.page_content for d in docs)

        prompt = (
            "Answer the user's question using only the context below. "
            "If the answer is not in context, say so clearly.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}"
        )

        import litellm

        try:
            response = await asyncio.to_thread(
                litellm.completion,
                model=settings.LLM_MODEL,
                api_base=settings.LITELLM_PROXY_URL,
                api_key=settings.LITELLM_API_KEY,
                messages=[{"role": "user", "content": prompt}],
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logging.exception("RAG chat provider error")
            raise RuntimeError("RAG chat failed. Please try again.") from exc

        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("RAG chat returned empty response.")
        return f"{content}{self._format_citations(docs)}"

    async def list_thread_pdfs(self, db: AsyncSession, user: User, thread_id: int) -> list[PdfDocument]:
        thread = await db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == user.id))
        if not thread:
            raise ValueError("Thread not found")

        result = await db.scalars(
            select(PdfDocument)
            .where(PdfDocument.user_id == user.id, PdfDocument.thread_id == thread_id)
            .order_by(PdfDocument.created_at.asc())
        )
        return list(result)

    async def get_pdf(self, db: AsyncSession, user: User, pdf_id: int) -> PdfDocument:
        record = await db.scalar(
            select(PdfDocument).where(PdfDocument.id == pdf_id, PdfDocument.user_id == user.id)
        )
        if not record:
            raise ValueError("PDF not found")
        return record


rag_service = RagService()
