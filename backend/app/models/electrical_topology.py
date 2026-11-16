"""Explicit draft evidence for the bounded DB connectivity checker."""
from typing import Literal

from pydantic import Field, model_validator

from app.models.identity import ContractModel, StableID, unique_ids


class TerminalDomainEvidence(ContractModel):
    component_id: StableID
    terminal_id: StableID
    supply_id: StableID
    role: Literal['L1', 'L2', 'L3', 'N', 'PE']


class PermanentGroupEvidence(ContractModel):
    id: StableID
    members: list[tuple[StableID, StableID]] = Field(min_length=2)
    evidence_id: StableID | None = None


class ElectricalTopologyEvidence(ContractModel):
    domains: list[TerminalDomainEvidence]
    equivalences: list[PermanentGroupEvidence] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_evidence(self):
        keys = [(d.component_id, d.terminal_id) for d in self.domains]
        if len(set(keys)) != len(keys):
            raise ValueError('Terminal domains must be unique.')
        unique_ids((e.id for e in self.equivalences), 'electrical_topology.equivalences')
        for group in self.equivalences:
            if len(set(group.members)) != len(group.members):
                raise ValueError('Permanent group members must be unique.')
        return self
