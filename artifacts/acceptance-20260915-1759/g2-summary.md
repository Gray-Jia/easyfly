# G2 测试结论（功能与 lint 分离统计）— 2026-09-15
基线: 04d99d4（+ build-v2 隔离构建, easyfly_serial 于本轮补构建）
colcon 原始汇总: 156 tests, 1 error, 92 failures, 13 skipped
（92 失败 = 79 项 lint xunit + 13 项 ctest Test.xml 聚合层重复计数；1 error = test_sort 架子缺陷；13 skipped 全部为 cppcheck 条目）

## 功能 gtest（G2 验收对象）
| 套件 | 包 | 结果 |
|---|---|---|
| test_loopback | easyfly_serial | 1/1 PASS |
| test_filter_core | easyfly_pointcloud_filter | 5/5 PASS |
| test_sort | easyfly_multi_object_tracking | 6/6 断言实际通过（stdout PASS 1-6），但 gtest 架子缺陷报 1 error（V2-04） |
| test_id_consolidator | easyfly_multi_object_tracking | 10/10 PASS |
| test_astar | easyfly_global_planner | 8/8 PASS（与历史 8/8 一致） |
功能断言合计 30/30 通过，无功能回归。

## lint（债务清单，非 G2 阻塞项）
| 类型 | 失败/总数 | 涉及包 |
|---|---|---|
| cpplint | 45/45 | 三包全败 |
| copyright | 16/16 | 三包全败 |
| uncrustify | 12/13 | 三包 |
| pep257 | 6/6 | 三包全败 |
| cppcheck/flake8/lint_cmake/xmllint | 0 失败（cppcheck 13 skipped） | — |
lint 债务合计 79 项，与历史"84 失败主要为 lint"结论吻合。easyfly_serial 未注册 lint 测试。

## G2 结论
功能层通过；正式 colcon 全绿被 V2-04（TEST 类）阻挡，修复后仅需重测 easyfly_multi_object_tracking 一包。

## 复测补记（V2-04 修复后）
- 修复: test_sort.cpp 改写为标准 gtest (6 个 TEST 用例, 语义与原 6 项断言一一对应), 加 Apache license 头
- 复测结果: test_sort 6/6 PASS, 0 error, 结果文件正常生成; 本包 lint 失败 41→37 (新测试文件自身 lint 合规)
- G2 功能层结论: 5 套件 30/30 断言全过, 0 error —— G2 功能全绿达成
- 剩余失败均为 V2-05 lint 债务 (非阻塞)
