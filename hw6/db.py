"""
db.py - shared Cloud SQL helpers (used by the web server, setup_schema.py and stats.py).

Connects to the Cloud SQL for MySQL instance with the Cloud SQL Python Connector:
no IP allow-listing, the connection is TLS-encrypted and authorised through IAM
(the caller needs roles/cloudsql.client). The database password is never stored
in the repository: it comes from Secret Manager (or the DB_PASS env var).
"""

import os

import sqlalchemy

# ---------------------------------------------------------------- schema
SCHEMA = [
    # one row per request the server receives (successful or not)
    """
    CREATE TABLE IF NOT EXISTS requests (
        request_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        received_at     DATETIME(6)     NOT NULL,          -- server time (UTC)
        country         VARCHAR(64)     NULL,               -- X-country
        client_ip       VARCHAR(45)     NULL,               -- X-client-IP (IPv4/IPv6)
        gender          VARCHAR(16)     NULL,               -- X-gender
        age_group       VARCHAR(16)     NULL,               -- X-age, e.g. '26-35'
        income_group    VARCHAR(16)     NULL,               -- X-income, e.g. '40k-60k'
        is_banned       BOOLEAN         NOT NULL DEFAULT FALSE,
        client_time     DATETIME        NULL,               -- X-time as sent by the client
        time_of_day     TINYINT UNSIGNED NULL,              -- hour 0-23 taken from X-time
        requested_file  VARCHAR(255)    NOT NULL,
        status_code     SMALLINT UNSIGNED NOT NULL,
        PRIMARY KEY (request_id),
        INDEX idx_country (country),
        INDEX idx_status (status_code)
    ) ENGINE=InnoDB
    """,
    # failed requests only (status != 200): time, file, error code
    """
    CREATE TABLE IF NOT EXISTS failed_requests (
        failure_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        request_time    DATETIME(6)     NOT NULL,
        requested_file  VARCHAR(255)    NOT NULL,
        error_code      SMALLINT UNSIGNED NOT NULL,
        PRIMARY KEY (failure_id),
        INDEX idx_error (error_code)
    ) ENGINE=InnoDB
    """,
]


def get_password(project, secret):
    if os.environ.get("DB_PASS"):
        return os.environ["DB_PASS"]
    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project}/secrets/{secret}/versions/latest"
    return client.access_secret_version(name=name).payload.data.decode().strip()


def make_engine(instance_connection_name, user, password, db, pool_size=5):
    """SQLAlchemy connection pool on top of the Cloud SQL Python Connector."""
    from google.cloud.sql.connector import Connector
    connector = Connector()

    def getconn():
        return connector.connect(instance_connection_name, "pymysql",
                                 user=user, password=password, db=db)

    return sqlalchemy.create_engine("mysql+pymysql://", creator=getconn,
                                    pool_size=pool_size, max_overflow=5,
                                    pool_pre_ping=True, pool_recycle=1800)


def create_schema(engine):
    with engine.begin() as conn:
        for stmt in SCHEMA:
            conn.execute(sqlalchemy.text(stmt))
