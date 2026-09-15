"""Frozen additive occupancy observations schema; no historical data rewritten."""
from alembic import op

revision = "20260915_05"
down_revision = "20260915_04"
branch_labels = None
depends_on = None

UPGRADE_SQL = ('\n'
 'CREATE TABLE occupancy_calibrations (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tsite_id INTEGER NOT NULL, \n'
 '\tcamera_id INTEGER NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\treference_observation_id VARCHAR(36), \n'
 '\treference_id_snapshot VARCHAR(36) NOT NULL, \n'
 '\treference_image_hash VARCHAR(64) NOT NULL, \n'
 '\treference_width INTEGER NOT NULL, \n'
 '\treference_height INTEGER NOT NULL, \n'
 '\treference_observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\treference_expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tengine VARCHAR(40) NOT NULL, \n'
 '\tsettings_schema_version INTEGER NOT NULL, \n'
 '\tregions JSON NOT NULL, \n'
 '\tsettings JSON NOT NULL, \n'
 '\trequest_id VARCHAR(64) NOT NULL, \n'
 '\tpayload_hash VARCHAR(64) NOT NULL, \n'
 '\tcreated_by_id INTEGER NOT NULL, \n'
 '\tcreated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_occupancy_camera_version UNIQUE (camera_id, version), \n'
 '\tCONSTRAINT uq_occupancy_calibration_request UNIQUE (camera_id, request_id), \n'
 '\tCONSTRAINT ck_occupancy_calibration_version CHECK (version > 0), \n'
 '\tCONSTRAINT ck_occupancy_settings_version CHECK (settings_schema_version = 1), \n'
 "\tCONSTRAINT ck_occupancy_calibration_engine CHECK (engine = 'reference-diff-v1'), \n"
 '\tFOREIGN KEY(site_id) REFERENCES parking_sites (id), \n'
 '\tFOREIGN KEY(camera_id) REFERENCES vision_cameras (id), \n'
 '\tFOREIGN KEY(reference_observation_id) REFERENCES vision_observations (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(created_by_id) REFERENCES users (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_occupancy_calibrations_camera_id ON occupancy_calibrations (camera_id)',
 'CREATE INDEX ix_occupancy_calibrations_site_id ON occupancy_calibrations (site_id)',
 '\n'
 'CREATE TABLE occupancy_calibration_slots (\n'
 '\tcalibration_id VARCHAR(36) NOT NULL, \n'
 '\tslot_id INTEGER NOT NULL, \n'
 '\tPRIMARY KEY (calibration_id, slot_id), \n'
 '\tFOREIGN KEY(calibration_id) REFERENCES occupancy_calibrations (id), \n'
 '\tFOREIGN KEY(slot_id) REFERENCES parking_slots (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_occupancy_calibration_slots_slot_id ON occupancy_calibration_slots (slot_id)',
 '\n'
 'CREATE TABLE occupancy_observations (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tcalibration_id VARCHAR(36) NOT NULL, \n'
 '\tsource_observation_id VARCHAR(36), \n'
 '\tsource_id_snapshot VARCHAR(36) NOT NULL, \n'
 '\tsource_image_hash VARCHAR(64) NOT NULL, \n'
 '\tmeasured_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\treceived_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\texpires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tanalyzed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, \n'
 '\tanalyzed_by_id INTEGER NOT NULL, \n'
 '\tengine VARCHAR(40) NOT NULL, \n'
 '\tquality JSON NOT NULL, \n'
 '\treadings JSON NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_occupancy_calibration_source UNIQUE (calibration_id, source_id_snapshot), \n'
 "\tCONSTRAINT ck_occupancy_observation_engine CHECK (engine = 'reference-diff-v1'), \n"
 '\tFOREIGN KEY(calibration_id) REFERENCES occupancy_calibrations (id), \n'
 '\tFOREIGN KEY(source_observation_id) REFERENCES vision_observations (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(analyzed_by_id) REFERENCES users (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX ix_occupancy_observations_calibration_id ON occupancy_observations (calibration_id)',
 'CREATE INDEX ix_occupancy_observations_measured_at ON occupancy_observations (measured_at)')


def upgrade():
    for sql in UPGRADE_SQL:
        op.execute(sql)


def downgrade():
    raise RuntimeError("Keep observation history and use a compatible application or forward migration; destructive downgrade is unsupported.")
