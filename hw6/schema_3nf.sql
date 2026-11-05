-- HW6: third-normal-form schema (new tables live next to the HW5 tables in database `hw5`)
--
-- Functional dependencies in the HW5 table `requests`:
--   request_id  -> received_at, client_ip, gender, age_group, income_group,
--                  client_time, requested_file, status_code
--   client_ip   -> country          (an IP always comes from the same country)
--   country     -> is_banned        (banned-ness is a property of the country)
--   client_time -> time_of_day      (the hour is computed from the timestamp)
-- The last three are transitive dependencies (non-key -> non-key), which 3NF
-- forbids, so country / is_banned move to their own tables and time_of_day is dropped.
-- `failed_requests` duplicated request data (time, file, code), so it becomes a view.

CREATE TABLE IF NOT EXISTS country (
    country_id     SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    country_name   VARCHAR(64)       NOT NULL,
    is_banned      BOOLEAN           NOT NULL DEFAULT FALSE,
    PRIMARY KEY (country_id),
    UNIQUE KEY uq_country_name (country_name)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS client_ip (
    client_ip      VARCHAR(45)       NOT NULL,
    country_id     SMALLINT UNSIGNED NULL,            -- NULL: request sent no X-country
    PRIMARY KEY (client_ip),
    CONSTRAINT fk_ip_country FOREIGN KEY (country_id) REFERENCES country (country_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS request (
    request_id     BIGINT UNSIGNED   NOT NULL,        -- same ids as HW5 `requests`
    received_at    DATETIME(6)       NOT NULL,
    client_ip      VARCHAR(45)       NULL,
    gender         VARCHAR(16)       NULL,
    age_group      VARCHAR(16)       NULL,
    income_group   VARCHAR(16)       NULL,
    client_time    DATETIME          NULL,            -- time of day = HOUR(client_time)
    requested_file VARCHAR(255)      NOT NULL,
    status_code    SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (request_id),
    INDEX idx_request_ip (client_ip),
    INDEX idx_request_status (status_code),
    CONSTRAINT fk_request_ip FOREIGN KEY (client_ip) REFERENCES client_ip (client_ip)
) ENGINE=InnoDB;

-- the HW5 "failed requests" information, now derived instead of stored twice
CREATE OR REPLACE VIEW failed_request AS
    SELECT request_id, received_at AS request_time, requested_file, status_code AS error_code
    FROM request WHERE status_code <> 200;
