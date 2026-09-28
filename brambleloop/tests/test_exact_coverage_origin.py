"""Local exact-origin controls; no provider or certification gate is bypassed as proof."""
import copy
import unittest
from brambleloop.core.db import Database, Base
from brambleloop.core.models import CoverageGap, MjsMissionEvent
from brambleloop.intel import coverage, mission_runtime
from brambleloop.creative import intake, concept

class OriginTests(unittest.TestCase):
    def setUp(self):
        self.db=Database('sqlite:///:memory:',scratch=True)
        Base.metadata.create_all(self.db.engine)
        self.a=coverage.upsert(self.db,benchmark_key='a',arena='coverage-a',pod='blankets')
        self.b=coverage.upsert(self.db,benchmark_key='b',arena='coverage-b',pod='blankets')
        with self.db.session() as s:
            ev=MjsMissionEvent(benchmark_key='b',listing_ref='listing-b',fingerprint='f'*64,
                pod='blankets',arena='mission-topic',tournament_job_id=17)
            s.add(ev);s.flush();self.event=ev.id
        gid,state,origin=mission_runtime.coverage_target(self.db,key='b',pod='blankets',event_id=self.event,fp='f'*64)
        with self.db.session() as s:
            ev=s.get(MjsMissionEvent,self.event);ev.gap_id=gid;ev.steps={'coverage':{'gap':gid,'origin':origin}}
        self.origin=intake.coverage_origin(self.db,event_id=self.event,pod='blankets',product_slug='product-b',candidate_key='candidate-b',job_id=17)
    def tearDown(self): self.db.engine.dispose()
    def advance(self,origin=None,**kw):
        args=dict(event_id=self.event,candidate_key='candidate-b',product_slug='product-b')
        args.update(kw)
        return intake.advance_gap(self.db,'blankets','certified',reason='local stage evidence premise',origin=self.origin if origin is None else origin,**args)
    def states(self):
        with self.db.session() as s:
            return [(s.get(CoverageGap,i).state,s.get(CoverageGap,i).product_slug) for i in (self.a,self.b)]
    def test_producer_brief_payload_consumer(self):
        c=concept.Concept(key='candidate-b',title='test',premise='A patterned blanket with a distinctive woven border',pod='blankets',
            form=next(iter(concept.FORMS)),construction=next(iter(concept.CONSTRUCTIONS)),motif='waves',palette_story='blue',
            recipient=next(iter(concept.RECIPIENTS)),occasion=next(iter(concept.OCCASIONS)),feeling=next(iter(concept.FEELINGS)),
            function='warmth',make_lane=next(iter(concept.MAKE_LANES)))
        payload=intake._payload(c,{'source_context':{'coverage_origin':self.origin}},source='test',original_key=c.key,mjs_event_id=self.event,pod=c.pod)
        # JSON transport is the same durable brief shape consumed by regate and pipeline.
        import json
        origin=json.loads(json.dumps(payload))['brief']['source_context']['coverage_origin']
        self.assertEqual(origin['coverage_arena'],'coverage-b')
        self.assertEqual(origin['mission_arena'],'mission-topic')
        self.assertTrue(self.advance(origin)['moved'])
        self.assertEqual(self.states(),[('uncovered',''),('certified','product-b')])
    def test_no_origin_no_mutation(self):
        result=intake.advance_gap(self.db,'blankets','certified',reason='missing',product_slug='product-b')
        self.assertEqual(result['verdict'],'UNKNOWN');self.assertEqual(self.states(),[('uncovered',''),('uncovered','')])
    def test_identity_tampering(self):
        for key in self.origin:
            bad={**self.origin,key:'wrong'}
            self.assertEqual(self.advance(bad)['verdict'],'UNKNOWN',key)
        self.assertEqual(self.states(),[('uncovered',''),('uncovered','')])
    def test_wrong_candidate_or_event_consumer(self):
        self.assertEqual(self.advance(candidate_key='other')['verdict'],'UNKNOWN')
        self.assertEqual(self.advance(event_id=self.event+1)['verdict'],'UNKNOWN')
        self.assertIsNone(intake.coverage_origin(self.db,event_id=self.event,pod='blankets',product_slug='product-b',candidate_key='candidate-b',job_id=99))
    def test_ambiguous_producer_no_selection(self):
        coverage.upsert(self.db,benchmark_key='b',arena='another',pod='blankets')
        self.assertEqual(mission_runtime.coverage_target(self.db,key='b',pod='blankets',event_id=self.event,fp='f'*64),(None,None,None))
    def test_changed_event_or_existing_product_refuses(self):
        with self.db.session() as s: s.get(CoverageGap,self.b).product_slug='other-product'
        self.assertEqual(self.advance()['verdict'],'UNKNOWN')
        with self.db.session() as s:
            s.get(CoverageGap,self.b).product_slug='';s.get(MjsMissionEvent,self.event).fingerprint='changed'
        self.assertEqual(self.advance()['verdict'],'UNKNOWN')
        self.assertEqual(self.states(),[('uncovered',''),('uncovered','')])
    def test_actual_intake_carries_producer_origin(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        c=concept.Concept(key='candidate-b',title='test',premise='A patterned blanket with a distinctive woven border',pod='blankets',
            form=next(iter(concept.FORMS)),construction=next(iter(concept.CONSTRUCTIONS)),motif='waves',palette_story='blue',
            recipient=next(iter(concept.RECIPIENTS)),occasion=next(iter(concept.OCCASIONS)),feeling=next(iter(concept.FEELINGS)),
            function='warmth',make_lane=next(iter(concept.MAKE_LANES)))
        records=[];queued=[]
        ctx=SimpleNamespace(db=self.db,job=SimpleNamespace(id=17),
            audit=lambda *a,**kw: records.append(kw),
            enqueue=lambda *a,**kw: queued.append(a) or SimpleNamespace(id=23))
        brief={'motifs':['waves'],'wow_mechanism':'border','skill_level':'intermediate'}
        # Upstream gate clearance is an explicit fixture premise, not certification evidence.
        with patch.object(intake,'design_slug',return_value='product-b'), patch.object(intake,'judgement_for',return_value={}), \
             patch.object(intake,'_event_for',return_value=('',None,100)), patch.object(intake,'brief_for',return_value=brief), \
             patch.object(intake,'culture_domain',return_value=''), patch.object(intake,'funnel_verdict',return_value={'carried':True}), \
             patch('brambleloop.creative.ideation.pre_engineering_gate',return_value={'cleared_for_engineering':True,'verdict':{}}), \
             patch('brambleloop.creative.prototype.source_provenance',return_value=None), \
             patch('brambleloop.improve.roi.design_provenance',return_value={}), patch.object(intake,'response_lesson',return_value={}):
            result=intake.intake(ctx,candidate=SimpleNamespace(concept=c),plan={},source='test',mjs_event_id=self.event)
        self.assertEqual(result['coverage']['gap'],self.b)
        self.assertEqual(self.states(),[('uncovered',''),('engineering','product-b')])
        self.assertEqual(queued[0][2]['brief']['source_context']['coverage_origin'],self.origin)
        self.assertEqual(records[0]['detail']['brief']['source_context']['coverage_origin'],self.origin)
        from brambleloop.core.models import AuditLog
        from brambleloop.intel.response import PIPELINE_STAGES
        with self.db.session() as session:
            session.add(AuditLog(actor='local-control',action=intake.INTAKE_ACTION,
                artifact='product-b',detail=records[0]['detail']))
            ev=session.get(MjsMissionEvent,self.event)
            ev.observation_id=1;ev.proven=True;ev.seasonal={'target':{'event':'test'}}
            ev.steps={**ev.steps,'decomposition':{'mechanisms':['local-premise']}}
        # The runtime consumer and durable winner reader are real; stage proof is separately assumed.
        stages=[(name,True,'explicit local premise') for name in PIPELINE_STAGES[4:9]]
        with patch.object(mission_runtime,'_stage_evidence',return_value=stages), \
             patch.object(mission_runtime,'_tournament_ran_for',return_value=True):
            outcome=mission_runtime.advance_pipeline(self.db,event_ids=[self.event])
        self.assertEqual(outcome['events'][0]['coverage']['gap'],self.b)
        self.assertEqual(self.states(),[('uncovered',''),('certified','product-b')])
if __name__=='__main__': unittest.main()
