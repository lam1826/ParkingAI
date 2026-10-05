from datetime import timedelta
from core.clock import business_now
from test_portal_api import portal  # noqa: F401
from test_timed_parking import timed  # noqa: F401

def test_timed_order_without_effective_rate_returns_conflict(timed):
    context,body,slot,rate=timed
    client,current,users,site,kind,db=context
    rate.effective_date=business_now().date()+timedelta(days=1);db.commit()
    response=client.post('/api/v2/me/orders',json=body)
    assert response.status_code == 409,response.text
    assert 'bảng giá' in response.json()['detail']
