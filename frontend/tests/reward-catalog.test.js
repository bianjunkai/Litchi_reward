import test from 'node:test'
import assert from 'node:assert/strict'
import { blankReward, editReward, filterRewards, rewardPayload, rewardTemplates } from '../src/reward-catalog.js'
import { productQuote } from '../src/shop.js'

test('Reward templates create catalogue entries, not financial asset grants', () => {
  assert.equal(blankReward().active,false)
  for (const template of rewardTemplates) {
    const payload = rewardPayload({...blankReward(),...template},true)
    assert.ok(payload.price >= 1 && payload.price <= 5)
    assert.equal(payload.active,true)
    assert.equal('asset_code' in payload,false)
    assert.equal('delta' in payload,false)
  }
})
test('Reward form uses exact fen, preserves images and trims names', () => {
  const image = 'data:image/png;base64,test'
  const draft = {...blankReward(),name:' 门票券 ',cash_price:'39.9',image_data:image}
  const payload = rewardPayload(draft,true)
  assert.equal(payload.name,'门票券'); assert.equal(payload.cash_price_fen,3990)
  assert.equal(payload.image_data,image)
  assert.equal(rewardPayload({...draft,cash_price:''},false).cash_price_fen,null)
  assert.equal(editReward({...payload,id:4}).cash_price,'39.90')
  assert.equal(editReward({...payload,cash_price_fen:null}).cash_price,'')
})
test('Blank rewards, out-of-range coupon counts and invalid money are blocked before publish', () => {
  const draft = {...blankReward(),name:'门票券'}
  for (const change of [{name:' '},{price:0},{price:6},{price:1.5},{price:'1'},{cash_price:'39.999'},{cash_price:'-1'},{description:'字'.repeat(501)}]) assert.throws(()=>rewardPayload({...draft,...change},true))
})
test('Management filters retain unlisted rewards instead of deleting them', () => {
  const listed = {...blankReward(),id:1,name:'门票券',active:1}
  const draft = {...blankReward(),id:2,name:'充值券',active:0}
  assert.deepEqual(filterRewards([listed,draft],'','all'),[listed,draft])
  assert.deepEqual(filterRewards([listed,draft],'','inactive'),[draft])
  assert.deepEqual(filterRewards([listed,draft],' 门票 ','active'),[listed])
})
test('Child confirmation includes the displayed image but never submits publication controls', () => {
  const product = {...blankReward(),id:1,name:'门票券',image_data:'image',cash_price_fen:3990,active:true}
  const quote = productQuote(product)
  assert.equal(quote.image_data,'image'); assert.equal(quote.cash_price_fen,3990)
  assert.equal('active' in quote,false); assert.equal('id' in quote,false)
})
