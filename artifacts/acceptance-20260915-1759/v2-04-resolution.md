# V2-04 修复与验收记录

- 日期：2026-09-15
- 范围：`easyfly_multi_object_tracking/test/test_sort.cpp`
- 问题：测试通过 `ament_add_gtest` 注册，但原测试程序使用手写 `main()` 和 `assert`，无法产生 gtest XML，因而被结果收集器记录为 error。
- 修复：将原有六项验证改写为六个原生 GoogleTest 用例；未修改 SORT 算法或运行时代码。

## 验证结果

1. 目标构建：

   ```bash
   cmake --build build-v2/easyfly_multi_object_tracking --target test_sort -j2
   ```

   结果：通过。

2. 定向 CTest：

   ```bash
   ctest --test-dir build-v2/easyfly_multi_object_tracking -R '^test_sort$' --output-on-failure
   ```

   结果：1/1 通过。

3. 包级测试：

   ```bash
   colcon test --build-base build-v2 --install-base install-v2 \
     --packages-select easyfly_multi_object_tracking \
     --event-handlers console_direct+
   ```

   功能结果：

   - `test_sort`：6/6 通过；
   - `test_id_consolidator`：10/10 通过；
   - `test_sort.gtest.xml`：6 tests、0 errors、0 failures。

包级结果中的其余失败均来自 copyright、cpplint、pep257 和 uncrustify，对应 V2-05，不属于 V2-04。

## 验收结论

V2-04 已解决：GoogleTest 结果文件可稳定生成，结果收集器不再报告 `The test did not generate a result file`。G2 功能测试可按 16/16 通过记录；lint 债务继续单独统计。

当前源码修复尚未提交。提交后应按 G0 规则登记新的基线编号。
