import { formatMoney, moneyToFen } from './reward-rules.js'

export const rewardTemplates = [
  {label:'🎠 门票奖励',name:'木马王国门票券',icon:'🎠',price:1,cash_price:'39.90',description:'和家长约定游玩日期，由家长确认后购买门票。'},
  {label:'⌚ 手表充值',name:'小天才充值券',icon:'⌚',price:1,cash_price:'39.90',description:'向双方认可的小天才手表账户充值 39.90 元，由家长操作。'},
  {label:'🧸 自选玩具',name:'自选玩具兑换奖励',icon:'🧸',price:2,cash_price:'',description:'和家长一起挑选玩具，实际价格及差额由家长确认。'},
]
export const blankReward = () => ({name:'',description:'',icon:'🎁',price:1,cash_price:'',image_data:'',active:false})
export const editReward = item => ({...item,active:!!item.active,image_data:item.image_data || '',cash_price:item.cash_price_fen == null ? '' : formatMoney(item.cash_price_fen)})
export function rewardPayload(draft, active) {
  const name = draft.name.trim(), icon = draft.icon.trim() || '🎁'
  if (!name || name.length > 80) throw new Error('请填写 1–80 字的奖励名称')
  if (draft.description.length > 500 || icon.length > 20) throw new Error('兑换说明最多 500 字，图标最多 20 字符')
  if (!Number.isSafeInteger(draft.price) || draft.price < 1 || draft.price > 5) throw new Error('每份奖励需要 1–5 张通用兑换券')
  const text = String(draft.cash_price ?? '').trim()
  const cash = text ? moneyToFen(text) : null
  if (text && cash == null) throw new Error('参考金额须为有效人民币金额，最多两位小数')
  return {name,description:draft.description.trim(),icon,price:draft.price,cash_price_fen:cash,image_data:draft.image_data || '',active:!!active}
}
export function filterRewards(items, search, status) {
  const term = search.trim().toLocaleLowerCase()
  return items.filter(item => (status === 'all' || !!item.active === (status === 'active'))
    && (!term || `${item.name} ${item.description}`.toLocaleLowerCase().includes(term)))
}

export async function compressRewardImage(file) {
  if (!['image/jpeg','image/png','image/webp'].includes(file.type)) throw new Error('请选择 JPG、PNG 或 WebP 图片，不支持 SVG 或 HEIC')
  if (!file.size || file.size > 5_000_000) throw new Error('原图需小于 5MB，请先在手机中缩小图片')
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    if (!image.naturalWidth || image.naturalWidth * image.naturalHeight > 20_000_000) throw new Error('图片尺寸过大，请先缩小后再上传')
    const scale = Math.min(1,512 / Math.max(image.naturalWidth,image.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1,Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1,Math.round(image.naturalHeight * scale))
    const context = canvas.getContext('2d')
    if (!context) throw new Error('当前浏览器无法处理图片，请更换浏览器或使用图标')
    context.fillStyle = '#ffffff'; context.fillRect(0,0,canvas.width,canvas.height)
    context.drawImage(image,0,0,canvas.width,canvas.height)
    for (const quality of [0.82,0.65,0.48,0.35]) {
      const data = canvas.toDataURL('image/jpeg',quality)
      if (data.startsWith('data:image/jpeg;base64,') && data.length <= 128_023) return data
    }
    throw new Error('图片压缩后仍过大，请选择更简单的图片')
  } catch (error) {
    if (error.name === 'EncodingError') throw new Error('图片无法读取，请重新选择一张图片')
    throw error
  } finally { URL.revokeObjectURL(url) }
}
