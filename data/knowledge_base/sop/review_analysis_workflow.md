> PawPilot 产品差评/评论分析标准流程（中文，供运营团队使用）

# 一、分析目的

通过聚合评论主题，识别产品质量、Listing 描述、物流或客服问题，为产品改进、Listing 优化、客服话术提供数据依据。

# 二、数据准备

1. 从 Seller Central 导出目标 ASIN 的评论报告（Review Report），时间范围建议最近 90 天。
2. 如需扩展，导入广告报告中的搜索词表现、退货报告（Return Report）。
3. 将 CSV 放入 `data/reviews/` 目录，文件命名：`reviews_[ASIN]_[开始日期]_[结束日期].csv`。

# 三、评论分类标签

| 标签 | 含义 | 典型关键词 |
|---|---|---|
| 尺码 | 尺寸不合适、偏小/偏大 | size, small, large, tight, loose, did not fit |
| 质量 | 材质、做工、耐用性 | broke, cheap, fell apart, quality, durable |
| 气味 | 异味、橡胶味、化学味 | smell, odor, stinks, chemical |
| 物流包装 | 到货损坏、包装差、延迟 | damaged, package, box crushed, late |
| 描述不符 | 实物与图片/描述不一致 | not as described, different color, smaller than expected |
| 使用效果 | 功能未达预期 | does not work, my dog ignores it, no difference |
| 清洁维护 | 难清洗、褪色、变形 | hard to clean, discolored, warped |

# 四、分析步骤

1. **情感过滤**：先筛选 1–3 星评论与 4–5 星评论中提到的负面点。
2. **主题聚类**：逐条阅读并打标签，一条评论可打多个标签。
3. **量化排序**：统计每个标签出现次数 / 评论总数，计算占比。
4. **根因定位**：
   - 尺码问题占比高 → 检查 Listing 尺码图是否清晰、是否缺少 breed-weight 参考。
   - 质量问题占比高 → 联系工厂 QC，检查批次。
   - 描述不符占比高 → 修订标题/图片/A+ Content。
5. **输出 Action Items**：每项问题对应负责人、截止日期、预期可衡量的改进指标（如下月同类差评占比下降 30%）。

# 五、会议节奏

- 每周一上午 10:00 召开 30 分钟评论Review会。
- 重点关注过去 7 天新增差评与上周 Action Items 的闭环。
