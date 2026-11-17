"""Read-only audits. Reports contain counts/codes, never paths or payloads."""
from sqlalchemy import select

from app.persistence import models as m
from app.persistence.assets import AssetStore, content_hash
from app.persistence.documents import DocumentRepository
from app.persistence.integrity import revision_rows, verify_revision_rows
from app.persistence.repositories import PersistenceError


def audit_assets(database):
    assets = AssetStore(database.settings.asset_root)
    with database.sessions() as session:
        rows = [dict(r) for table in (m.cad_assets, m.generated_artifacts)
                for r in session.execute(select(table).where(table.c.generation_status == 'READY')).mappings()]
        # Cache references retain shared content too, including superseded entries.
        # Malformed metadata is a finding rather than a failed audit command.
        rows.extend(asset if isinstance(asset, dict) else {}
                    for manifest in session.scalars(select(m.stage_results.c.assets)) for asset in manifest)
    referenced = {r['storage_key'] for r in rows if isinstance(r.get('storage_key'), str)}
    stored = {p.relative_to(assets.root).as_posix() for p in assets.root.glob('sha256/*/*/*') if p.is_file()}
    return {'referenced': len(referenced),
            'missing_or_corrupt': sum(r.get('storage_backend') != 'LOCAL' or assets.availability(r) != 'READY' for r in rows),
            'unreferenced_files': len(stored - referenced), 'automatic_deletion': False}


def audit_revisions(database):
    assets = AssetStore(database.settings.asset_root)
    report = dict(revisions=0, complete=0, legacy_missing_outputs=0, invalid_revisions=0,
                  documents=0, invalid_documents=0, document_snapshots=0,
                  invalid_document_snapshots=0, automatic_deletion=False)
    with database.sessions() as session:
        ids = list(session.scalars(select(m.project_revisions.c.id)))
        projects = [dict(row) for row in session.execute(select(m.projects).where(
            m.projects.c.id.in_(select(m.design_documents.c.project_id)))).mappings()]
    # Includes revisions of tombstoned projects. No lifecycle visibility filter.
    for rid in ids:
        with database.sessions() as session:
            revision = session.execute(select(m.project_revisions).where(m.project_revisions.c.id == rid)).mappings().one()
            rows = revision_rows(session, revision)
        report['revisions'] += 1
        try:
            _, missing = verify_revision_rows(rows, assets)
            report['legacy_missing_outputs' if missing else 'complete'] += 1
        except PersistenceError:
            report['invalid_revisions'] += 1
    for project in projects:
        report['documents'] += 1
        try:
            with database.sessions() as session:
                DocumentRepository(session).load(project)
        except PersistenceError:
            report['invalid_documents'] += 1
    # Retained values remain immutable even after a working document stops
    # referencing them. Check their envelope/hash too, without installing defaults.
    with database.sessions() as session:
        for row in session.execute(select(m.design_document_snapshots)).mappings():
            report['document_snapshots'] += 1
            if row['schema_version'] != 1 or content_hash(row['snapshot']) != row['sha256']:
                report['invalid_document_snapshots'] += 1
    return report
