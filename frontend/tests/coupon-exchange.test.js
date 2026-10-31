import test from 'node:test'
import assert from 'node:assert/strict'
import { couponBadgeChoices, couponSelection, isCouponRequestPage } from '../src/coupon-exchange.js'

const badges = [
  {id:1,code:'sports',name:'体育徽章',active:1,colors:[{color:'#4eb478',count:12,available_count:3},{color:'#d4af37',count:2,available_count:2}]},
  {id:3,code:'fire',name:'预留徽章',active:0,colors:[{color:'#4eb478',count:5,available_count:5}]},
]
test('Child coupon choices use current unspent counts and exclude inactive badges', () => {
  const choices = couponBadgeChoices(badges)
  assert.equal(choices.length,2)
  assert.equal(choices[0].available,3)
  assert.equal(couponSelection(choices,{[choices[0].key]:3,[choices[1].key]:2}).valid,true)
  assert.equal(couponSelection(choices,{[choices[0].key]:5}).valid,false)
  for (const count of [0,-1,1.5,'5',NaN]) assert.equal(couponSelection(choices,{[choices[0].key]:count}).valid,false)
  assert.equal(couponSelection(choices,{[choices[0].key]:3,[choices[1].key]:2,'missing':1}).valid,false)
})
test('Malformed coupon approvals cannot enable action buttons', () => {
  const entry = {id:1,status:'pending',can_approve:true,requested_at:'2026-10-24T08:00:00Z',selections:[{badge_id:1,name:'体育徽章',code:'sports',color:'#4eb478',count:5}]}
  const page = {items:[entry],total:1,has_more:false,next_before_id:null,pending_count:1}
  assert.equal(isCouponRequestPage(page),true)
  for (const changed of [{status:'bad'},{can_approve:'yes'},{selections:[]},{selections:[{...entry.selections[0],count:4}]}]) assert.equal(isCouponRequestPage({...page,items:[{...entry,...changed}]}),false)
})
