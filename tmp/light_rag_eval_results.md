# Lightweight RAG Eval Results

- Generated at (UTC): `2026-04-28T08:29:49.740Z`
- Corpus size: `23`
- Sample count: `24`

## Overall

- `hit_rate@1`: `0.75`
- `hit_rate@3`: `0.9583`
- `hit_rate@5`: `1`
- `mrr`: `0.8556`
- `precision@1`: `0.75`
- `precision@3`: `0.5139`
- `precision@5`: `0.375`
- `recall@1`: `0.4181`
- `recall@3`: `0.7403`
- `recall@5`: `0.875`

## By Category

### case_lookup
- `hit_rate@1`: `0.75`
- `hit_rate@3`: `0.875`
- `hit_rate@5`: `1`
- `mrr`: `0.8375`
- `precision@1`: `0.75`
- `precision@3`: `0.5417`
- `precision@5`: `0.375`
- `recall@1`: `0.4167`
- `recall@3`: `0.8125`
- `recall@5`: `0.9375`

### diagnosis
- `hit_rate@1`: `0.8333`
- `hit_rate@3`: `1`
- `hit_rate@5`: `1`
- `mrr`: `0.8889`
- `precision@1`: `0.8333`
- `precision@3`: `0.5556`
- `precision@5`: `0.4333`
- `recall@1`: `0.3389`
- `recall@3`: `0.6556`
- `recall@5`: `0.8056`

### rule_explanation
- `hit_rate@1`: `0.7`
- `hit_rate@3`: `1`
- `hit_rate@5`: `1`
- `mrr`: `0.85`
- `precision@1`: `0.7`
- `precision@3`: `0.4667`
- `precision@5`: `0.34`
- `recall@1`: `0.4667`
- `recall@3`: `0.7333`
- `recall@5`: `0.8667`

## Sample Highlights

### rq_rule_01 - rule_explanation
- Query: 什么是 full 和 partial 的区别？
- Expected: case.tc06_edge_goal_full, case.tc06_edge_goal_partial, rules.goal_modes
- Top 3: rules.goal_modes (8.25), case.tc06_edge_goal_partial (1.75), case.tc06_edge_goal_full (1.5)
- MRR: `1`

### rq_rule_02 - rule_explanation
- Query: 为什么大物体不能只看左上角占位？
- Expected: case.tc04_large_piece_footprint, rules.large_piece_footprint
- Top 3: rules.large_piece_footprint (13.75), case.tc01_multiple_legal_stops (0), case.tc02_fixed_adjacent_blocks (0)
- MRR: `1`

### rq_rule_03 - rule_explanation
- Query: horizontal 为什么会禁止 vertical 移动？
- Expected: case.tc05_horizontal_forbids_vertical, rules.basic_movement, rules.lanes_and_priority
- Top 3: rules.entities_and_tags (8), rules.lanes_and_priority (8), case.tc05_horizontal_forbids_vertical (5.75)
- MRR: `0.5`

### rq_rule_04 - rule_explanation
- Query: target-lane 和 horizontal 冲突时应该听谁的？
- Expected: case.tc03_target_lane_priority, rules.lanes_and_priority
- Top 3: rules.entities_and_tags (11), rules.lanes_and_priority (8), case.tc05_horizontal_forbids_vertical (4.25)
- MRR: `0.5`

### rq_rule_05 - rule_explanation
- Query: 为什么 block 不能进入 edge goal？
- Expected: case.tc07_block_cannot_enter_edge_goal, rules.edge_goal_rules
- Top 3: rules.entities_and_tags (8), rules.edge_goal_rules (6.75), rules.goal_modes (5.5)
- MRR: `0.5`

### rq_rule_06 - rule_explanation
- Query: 最后一步进入边缘终点为什么可以放宽轨道限制？
- Expected: case.tc07_edge_goal_last_step_only, rules.edge_goal_rules
- Top 3: rules.edge_goal_rules (14.5), rules.lanes_and_priority (2.5), rules.search_model (2.5)
- MRR: `1`

### rq_rule_07 - rule_explanation
- Query: 结构合法和可解到底有什么区别？
- Expected: rules.validation_vs_solving
- Top 3: rules.validation_vs_solving (9.5), rules.basic_movement (2.5), rules.architecture_node_java (1.25)
- MRR: `1`

### rq_rule_08 - rule_explanation
- Query: 为什么这个系统需要 Node 桥接和 Java 求解器？
- Expected: rules.architecture_node_java
- Top 3: rules.architecture_node_java (13.5), rules.shared_interfaces (2), rules.validation_vs_solving (1.25)
- MRR: `1`
