from .memory import MemoryStore


class RAGRetriever:
    def __init__(self, memory: MemoryStore):
        self.memory = memory

    def build_context(self, query: str, *, project_id: str | None, top_k: int = 5) -> dict:
        project = self.memory.search_conversations(query, project_id=project_id, scope="project", top_k=top_k) if project_id else []
        cross = [hit for hit in self.memory.search_conversations(query, project_id=project_id, scope="cross_project", top_k=top_k * 2) if hit.get("project_id") != project_id][:top_k]
        return {"project_history": project, "cross_project_history": cross}

