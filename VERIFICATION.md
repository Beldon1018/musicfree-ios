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

---

## 启动闪退诊断与修复（用户反馈「ios签名打开闪退」，提交 `a4f3d63`）

**先纠正一处此前的过度修复。** run `42838707999` 的报错是 `CompileStoryboard LaunchScreen.storyboard: error: iOS 18.2 Platform Not Installed.`，当时同时做了两件事：给 `xcodebuild` 加 `-sdk iphoneos`，以及删掉启动屏 storyboard。前者才是真正的修复；后者是多余动作，并且造成新 bug —— 产物里**一个启动屏资源都没有**，而上游 `bootstrap.ts` 会调用 `expo-splash-screen`，`AppDelegate` 又是 `EXAppDelegateWrapper`。旧包用新校验器复核直接判失败：`VERIFY FAILED: no compiled launch screen in bundle`。

### 逐项复核旧包（结论：编译没问题，启动链有问题）

| 检查 | 结果 |
| --- | --- |
| `Payload/MusicFree.app`、arm64 Mach-O、可执行文件 | 正常 |
| `main.jsbundle` | 6,321,199 字节，Hermes bytecode magic `c61fbc03c103191f` 正确 |
| 根组件名一致性 | `app.json` = `AppRegistry.registerComponent` = `AppDelegate.moduleName` = `MusicFree`；Release 走本地 bundle，不依赖 Metro |
| iOS 平台覆盖是否进包 | `MusicFreeLiveActivity` / `liveCall` 在 bundle 内；上游 Android LyricUtil monkey patch 标记不在，说明 `index.ios.ts` 生效 |
| 签名状态 | 确实未签名（4 类签名标记全为 0） |
| `.appex` | 无，灵动岛未接线，不参与启动 |
| **启动屏资源** | **0 个**：无 `LaunchScreen.storyboardc` / `.nib` / `Assets.car`；plist 中 `UILaunchStoryboardName = None`，仅 `UILaunchScreen = {}` |
| **嵌套动态框架** | `Frameworks/hermes.framework/hermes` —— 自签时必须递归签名，否则 dyld 在 `main()` 之前终止进程 |
| JS 启动分支 | `bootstrap.ts` 在 iOS 上走 `PERMISSIONS.ANDROID.*`；`src/entry/index.tsx` 在模块顶层调用 Android-only 的 `StatusBar.setBackgroundColor` / `setTranslucent` |

置信度说明：启动屏缺失与 Android-only 启动调用是**可确证的包内事实**，已在源码侧修复。`hermes.framework` 未递归签名是自签场景下概率最高的解释，但只有真机崩溃日志才能最终确认。另外 `bootstrap.ts` 的权限异常其实会被外层 `try/catch` 接住，更可能表现为「初始化出错」界面而非进程闪退 —— 它仍是必须修的真实 bug，但不作为闪退唯一根因。

### 修复内容

| 文件 | 改动 |
| --- | --- |
| `scripts/inject_ios.py` | 恢复 `UILaunchStoryboardName = LaunchScreen`、移除 `UILaunchScreen = {}`、**不再**从 pbxproj 删除 `LaunchScreen.storyboard in Resources`；新增 `inject_bootstrap()` 与 `inject_entry_index()`，把两处 Android-only 启动调用按 `Platform.OS === "android"` 门控；保留 `-sdk iphoneos` |
| `scripts/verify_adaptation.py` | 断言反转为「启动屏必须保留」，新增启动分支断言，35 → **38 项** |
| `scripts/verify_ipa.py` | 新增启动屏资源检查（缺失即判失败）与 `nested_frameworks_to_resign` 输出，签包前就提示需要递归签名的框架 |
| `docs/signing-and-crash-guide.html` | 新增：诊断证据、`codesign` 顺序（先框架后 `.app`）、entitlements 示例、崩溃日志导出与关键字对照 |
| `scripts/verify_signed_ipa.sh` | 新增：签完包后逐个校验 `Frameworks/*.framework`、`PlugIns/*.appex` 并执行 `codesign --verify --deep --strict`。用未签名原始包实测，输出 `[FAIL] framework NOT signed : hermes.framework — code object is not signed at all`，证明脚本能抓到这类问题；`bash -n` 通过 |

### 本地复验（修复后，未依赖云端）

| 项 | 结果 |
| --- | --- |
| `prepare.sh` | **38 checks, 0 failures**，注入报告包含 `iOS skips PERMISSIONS.ANDROID.*`、`Android-only StatusBar calls gated` |
| 幂等性 | `prepare.sh` 连跑两次，5 个注入文件聚合 SHA-256 一致：`b0cf3f72…eff2040` |
| `plutil -lint` | 主 App `Info.plist` / `project.pbxproj` 均 OK；`UILaunchStoryboardName = LaunchScreen`、`UILaunchScreen` 已不存在 |
| `ruby -c` / `py_compile` / `bash -n` | 全部通过 |
| TypeScript 5.7.3 `transpileModule` | 5 个文件（`bootstrap.ts`、`index.tsx`、3 个 `index.ios.ts`）0 错误 |
| 旧包反向验证 | 新 `verify_ipa.py` 判 `VERIFY FAILED: no compiled launch screen in bundle`，`launch_screen_resources = 0`，`nested_frameworks_to_resign = ["hermes.framework"]` |

### 仍必须由用户确认的边界

本机只有 CommandLineTools，没有完整 Xcode，**无法跑模拟器或真机**。所有构建在 macOS runner 完成，本机只能做静态校验与产物结构校验。「修复版真机不再闪退」需用户在设备上确认；若仍崩溃，按 `docs/signing-and-crash-guide.html` 导出 `.ips`，重点看 `dyld: Library not loaded` / `code signature invalid`（签名问题）还是 `EXSplashScreen` 相关的 `NSInternalInconsistencyException`（启动屏问题）。

---

## 更正：真正的启动崩溃根因与最终修复（提交 `f70b008`）

> 上一节把「加 `-sdk iphoneos` 就是 `ibtool` 的真正修复」当成结论，**这是错的**。按上一节方案恢复 `LaunchScreen.storyboard` 后，run `42853265361` 仍在 `CompileStoryboard` 阶段失败、**没有产出 IPA**。以下是更正后的结论。

### 证据链

1. 失败日志第 54938 行显示 `ibtool` 命令**没有 `--platform` 参数**（同一构建里的 `actool` 却带 `--platform iphoneos`），随后报 `LaunchScreen.storyboard: error: iOS 18.2 Platform Not Installed.`。所以 `-sdk iphoneos` 不能让 ibtool 正确解析平台。
2. 上游 storyboard 是旧 RN 模板，含 `<dependencies><deployment identifier="iOS"/>…</dependencies>` 与 `<device id="retina4_7" .../>`，`toolsVersion="15702"`。这段元数据是 ibtool 去查找「iOS 18.2」平台的来源。
3. 查 Expo SDK 52 源码（GitHub `sdk-52` 分支）：
   - `SplashScreenAppDelegateSubscriber.swift` → `customizeRootView(_:)` 调用 `SplashScreenManager.shared.initWith(rootView)`；
   - `SplashScreenManager.swift` → `initWith` 无条件调用 `showSplashScreen()`，其中硬编码 `UIStoryboard(name: "SplashScreen", bundle: nil)`；`UIStoryboard(name:)` 找不到资源会抛异常；
   - `ExpoSplashScreen.podspec` 的 `source_files` 只有 `**/*.{h,m,swift}`，**不自带任何 storyboard 资源**。
   - 上游 RN 模板只有 `LaunchScreen.storyboard`，名字不匹配。

   → 旧包在 React Native 挂载之前、由 Expo 的 AppDelegate subscriber 触发原生异常，这就是「打开即闪退」的主因；与 JS 里是否调用 `SplashScreen` 无关。

### 最终修复（`f70b008`）

| 改动 | 内容 |
| --- | --- |
| `inject_storyboard()` | 从上游 `LaunchScreen.storyboard` 生成一份最小 `SplashScreen.storyboard`：移除 `<dependencies>` 与 `<device>`、`toolsVersion` 改为 22505，保留 scene/label/约束。同时满足系统启动屏与 Expo 的硬编码查找 |
| `inject_info_plist()` | `UILaunchStoryboardName = "SplashScreen"`，移除 `UILaunchScreen = {}` |
| `inject_pbxproj()` | 把 7 处 `LaunchScreen.storyboard` **文件名字符串**替换为 `SplashScreen.storyboard`；pbxproj 对象结构不变，`plutil -lint` 通过 |
| `verify_adaptation.py` | 41 项：断言 plist 指向 `SplashScreen`、pbxproj 无残留 `LaunchScreen` 引用、storyboard XML 无 dependencies/device、仍有 launch scene |
| `verify_ipa.py` | 缺少 `SplashScreen.storyboardc` 直接判失败；新增 `expo_splash_screen_present` 字段 |
| 保留 | `bootstrap.ts` / `index.tsx` 的 Android 门控、`verify_signed_ipa.sh`、`-sdk iphoneos` |

### 本地复验

| 项 | 结果 |
| --- | --- |
| `prepare.sh` | **41 checks, 0 failures**；注入报告含 `UILaunchStoryboardName = SplashScreen`、`LaunchScreen.storyboard -> SplashScreen.storyboard (7 places)`、`SplashScreen.storyboard generated` |
| 生成的 storyboard | XML 解析通过：`scenes=1`、`has dependencies=False`、`has device=False`、`initialViewController` 仍在 |
| `plutil -lint` | `project.pbxproj` / `Info.plist` 均 OK；`UILaunchStoryboardName = SplashScreen` |
| 脚本语法 | `py_compile`、`bash -n`、TypeScript `transpileModule` 全部通过 |

### 云端构建

run `42857755459`（提交 `f70b008`）用于验证清理后的 storyboard 能否通过该 runner 的 `ibtool` 并产出含 `SplashScreen.storyboardc` 的 IPA。结果见本节追加的产物校验记录。
