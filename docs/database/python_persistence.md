# Python persistence starter

This is the historical design starter. The implemented mappings, repositories, sessions and migrations now live in `backend/app/persistence` and `backend/migrations`. Follow [OPERATIONS.md](OPERATIONS.md) for the current setup; the snippets below explain the original approach rather than serving as the runtime implementation.

This is a persistence boundary proposal, not a rewrite of the engineering engine. Add the packages in a pinned backend requirements update after choosing supported SQLAlchemy/Alembic versions: `SQLAlchemy>=2,<3`, `alembic`, and a PostgreSQL driver such as `psycopg[binary]`. Keep SQLite URL configuration available for desktop/offline operation. The current typed models under `backend/app/models` remain service contracts; map persistence rows to/from those DTOs in repositories.

## SQLAlchemy 2.x mappings

Use generic SQLAlchemy UUID and JSON types with a PostgreSQL JSONB variant. Keep all database imports under a new `backend/app/persistence/` package to avoid coupling the services to SQLAlchemy.

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")

class Base(DeclarativeBase):
    pass

class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_code: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revisions: Mapped[list["ProjectRevisionRow"]] = relationship(back_populates="project")

class ProjectRevisionRow(Base):
    __tablename__ = "project_revisions"
    __table_args__ = (UniqueConstraint("project_id", "revision_no"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("project_revisions.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_manifest: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[ProjectRow] = relationship(back_populates="revisions")

class CemSnapshotRow(Base):
    __tablename__ = "cem_snapshots"
    project_revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("project_revisions.id", ondelete="RESTRICT"), primary_key=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

class ComponentRow(Base):
    __tablename__ = "components"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
```

The production mappings should mirror `001_core.sql`, including all FK actions, checks, scoped uniqueness and partial indexes. Since portable SQLAlchemy metadata does not make dialect semantics identical, keep PostgreSQL-only index/JSONB constructs in explicit dialect-aware model configuration or Alembic operations. For SQLite constraint changes, use Alembic batch operations.

## Repository interfaces

Services depend on protocols/data contracts, not SQLAlchemy sessions. Keep the current JSON repository as an adapter while porting endpoint-by-endpoint.

```python
from typing import Protocol
from uuid import UUID

class ComponentRepository(Protocol):
    def get_published_by_code(self, code: str) -> dict | None: ...
    def search(self, category: str, filters: dict) -> list[dict]: ...

class CadModelRepository(Protocol):
    def get_version(self, version_id: UUID) -> dict | None: ...
    def list_assets(self, version_id: UUID) -> list[dict]: ...

class RuleRepository(Protocol):
    def get_rule_set_version(self, version_id: UUID) -> dict | None: ...

class ArchetypeRepository(Protocol):
    def get_published_version(self, code: str) -> dict | None: ...

class ProjectRepository(Protocol):
    def create(self, name: str, archetype_version_id: UUID) -> UUID: ...
    def get_revision(self, project_id: UUID, revision_no: int | None = None) -> dict | None: ...
    def publish_revision(self, project_id: UUID, payload: dict) -> UUID: ...
```

Concrete classes (`SqlComponentRepository`, `SqlCadModelRepository`, `SqlRuleRepository`, `SqlArchetypeRepository`, `SqlProjectRepository`) receive a SQLAlchemy `Session` or session factory. Translate SQL rows into existing Pydantic CEM/PDM DTOs at the repository/service boundary. Do not pass ORM objects into the engineering algorithms.

## Transactions and immutable revision writes

Run the design pipeline in memory first. Once outputs pass the configured validation gate, create one revision atomically: lock or serialize revision-number allocation for the project; insert revision header and pinned model manifest; insert requirements and provenance; insert CEM snapshot and its component/terminal/net projections; insert PDM snapshot and placement/route projections; insert validation run/results, dependencies and artifact job metadata; then commit. If any relational projection or hash check fails, roll back the complete revision. Use a unique `(project_id, revision_no)` constraint to resolve concurrent writers. Publish by changing draft to published only once all required records exist; published snapshots are never updated.

```python
def save_revision(session, project_id, revision_payload):
    # revision_payload has already been validated and canonicalized by the service.
    with session.begin():
        project = session.get(ProjectRow, project_id, with_for_update=True)
        if project is None:
            raise LookupError(project_id)
        next_no = max((r.revision_no for r in project.revisions), default=0) + 1
        header = ProjectRevisionRow(
            project_id=project_id,
            revision_no=next_no,
            status="DRAFT",
            schema_version=1,
            model_manifest=revision_payload["model_manifest"],
            content_sha256=revision_payload["content_sha256"],
        )
        session.add(header)
        session.flush()
        # Insert CEM/PDM snapshot rows and their normalized projections here.
        # Verify snapshot hashes equal hashes on the header/model manifest.
        session.flush()
        header.status = "PUBLISHED"
        return header.id
```

For SQLite, `SELECT FOR UPDATE` is not effective; rely on a short write transaction plus the unique constraint and retry revision allocation on collision. For PostgreSQL, row-level locking serializes allocation. Do not hold DB locks while running optimization or CAD generation.

## Alembic organization

Initialize Alembic under `backend/alembic/`; import `Base.metadata` from the persistence package in `env.py`, read the connection URL from application settings, and support offline SQL generation. Keep migrations additive and ordered by domain:

1. `001_core_catalog_projects`: identities, products, archetypes, projects, requirements.
2. `002_cem_pdm_snapshots`: CEM/PDM projections, nets, placements, routes.
3. `003_cad_assets_rules_validation`: parameter models, assets, rules, validations, artifacts.
4. Later revisions add expanded questionnaire/module/compatibility fields.

The combined baseline SQL is provided in `001_core.sql`; splitting it into the first reviewed Alembic revisions is the initial implementation step. Do not hand-edit an applied migration. Schema changes use a new revision and a tested upgrade path; data backfills should be restartable and track a migration marker. Preserve the source JSON files until record counts, sample snapshots, and hashes have been reconciled.

## Pydantic API boundary

API request/response types remain independent of ORM types. Validate explicit measurement units and finite numeric values before repository writes. A project requirement value uses an operator and tagged value; CEM/PDM payloads carry their snapshot schema version.

```python
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class RequirementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    operator: Literal["EQ", "MIN", "MAX", "RANGE", "IN", "NOT_IN", "QUANTITY"]
    value: Any
    unit: str | None = None
    source_answer_id: UUID | None = None

class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_parent_revision_id: UUID | None = None
    archetype_version_id: UUID
    requirements: list[RequirementInput] = Field(default_factory=list)

class RevisionSummary(BaseModel):
    revision_id: UUID
    revision_no: int
    status: Literal["DRAFT", "PUBLISHED", "SUPERSEDED"]
    snapshot_sha256: str
```

Use Pydantic validators or a shared unit library to check compatible dimensions and convert to canonical units. SQL basic checks are a second line of defense, not a substitute for the engineering service's validation.
