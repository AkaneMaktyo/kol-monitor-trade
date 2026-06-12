CHANNELS_SQL = """
CREATE TABLE IF NOT EXISTS youtube_channels (
    id VARCHAR(40) PRIMARY KEY,
    channel_id VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    handle VARCHAR(120) NOT NULL DEFAULT '',
    source_url VARCHAR(255) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    last_checked_at VARCHAR(32) NOT NULL DEFAULT '',
    last_video_published_at VARCHAR(32) NOT NULL DEFAULT '',
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    INDEX idx_youtube_channels_updated(updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

VIDEOS_SQL = """
CREATE TABLE IF NOT EXISTS youtube_videos (
    video_id VARCHAR(32) PRIMARY KEY,
    channel_row_id VARCHAR(40) NOT NULL,
    channel_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    video_url VARCHAR(255) NOT NULL,
    published_at VARCHAR(32) NOT NULL,
    audio_path VARCHAR(500) NOT NULL DEFAULT '',
    audio_duration_ms INT NOT NULL DEFAULT 0,
    transcript_status VARCHAR(32) NOT NULL,
    transcript_language VARCHAR(32) NOT NULL DEFAULT '',
    transcript_source VARCHAR(32) NOT NULL DEFAULT '',
    transcript_text LONGTEXT,
    transcript_segments_json MEDIUMTEXT,
    error_message TEXT,
    synced_at VARCHAR(32) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    INDEX idx_youtube_videos_channel(channel_row_id),
    INDEX idx_youtube_videos_published(published_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""
