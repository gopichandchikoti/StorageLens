"""Relocation tests touch only owned personal-file and destination fixtures."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Web'))
import cleanup
import relocation as move
import native_files
import storage

@unittest.skipUnless(os.name=='nt','Windows copy and metadata APIs')
class MoveTests(unittest.TestCase):
    def setUp(self):
        documents=Path.home()/'Documents'
        if not documents.is_dir():self.skipTest('Personal Documents folder is unavailable')
        alternatives=[v['drive']+'\\' for v in storage.volumes() if v['drive']!=str(documents)[:2]]
        if not alternatives:self.skipTest('Cross-drive tests require two connected local volumes')
        self.sourceBase=Path(tempfile.mkdtemp(prefix='StorageLensMoveTest-',dir=documents))
        self.destination=Path(tempfile.mkdtemp(prefix='StorageLensMoveTest-',dir=alternatives[0]))
        self.state=Path(tempfile.mkdtemp(prefix='move-state-',dir=ROOT/'work'))
        self.priorData=storage.DATA;storage.DATA=self.state
        self.source=self.sourceBase/'Music export';self.source.mkdir()
        (self.source/'song.txt').write_bytes(b'original personal-file fixture'*1024)
        with open(str(self.source/'song.txt')+':Zone.Identifier','wb') as stream:stream.write(b'[ZoneTransfer]\r\nZoneId=3\r\n')
        self.recovery=self.sourceBase/'test-recovery';self.recovery.mkdir()
        with move._guard:move._current=None;move._tickets.clear()
        self.recycled=[]
        def recycle_owned(path):
            # The fake only substitutes the existing Shell recycle API, after real
            # CopyFileEx + SHA verification. Retain originals in an owned recovery folder.
            self.assertTrue(move._current['copiesVerified'])
            self.assertTrue(Path(path).resolve().is_relative_to(self.sourceBase.resolve()))
            target=self.recovery/Path(path).name
            os.rename(path,target);self.recycled.append(path)
            return {'recycled':True}
        self.recycler=patch.object(cleanup,'native_recycle',side_effect=recycle_owned)
        self.recycler.start()

    def tearDown(self):
        if not hasattr(self,'recycler'):return
        self.recycler.stop()
        self.assertFalse(move.status().get('active'))
        storage.DATA=self.priorData
        for path in [self.sourceBase,self.destination,self.state]:
            self.assertTrue(path.name.startswith(('StorageLensMoveTest-','move-state-')))
            self.assertGreater(len(path.parts),1)
            shutil.rmtree(path)
        with move._guard:move._current=None;move._tickets.clear()

    def review(self,paths=None,name='New media'):
        return move.preview(paths or [str(self.source)],str(self.destination),name)

    def finish(self,ticket):
        move.start(ticket,'MOVE')
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            result=move.status()
            if not result['active']:return result
            time.sleep(.01)
        move.cancel();self.fail('Owned transfer did not finish within its test deadline')

    def test_verified_cross_drive_copy_preserves_named_streams_then_recycles(self):
        review=self.review();expected=(self.source/'song.txt').read_bytes()
        result=self.finish(review['ticket'])
        self.assertEqual(result['status'],'complete')
        target=Path(review['destination'])/self.source.name/'song.txt'
        self.assertEqual(target.read_bytes(),expected)
        self.assertEqual(Path(str(target)+':Zone.Identifier').read_bytes(),b'[ZoneTransfer]\r\nZoneId=3\r\n')
        self.assertFalse(self.source.exists());self.assertTrue((self.recovery/self.source.name).exists())
        self.assertEqual(result['immediateSpaceFreed'],0)
        self.assertEqual(move.history()[0]['recycled'],[str(self.source)])
        with self.assertRaises(move.MoveError):move.start(review['ticket'],'MOVE')

    def test_expired_wrong_confirmation_and_existing_targets_do_not_move(self):
        review=self.review()
        with self.assertRaises(move.MoveError):move.start(review['ticket'],'move')
        with move._guard:move._tickets[review['ticket']]['expires']=0
        with self.assertRaises(move.MoveError):move.start(review['ticket'],'MOVE')
        (self.destination/'Already here').mkdir()
        with self.assertRaises(move.MoveError):self.review(name='Already here')
        self.assertTrue(self.source.exists());self.assertEqual(self.recycled,[])

    def test_changed_source_and_destination_fail_without_recycling(self):
        for changed in ['source','destination']:
            with self.subTest(changed=changed):
                review=self.review(name=changed)
                if changed=='source':(self.source/'added.txt').write_text('new content')
                else:(self.destination/changed).mkdir()
                result=self.finish(review['ticket'])
                self.assertEqual(result['status'],'failed');self.assertTrue(self.source.exists())
                self.assertEqual(self.recycled,[])

    def test_copy_corruption_does_not_recycle_original(self):
        review=self.review();original=native_files.copy
        def corrupt(source,destination,report,cancelled):
            original(source,destination,report,cancelled)
            with open(destination,'wb') as stream:stream.write(b'corrupt')
        with patch.object(native_files,'copy',side_effect=corrupt):result=self.finish(review['ticket'])
        self.assertEqual(result['status'],'failed');self.assertFalse(result['copiesVerified'])
        self.assertTrue(self.source.exists());self.assertEqual(self.recycled,[])

    def test_cancellation_preserves_original_and_copy_history(self):
        review=self.review();entered=threading.Event();release=threading.Event();original=native_files.copy
        def held(source,destination,report,cancelled):
            entered.set();release.wait(5);return original(source,destination,report,cancelled)
        with patch.object(native_files,'copy',side_effect=held):
            move.start(review['ticket'],'MOVE');self.assertTrue(entered.wait(5))
            with self.assertRaises(move.MoveError):self.review(name='Concurrent')
            with self.assertRaises(move.MoveError):move.start('other-ticket','MOVE')
            move.cancel();release.set()
            deadline=time.monotonic()+10
            while move.status()['active'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(move.status()['status'],'cancelled')
        self.assertTrue(self.source.exists());self.assertEqual(self.recycled,[])

    def test_space_overlaps_same_drive_and_reserved_names_are_rejected(self):
        with self.assertRaises(move.MoveError):self.review([str(self.source),str(self.source/'song.txt')])
        with self.assertRaises(move.MoveError):move.preview([str(self.source)],str(self.sourceBase),'Other')
        for name in ['..','CON','bad/name','trailing.']:
            with self.assertRaises(move.MoveError):self.review(name=name)
        usage=shutil.disk_usage(self.destination)
        with patch.object(shutil,'disk_usage',return_value=type(usage)(usage.total,usage.used,0)):
            with self.assertRaises(move.MoveError):self.review()
        self.assertTrue(self.source.exists());self.assertEqual(self.recycled,[])

    def test_projects_state_and_hard_links_are_protected(self):
        for path in [storage.DATA,ROOT/'Web',self.sourceBase.parent,Path(os.environ['WINDIR'])]:
            with self.assertRaises(move.MoveError):move.source_policy(str(path))
        (self.source/'.git').mkdir()
        with self.assertRaises(move.MoveError):self.review()
        (self.source/'.git').rmdir()
        os.link(self.source/'song.txt',self.source/'shared.txt')
        with self.assertRaises(move.MoveError):self.review()

    def test_restart_marks_unfinished_journal_interrupted(self):
        record=dict(id='owned-test',active=True,status='running',sources=[str(self.source)],destination=str(self.destination),recycled=[])
        move._save(record)
        self.assertEqual(move.status()['status'],'interrupted')
        self.assertFalse(move.status()['active']);self.assertTrue(self.source.exists())

    def test_native_copy_rejects_dangling_destination_link(self):
        escape=self.state/'must-not-be-created.txt';link=self.destination/'existing-link.txt'
        try:os.symlink(escape,link)
        except OSError:self.skipTest('Unprivileged symbolic-link creation is unavailable')
        with self.assertRaises(OSError):
            native_files.copy(self.source/'song.txt',link,lambda n:None,threading.Event())
        self.assertFalse(escape.exists())

if __name__=='__main__':unittest.main()
