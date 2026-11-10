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

## 云端验证（真实 macOS runner）

用户授权后工程已推到公开仓库 <https://github.com/Beldon1018/musicfree-ios> 并触发构建。

| run | 结果 |
| --- | --- |
| `42838316267`（同步流程手动触发） | **成功**。`check` 判定「已是最新 `v1.0.0-beta.4`」，正确跳过 build / publish / notify —— 云端同步逻辑闭环验证通过 |
| `42838140958`（首次构建） | **失败，已定位并修复**。`setup-xcode 16.2`、`prepare.sh`（适配层在真实 macOS 上成功重放，19/19）、`npm ci` 全部通过；`pod install` 报 `Invalid MusicFreeNative.podspec: undefined method 'join' for an instance of String`。根因是 `s.dependency = 'React-Core'` 用了赋值写法，CocoaPods 该 setter 只接受数组。已改成方法调用 `s.dependency 'React-Core'`，并把 `source_files` / `frameworks` 显式写成数组，提交 `54885b2` 推送 |
| `42838707999`（修复后重跑） | **失败，已定位并修复**。`pod install` 通过，60+ 依赖全部编译，最后卡在 `CompileStoryboard LaunchScreen.storyboard: error: iOS 18.2 Platform Not Installed.`（`ibtool` 在 macOS runner 上找不到对应 platform），`SwiftCompile` 是级联取消（日志里没有独立 `error:`）。修法：`inject_ios.py` 幂等移除 storyboard 的 Resources 引用并改用 iOS 14+ `UILaunchScreen` plist 启动屏；`build_unsigned_ipa.sh` 显式加 `-sdk iphoneos` |

## 追加验证：iOS 原生替代方案落地（2026-11-10 23:1x GMT+8）

| # | 验证项 | 结果 |
| --- | --- | --- |
| 11 | `verify_adaptation.py` 扩展到 **35 项**（新增浮层、ID3 歌词、元数据覆盖层、Live Activity 源码、storyboard 移除、plist 能力、`-sdk iphoneos`） | **35 项 0 失败** |
| 12 | `prepare.sh` 连续两次重放，对 overlay 全部文件 + 3 个注入文件做聚合哈希对比 | 通过，`IDEMPOTENT=yes`（两次 `1c955454…21dc2`） |
| 13 | `plutil -lint`：`project.pbxproj` / 主 App `Info.plist` / Extension `Info.plist` | 全部 OK（pbxproj 结构语法有效） |
| 14 | `ruby -c` podspec、4 个 Python `py_compile`、4 个 shell `bash -n` | 全部通过 |
| 15 | 3 个 `index.ios.ts` 的 TypeScript 5.7.3 `transpileModule` | 0 语法错误 |

新增实现清单：`LyricUtilModule.{h,m}`（App 内可拖动浮层 + 触摸穿透）、`Mp3UtilModule.m`（ID3 USLT/SYLT/©lyr 读取 + `Documents/` 元数据覆盖层）、`MusicFreeLiveActivityModule.{h,m}`（运行时解析 Swift，没有 Extension 时静默 no-op）、`overlay/ios/LiveActivity/` 三份 Swift 源码 + Extension plist + 接线说明。

## 尚未验证（必须如实说明）

- **基础 IPA 仍未产出**：`xcodebuild ... CODE_SIGNING_ALLOWED=NO` 的完整 Release archive 需要重跑一次，才能确认 storyboard 修复生效、60 个 RN/Expo 依赖能全部编译链接、`main.jsbundle` 成功嵌入（`verify_ipa.py` 已写好产物断言）。
- **ObjC / Swift 真机编译**：本机无完整 Xcode，新增原生代码只做了静态与语法校验，未过 Clang / Swift 编译器。
- **灵动岛 Extension**：Swift 源码与接线步骤齐备，但 Widget Extension target 需要一次 Xcode GUI / XcodeGen 改造 + 云端构建验证，默认构建不包含它。
- 真机安装与运行时行为（自签后），以及 `.appex` 与 `.app` 一起重签的兼容性。

`verify_adaptation.py` 会在上游新增 Android-only 原生模块时提前报错，避免静默产出坏包。云端失败日志保留在 `outputs/cloud-build/`，便于按日志继续迭代。
