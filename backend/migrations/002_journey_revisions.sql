-- 补传入口：journeys增加来源修订号与撤回标记
-- 撤回保留墓碑行，旧版晚到不复活；读取侧一律过滤withdrawn
ALTER TABLE journeys ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 1;
ALTER TABLE journeys ADD COLUMN IF NOT EXISTS withdrawn BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS ix_journeys_batch_active ON journeys (batch_id) WHERE NOT withdrawn;
