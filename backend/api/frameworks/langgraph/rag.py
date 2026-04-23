"""
RAG utilities for LangGraph agents using Qdrant.
"""
import os
import asyncio
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.models import Distance, VectorParams
from langchain_core.tools import tool
from sentence_transformers import SentenceTransformer

from api.models import Project


class RAGManager:
    """Manager for project-specific RAG databases using Qdrant."""

    def __init__(self, project: Project):
        self.project = project
        self.client = AsyncQdrantClient(url="http://localhost:6333")  # Assuming Qdrant runs locally
        self.collection_name = f"project_{project.id}_rag"
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')  # Lightweight encoder

    async def ensure_collection(self):
        """Create collection if it doesn't exist."""
        try:
            await self.client.get_collection(self.collection_name)
        except Exception:
            # Collection doesn't exist, create it
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),  # all-MiniLM-L6-v2 has 384 dims
            )

    async def add_documents(self, documents: List[str], metadata: Optional[List[Dict[str, Any]]] = None):
        """Add documents to the RAG database."""
        await self.ensure_collection()

        if not metadata:
            metadata = [{}] * len(documents)

        # Encode documents
        embeddings = self.encoder.encode(documents, convert_to_numpy=True).tolist()

        # Prepare points
        points = []
        for i, (doc, meta, emb) in enumerate(zip(documents, metadata, embeddings)):
            points.append(models.PointStruct(
                id=i,
                vector=emb,
                payload={"text": doc, **meta}
            ))

        # Upsert to collection
        await self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    async def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for relevant documents."""
        await self.ensure_collection()

        # Encode query
        query_vector = self.encoder.encode([query])[0].tolist()

        # Search
        results = await self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit
        )

        # Format results
        hits = []
        for result in results:
            hits.append({
                "text": result.payload.get("text", ""),
                "score": result.score,
                "metadata": {k: v for k, v in result.payload.items() if k != "text"}
            })

        return hits

    async def index_codebase(self, container_name: str):
        """Index the entire codebase for RAG."""
        from api.podman_orchestrator import PodmanOrchestrator

        orchestrator = PodmanOrchestrator()

        # Get all Python/JS/TS files
        cmd = "find /workspace -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.java' | head -50"  # Limit for demo
        result = orchestrator._run(['exec', container_name, 'sh', '-c', cmd])

        if result.returncode != 0:
            return f"Error finding files: {result.stderr}"

        files = result.stdout.strip().split('\n')
        documents = []
        metadata = []

        for file_path in files:
            if not file_path.strip():
                continue

            # Read file content
            read_cmd = f"cat '{file_path}' | head -100"  # Limit content for demo
            read_result = orchestrator._run(['exec', container_name, 'sh', '-c', read_cmd])

            if read_result.returncode == 0:
                content = read_result.stdout
                if content.strip():
                    documents.append(content)
                    metadata.append({
                        "file_path": file_path,
                        "language": file_path.split('.')[-1] if '.' in file_path else 'unknown'
                    })

        if documents:
            await self.add_documents(documents, metadata)
            return f"Indexed {len(documents)} code files"
        else:
            return "No code files found to index"


# Global RAG managers cache
_rag_managers = {}

def get_rag_manager(project: Project) -> RAGManager:
    """Get or create RAG manager for project."""
    if project.id not in _rag_managers:
        _rag_managers[project.id] = RAGManager(project)
    return _rag_managers[project.id]


def get_rag_tools(project: Project, container_name: str) -> List:
    """Create RAG tools for the given project."""

    @tool
    def search_codebase(query: str, limit: int = 5) -> str:
        """Search the codebase using RAG for relevant code snippets.

        Args:
            query: Search query
            limit: Maximum number of results
        """
        try:
            rag_manager = get_rag_manager(project)
            results = asyncio.run(rag_manager.search(query, limit))

            if not results:
                return "No relevant code found in the codebase."

            output = "Relevant code snippets:\n\n"
            for i, result in enumerate(results, 1):
                output += f"{i}. Score: {result['score']:.3f}\n"
                output += f"File: {result['metadata'].get('file_path', 'unknown')}\n"
                output += f"Content: {result['text'][:500]}...\n\n"

            return output

        except Exception as e:
            return f"Error searching codebase: {str(e)}"

    @tool
    def index_codebase() -> str:
        """Index the entire codebase for future RAG searches."""
        try:
            rag_manager = get_rag_manager(project)
            result = asyncio.run(rag_manager.index_codebase(container_name))
            return result
        except Exception as e:
            return f"Error indexing codebase: {str(e)}"

    return [search_codebase, index_codebase]