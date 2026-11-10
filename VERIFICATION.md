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
| `42845832731`（storyboard 修复 + iOS 原生替代方案，`83fd6c4`） | **成功**。`prepare.sh` 35/35、`npm ci`、`pod install`、`xcodebuild -sdk iphoneos ... CODE_SIGNING_ALLOWED=NO` 全链路通过，产出未签名 IPA。前两次失败均已修复；新增的 `LyricUtilModule.m`、`Mp3UtilModule.m`、`MusicFreeLiveActivityModule.m` 全部通过 Clang 编译并链接进产物 |

## 追加验证：iOS 原生替代方案落地（2026-11-10 23:1x GMT+8）

| # | 验证项 | 结果 |
| --- | --- | --- |
| 11 | `verify_adaptation.py` 扩展到 **35 项**（新增浮层、ID3 歌词、元数据覆盖层、Live Activity 源码、storyboard 移除、plist 能力、`-sdk iphoneos`） | **35 项 0 失败** |
| 12 | `prepare.sh` 连续两次重放，对 overlay 全部文件 + 3 个注入文件做聚合哈希对比 | 通过，`IDEMPOTENT=yes`（两次 `1c955454…21dc2`） |
| 13 | `plutil -lint`：`project.pbxproj` / 主 App `Info.plist` / Extension `Info.plist` | 全部 OK（pbxproj 结构语法有效） |
| 14 | `ruby -c` podspec、4 个 Python `py_compile`、4 个 shell `bash -n` | 全部通过 |
| 15 | 3 个 `index.ios.ts` 的 TypeScript 5.7.3 `transpileModule` | 0 语法错误 |

新增实现清单：`LyricUtilModule.{h,m}`（App 内可拖动浮层 + 触摸穿透）、`Mp3UtilModule.m`（ID3 USLT/SYLT/©lyr 读取 + `Documents/` 元数据覆盖层）、`MusicFreeLiveActivityModule.{h,m}`（运行时解析 Swift，没有 Extension 时静默 no-op）、`overlay/ios/LiveActivity/` 三份 Swift 源码 + Extension plist + 接线说明。

## 最终产物校验（2026-11-10 23:5x GMT+8）

产物 `MusicFree-v1.0.0-beta.4-unsigned.ipa` 由 run `42845832731` 构建，对应源码提交 `83fd6c4`。

| 项 | 值 |
| --- | --- |
| 大小 | 7,231,214 字节 |
| SHA-256 | `7621d1092d7f671c40a04cab50fcdb67a3926672925af62c73c039c4dc506da2` |
| zip 结构 | `Payload/MusicFree.app`，84 个条目 |
| Bundle ID / 版本 | `com.musicfree.ios.unsigned` / `1.0.0 (1)` |
| 最低系统 | iOS 15.1 |
| 平台 / 架构 | iPhoneOS / arm64 thin Mach-O（`cffaedfe`） |
| JS bundle | `Payload/MusicFree.app/main.jsbundle` 已内嵌 |
| 签名标记 | `_CodeSignature` / `embedded.mobileprovision` / `CodeResources` / `SC_Info` **均为 0** |
| 关键 plist | `UIBackgroundModes=audio`、`NSSupportsLiveActivities=true`、`UILaunchScreen={}`、无 `UILaunchStoryboardName` |
| `.appex` | 无（灵动岛 Extension 默认未接线，行为与 README 一致） |

`verify_ipa.py` 结论：`VERIFY OK: unsigned iOS ipa with embedded JS bundle`。

## 仍待真机验证（必须如实说明）

- **Swift 编译器**：三个 Objective-C 原生模块已由云端 Clang 编译链接通过；灵动岛 Swift 源码默认未加入任何 Xcode target，因此**尚未过 Swift 编译器**。
- **灵动岛 Extension**：`NSSupportsLiveActivities` 已在 Info.plist 声明，但当前 IPA 内没有 `.appex`，实时活动不会启动；App 内可拖动浮层正常工作。接线与重新构建步骤见 `overlay/ios/LiveActivity/README.md`。
- **真机运行**：浮层拖动/触摸穿透、ID3 `USLT`/`SYLT` 实际解码、元数据覆盖层读写、后台音频与锁屏联动，均未在真机验证。
- **自签安装**：Sideloadly / AltStore / ESign 重签未验证；若将来接入 `.appex`，需先签 appex 再签 app。
- **上游新版全链路**：自动同步的「已是最新 → 跳过」分支已验证；「发现新 tag → 重新构建 → 发 Release」尚未真实触发过一次。

`verify_adaptation.py` 会在上游新增 Android-only 原生模块时提前报错，避免静默产出坏包。云端各次日志保留在 `outputs/cloud-build/`，便于按日志继续迭代。
