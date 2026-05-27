import unittest
from unittest.mock import patch

from app.config import MySQLConfig
from app.persistence import close_mysql_pool, connect_mysql


class MysqlPoolTests(unittest.TestCase):
    def setUp(self):
        close_mysql_pool()

    def tearDown(self):
        close_mysql_pool()

    def test_same_database_reuses_connection(self):
        config = MySQLConfig(password="secret", database="kol_monitor_trade")
        created = []
        with patch("app.persistence.pymysql.connect", side_effect=lambda **kw: _FakeConn(created, kw)):
            with connect_mysql(config) as first:
                self.assertEqual(first.ping_calls, 1)
            with connect_mysql(config) as second:
                self.assertEqual(second.ping_calls, 2)
        self.assertIs(first, second)
        self.assertEqual(len(created), 1)

    def test_different_database_uses_separate_connection(self):
        config = MySQLConfig(password="secret", database="kol_monitor_trade")
        created = []
        with patch("app.persistence.pymysql.connect", side_effect=lambda **kw: _FakeConn(created, kw)):
            with connect_mysql(config):
                pass
            with connect_mysql(config, database="market_opinion_tracker"):
                pass
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]["database"], "kol_monitor_trade")
        self.assertEqual(created[1]["database"], "market_opinion_tracker")

    def test_close_pool_closes_cached_connections(self):
        config = MySQLConfig(password="secret", database="kol_monitor_trade")
        instances = []
        with patch("app.persistence.pymysql.connect", side_effect=lambda **kw: _FakeConn(instances, kw)):
            with connect_mysql(config) as conn:
                self.assertTrue(conn.open)
            close_mysql_pool()
        self.assertFalse(instances[0].open)
        self.assertEqual(instances[0].close_calls, 1)


class _FakeConn:
    def __init__(self, sink, kwargs):
        sink.append(self)
        self.kwargs = kwargs
        self.open = True
        self.ping_calls = 0
        self.close_calls = 0

    def ping(self, reconnect=True):
        self.ping_calls += 1

    def close(self):
        self.open = False
        self.close_calls += 1

    def __getitem__(self, key):
        return self.kwargs[key]


if __name__ == "__main__":
    unittest.main()
