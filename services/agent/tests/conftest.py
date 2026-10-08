import os

# Must be set before the app is imported: tests never load the real embedding model.
os.environ.setdefault("PRELOAD_EMBEDDER", "false")
