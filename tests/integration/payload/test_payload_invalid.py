"""test to verify validation on invalid yml"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.schemas.full_simulation_input import SimulationPayload

DATA_DIR = Path(__file__).parent / "data" / "invalid"
YMLS = sorted(DATA_DIR.glob("*.yml"))

@pytest.mark.integration
@pytest.mark.parametrize("yaml_path", YMLS, ids=lambda p: p.stem)
def test_invalid_payloads_raise(yaml_path: Path)  -> None :
    raw = yaml.safe_load(yaml_path.read_text())
    with pytest.raises(ValidationError):
        SimulationPayload.model_validate(raw)
