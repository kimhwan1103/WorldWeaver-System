from pathlib import Path

from langchain_community.document_loaders import DirectoryLoader
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from worldweaver.config import CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_MODEL


class LoreMemory:
    """세계관 문서를 로드하고 기억을 누적하는 RAG 벡터 스토어."""

    def __init__(self, lore_dir: Path):
        print("세계관 정보를 로드하여 RAG 메모리 구축 ....")

        embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)

        loader = DirectoryLoader(str(lore_dir), glob="**/*.txt")
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        documents = splitter.split_documents(docs)

        self._vector_store = FAISS.from_documents(documents, embeddings)
        print("RAG 구축 완료")

    def as_retriever(self):
        """검색기(Retriever)를 반환."""
        return self._vector_store.as_retriever()

    def add_memory(self, text: str):
        """새로운 스토리를 벡터 스토어에 누적."""
        self._vector_store.add_texts([text])
