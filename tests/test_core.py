"""Behavior tests use a temporary database and files created by this suite only."""
import http.client
import json
import contextlib
import io
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = tempfile.TemporaryDirectory(prefix='core-', dir=ROOT/'work')
os.environ['STORAGELENS_DATA_DIR'] = str(Path(FIXTURE.name)/'state')
os.environ['STORAGELENS_SESSION_TOKEN'] = secrets.token_hex(24)
sys.path.insert(0, str(ROOT/'Web'))
import config
import storage
import cleanup
import app

class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Path(tempfile.mkdtemp(dir=FIXTURE.name))
        self.tree = self.fixture/'tree'
        self.tree.mkdir()
        (self.tree/'small.txt').write_bytes(b's'*4096)
        nested = self.tree/'nested'; nested.mkdir()
        (nested/'large.bin').write_bytes(b'l'*16384)
        storage.DATA = self.fixture/'state'; storage.DATA.mkdir()
        storage.DB = storage.DATA/'storage.sqlite3'
        storage.PROGRESS = storage.DATA/'progress.json'
        config.INVENTORY = storage.DATA/'inventory.json'
        config.INVENTORY.write_text('{"apps":[]}', encoding='utf-8')
        self.inventory = patch.object(storage, 'refresh_inventory', return_value=[])
        self.inventory.start()
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        app.APP_CACHE.clear()

    def tearDown(self):
        self.inventory.stop()
        self.output.__exit__(None,None,None)

    def test_recursive_sizes_and_hardlink_deduplication(self):
        os.link(self.tree/'small.txt', self.tree/'shared.txt')
        storage.scan(mode='quick', roots=[str(self.tree)])
        with storage.connect() as connection:
            quick = dict(connection.execute('SELECT * FROM nodes WHERE path=?', (str(self.tree),)).fetchone())
        self.assertEqual(quick['logical'], 24576)
        storage.scan(mode='deep', roots=[str(self.tree)])
        with storage.connect() as connection:
            latest = app.latest(connection)
            deep = dict(connection.execute('SELECT * FROM nodes WHERE scan=? AND path=?',
                                           (latest['id'],str(self.tree))).fetchone())
        self.assertEqual(deep['logical'],24576)
        self.assertEqual(deep['files'],3)
        self.assertLess(deep['allocated'],quick['allocated'])
        self.assertEqual(latest['status'],'complete')

    def test_folder_scan_preserves_other_snapshots(self):
        storage.scan(mode='quick',roots=[str(self.tree)])
        other=self.fixture/'other';other.mkdir();(other/'one.txt').write_bytes(b'o'*123)
        storage.scan(mode='quick',roots=[str(other)])
        with storage.connect() as connection:
            self.assertEqual(app.snapshot_for(connection,str(self.tree))['id'],1)
            self.assertEqual(app.snapshot_for(connection,str(other))['id'],2)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM scans').fetchone()[0],2)

    def test_external_state_and_install_paths_are_protected(self):
        self.assertFalse(cleanup.policy(str(storage.DATA))['allowed'])
        self.assertFalse(cleanup.policy(str(storage.DATA.parent))['allowed'])
        self.assertFalse(cleanup.policy(str(config.ASSETS))['allowed'])
        self.assertFalse(cleanup.policy('C:\\Users')['allowed'])
        self.assertFalse(cleanup.policy('C:\\Windows')['allowed'])

    def test_stale_review_manifest_changes(self):
        before=cleanup.inspect_tree(str(self.tree))['fingerprint']
        (self.tree/'new.txt').write_bytes(b'new')
        after=cleanup.inspect_tree(str(self.tree))['fingerprint']
        self.assertNotEqual(before,after)

    def test_foreign_database_is_refused_without_modification(self):
        import sqlite3
        with sqlite3.connect(storage.DB) as connection:
            connection.execute('CREATE TABLE unrelated(value TEXT)')
        connection.close()
        before=storage.DB.read_bytes()
        with self.assertRaises(ValueError): storage.validate_database()
        self.assertEqual(before,storage.DB.read_bytes())

    def test_csv_text_cannot_become_a_spreadsheet_formula(self):
        for value in ['=1+1','+SUM(A1)','-cmd','@SUM(A1)',' \t=HYPERLINK("x")']:
            self.assertTrue(app.csv_value(value).startswith("'"))
        self.assertEqual(app.csv_value('C:\\Users\\example'),'C:\\Users\\example')
        self.assertEqual(app.csv_value(-12),-12)

class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture=Path(tempfile.mkdtemp(dir=FIXTURE.name))
        storage.DATA=fixture/'state';storage.DATA.mkdir()
        storage.DB=storage.DATA/'storage.sqlite3';storage.PROGRESS=storage.DATA/'progress.json'
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)

    def request(self,path,method='GET',headers=None,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        supplied={'X-StorageLens-Session':config.SESSION,**(headers or {})}
        connection.request(method,path,body=body,headers=supplied)
        response=connection.getresponse();content=response.read();code=response.status;connection.close()
        return code,content

    def test_health_and_empty_device_are_real_states(self):
        code,body=self.request('/api/health')
        self.assertEqual(code,200);self.assertTrue(json.loads(body)['ready'])
        self.assertEqual(json.loads(body)['platform'],'windows')
        code,body=self.request('/api/summary')
        self.assertEqual(code,200);self.assertIsNone(json.loads(body)['scan'])
        self.assertEqual(self.request('/api/apps')[0],409)

    def test_session_host_origin_and_cross_site_denial(self):
        for headers in [{'X-StorageLens-Session':''},{'Host':'other.example'},
                        {'Origin':'https://other.example'},{'Sec-Fetch-Site':'cross-site'}]:
            with self.subTest(headers=list(headers)):
                self.assertEqual(self.request('/api/summary',headers=headers)[0],403)

    def test_private_files_and_unknown_routes_are_not_served(self):
        for path in ['/inventory.json','/.data/storage.sqlite3','/../../inventory.json','/missing']:
            self.assertEqual(self.request(path)[0],404)

    def test_native_cookie_and_post_guards(self):
        self.assertEqual(self.request('/',headers={'X-StorageLens-Session':'',
            'Cookie':'StorageLensSession='+config.SESSION})[0],200)
        self.assertEqual(self.request('/',headers={'Cookie':'StorageLensSession=one; StorageLensSession='+config.SESSION})[0],403)
        self.assertEqual(self.request('/api/cancel-scan','POST',body=b'{}')[0],403)
        self.assertEqual(self.request('/api/cancel-scan','POST',body=b'{}',headers={
            'X-StorageLens-Token':app.TOKEN,'Content-Length':'-1'})[0],413)
        self.assertEqual(self.request('/api/scan','POST',body=b'{"mode":"invalid"}',headers={
            'X-StorageLens-Token':app.TOKEN})[0],400)

if __name__=='__main__':
    try: unittest.main()
    finally: FIXTURE.cleanup()
