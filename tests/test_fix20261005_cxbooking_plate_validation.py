import pytest
from pydantic import ValidationError
from schemas.vehicle import VehicleCreate, VehicleUpdate
from schemas.session_exception import PlateCorrectionRequest

@pytest.mark.parametrize('plate',['29MĐ1-123.45','30A\u2013123.45','30A/12345','30A\u00a012345'])
@pytest.mark.parametrize('schema',[VehicleCreate,PlateCorrectionRequest])
def test_creation_and_correction_reject_unadmittable_plate(schema, plate):
    fields={'license_plate':plate,'vehicle_type_id':1} if schema is VehicleCreate else {'license_plate':plate}
    if schema is PlateCorrectionRequest:
        fields.update(reason='correct misread', request_id='plate-validation-1')
    with pytest.raises(ValidationError):
        schema(**fields)
