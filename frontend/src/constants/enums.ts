export const Roles={admin:'传播负责人',analyst:'路径研究员',viewer:'策展阅读者'} as const;
export const RunStatus={queued:'队列等待',running:'计算中',completed:'已完成',failed:'失败'} as const;
export const ReviewStatus={submitted:'待复核',approved:'已批准',rejected:'退回讨论'} as const;
export const ImportOutcome={imported:'新建接收',updated:'修订更新',moved:'跨周迁移',revived:'撤回后恢复',withdrawn:'撤回生效',unchanged:'重复送达',stale:'旧版忽略',superseded:'批内被覆盖',duplicate:'批内重复',conflict:'同版冲突',invalid:'记录无效',skipped:'整批拒收'} as const;
