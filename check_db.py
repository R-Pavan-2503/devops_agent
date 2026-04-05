from context_engine.vector_store import _collection

for repo in ['admin_pandhi', 'backend_pandhi', 'staff_pandhi', 'mobile_pandhi']:
    results = _collection.get(where={'repo_name': repo}, include=['metadatas'])
    print(f"{repo}: {len(results.get('ids', []))} chunks stored")
