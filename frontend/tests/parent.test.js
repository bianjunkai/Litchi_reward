import test from 'node:test'
import assert from 'node:assert/strict'
import {adjustmentPreview,isParentPage,isReviewPage,isReversalPreview,parentQuery,signed} from '../src/parent.js'

const assets = [{code:'study_star',balance:3,active:true},{code:'gold_star',balance:0,active:false}]
test('Parent adjustments require a meaningful reason and never preview negative balances', () => {
  assert.deepEqual(adjustmentPreview(assets,{asset_code:'study_star',delta:-2,reason:'误发扣回'}), {valid:true,asset:assets[0],after:1})
  for (const delta of [0,-4,1.5,1000,NaN]) assert.equal(adjustmentPreview(assets,{asset_code:'study_star',delta,reason:'纠错'}).valid,false)
  assert.equal(adjustmentPreview(assets,{asset_code:'study_star',delta:1,reason:'  '}).valid,false)
  assert.equal(adjustmentPreview(assets,{asset_code:'gold_star',delta:1,reason:'纠错'}).valid,false)
  assert.equal(adjustmentPreview(assets,{asset_code:'missing',delta:1,reason:'纠错'}).valid,false)
})
test('Parent history query encodes literal searches and keyset cursors', () => {
  const params = new URLSearchParams(parentQuery({view:'ledger',search:'%_#家庭',from_date:'2026-10-19',to_date:''},42))
  assert.equal(params.get('search'),'%_#家庭'); assert.equal(params.get('before_id'),'42')
  assert.equal(params.get('from_date'),'2026-10-19'); assert.equal(params.has('to_date'),false)
  assert.equal(params.get('limit'),'20'); assert.equal(signed(-2),'-2'); assert.equal(signed(2),'+2')
})
test('Parent history pages reject unsafe ids, invalid totals and non-progressing cursors', () => {
  const valid = {items:[{id:5},{id:3}],total:4,has_more:true,next_before_id:3}
  assert.equal(isParentPage(valid),true)
  for (const changes of [{items:[{id:3},{id:5}]},{items:[{id:3},{id:3}]},{total:1},{total:-1},{next_before_id:5},{has_more:false},{items:[{id:0}]}]) assert.equal(isParentPage({...valid,...changes}),false)
  assert.equal(isParentPage({...valid,has_more:false,next_before_id:null}),true)
})
test('Malformed review balances or unsafe reversal previews never enable financial confirmations', () => {
  const page = {items:[],total:0,has_more:false,next_before_id:null,coupon_balance:0,counts:{pending:0,approved:0,rejected:0,reversed:0}}
  assert.equal(isReviewPage(page),true)
  assert.equal(isReviewPage({...page,coupon_balance:undefined}),false)
  assert.equal(isReviewPage({...page,coupon_balance:-1}),false)
  const preview = {operation:{id:1},can_reverse:true,blockers:[],assets:[{code:'coupon',before:2,delta:-1,after:1}],badges_remove:[],badges_restore:[]}
  assert.equal(isReversalPreview(preview,1),true)
  assert.equal(isReversalPreview(preview,2),false)
  assert.equal(isReversalPreview({...preview,blockers:['徽章已使用']},1),false)
  assert.equal(isReversalPreview({...preview,assets:[{code:'coupon',before:0,delta:-1,after:-1}]},1),false)
  assert.equal(isReversalPreview({...preview,can_reverse:false,blockers:['余额不足'],assets:[{code:'coupon',before:0,delta:-1,after:-1}]},1),true)
})
