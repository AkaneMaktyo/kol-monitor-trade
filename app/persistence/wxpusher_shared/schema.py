SETTINGS_SQL = """
    CREATE TABLE IF NOT EXISTS wxpusher_settings (
      id VARCHAR(32) PRIMARY KEY,
      device_token VARCHAR(255) NOT NULL,
      push_token VARCHAR(255) NOT NULL,
      device_uuid VARCHAR(255) NOT NULL,
      platform VARCHAR(64) NOT NULL,
      version VARCHAR(32) NOT NULL,
      poll_interval_seconds INT NOT NULL,
      enable_polling BOOLEAN NOT NULL DEFAULT FALSE,
      enable_websocket BOOLEAN NOT NULL DEFAULT FALSE,
      last_heartbeat_at VARCHAR(64),
      last_error TEXT,
      last_poll_at VARCHAR(64),
      created_at VARCHAR(64) NOT NULL,
      updated_at VARCHAR(64) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

RAW_MESSAGES_SQL = """
    CREATE TABLE IF NOT EXISTS wxpusher_raw_messages (
      id VARCHAR(64) PRIMARY KEY,
      message_key VARCHAR(512) NOT NULL,
      channel VARCHAR(32) NOT NULL,
      source_name VARCHAR(255) NOT NULL,
      title VARCHAR(500) NOT NULL,
      summary TEXT,
      detail_url VARCHAR(1000),
      source_url VARCHAR(1000),
      message_time VARCHAR(64) NOT NULL,
      raw_payload_json MEDIUMTEXT,
      created_at VARCHAR(64) NOT NULL,
      updated_at VARCHAR(64) NOT NULL,
      UNIQUE KEY uq_wxpusher_raw_message_key(message_key),
      INDEX idx_wxpusher_raw_message_time(message_time, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

CONSUMER_STATE_SQL = """
    CREATE TABLE IF NOT EXISTS wxpusher_consumer_state (
      id VARCHAR(64) PRIMARY KEY,
      consumer_name VARCHAR(64) NOT NULL,
      message_key VARCHAR(512) NOT NULL,
      status VARCHAR(32) NOT NULL,
      error_message TEXT,
      derived_id VARCHAR(64),
      created_at VARCHAR(64) NOT NULL,
      updated_at VARCHAR(64) NOT NULL,
      UNIQUE KEY uq_wxpusher_consumer_message(consumer_name, message_key),
      INDEX idx_wxpusher_consumer_status(consumer_name, status, updated_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""
