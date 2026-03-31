import pickle
from pathlib import Path

import faiss  # type: ignore
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

def load_pdfs(papers_dir: Path) -> list[Document]:
    docs: list[Document] = []
    for pdf_path in sorted(papers_dir.glob("*.pdf")):
        reader = PdfReader(str(pdf_path))
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if not text.strip():  # skip empty pages
                continue
            metadata = {"source": pdf_path.name, "page": i + 1}
            docs.append(Document(page_content=text, metadata=metadata))
    return docs

def main() -> None:
    papers_dir = Path("papers")
    index_dir = Path("index")

    if not papers_dir.is_dir():
        raise SystemExit(f"papers directory not found: {papers_dir}")

    docs = load_pdfs(papers_dir)
    if not docs:
        raise SystemExit(f"No PDFs with extractable text found in {papers_dir}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)

    model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
    texts = [d.page_content for d in chunks]
    metadatas = [d.metadata for d in chunks]
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings.astype("float32"))

    index_dir.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_dir / "index.faiss"))
    with open(index_dir / "texts.pkl", "wb") as f:
        pickle.dump(texts, f)
    with open(index_dir / "metadatas.pkl", "wb") as f:
        pickle.dump(metadatas, f)

    print(f"Indexed {len(docs)} pages into {len(chunks)} chunks from {papers_dir}")
    print(f"Index stored in {index_dir}")

if __name__ == "__main__":
    main()

