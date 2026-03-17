# Storage
MindDock stores document chunks and metadata in a local Chroma database.
The default persistence directory is `data/chroma`.
This section is useful for `/search`, `/chat`, and `/summarize` demos about storage design.

# Citations
Chat and summarize responses return citations with `source`, `section`, `location`, and `ref`.
These fields make it easier to explain where an answer or summary came from during a defense.

# Incremental Updates
The knowledge base supports both full rebuild and per-file incremental maintenance.
For a live demo, you can create, modify, or delete this file while the watcher is running.
