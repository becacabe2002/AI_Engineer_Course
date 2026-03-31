import sys
import pickle
from pathlib import Path
from typing import Any, Dict, List

import faiss  # type: ignore
import requests
from sentence_transformers import SentenceTransformer
from langchain_core.runnables import RunnableLambda, RunnableBranch


def load_proxy_base_url(base_dir: Path) -> str:
    """Load PROXY_BASE_URL from a local 'env' file next to this script."""

    env_path = base_dir / "env"
    if not env_path.is_file():
        raise SystemExit(f"env file with PROXY_BASE_URL not found at {env_path}")

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("PROXY_BASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("PROXY_BASE_URL not found in env file")


def llm_call(system_prompt: str, user_prompt: str, base_url: str) -> str:
    """Call the OpenRouter proxy with the GPT-4.1-mini model via HTTP."""

    payload = {
        "model": "openai/gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def build_router(index_dir: Path, base_dir: Path):
    """Create a LangChain router runnable over the local FAISS index."""

    if not index_dir.is_dir():
        raise SystemExit(f"index directory not found: {index_dir}")

    base_url = load_proxy_base_url(base_dir)

    # Load vector index + metadata
    index = faiss.read_index(str(index_dir / "index.faiss"))
    with open(index_dir / "texts.pkl", "rb") as f:
        texts: List[str] = pickle.load(f)
    with open(index_dir / "metadatas.pkl", "rb") as f:
        metadatas: List[Dict[str, Any]] = pickle.load(f)

    model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

    def retrieve(question: str, k: int = 4) -> List[Dict[str, Any]]:
        vec = model.encode([question], convert_to_numpy=True, normalize_embeddings=True)
        scores, indices = index.search(vec.astype("float32"), k)
        docs: List[Dict[str, Any]] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue
            meta = dict(metadatas[idx])
            meta["score"] = float(score)
            docs.append({"page_content": texts[idx], "metadata": meta})
        return docs

    def build_context(docs: List[Dict[str, Any]]) -> str:
        if not docs:
            return "No relevant context found in the indexed papers."
        parts: List[str] = []
        for d in docs:
            meta = d.get("metadata", {})
            src = meta.get("source", "unknown")
            page = meta.get("page", "?")
            text = (d.get("page_content") or "").strip()
            parts.append(f"[DOC: {src}, PAGE: {page}]\n{text}")
        return "\n\n---\n\n".join(parts)

    router_system_prompt = (
        "You are a routing assistant for a scientific literature QA system.\n"
        "Choose exactly one specialised agent to answer the user's question.\n"
        "Respond with only one lowercase word (no explanation):\n"
        "- 'methods'   for questions about methods, setup, datasets, models, or metrics.\n"
        "- 'results'   for questions about experimental results, numbers, tables, or comparisons.\n"
        "- 'skeptical' for questions about limitations, threats, weaknesses, or critique.\n"
        "- 'general'   for all other questions.\n"
    )

    def classify_route(inputs: Dict[str, Any]) -> Dict[str, Any]:
        question = inputs["question"]
        raw = llm_call(router_system_prompt, question, base_url)
        route = raw.strip().lower()
        if "method" in route:
            route = "methods"
        elif "result" in route:
            route = "results"
        elif "skept" in route:
            route = "skeptical"
        elif route not in {"methods", "results", "skeptical", "general"}:
            route = "general"
        return {"route": route, "question": question}

    router_classifier = RunnableLambda(classify_route)

    def make_agent_chain(agent_name: str, system_prompt: str):
        def run_agent(inputs: Dict[str, Any]) -> str:
            question = inputs["question"]
            docs = retrieve(question)
            context = build_context(docs)
            user_prompt = (
                "You answer questions about scientific papers using only the context below.\n"
                "Context passages come from PDFs and each passage is tagged with its source and page.\n"
                "When you rely on a specific passage, cite it inline like (source: FILENAME.pdf, page: N).\n"
                "If the answer is not clearly supported by the context, say that it is not specified.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {question}\n"
            )
            answer = llm_call(system_prompt, user_prompt, base_url)
            return f"{agent_name}:\n{answer}"

        return RunnableLambda(run_agent)

    methods_system_prompt = (
        "You are the Methods Analyst. You focus on methods, experimental setup, datasets, "
        "models, training details, and evaluation metrics in scientific papers. "
        "Use only the provided context and include clear citations (source + page)."
    )

    results_system_prompt = (
        "You are the Results Extractor. You focus on experimental results, numbers, tables, "
        "ablations, and comparisons between methods. Be precise with numbers and cite the "
        "source and page for each important claim."
    )

    skeptical_system_prompt = (
        "You are the Skeptical Reviewer. You highlight limitations, threats to validity, "
        "assumptions, weaknesses, and missing analyses in the papers. Base your critique "
        "only on the provided context and always ground claims with citations."
    )

    general_system_prompt = (
        "You are the General Synthesizer. You answer other questions about the papers, "
        "including summaries, motivation, implications, and high-level understanding. "
        "Stay grounded in the context and use citations when you rely on specific details."
    )

    methods_chain = make_agent_chain("Methods Analyst", methods_system_prompt)
    results_chain = make_agent_chain("Results Extractor", results_system_prompt)
    skeptical_chain = make_agent_chain("Skeptical Reviewer", skeptical_system_prompt)
    general_chain = make_agent_chain("General Synthesizer", general_system_prompt)

    router = router_classifier | RunnableBranch(
        (lambda x: x["route"] == "methods", methods_chain),
        (lambda x: x["route"] == "results", results_chain),
        (lambda x: x["route"] == "skeptical", skeptical_chain),
        general_chain,
    )

    return router


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    index_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else base_dir / "index"

    router = build_router(index_dir, base_dir)
    print(f"Loaded index from {index_dir}")
    print("Type your questions about the papers. Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            question = input("Question> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()  # newline
            break

        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break

        answer = router.invoke({"question": question})
        print()
        print(answer)
        print("\n" + "-" * 60 + "\n")


if __name__ == "__main__":
    main()

