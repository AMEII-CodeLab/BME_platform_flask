"""Importing QA scripts must never read business credentials or touch a database."""
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('test_project_core_mysql.py')


class MysqlEntrypointTest(unittest.TestCase):
    def test_import_is_inert(self):
        before = dict(os.environ)
        cwd = Path.cwd()
        with patch('pymysql.connect', side_effect=AssertionError('Unexpected database connection')):
            namespace = runpy.run_path(str(SCRIPT), run_name='mysql_qa_import_check')
        self.assertTrue(callable(namespace['main']))
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(Path.cwd(), cwd)

    def test_explicit_connection_is_required(self):
        with patch.dict(os.environ), patch('pymysql.connect', side_effect=AssertionError('Unexpected database connection')):
            os.environ.pop('BME_TEST_MYSQL_URI', None)
            with self.assertRaisesRegex(SystemExit, 'BME_TEST_MYSQL_URI'):
                runpy.run_path(str(SCRIPT), run_name='__main__')

    def test_remote_or_business_database_is_rejected(self):
        for uri in ('mysql+pymysql://qa@192.0.2.1/bme_project_test_tmp',
                    'mysql+pymysql://qa@localhost/sysu_bme'):
            with self.subTest(uri=uri), patch.dict(os.environ, BME_TEST_MYSQL_URI=uri), \
                    patch('pymysql.connect', side_effect=AssertionError('Unexpected database connection')):
                with self.assertRaises(SystemExit):
                    runpy.run_path(str(SCRIPT), run_name='__main__')
