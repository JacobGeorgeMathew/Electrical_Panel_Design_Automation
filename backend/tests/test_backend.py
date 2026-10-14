from app.services.orchestrator import DesignOrchestrator
from app.services.requirement_engine import RequirementEngine
from app.services.calculation_engine import CalculationEngine
from app.services.change_propagation import ChangePropagationEngine


def test_requirement_engine():
    engine = RequirementEngine()
    questions = engine.get_questions("DB")
    assert len(questions) > 0

    req_set = engine.validate_requirements("TEST_001", "DB", {
        "supply_voltage": 415,
        "phases": 3,
        "incomer_rating": 250,
        "num_feeders": 12
    })
    assert req_set.is_valid


def test_calculation_engine():
    calc = CalculationEngine()
    results = calc.calculate_db_parameters({
        "supply_voltage": 415,
        "phases": 3,
        "incomer_rating": 250,
        "num_feeders": 12
    })
    assert len(results) >= 6
    capacity = next(r for r in results if r.type == "total_capacity")
    assert capacity.value > 100.0


def test_orchestrator_pipeline():
    orch = DesignOrchestrator()
    result = orch.generate_design("TEST_PROJ_001")
    assert "cem" in result
    assert "pdm" in result
    assert "schematic" in result
    assert "cad" in result
    assert len(result["cem"]["components"]) > 5
    assert len(result["pdm"]["routes"]) > 0


def test_change_propagation():
    change_engine = ChangePropagationEngine()
    dirty = change_engine.identify_dirty_nodes("num_feeders")
    assert "COMPONENT_SELECTION" in dirty
    assert "ENCLOSURE" in dirty
