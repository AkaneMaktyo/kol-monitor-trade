from app.config import AppConfig, MySQLConfig


def test_config() -> AppConfig:
    return AppConfig(mysql=test_mysql_config())


def test_mysql_config() -> MySQLConfig:
    return MySQLConfig(
        host="127.0.0.1",
        port=13306,
        user="tester",
        password="secret",
        database="kol_monitor_trade",
    )
