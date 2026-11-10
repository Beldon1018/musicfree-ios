# 本地验证记录

验证环境：macOS 15.7.8（Intel），**只有 CommandLineTools，没有完整 Xcode**。因此本轮验证覆盖的是「适配层能否正确、稳定地重放」以及脚本/产物结构，不包含 `xcodebuild` 实际编译与真机运行 —— 那一步由 GitHub Actions 的 macOS runner 完成。

验证时间：2026-11-10 22:2x (GMT+8)

| # | 验证项 | 结果 |
| --- | --- | --- |
| 1 | `prepare.sh` 首次执行：检出 `v1.0.0-beta.4` → 复制 overlay → 幂等注入 → 静态校验 | 通过。`verify_adaptation.py` **19 项检查 0 失败** |
| 2 | 注入内容：Podfile 挂本地 Pod、Info.plist 5 个键、pbxproj 换 Bundle ID / 版本号 | 通过，逐项读回确认 |
| 3 | 幂等性：连续执行两次 `prepare.sh`，对 3 个注入文件 + 全部 overlay 文件做 SHA-256 对比 | 通过，两次结果**字节级完全一致** |
| 4 | 跨版本重放：切换到 `v0.6.2`（2025-10 的旧代码结构） | 通过，19/19；版本号自动变为 `0.6.2` |
| 5 | 自动同步回最新版（`v0.6.2` → `v1.0.0-beta.4`） | 通过，19/19 |
| 6 | 失败回滚：指定不存在的 tag 触发 `--apply` | 通过，`UPSTREAM_REF` 自动恢复为 `v1.0.0-beta.4`，仓库不会停在坏状态 |
| 7 | 3 个 `index.ios.ts` 的 TypeScript 语法（TypeScript 5.7.3 `transpileModule`） | 通过，0 语法错误 |
| 8 | 所有 shell 脚本 `bash -n`、所有 Python 脚本 `py_compile` | 通过 |
| 9 | 两个 GitHub Actions workflow 的 YAML 解析 | 通过 |
| 10 | 同步版本检测 | 修掉一个真 bug：GitHub `/releases/latest` 会跳过 `-beta.N` 预发布，返回 `v0.6.2`，险些让自动同步**降级**。改为合并 releases 列表 + `git ls-remote` 全量 tag 后按语义版本取最大值；已单测 `v1.0.0` > `v1.0.0-beta.4` > `v0.6.2` |

## 尚未验证（必须如实说明）

- `xcodebuild ... CODE_SIGNING_ALLOWED=NO` 的完整 Release archive。RN 0.76 / Expo 52 + 60 个依赖中，个别第三方库是否缺少可用的 iOS podspec，只有真实编译才能确认。
- `main.jsbundle` 是否成功嵌入（脚本里已用 `verify_ipa.py` 做产物断言，构建失败会被拦下而不是交付白屏包）。
- 真机安装与运行时行为（自签后）。

首次云端构建就是这些项的验证点。若失败，日志会留在 Actions run 里；`verify_adaptation.py` 会在上游新增 Android-only 原生模块时提前报错，避免静默产出坏包。
