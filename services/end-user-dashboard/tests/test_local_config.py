from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]

class LocalConfigTest(unittest.TestCase):
    def test_dashboard_local_security_configuration(self):
        compose = (ROOT / 'docker-compose.yml').read_text()
        migration = (ROOT / 'infra/clickhouse/migrations/0011_dashboard_role.sql').read_text()
        self.assertIn('127.0.0.1:${DASHBOARD_HOST_PORT:-8083}:3000', compose)
        self.assertIn('sentinel_dashboard_u', compose)
        self.assertIn('GRANT SELECT ON bronze.otel_traces', migration)
        self.assertIn('readonly = 2', migration)
        self.assertNotIn('GRANT SELECT ON bronze.*', migration)

if __name__ == '__main__':
    unittest.main()
