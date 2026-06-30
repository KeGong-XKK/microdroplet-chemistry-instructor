"""One-shot vector-index builder.

Reads data/unified_corpus.parquet, encodes every record's _doc_text with
BAAI/bge-m3 (multilingual; handles the mixed Chinese/English LLM
extractions), and writes:

    data/embeddings.npy   (float32, shape = [N, 1024])
    data/faiss.index      (inner-product index over L2-normalised vectors;
                           equivalent to cosine similarity)
    data/index_meta.json  (row_id ordering — must match the parquet row order)

Run this once after merge_datasets.py. Re-run when the underlying corpus
changes (e.g., after update_corpus.py adds new papers).

The first run downloads the bge-m3 weights (~2.3 GB) into the local HF cache.
On a CPU machine, encoding 2,400 records takes 3-8 minutes; on a CUDA GPU,
under a minute.
"""
from __future__ import annotations

import json
import sys
import io
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data'

MODEL_NAME = 'BAAI/bge-m3'
BATCH_SIZE = 16
MAX_LEN = 1024     # bge-m3 supports up to 8192; 1024 is plenty for our docs


def main() -> None:
    corpus_path = DATA / 'unified_corpus.parquet'
    if not corpus_path.exists():
        sys.exit(f'[abort] {corpus_path} not found — run scripts/merge_datasets.py first.')

    df = pd.read_parquet(corpus_path)
    texts: list[str] = df['_doc_text'].astype(str).tolist()
    row_ids: list[str] = df['_row_id'].astype(str).tolist()
    print(f'[load] {len(texts)} documents from {corpus_path.name}')

    print(f'[model] loading {MODEL_NAME} (first run downloads ~2.3 GB)...')
    # Import here so a fresh checkout that only wants merging doesn't
    # need torch / sentence-transformers installed.
    from sentence_transformers import SentenceTransformer
    import torch

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f'[model] device = {device}')
    model = SentenceTransformer(MODEL_NAME, device=device)
    model.max_seq_length = MAX_LEN

    print(f'[encode] batch_size={BATCH_SIZE}  max_len={MAX_LEN}')
    emb = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,   # IP search == cosine similarity
    ).astype('float32')
    print(f'[encode] embeddings shape = {emb.shape}')

    np.save(DATA / 'embeddings.npy', emb)
    print(f'[write] {DATA / "embeddings.npy"}  ({emb.nbytes / 1024 / 1024:.1f} MB)')

    # FAISS index (inner product on normalised vectors == cosine)
    import faiss
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    faiss.write_index(index, str(DATA / 'faiss.index'))
    print(f'[write] {DATA / "faiss.index"}  (FlatIP, ntotal={index.ntotal})')

    with open(DATA / 'index_meta.json', 'w', encoding='utf-8') as f:
        json.dump({
            'model': MODEL_NAME,
            'dim': int(emb.shape[1]),
            'n_records': int(len(row_ids)),
            'row_id_order': row_ids,
        }, f, ensure_ascii=False, indent=2)
    print(f'[write] {DATA / "index_meta.json"}')

    print('\n[done] vector index ready. Try:')
    print('  python -c "from tools.search import semantic_search; '
          'print(semantic_search(\'CO2 reduction in microdroplets\', k=5))"')


if __name__ == '__main__':
    main()
