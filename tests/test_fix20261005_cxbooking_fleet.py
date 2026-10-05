from test_expansion_sites import env  # noqa: F401

def test_fleet_grants_are_customer_only_and_auditable(env):
    response=env.client.post(f'/api/v2/sites/{env.a.id}/organizations',json={'name':'Fleet'})
    assert response.status_code == 201,response.text
    oid=response.json()['id'];base=f'/api/v2/organizations/{oid}'
    staff_grant=env.client.post(base+'/members',json={'user_id':env.staff.id})
    assert staff_grant.status_code == 422,staff_grant.text
    customer_grant=env.client.post(base+'/members',json={'user_id':env.account.id})
    assert customer_grant.status_code == 200,customer_grant.text
    rows=env.client.get(base+'/members')
    assert rows.status_code == 200,rows.text
    assert rows.json()[0]['user_id'] == env.account.id
    env.actor['user']=env.account
    assert any(r['id']==oid for r in env.client.get('/api/v2/me/organizations').json())
    assert env.client.get(base+'/fleet').status_code == 200
    assert env.client.get(base+'/members').status_code == 403
    env.actor['user']=env.staff
    assert env.client.delete(base+f'/members/{env.stranger.id}').status_code == 404
    assert env.client.delete(base+f'/members/{env.account.id}').status_code == 204
