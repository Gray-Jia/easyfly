# EasyFly 回归测试

## 控制链回归（Q32 轻量实现）

把 `test-guide.md` 的手动回归流程脚本化，一键执行并给出 PASS/FAIL 汇总。

```bash
bash test/run_control_regression.sh
```

- 全程约 6-10 分钟（含 T8 的 RTL 落地等待，最长 4 分钟，属信息性检查不参与判定）；
- launch 日志：`/tmp/easyfly_regression_launch.log`（可用 `LOG=...` 改路径）；
- 退出码 0 = 全部硬断言通过。

### 覆盖项

| 用例 | 回归目标 | 来源 |
|------|----------|------|
| T1 就绪检查 | /uav_state 数据流 + action server 可用 | — |
| T2 起飞 2.5m | 起飞 + 悬停 + armed/OFFBOARD | V7 |
| T3 航点往返 | 航点飞行位置精度 <1.0m | M6 |
| T4 航点取消 | 就地悬停，不飞到目标 | P0/Q4 |
| T5 降落取消 | 切回 OFFBOARD 恢复悬停高度 | P0/Q3 |
| T6 连续起降 ×2 | 降落 disarm 后可再次起飞 | 复查缺陷 D |
| T7 坏任务文件 | 非法数值不崩溃、mission abort | P0/Q8 |
| T8 低电量 RTL | 10% 电量注入 → 任务 EMERGENCY abort + AUTO.RTL | P0/Q2 + 接管检测 |

### 设计约定

- **纯控制仿真**（empty.world，无感知层）——感知链回归仍用 `perception_sitl.launch.py` 手动验证（V1-V6）；
- `test/` 不参与 colcon 构建（`colcon_defaults.yaml` base-paths=src），launch 文件以直接路径方式启动；
- T8 低电量注入方式与 test-guide.md 附录一致：向 `/mavros/battery` 以 10Hz 注入 10% 电量；
- **SITL 磁力计怪癖**：单次仿真会话内本套件共 4 次起飞，接近"连续 3+ 轮起降退化"边界；末尾用例若报 failsafe 属环境问题，重跑即可（编排器每次都会重启仿真）；
- headless 环境下 `px4_sitl.launch.py` 里的 gzclient 启动失败属正常，不影响测试。

### 文件

- `run_control_regression.sh` — 编排器（清理 → 启动 → 测试 → 关闭）
- `control_regression.launch.py` — 纯控制仿真一键启动（复用 px4_sitl / mavlink_bridge / flight_control / mission_fsm 的现有 launch）
- `control_regression.py` — rclpy 测试客户端（用例与断言）
