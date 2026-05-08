Write-Host "1. Downloading dataset..."
.\venv\Scripts\python -m scripts.ingest.download_dataset --year-from 2024 --year-to 2024 --output-dir ../data/raw

Write-Host "2. Extracting text..."
.\venv\Scripts\python -m scripts.ingest.extract_text --input-dir ../data/raw/pdfs --output-dir ../data/processed

Write-Host "3. Segmenting text..."
.\venv\Scripts\python -m scripts.ingest.segment_text --input-dir ../data/processed --output-dir ../data/processed/segmented

Write-Host "4. Generating embeddings..."
.\venv\Scripts\python -m scripts.ingest.build_embeddings --input-dir ../data/processed/segmented --output-dir ../data/embeddings

Write-Host "5. Building FAISS index..."
.\venv\Scripts\python -m scripts.ingest.build_faiss_index --embeddings-dir ../data/embeddings --output-dir ../data/index

Write-Host "Ingestion complete!"
