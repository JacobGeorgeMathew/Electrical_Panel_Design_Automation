# Storage decision

Use disk files for cached raw responses, SQLite for staging, and JSON/JSONL for exports.

- **Raw files on disk:** HTML/JSON responses can be inspected and hashed without bloating a relational database. They are gitignored to avoid accidentally committing copyrighted source documents or large caches. Source PDFs are not downloaded unless their license clearly allows it.
- **SQLite staging:** it is local, portable and easy to inspect; transaction support allows resumable upserts and a separate rejected-record table. It avoids requiring PostgreSQL credentials during collection and keeps collection isolated from the main project's production catalog.
- **JSON exports:** `components.json` can match the existing repository fixture contract; JSONL retains extra metadata and provenance without forcing those fields into the legacy loader. Enclosures stay in their separate legacy shape.

PostgreSQL is not the staging store because the existing application has a versioned catalog, writes published records, and may contain project history. Loading there during experimentation would couple data gathering to the live catalog and credentials. CSV is less suitable for nested terminals/provenance; a document database adds a service dependency with no benefit for this local pipeline. The import helper therefore prints a reviewable manual command and never connects to a database.
