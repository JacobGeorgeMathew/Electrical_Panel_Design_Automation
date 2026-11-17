"""Explicit legacy-history fixtures; never imported by application code.

These low-level fixtures preserve testing of old revisions after runtime legacy
publication was closed. They grant no engineering approval or runtime bypass.
"""
from app.services import project_service


def seed_historical_revision(service, key, overrides=None, expected_version=None, configuration=None):
    project, template, *_ = service._inputs(key)
    values = {**project['requirements'], **(overrides or {})}
    source, requirements, result, manifest = service.generate(
        key, values, expected_version, configuration, propose=True)
    if configuration is not None:
        project['configuration'] = configuration
    files = service.generate_files(result)
    version = project['lock_version'] if expected_version is None else expected_version
    outputs = project_service.prepare_outputs(project, requirements, values, result,
        manifest, files, source, service.assets, version)
    with service.db.sessions.begin() as session:
        saved = project_service.write_revision(session, project, template, requirements,
            values, result, manifest, files, version, outputs=outputs)
    return service.load_revision(key, saved['revision_id'])


def historical_design(api, key, overrides=None, expected_version=None, configuration=None):
    return seed_historical_revision(project_service.ProjectService(api.app.state.database),
        key, overrides, expected_version, configuration)
