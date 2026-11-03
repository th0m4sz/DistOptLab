"""Regresiones de comunicación: rondas exactas, caché libre y descarga incremental."""
import io
from pathlib import Path,PurePosixPath
import tempfile
import threading
from types import SimpleNamespace
import unittest

from lab.network import RoundExchange,SnapshotStore,ProtocolError,serve
from lab.transport import Latest
from lab.remote_runner import collect


class TransportPerformanceTests(unittest.TestCase):
    def runtime(self):
        return SimpleNamespace(fingerprint='cfg',steps=20,neighbors={1:{2:1}},
            nodes={2:dict(host='127.0.0.1',port=1)},check_received_state=lambda i,s:dict(s),
            fault_plan=SimpleNamespace(enabled=False))

    def test_published_round_rejects_wrong_run_and_undeclared_neighbor(self):
        store=RoundExchange(self.runtime(),1,'run')
        message=dict(protocol=3,config='cfg',run='run',**{'from':2},round=0,state={'x':2})
        try:
            for changed in [dict(run='another-run'),{'from':3},dict(round=-1)]:
                with self.assertRaises(ProtocolError):store.respond(dict(message,**changed))
            self.assertEqual(store.history,{2:{}})
        finally:store.close()

    def test_neighbor_cannot_change_an_already_published_round(self):
        store=RoundExchange(self.runtime(),1,'run')
        message=dict(protocol=3,config='cfg',run='run',**{'from':2},round=0,state={'x':2})
        try:
            store.respond(message);store.respond(message)  # A reconnect may replay the same value.
            self.assertEqual(store.fetch(0,.1),{2:{'x':2}})
            store.respond(dict(message,state={'x':3}))
            with self.assertRaises(ProtocolError):store.fetch(0,.1)
        finally:store.close()

    def test_missing_sync_round_times_out_and_wait_can_be_cancelled(self):
        store=RoundExchange(self.runtime(),1,'run')
        try:
            store.respond(dict(protocol=3,config='cfg',run='run',**{'from':2},round=0,state={'x':2}))
            with self.assertRaises(TimeoutError):store.fetch(1,.01)
            def stopped():raise InterruptedError('stopped')
            with self.assertRaises(InterruptedError):store.fetch(1,1,stopped)
            self.assertEqual(store.fetch(0,.1),{2:{'x':2}})
        finally:store.close()

    def test_published_sync_rounds_are_exact_and_wait_for_the_next_round(self):
        from lab.runner import allocate_ports
        ports=allocate_ports(2)
        rt=SimpleNamespace(fingerprint='cfg',steps=20,neighbors={1:{2:1},2:{1:1}},
            nodes={i:dict(host='127.0.0.1',port=ports[i-1]) for i in [1,2]},
            fault_plan=SimpleNamespace(enabled=False),check_received_state=lambda i,s:dict(s))
        a,b=RoundExchange(rt,1,'run'),RoundExchange(rt,2,'run')
        servers=[serve(a,'127.0.0.1'),serve(b,'127.0.0.1')]
        thread=None
        try:
            a.publish(0,{'x':1});b.publish(0,{'x':2})
            self.assertEqual(a.fetch(0,2),{2:{'x':2}})
            result=[];thread=threading.Thread(target=lambda:result.append(a.fetch(1,2)))
            thread.start();thread.join(.025);self.assertTrue(thread.is_alive())
            b.publish(1,{'x':9});thread.join(2)
            self.assertEqual(result,[{2:{'x':9}}])
        finally:
            a.close();b.close()
            if thread:thread.join(2)
            for server in servers:server.shutdown();server.server_close()

    def test_sync_request_wakes_on_requested_publication(self):
        store=SnapshotStore(self.runtime(),1,'run');store.publish(0,{'x':0})
        request=dict(protocol=1,config='cfg',run='run',**{'from':2},round=1)
        result=[];thread=threading.Thread(target=lambda:result.append(store.respond(request)))
        thread.start()
        try:
            thread.join(.025);self.assertTrue(thread.is_alive())
            store.publish(1,{'x':9});thread.join(1)
            self.assertEqual(result[0]['round'],1);self.assertEqual(result[0]['state'],{'x':9})
        finally:thread.join(1)

    def test_async_receiver_waits_for_publication_without_locking_publisher(self):
        endpoint=Latest(self.runtime(),1,'run');endpoint.publish(0,{'x':4})
        request=dict(protocol=2,config='cfg',run='run',**{'from':2},after_version=0)
        result=[];thread=threading.Thread(target=lambda:result.append(endpoint.respond(request)))
        thread.start()
        try:
            thread.join(.025);self.assertTrue(thread.is_alive())
            endpoint.publish(1,{'x':8});thread.join(1)
            self.assertEqual(result[0]['version'],1);self.assertEqual(result[0]['state'],{'x':8})
        finally:thread.join(1)

    def test_unchanged_async_value_returns_after_bounded_idle_wait(self):
        endpoint=Latest(self.runtime(),1,'run');endpoint.publish(0,{'x':4})
        result=[]
        thread=threading.Thread(target=lambda:result.append(endpoint.respond(dict(protocol=2,config='cfg',run='run',**{'from':2},after_version=0))))
        thread.start();thread.join(1)
        self.assertFalse(thread.is_alive());self.assertEqual(result[0]['state'],{'x':4})

    def test_incremental_log_keeps_partial_record_and_reads_only_new_bytes(self):
        content=[b'{"x":1}\n{"x":']
        class SFTP:
            def stat(self,*args):return SimpleNamespace(st_size=len(content[0]))
            def open(self,*args):return io.BytesIO(content[0])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);stats={}
            collect(SFTP(),PurePosixPath('/run'),folder,['log.jsonl'],incremental=True,stats=stats)
            self.assertEqual((folder/'log.jsonl').read_bytes(),b'{"x":1}\n')
            before=stats['received_bytes'];content[0]+=b'2}\n'
            collect(SFTP(),PurePosixPath('/run'),folder,['log.jsonl'],incremental=True,stats=stats)
            self.assertEqual((folder/'log.jsonl').read_bytes(),content[0])
            self.assertEqual(stats['received_bytes']-before,len(b'{"x":2}\n'))
            collect(SFTP(),PurePosixPath('/run'),folder,['log.jsonl'],incremental=True,stats=stats)
            self.assertEqual(stats['received_bytes']-before,len(b'{"x":2}\n'))
            content[0]=b''
            with self.assertRaises(ValueError):collect(SFTP(),PurePosixPath('/run'),folder,['log.jsonl'],incremental=True)


if __name__=='__main__':unittest.main()
