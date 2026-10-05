"""Malformed editor input must refuse without mutating an approved lesson."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from brambleloop.core.db import Database
from brambleloop.learn import service, api
from brambleloop.learn.models import Lesson, LearnGap
from test_learn_launch import spec

class MalformedInputTests(unittest.TestCase):
    def setUp(self):
        self.db=Database('sqlite:///:memory:',scratch=True);self.db.create_all()
        with self.db.session() as s:
            s.add(LearnGap(topic='stitch:sc',evidence=[{'fixture':'local source premise'}]))
        self.revision=service.save_lesson(self.db,'single-crochet',spec())
        service.review_lesson(self.db,'single-crochet',self.revision,'independent-fixture',
            dict.fromkeys(service.DIMENSIONS,'PASS'),'test-only human attestation premise')
    def tearDown(self): self.db.engine.dispose()
    def snapshot(self):
        with self.db.session() as s:
            row=s.get(Lesson,'single-crochet')
            return copy.deepcopy((row.revision,row.spec,row.reviews,row.state))
    def test_null_and_malformed_shapes_raise_valueerror_preserve_review(self):
        before=self.snapshot()
        values=[None,[], 'text']
        for field in ('assumptions','assets','steps'):
            for value in (None,7,'text',[None],['text']):
                item=spec();item[field]=value;values.append(item)
        for field in ('assets','steps'):
            item=spec();item[field]=[{'instruction':['not prose']}];values.append(item)
        for value in values:
            with self.assertRaises(ValueError): service.save_lesson(self.db,'single-crochet',value)
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(service.approved_lesson(self.db,'single-crochet')['revision'],self.revision)
    def test_real_draft_endpoint_maps_malformed_shapes_to422(self):
        endpoint=next(r.endpoint for r in api.router(self.db).routes if 'PUT' in r.methods)
        before=self.snapshot()
        # Authentication is an explicit isolated premise; invoke actual endpoint/service without network.
        with patch.object(api,'_editor',return_value=None):
            for field,value in [('assumptions',None),('assets',[None]),('steps',['bad'])]:
                item=spec();item[field]=value
                with self.assertRaises(HTTPException) as result:
                    endpoint('single-crochet',item,authorization='test-only')
                self.assertEqual(result.exception.status_code,422)
                self.assertEqual(self.snapshot(),before)
    def test_valid_draft_preserves_existing_approval_semantics(self):
        item=spec();item['learner_problem']='work a revised single crochet lesson'
        revision=service.save_lesson(self.db,'single-crochet',item)
        self.assertNotEqual(revision,self.revision)
        self.assertIsNone(service.approved_lesson(self.db,'single-crochet'))
        with self.db.session() as s:
            row=s.get(Lesson,'single-crochet');self.assertEqual(row.state,'DRAFT');self.assertEqual(row.reviews,[])
if __name__=='__main__': unittest.main()
