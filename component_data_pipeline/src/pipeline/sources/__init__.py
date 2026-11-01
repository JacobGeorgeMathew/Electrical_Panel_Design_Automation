"""Source connectors."""
from .generic import CandidateSource

def get_source(source_id, config):
    return CandidateSource(source_id, config)
from .abb import ABBSource
from .havells_india import HavellsIndiaSource
from .lt_india import LTIndiaSource
from .schneider_india import SchneiderIndiaSource

CONNECTORS = {
    "abb": ABBSource,
    "havells_india": HavellsIndiaSource,
    "lt_india": LTIndiaSource,
    "schneider_india": SchneiderIndiaSource,
}

def get_source(source_id, config):
    connector = CONNECTORS.get(source_id)
    if connector is None:
        from .generic import CandidateSource
        return CandidateSource(source_id, config)
    return connector(source_id, config)
