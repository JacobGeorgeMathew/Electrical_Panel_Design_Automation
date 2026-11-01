from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel

class InputModel(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class WorkspaceTransform(InputModel):
    x: float
    y: float
    z: float
    rotation_deg: float = 0

class WorkspaceDocument(InputModel):
    editorTransforms: dict[str,WorkspaceTransform] = Field(default_factory=dict)
    schematicData: dict[str,Any] | None = None

class RecoveryDocument(InputModel):
    requirements: dict[str,Any]
    configuration: dict[str,Any]
    workspace: WorkspaceDocument
    baseRevisionId: str | None

class ProjectCreate(InputModel):
    name: str = Field(min_length=1,max_length=200)
    id: str | None = Field(default=None,min_length=1,max_length=100)
    description: str = Field(default='',max_length=10000)
    location: str = Field(default='',max_length=500)
    archetype: str = 'DB'
    archetype_version_id: str | None = None
    requirements: dict[str,Any] = Field(default_factory=dict)
    @field_validator('name')
    @classmethod
    def trim_name(cls,value):
        if not value.strip(): raise ValueError('Project name is required.')
        return value.strip()

class ProjectUpdate(InputModel):
    expected_version: int = Field(ge=1)
    expected_recovery_version: int | None = Field(default=None,ge=0)
    name: str | None = Field(default=None,min_length=1,max_length=200)
    description: str | None = Field(default=None,max_length=10000)
    location: str | None = Field(default=None,max_length=500)
    workspace: dict[str,Any] | None = None
    requirements: dict[str,Any] | None = None
    configuration: dict[str,Any] | None = None
    @field_validator('workspace')
    @classmethod
    def workspace_shape(cls,value):
        return WorkspaceDocument(**value).model_dump() if value is not None else None
    @field_validator('configuration')
    @classmethod
    def configuration_shape(cls,value):
        if value is not None:
            if set(value)-{'enclosure_id','enclosure_parameters'}: raise ValueError('Unknown project configuration field.')
            if not isinstance(value.get('enclosure_parameters',{}),dict): raise ValueError('Enclosure parameters must be an object.')
        return value
    @field_validator('name')
    @classmethod
    def trim_name(cls,value):
        if value is not None and not value.strip(): raise ValueError('Project name is required.')
        return value.strip() if value is not None else value

class ProjectView(BaseModel):
    id: str
    database_id: str
    name: str
    status: str
    archetype: str | None
    archetype_version_id: str | None
    requirements: dict[str,Any]
    configuration: dict[str,Any]
    lock_version: int
    current_revision_id: str | None
    created_at: str
    updated_at: str
    description: str
    location: str
    last_opened_at: str | None
    workspace: dict[str,Any]
    recovery: dict[str,Any] | None
    recovery_version: int

class ExpectedVersion(InputModel):
    expected_version: int = Field(ge=1)

class RevisionCreate(ExpectedVersion):
    requirements: dict[str,Any] = Field(default_factory=dict)
    configuration: dict[str,Any] | None = None

    @field_validator('configuration')
    @classmethod
    def validate_configuration(cls,value):
        return ProjectUpdate.configuration_shape(value)

class AnswerSave(ExpectedVersion):
    answers: dict[str,Any]

class ChangeInput(InputModel):
    modified_field: str = Field(min_length=1)
    new_value: Any
    expected_version: int | None = Field(default=None,ge=1)

class CadJobInput(ExpectedVersion):
    file_format: Literal['GLB','FREECAD_SCRIPT'] = 'GLB'

class ArtifactView(BaseModel):
    id: str
    file_format: str
    sha256: str | None = None
    byte_size: int | None = None
    status: str
    type: str | None = None
    project_revision_id: str | None = None
    url: str | None = None
    generator_name: str | None = None
    generator_version: str | None = None
    error: dict[str,Any] | None = None

class DesignPackage(BaseModel):
    cem: CanonicalEngineeringModel
    pdm: PhysicalDesignModel
    schematic: dict[str,Any]
    cad: dict[str,Any]
    bom: list[dict[str,Any]]
    validation_errors: list[dict[str,Any]]
    revision_id: str
    revision_no: int
    lock_version: int
    snapshot_sha256: str
    manifest: dict[str,Any]
    artifacts: list[ArtifactView]
    is_stale: bool

class CatalogComponentView(BaseModel):
    model_config=ConfigDict(extra='allow')
    id: str
    code: str
    name: str
    catalog_id: str
    category: str
    component_version_id: str
    version_no: int
    current_rating: float
    rated_voltage_v: float | None
    breaking_capacity: float
    poles: int
    width: float
    height: float
    depth: float
    mounting: str
    manufacturer: str | None
    sku: str | None
    terminals: list[dict[str,Any]]
    specification: dict[str,Any]
    cad_models: list[dict[str,Any]] | None = None

class CatalogPageView(BaseModel):
    items: list[CatalogComponentView]
    total: int
    page: int
    page_size: int

class ArchetypeView(BaseModel):
    id: str
    code: str
    name: str
    description: str | None = None
    version_id: str
    version_no: int
    supported: bool


class RecoverySave(ExpectedVersion):
    expected_recovery_version: int = Field(ge=0)
    document: dict[str,Any] | None
    @field_validator('document')
    @classmethod
    def document_shape(cls,value):
        return RecoveryDocument(**value).model_dump() if value is not None else None

class ProjectDuplicate(ExpectedVersion):
    name: str = Field(min_length=1,max_length=200)
    @field_validator('name')
    @classmethod
    def trim_name(cls,value):
        if not value.strip(): raise ValueError('Project name is required.')
        return value.strip()

class ProjectImport(InputModel):
    format: Literal['panelstudio-project']
    version: Literal[1]
    project: ProjectCreate
    configuration: dict[str,Any] = Field(default_factory=dict)
    workspace: dict[str,Any] = Field(default_factory=dict)
    revisions: list[dict[str,Any]] = Field(default_factory=list,max_length=200)
    source_project_id: str = Field(min_length=1,max_length=100)
    @field_validator('workspace')
    @classmethod
    def workspace_shape(cls,value):
        return WorkspaceDocument(**value).model_dump()
