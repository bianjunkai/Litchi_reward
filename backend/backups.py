"""Validated logical backups. Credentials and live sessions are never exported."""
import json
import sqlite3
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from database import SCHEMA, utc_now
from product_images import validate_image
from reward_rules import (BADGE_CODES, BADGE_COLORS, COUPON_VALUE_FEN, MAX_COUPONS_PER_USE,
                          RULE_VERSION, STAR_CODES, normalize_legacy_data)

TABLES = ('children','asset_types','badges','products','tasks','operations','child_assets',
          'task_claims','child_badges','coupon_requests','coupon_request_badges','redemptions','ledger','audit_logs')


class BackupInput(BaseModel):
    version: int
    tables: dict[str,list[dict]]
    rules: dict[str,str]


def register_backups(app, get_db, parent, path, rules_model, read_rules, audit):
    def export_data(db):
        return {'version':3,'exported_at':utc_now(),
                'tables':{t:[dict(r) for r in db.execute(f'SELECT * FROM {t}')] for t in TABLES},
                'rules':{k:str(v) for k,v in read_rules(db).items()}}

    @app.get('/api/parent/backup')
    def backup(token=Depends(parent), db=Depends(get_db)):
        return JSONResponse(export_data(db),headers={'Content-Disposition':'attachment; filename="family-rewards.json"'})

    @app.post('/api/parent/restore')
    async def restore(request: Request, token=Depends(parent), db=Depends(get_db)):
        raw = await request.body()
        if len(raw)>8_000_000:
            raise HTTPException(413,'备份文件不能超过 8MB')
        try:
            payload = BackupInput.model_validate_json(raw)
            if payload.version in (1,2):
                payload.tables.setdefault('coupon_requests',[])
                payload.tables.setdefault('coupon_request_badges',[])
            if payload.version not in (1,2,3) or set(payload.tables)!=set(TABLES):
                raise ValueError('备份版本或数据表不匹配')
            for product in payload.tables['products']:
                product.setdefault('image_data', '')
                validate_image(product['image_data'])
            if payload.version==1:
                additions = {
                    'tasks':{'badge_color':None}, 'products':{'cash_price_fen':None},
                    'operations':{'rule_version':'legacy'},
                    'redemptions':{'coupon_value_fen':None,'coupons_used':None,'actual_amount_fen':None,
                        'parent_top_up_fen':None,'forfeited_fen':None,'quoted_amount_fen':None,
                        'settlement_note':'','rule_version':'legacy'},
                }
                for table, defaults in additions.items():
                    for row in payload.tables[table]:
                        for key,value in defaults.items():
                            row.setdefault(key,value)
                normalize_legacy_data(payload.tables)
                payload.rules.update(badge_ratio='5',badges_per_coupon='5',coupon_value_fen='3990',max_coupons_per_redemption='5')
            settings = rules_model(**payload.rules)
            if sum(len(rows) for rows in payload.tables.values())>100_000:
                raise ValueError('备份数据量过大')
            sandbox = sqlite3.connect(':memory:')
            try:
                sandbox.executescript(SCHEMA)
                for table in TABLES:
                    columns = [r[1] for r in sandbox.execute(f'PRAGMA table_info({table})')]
                    for row in payload.tables[table]:
                        if set(row)!=set(columns):
                            raise ValueError('备份字段不匹配')
                        sandbox.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",[row[c] for c in columns])
                if sandbox.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('备份包含损坏的关联记录')
                if not sandbox.execute('SELECT 1 FROM children WHERE id=1').fetchone():
                    raise ValueError('备份缺少家庭账户')
                codes = {r[0] for r in sandbox.execute('SELECT code FROM asset_types')}
                if not {'study_star','tidy_star','meal_star','gold_star','coupon'}.issubset(codes):
                    raise ValueError('备份缺少必要资产')
                if sandbox.execute('''SELECT 1 FROM child_assets ca LEFT JOIN ledger l ON l.child_id=ca.child_id AND l.asset_type_id=ca.asset_type_id
                    GROUP BY ca.child_id,ca.asset_type_id HAVING ca.balance!=COALESCE(SUM(l.delta),0)''').fetchone():
                    raise ValueError('备份资产与流水不一致')
                for table,column in [('child_assets','balance'),('ledger','delta'),('tasks','amount'),('products','price'),('redemptions','price')]:
                    if sandbox.execute(f"SELECT 1 FROM {table} WHERE typeof({column})!='integer'").fetchone():
                        raise ValueError('代币、徽章和兑换券数量必须为整数')
                if sandbox.execute("SELECT 1 FROM products WHERE cash_price_fen IS NOT NULL AND (typeof(cash_price_fen)!='integer' OR cash_price_fen<0 OR cash_price_fen>100000000)").fetchone():
                    raise ValueError('商品参考金额不合法')
                if sandbox.execute('SELECT 1 FROM products WHERE price<1 OR price>999').fetchone() or sandbox.execute('SELECT 1 FROM tasks WHERE amount<1 OR amount>99').fetchone():
                    raise ValueError('备份数值不合法')
                if sandbox.execute('SELECT 1 FROM redemptions WHERE price<1 OR price>999').fetchone() or sandbox.execute('SELECT 1 FROM badges WHERE threshold<1 OR threshold>100').fetchone():
                    raise ValueError('备份奖励规则不合法')
                if sandbox.execute("SELECT 1 FROM redemptions WHERE status NOT IN ('pending','approved','rejected','reversed')").fetchone():
                    raise ValueError('备份兑换状态不合法')
                for request_id,child_id,status,op_id in sandbox.execute('SELECT id,child_id,status,operation_id FROM coupon_requests'):
                    selected = sandbox.execute('''SELECT cb.child_id,cb.spent_operation_id FROM coupon_request_badges link
                        JOIN child_badges cb ON cb.id=link.child_badge_id WHERE link.request_id=?''',(request_id,)).fetchall()
                    if len(selected)!=5 or any(row[0]!=child_id for row in selected):
                        raise ValueError('换券申请必须关联同一个孩子的 5 枚徽章')
                    if status in ('approved','reversed'):
                        op = sandbox.execute('SELECT child_id,kind,reversed_at FROM operations WHERE id=?',(op_id,)).fetchone()
                        if not op or op[0]!=child_id or op[1]!='badges_to_coupon' or bool(op[2])!=(status=='reversed'):
                            raise ValueError('换券审批与记账操作不一致')
                        if status=='approved' and any(row[1]!=op_id for row in selected):
                            raise ValueError('换券审批与徽章扣除不一致')
                    elif op_id is not None:
                        raise ValueError('尚未批准的换券申请不能关联资产操作')
                life = sandbox.execute("SELECT threshold FROM badges WHERE code='life'").fetchone()
                if not life or life[0]!=settings.badge_ratio:
                    raise ValueError('生活徽章规则不一致')
                missing = sandbox.execute('''SELECT 1 FROM children c CROSS JOIN asset_types a LEFT JOIN child_assets ca
                    ON ca.child_id=c.id AND ca.asset_type_id=a.id WHERE ca.child_id IS NULL''').fetchone()
                if missing:
                    raise ValueError('备份资产账户不完整')
                if sandbox.execute("SELECT 1 FROM asset_types WHERE code='gold_star' AND active!=0").fetchone():
                    raise ValueError('金色代币尚未设置条件，不可启用')
                for task in sandbox.execute('''SELECT t.amount,t.badge_id,t.badge_color,a.code,b.code
                    FROM tasks t JOIN asset_types a ON a.id=t.asset_type_id LEFT JOIN badges b ON b.id=t.badge_id WHERE t.active=1'''):
                    amount,badge_id,color,asset_code,badge_code = task
                    if (not badge_id and (amount!=1 or asset_code not in STAR_CODES)) or (badge_id and badge_code not in ('sports','fire','royal')):
                        raise ValueError('任务奖励不符合日常代币／徽章规则')
                    if color is not None and color not in BADGE_COLORS:
                        raise ValueError('徽章颜色版本不合法')
                for code,color in sandbox.execute('SELECT code,color FROM badges WHERE active=1'):
                    if code not in BADGE_CODES or color not in BADGE_COLORS:
                        raise ValueError('徽章类型或颜色不符合约定')
                if sandbox.execute('SELECT 1 FROM products WHERE active=1 AND price>5').fetchone():
                    raise ValueError('单次最多使用 5 张兑换券')
                for row in sandbox.execute('''SELECT status,rule_version,coupons_used,coupon_value_fen,actual_amount_fen,
                    parent_top_up_fen,forfeited_fen,price,quoted_amount_fen FROM redemptions'''):
                    status,version,count,unit,actual,top_up,forfeited,price,quote = row
                    if quote is not None and (type(quote) is not int or quote<0):
                        raise ValueError('商品参考金额不合法')
                    if version!=RULE_VERSION:
                        continue  # Do not reinterpret completed transactions under old rules.
                    if unit!=COUPON_VALUE_FEN or not 1<=price<=MAX_COUPONS_PER_USE:
                        raise ValueError('兑换券面额或申请张数不合法')
                    if status in ('approved','reversed'):
                        if any(type(v) is not int for v in (count,actual,top_up,forfeited)) or not 1<=count<=5 or actual<0:
                            raise ValueError('消费结算数据不完整')
                        if top_up!=max(0,actual-count*unit) or forfeited!=max(0,count*unit-actual):
                            raise ValueError('消费补差或不找零金额不一致')
            finally:
                sandbox.close()
        except (ValueError,TypeError,sqlite3.Error) as exc:
            raise HTTPException(422,'备份无效：'+str(exc))
        backup_dir = Path(path).parent / 'backups'
        backup_dir.mkdir(parents=True,exist_ok=True)
        before_path = backup_dir / f'before-restore-{time.time_ns()}.json'
        before_path.write_text(json.dumps(export_data(db),ensure_ascii=False),encoding='utf-8')
        db.execute('PRAGMA defer_foreign_keys=ON')
        for table in reversed(TABLES):
            db.execute(f'DELETE FROM {table}')
        for table in TABLES:
            columns = [r['name'] for r in db.execute(f'PRAGMA table_info({table})')]
            for row in payload.tables[table]:
                db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",[row[c] for c in columns])
        for key,value in settings.model_dump().items():
            db.execute('UPDATE settings SET value=? WHERE key=?',(str(value),key))
        audit(db,'backup_restored',before_path.name)
        if payload.version==1:
            audit(db,'legacy_backup_rules_corrected','旧版备份只迁移未来配置为 5→1、5→1；历史资产及扣款未重算')
        return {'success':True,'safety_backup':before_path.name}
