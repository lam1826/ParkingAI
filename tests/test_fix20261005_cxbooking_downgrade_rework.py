import os
import subprocess
import sys
from pathlib import Path
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_postgres_integration import _isolated_checkout_postgres
from test_fix20261005_cxbooking_postgres import _seed
from schemas.checkout import CheckoutConfirmation
from services.parking_service import ParkingService
from services.checkout_service import CheckoutService

pytestmark = pytest.mark.skipif(not os.getenv('POSTGRES_TEST_URL'),reason='Disposable PostgreSQL required')
FUNCTIONS = ['trg_declared_booking_source_fn','trg_declared_session_insert_fn',
             'trg_declared_session_activate_fn','trg_session_capacity_hold_fn','parkingai_validate_session']


def test_migration_11_roundtrip_restores_frozen_predecessor_without_rewriting_receipts():
    with _isolated_checkout_postgres() as engine:
        site_id, type_id, pairs, _ = _seed(engine,1,'same_zone')
        with Session(engine) as db:
            staff_id=db.execute(text("SELECT id FROM users WHERE username='op-a'")).scalar_one()
            admitted=ParkingService(db).check_in('ROLLBACK-1',type_id,staff_id,_expected_site_id=site_id)
            checkout=CheckoutService(db)
            quote=checkout.quote(admitted['session_id'],staff_id)
            checkout.confirm(CheckoutConfirmation(quote_token=quote['quote_token'],payment_confirmed=True, payment_method='transfer' if quote['parking_fee'] else None),staff_id,session_id=admitted['session_id'])
        def snapshot():
            with engine.connect() as connection:
                bodies=dict(connection.execute(text('SELECT proname, pg_get_functiondef(oid) FROM pg_proc WHERE proname = ANY(:names)'),{'names':FUNCTIONS}).all())
                receipt=connection.execute(text('SELECT row_to_json(p)::text FROM payments p ORDER BY id')).scalars().all()
                assert receipt,'Receipt witness must exist before migration'
                version=connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                return bodies,receipt,version
        before,receipt,head=snapshot()
        assert set(before)==set(FUNCTIONS)
        backend=Path(__file__).resolve().parents[1]/'backend'
        env={**os.environ,'DATABASE_URL':engine.url.render_as_string(hide_password=False)}
        def migrate(command,revision):
            result=subprocess.run([sys.executable,'-m','alembic','-c',str(backend/'alembic.ini'),command,revision],cwd=backend,env=env,capture_output=True,text=True,timeout=60)
            assert result.returncode==0,result.stdout+result.stderr
        migrate('downgrade','20260927_10')
        old,old_receipt,version=snapshot()
        assert version=='20260927_10'
        assert old_receipt==receipt
        assert all(old[name]!=before[name] for name in FUNCTIONS)
        assert 'PERFORM 1 FROM zones WHERE id = session_zone FOR UPDATE' in old['parkingai_validate_session']
        migrate('upgrade','head')
        after,new_receipt,version=snapshot()
        assert after==before
        assert new_receipt==receipt
        assert version==head
