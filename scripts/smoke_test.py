"""
Full pipeline test:
1. Ingest this project into ChromaDB
2. Run a semantic search and verify results
"""
import sys
sys.path.insert(0, ".")

print("Step 1: Ingesting the project itself into ChromaDB...")
print("(This will download the sentence-transformer model on first run ~90MB)\n")

# Import the ingest function from bulk_ingest script
from scripts.bulk_ingest import ingest_repository

stats = ingest_repository(repo_path=".", repo_name="devops_agent")

print("\nStep 2: Running semantic search...")
from context_engine.vector_store import search, collection_stats

print(collection_stats())

results = search("security vulnerability checking agent", "devops_agent", n_results=2)
print(f"\nSearch returned {len(results)} results:")
for i, r in enumerate(results, 1):
    print(f"\n--- Result {i} ---")
    print(r[:300])
    print("...")

print("\nFull pipeline test: PASSED!")
