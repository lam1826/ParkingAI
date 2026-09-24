"""Frozen additive approved-demo schema; preserve historical rows and authority."""
from alembic import op

revision = '20260923_09'
down_revision = '20260923_08'
branch_labels = None
depends_on = None

UPGRADE_SQL = ("ALTER TABLE vision_observations ADD COLUMN capture_source VARCHAR(16) NOT NULL DEFAULT 'manual_upload'",
 'CREATE TABLE vision_automation_policies (\n'
 '\tcamera_id INTEGER NOT NULL, \n'
 '\tenabled BOOLEAN NOT NULL, \n'
 '\tminimum_confidence FLOAT NOT NULL, \n'
 '\tmax_age_seconds INTEGER NOT NULL, \n'
 '\tdirection VARCHAR(8) NOT NULL, \n'
 '\tzone_id INTEGER, \n'
 '\tenabled_at TIMESTAMP WITHOUT TIME ZONE, \n'
 '\tupdated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tupdated_by_id INTEGER NOT NULL, \n'
 '\tPRIMARY KEY (camera_id), \n'
 '\tCONSTRAINT ck_vision_auto_confidence CHECK (minimum_confidence >= 0.9 AND minimum_confidence <= 1), \n'
 '\tCONSTRAINT ck_vision_auto_age CHECK (max_age_seconds BETWEEN 3 AND 30), \n'
 "\tCONSTRAINT ck_vision_auto_direction CHECK (direction IN ('entry','exit')), \n"
 '\tFOREIGN KEY(camera_id) REFERENCES vision_cameras (id), \n'
 '\tFOREIGN KEY(zone_id) REFERENCES zones (id), \n'
 '\tFOREIGN KEY(updated_by_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE vision_passage_events (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcamera_id INTEGER NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tobservation_id VARCHAR(36), \n'
 '\tobservation_key VARCHAR(36) NOT NULL, \n'
 '\tevent_id VARCHAR(36) NOT NULL, \n'
 '\tdirection VARCHAR(8) NOT NULL, \n'
 '\tstate VARCHAR(20) NOT NULL, \n'
 '\tlicense_plate VARCHAR(20), \n'
 '\tplate_key VARCHAR(20), \n'
 '\tvehicle_type_id INTEGER, \n'
 '\tsession_id VARCHAR(36), \n'
 '\treason VARCHAR(500) NOT NULL, \n'
 '\tactor_id INTEGER NOT NULL, \n'
 '\tcaptured_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tprocessed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_vision_passage_camera_event UNIQUE (camera_id, event_id), \n'
 '\tCONSTRAINT uq_vision_passage_observation UNIQUE (observation_key), \n'
 "\tCONSTRAINT ck_vision_passage_direction CHECK (direction IN ('entry','exit')), \n"
 '\tCONSTRAINT ck_vision_passage_state CHECK (state IN '
 "('entered','exited','already_entered','waiting_payment','manual','disabled')), \n"
 '\tFOREIGN KEY(camera_id) REFERENCES vision_cameras (id), \n'
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(observation_id) REFERENCES vision_observations (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(vehicle_type_id) REFERENCES vehicle_types (id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES parking_sessions (id), \n'
 '\tFOREIGN KEY(actor_id) REFERENCES users (id)\n'
 ')',
 'CREATE INDEX ix_vision_passage_plate_time ON vision_passage_events (site_id, plate_key, processed_at)',
 'CREATE INDEX ix_vision_passage_site_time ON vision_passage_events (site_id, processed_at)')

def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Preserve booking, payment-access and camera history; use a compatible application or a forward migration.")
