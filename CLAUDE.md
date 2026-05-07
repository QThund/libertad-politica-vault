Folder structure:
-vault: Contains the RAG database. The sources subfolder contains the plain-text files that were used as source for the wiki.
-procesador: Contains all the python scripts.
-all-sources: Contains the plain-text sources to be processed.
-documentos-procesados.txt is a file where the name of all processed documents is appended, so the system does not process them again.
-grupos-procesados.txt is a file where the name of the processed folders is appended, so nobody can process them again.
-config.txt is the file where some parameters that affect different steps of the process are stored.