import pytest
from test_expansion_sites import env  # noqa: F401

@pytest.mark.parametrize('query',['30A99999','30a 999.99','99999','30A-99999'])
def test_vehicle_picker_accepts_plate_formats(env,query):
    response=env.client.get(f'/api/v2/sites/{env.a.id}/vehicles',params={'q':query})
    assert response.status_code == 200,response.text
    assert [r['id'] for r in response.json()] == [env.vehicle.id]
