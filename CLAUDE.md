LLM Wiki
Build and maintain a persistent, evolving wiki (markdown-based knowledge base) from user-provided sources, instead of relying on one-time retrieval like RAG.

Core behavior
-Continuously ingest, synthesize, and update knowledge into a structured wiki.
-Treat the wiki as a long-term memory layer that compounds over time.
-Do not re-derive knowledge repeatedly—integrate it ერთხელ and keep it updated.

System structure
1. Raw sources: Immutable input files (read-only ground truth).
2. Wiki (annotations folder): LLM-generated markdown pages (you fully manage this).
3. Schema/config file: Defines structure, conventions, and workflows.

Key responsibilities
-Ingest sources:
--Read new documents.
--Extract key ideas.
--Create/update relevant wiki pages.
--Maintain cross-references and consistency.
--Log the operation.
-Answer queries:
--Search the wiki (start with index.md).
--Synthesize answers from existing pages.
--Cite relevant pages.
--Optionally save useful outputs as new wiki pages.
-Maintain (lint) the wiki:
--Detect contradictions, outdated info, missing pages, weak links.
--Suggest improvements and new research directions.

Special files
-index.md: Structured overview of all pages (use for navigation/search).
-log.md: Chronological record of all actions (append-only).

Operational rules
-Always read index.md and log.md first to understand current state.
-Store all markdown files in the annotations folder.
-Ensure the wiki is:
--Well-structured.
--Interlinked.
--Consistent.
--Continuously improving.

Role split
-User: provides sources, asks questions, guides focus.
-LLM (you): does all organization, summarization, linking, and upkeep.

Goal
Create a self-improving knowledge system where:
-Knowledge accumulates.
-Insights persist.
-Structure and connections are maintained automatically.

In each annotation, include a relative path link to the source file. If the source is a .txt file, replace the extension with .pdf, when including it in the annotation.
I consider important the followng concepts, when processing the documents: political parties; person names; media names; dates; organization names; company names; Antonio García-Trevijano's opinions and mentions; book citations, movie citations, art citations, paper citations.

Folder structure:
-vault: Contains the Obsidian vault. Subfolder annotations: the annotations used by the LLM Wiki; the sources subfolder contains the plain-text files that were used as source for the wiki.
-procesador: Contains all the python scripts.
-all-sources: Contains the plain-text sources to be processed.
-documentos-procesados.txt is a file where the name of all processed documents is appended, so the system does not process them again.
-grupos-procesados.txt is a file where the name of the processed folders is appended, so nobody can process them again.
-config.txt is the file where some parameters that affect different steps of the process are stored.
Files in all-sources will be copied to the vault/sources folder as they are processed.