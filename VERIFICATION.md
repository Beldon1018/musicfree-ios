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

### 云端构建（该次失败，见下一节的再次更正）

run `42857755459`（提交 `f70b008`）用于验证清理后的 storyboard 能否通过该 runner 的 `ibtool`。真实 API 结论 `conclusion=failure`：

```text
CompileStoryboard .../MusicFree/SplashScreen.storyboard
/Applications/Xcode_16.2.app/Contents/Developer/usr/bin/ibtool ... --target-device iphone --minimum-deployment-target 15.1 ...
SplashScreen.storyboard: error: iOS 18.2 Platform Not Installed.
** ARCHIVE FAILED **
```

即**移除了 `<dependencies>` / `<device>` 的精简 storyboard 仍然失败**。「旧模板 XML 元数据触发 ibtool 查平台」这一推断被证伪；`-sdk iphoneos` 同样不是修复。

---

## 第二次更正：`ibtool` 失败是 GitHub runner 镜像缺陷（提交 `5228820`）

### 证据链

1. 失败日志中 `ibtool` 命令**没有 `--platform`**，而同一构建里的 `actool` 带 `--platform iphoneos`；`xcodebuild -showsdks` 确实列出 iOS 18.2 SDK，但 `ibtool` 仍报 `iOS 18.2 Platform Not Installed.`。
2. 查到 GitHub 官方 runner 仓库 issue [`actions/runner-images#13560`](https://github.com/actions/runner-images/issues/13560)（2026-01）：`macos-15` 镜像 `20260112.0107.1` 起移除旧版 Xcode 的 iOS runtime，导致**任何** storyboard 都无法编译；Xcode 16.2 / 16.3 均受影响，极简 storyboard 也失败；同一份工程在 `macos-14` runner 和本地 Mac 的 Xcode 16.2 上都能编译。维护者给出的修复是：

   ```yaml
   - name: download platforms
     run: |
       xcrun simctl list
       xcodebuild -downloadPlatform iOS
   ```

3. `j3k0/cordova-plugin-purchase#1684` 也把同一报错归因于 CI 基础设施（其绕法是改用 `iphonesimulator` 编译检查，但我们需要真机 device archive，不能这么做）。

→ 结论：`ibtool` 报错与适配层 storyboard 内容**无关**，是 runner 缺 iOS platform/runtime。此前「删 storyboard → 出包成功」只是绕开了 ibtool，却破坏了 Expo 的原生启动契约；而「精简 XML」修不了 ibtool。

### 修复（`5228820`）

| 改动 | 内容 |
| --- | --- |
| `.github/workflows/build-ios-unsigned.yml` | `setup-xcode` 后新增 `Ensure iOS runtime is installed`：`xcodebuild -downloadPlatform iOS`（对所选 Xcode 的 iOS 18.2 runtime 做幂等安装；**不能用 `xcrun simctl list runtimes` 是否含 "iOS 18" 来判断**——runner 已装 18.5/18.6/26.x 属于别的 Xcode 版本，会让判断误以为已就绪而跳过，run `42861878571` 因此漏装） |
| 同上 | `prepare.sh` 后新增 `Smoke-test ibtool`：用 `ibtool --compile` 单独编译生成的 `SplashScreen.storyboard`，**几秒内失败即快速失败**，不再白跑约 18 分钟 RN 全量 archive |
| 保留 | `f70b008` 的 `SplashScreen.storyboard` 生成、plist / pbxproj 改名、iOS 启动分支门控、`verify_ipa.py` 强制检查 `SplashScreen.storyboardc` |

`sync-upstream.yml` 通过 `uses:` 复用该 workflow，因此自动同步链路也会一并获得修复。

### 待填

run `42861878571`（提交 `5228820`）第一次失败：平台步骤的 "iOS 18" 判断误判（runner 已装 18.5/18.6/26.x 属于别的 Xcode），漏掉了 `downloadPlatform`，冒烟测试立刻复现 `iOS 18.2 Platform Not Installed.`。已将安装改为**无条件执行**（匹配所选 Xcode 的 18.2 runtime），重新提交并重建，结果见下一节产物校验记录。

---

## 最终修复版产物（run `42863975900`，提交 `c8a13af` · 已成功）

`xcodebuild -downloadPlatform iOS` 装回 iOS 18.2 runtime 后，冒烟测试通过，完整 Release archive 成功，IPA 经 `verify_ipa.py` 通过。

### `verify_ipa.py` 实测（本地，`scripts/verify_ipa.py`）

```json
{
  "bytes": 7235006,
  "sha256": "15d56628e4b7b7ae4e5e1be93ca67db59e5fc774383774dd2e3b391eab995602",
  "bundle_id": "com.musicfree.ios.unsigned",
  "marketing_version": "1.0.0",
  "build_version": "1",
  "min_os": "15.1",
  "js_bundle_included": true,
  "executable_included": true,
  "launch_screen_resources": 4,
  "expo_splash_screen_present": true,
  "nested_frameworks_to_resign": ["hermes.framework"],
  "signature_files": [],
  "unsigned": true
}
```

解包后确认：

| 检查 | 结果 |
| --- | --- |
| `SplashScreen.storyboardc` | 存在，4 个条目：`Info.plist` + `01J-lp-oVM-view-Ze5-6b-2t3.nib` + `UIViewController-01J-lp-oVM.nib`（即 Expo 原生启动要找的资源，旧包为 0） |
| `UILaunchStoryboardName` | `SplashScreen`（旧包曾被设为 `None` / `UILaunchScreen = {}`） |
| `UILaunchScreen` | 已不存在 |
| `NSSupportsLiveActivities` | `true` |
| `UIBackgroundModes` | `audio` |
| 启动分支 | `bootstrap.ts` 不再走 `PERMISSIONS.ANDROID.*`；`index.tsx` 顶层 `StatusBar` 已按平台门控 |
| `Frameworks/hermes.framework` | 仍在包内，**自签时必须递归签名**（见签名指南） |

### 结论

- **可交付**：`outputs/MusicFree-v1.0.0-beta.4-unsigned.ipa`（SHA-256 前缀 `15d56628…`），iOS 15.1+ arm64 未签名包，内嵌 `main.jsbundle`，含 Expo 启动所需 `SplashScreen.storyboardc`。
- **旧包 `7621d109…` 已废弃**：已移到 `outputs/cloud-build/archive-deprecated-7621d109.ipa`，请勿再使用。
- **仍需真机确认**的边界不变：灵动岛 Swift 源码未接线、浮层/ID3 解码/后台音频行为、自签安装、自动同步全链路。用户自签后若仍闪退，按 `docs/signing-and-crash-guide.html` 导出 `.ips`，重点看 `code signature invalid` / `Library not loaded`（签名）还是 Expo splash 相关异常（启动屏）。

## 追加验证：真机第二份崩溃（bridgeless）根因修复（2026-11-11）

用户提供第二份 `.ips`（incident `4BA40D8B-6A2E-4922-9E98-19352F4A2AB0`，iPhone OS 26.4）。与第一份（`EXC_CRASH/SIGABRT`，Expo 找不到 `SplashScreen` storyboard）不同，这次是 `EXC_BAD_ACCESS/SIGSEGV`、`far=0`、faultingThread 为 `com.facebook.react.runtime.JavaScript`。

用同 UUID 二进制反汇编 + vtable/typeinfo 还原，崩溃链为：

```
_platform_strlen                                     strlen(NULL)
std::__1::basic_string::__init(char const*)          0x46f84
TurboModuleBinding::getModule                        0x49137c  字面量 "TurboModuleBinding::moduleProvider"
BridgelessNativeModuleProxy::get                     0x491a30  内联比较 "__esModule"
hermes JsiProxy::get / JSObject::getNamedWithReceiver_RJS → evaluateJavaScript
```

vtable typeinfo 解出 `facebook::react::BridgelessNativeModuleProxy` —— 该类**只在 bridgeless（新架构）下安装**。根因：`overlay/ios/Podfile.properties.json` 的 `newArchEnabled:"false"` **从未被读取**（裸 RN 的 Podfile 不解析该文件），而 RN 0.76 的 `NewArchitectureHelper.new_arch_enabled` 在 `ENV['RCT_NEW_ARCH_ENABLED']` 未设置时返回 `true`，于是构建默认走了新架构。

| # | 验证项 | 结果 |
| --- | --- | --- |
| 16 | `inject_ios.py` 在 `platform :ios` 前幂等注入 `ENV['RCT_NEW_ARCH_ENABLED'] = '0'` | 通过，`pod install` 日志出现 `forced legacy architecture` |
| 17 | 重建 `42948604678`（20m37s） | **成功**，IPA 6,934,977 B / SHA-256 `2f556f94…` |
| 18 | 产物是否真的回到旧架构 | 反汇编 `_RCTIsNewArchEnabled`（`0x10020e758`）= `adrp x8,0x100777000; ldrb w0,[x8,#0x968]; ret`，该全局落在 `__DATA` 的 BSS 尾（`vmsize 0xB4000` > `filesize 0x98000`）→ 初值 0 → 返回 **NO** |
| 19 | 认知修正 | RN 0.76 的 `setup_fabric!` **无条件**安装 Fabric pods，二进制里仍有 `RCTFabricSurface` / `BridgelessNativeModuleProxy` 符号属正常，不能据此判断新架构生效；真正的开关是 `-DRCT_NEW_ARCH_ENABLED` 编译宏 |
| 20 | workflow 增加 `Upload dSYM` | 通过；dSYM UUID 与二进制 `LC_UUID` 一致（`EEF75C89…`），可 `atos` 符号化 |

## 追加验证：软键盘遮挡输入框修复（2026-11-11）

用户报障：插件管理页弹出键盘后输入框被盖住。定位到两处 **iOS-only** 布局缺陷（Android 键盘会 resize window，upstream 从未踩到）：

| 文件 | 缺陷 |
| --- | --- |
| `src/components/panels/base/panelBase.tsx` | 包裹底部面板的 `KeyboardAvoidingView` 样式只有 `{ zIndex: 15010 }`，内部 panelBody 是 `position:absolute; bottom:0`，所以该容器**没有任何在流内容 → 高度 0**。RN 0.76 的 `behavior="height"` 用 `_initialFrameHeight(0) - keyboardHeight` 并被裁到 0 → 面板不动，「从网络安装插件」输入框留在键盘下 |
| `src/components/dialogs/components/base/index.tsx` | 弹窗卡片在全屏 absolute 容器里居中，**完全没有键盘避让** → 订阅插件弹窗（名称 / URL 两个输入框）被盖 |

修法（commit `ab779f3`，仍为幂等注入，不手改 upstream）：

- 给 `kbContainer` 补全屏 absolute 盒子（`_initialFrameHeight` 变成屏幕高，行为生效）+ `pointerEvents="box-none"`（保持遮罩可点关闭）。
- 弹窗卡片移入 `styles.dialogLayer`（全屏 absolute 居中）+ `behavior="padding"` 的 `KeyboardAvoidingView`：`paddingBottom` 收缩居中盒，卡片整体上移半个键盘高，收起键盘后自动回中。

| # | 验证项 | 结果 |
| --- | --- | --- |
| 21 | `verify_adaptation.py` 新增 4 条断言 | **46 项 0 失败** |
| 22 | `prepare.sh` 重放幂等 | 通过，二次注入 `panelBase.tsx` / `dialogs/base/index.tsx` 均为 `already present` |
| 23 | TypeScript 5.x `ts.transpileModule` 校验 4 个改过的 TS/TSX | 0 语法错误 |
| 24 | 重建 `42989752793`（约 18min） | **成功**，IPA 6,934,736 B / SHA-256 `690c5ef7…`，`verify_ipa.py` VERIFY OK |
| 25 | 补丁是否真的进了线上 bundle（指纹校验） | 新包 `main.jsbundle` 含 `dialogLayer` **1** 处，上一版 **0** 处 → 确认编译进产物 |
| 26 | dSYM UUID 与二进制一致 | `EEF75C89-227F-306D-BE14-664A4373CE14`（只改了 JS，Mach-O 未变，故 UUID 与上一版相同） |

## 追加验证：软键盘修复的回归与最终方案（2026-11-11）

第一次修复（`ab779f3`）把面板的 `KeyboardAvoidingView` 改成全屏尺寸，修好了 `behavior="height"`，却**弄坏了 `behavior="position"`**——那是所有未显式设置 `keyboardAvoidBehavior` 的面板（含 ＋ 号菜单 `SimpleSelect`）走的默认分支。该分支把 children 包进一个**普通流内 View**，由于面板 body 是 `position:absolute`，这个 View 高度为 0；原代码里它恰好落在屏幕底部（外层 KAV 本身是位于导航栈之后的 0 高流内元素），所以一直正常。外层容器一旦变成全屏，它就跑到**屏幕顶部**，于是菜单从上面弹出、点一下即消失。

结论：该布局依赖「0 高容器恰好在屏幕底」的巧合，**不能靠改容器尺寸解决**，`KeyboardAvoidingView` 对这种绝对定位面板无解。

最终方案（`6d30010`）：`panelBase` **彻底移除 KeyboardAvoidingView**。

- 面板 body 放进显式全屏 `View`（`pointerEvents="box-none"`），给它一个确定的底部基准；
- 键盘位移改为在既有 Reanimated transform 上叠加 `- kbOffset.value`；
- `kbOffset = windowHeight - endCoordinates.screenY`，**不用** `endCoordinates.height`——iOS 收起键盘时会带旧 height 配屏外 `screenY`，用 height 会导致面板不回位；
- 无输入的面板（＋ 菜单等）键盘高度恒为 0，布局与改动前完全一致；`editMusicSheetInfo` 这类默认 `position` 面板与原行为等价；`simpleInput` / `createMusicSheet` / `associateLrc` / `colorPicker` 是真正的修复。

| # | 验证项 | 结果 |
| --- | --- | --- |
| 27 | 断言改为「含 `kbOffset`/`keyboardWillChangeFrame`」「含 `<View style={style.kbContainer} pointerEvents="box-none">`」「**不得再有** `<KeyboardAvoidingView`」 | **47 项 0 失败**（第三条即为防回退护栏） |
| 28 | `prepare.sh` 重放 + 二次注入 | 通过，`panelBase.tsx` / `dialogs/base/index.tsx` 均 `already present` |
| 29 | `ts.transpileModule` 校验 panelBase / dialogs base | 0 语法错误 |
| 30 | 逐分支核对布局语义 | `position` 默认面板（＋ 菜单）回到屏幕底部；`height` 面板随键盘上移；`none` 面板不经过容器，行为不变 |
| 31 | 重建 `42994437080` | **成功**（20m18s），IPA 6,935,195 B / SHA-256 `7e476111…`，`verify_ipa.py` VERIFY OK |
| 32 | 新方案是否进入线上 bundle | 新 `main.jsbundle` 含 `kbOffset` **2** 处；上一版（回归版）**0** 处 → 确认 panelBase 新实现已进包 |
| 33 | dSYM UUID 与二进制一致 | `C13FF666-F650-3B26-808C-1E7855C6CCC3` |

## 追加验证：灵动岛歌词（Live Activity）接线（2026-11-11）

用户反馈：歌词本身已正常（有的歌没有属插件侧问题，非 bug），但**灵动岛不显示歌词**。

根因不是代码逻辑，而是**接线缺失**：`overlay/ios/LiveActivity/` 下三个 Swift 文件既不在 pod 的 `source_files`，也不在任何 target 的 Sources phase —— 即"从未被编译"。于是：

```
MFLiveActivityController 类不存在
→ NSClassFromString(@"MFLiveActivityController") == nil
→ MusicFreeLiveActivityModule 的 start / updateLyric / stop 全部 early-return
→ 灵动岛永远空白（且完全无日志、无报错）
```

而 ActivityKit 的硬性约束是：锁屏/灵动岛的 UI **只能由 Widget Extension（`ActivityConfiguration`）渲染**，主 app 进程只能 start/update/end。所以必须真的加一个 extension target。

### 落地方式

新增 `scripts/inject_live_activity.py`，由 `inject_ios.py` 在 `inject_pbxproj` **之前**调用（让版本号正则也覆盖新 target），用固定 UUID 幂等注入 `project.pbxproj`：

| 注入对象 | 作用 |
| --- | --- |
| `PBXNativeTarget MusicFreeLiveActivity` | `com.apple.product-type.app-extension`、`IPHONEOS_DEPLOYMENT_TARGET=16.1`、`com.musicfree.ios.unsigned.lyrics` |
| app target Sources 追加 | `MusicFreeLyricAttributes.swift`、`MusicFreeLiveActivityController.swift` |
| extension Sources | `MusicFreeLiveActivityWidget.swift`、`MusicFreeLyricAttributes.swift` |
| `PBXCopyFilesBuildPhase`（`dstSubfolderSpec=13`） | 把 `.appex` 拷进 `PlugIns` |
| `PBXTargetDependency` / `PBXContainerItemProxy` | 保证先构建 extension |

每个锚点都断言"全文唯一"，缺失即抛错（上游改版不会静默失配）；`verify_definitions()` 额外自检所有 24-hex 引用都有定义对象。

### 一个会直接编译失败的坑

`MusicFreeLyricAttributes` 继承 `ActivityAttributes`（iOS 16.1+），但同一个文件**也被编进 deployment target = 15.1 的 app target** → 必须加 `@available(iOS 16.1, *)`，否则 app target 直接报 "ActivityAttributes is only available in iOS 16.1 or newer"。

| # | 验证项 | 结果 |
| --- | --- | --- |
| 34 | `prepare.sh` | **56 项 0 失败**（新增 10 条 target/embed/sources/deployment 断言） |
| 35 | 二次注入幂等 | `LiveActivity target: already present` |
| 36 | `plutil -lint project.pbxproj` | OK（仅语法；结构另由 UUID 自检覆盖） |
| 37 | `py_compile` / `bash -n` | 全部通过 |
| 38 | CI `43017023240` | **成功**（21m52s；工程解析 + Swift 编译 + archive 全链路通过） |
| 39 | 包内含扩展 | `PlugIns/MusicFreeLiveActivity.appex`，`NSExtensionPointIdentifier = com.apple.widgetkit-extension` |
| 40 | 扩展确实链了 ActivityKit | `otool -L`：`ActivityKit` / `WidgetKit` / `SwiftUI` 全部存在（extension 侧非 weak） |
| 41 | 主 app 侧控制器已编入 | `strings MusicFree` 命中 `MFLiveActivityController`；`ActivityKit` 为 **weak** 链接（`@available` 生效，iOS 15.1 也能启动） |
| 42 | Swift 运行时 | 未嵌入，走系统 `/usr/lib/swift/libswiftCore.dylib`（iOS 12.2+ 内置），包体仅 +25 KB |
| 43 | dSYM | 两个：app `B85E8C23…`、extension `85A03AA3…`（与 appex 二进制一致） |

### 使用与自签注意

- 入口：**设置 → 歌词 → 桌面歌词**（开启后才会 `showStatusBarLyric` → 启动 Live Activity；iOS 上它同时驱动应用内悬浮歌词卡片 + 灵动岛/锁屏）。
- 自签必须**先签 `.appex`、再签 `.app`、然后重打包 `Payload/`**；`verify_signed_ipa.sh` 已包含 appex 校验。AltStore / Sideloadly 会自动处理。
- 若签名工具改了 app 的 bundle id，务必同步把 extension 的 `com.musicfree.ios.unsigned.lyrics` 一起改（extension id 必须是 app id 的前缀），否则安装被拒。

## 追加验证：插件安装失败（订阅源）(2026-11-11)

用户反馈：**上个版本还能用的插件，现在安装失败**，并给出订阅源
`https://fastly.jsdelivr.net/gh/Huibq/keep-alive/Music_Free/myPlugins.json`。

### 先排除"版本回退"

| 对比项 | 结果 |
| --- | --- |
| `UPSTREAM_REF` | 始终 `v1.0.0-beta.4`，自首次同步起未变（`git log -- UPSTREAM_REF` 只有 1 次提交） |
| 两版 `Info.plist` | **逐键完全相同**（含 ATS / `NSSupportsLiveActivities`） |
| 两版 `main.jsbundle` | 差异仅 1 处：bundle 内嵌的**构建产物路径字符串**（`Build/Products/...`），其后全部字节因长度位移而整体偏移；无逻辑差异 |
| 包结构差异 | 仅新增 `PlugIns/MusicFreeLiveActivity.appex` |

即：**JS 侧没有改动**，插件安装代码路径与上一版完全一致。

### 真正的根因：2 秒超时

`core/pluginManager/plugin.ts:36`

```ts
axios.defaults.timeout = 2000;
```

这个 2s 是**给插件运行期请求**（播放时调平台 API）做节流的，避免平台挂掉时卡死 UI。但
`installPluginFromUrl` 复用了同一个 axios 实例去**下载插件包本身**：

```ts
await axios.get(url, { headers: { "Cache-Control": "no-cache", ... } })
```

实测（本机 → jsDelivr，多次采样）：

| 指标 | 数值 |
| --- | --- |
| 冷 TLS 握手 | **1.10 / 1.20 / 0.96 s** |
| 26 KB 插件（`xiaomi.js`）端到端 | **1.93 s**，速度约 13 KB/s |
| 其余插件体积 | 15.4 – 26.1 KB |

也就是说 2s **不是余量，而是实测值本身**。叠加 `Cache-Control: no-cache` 强制回源、
订阅源里 5 个插件串行下载、移动网络抖动，必然出现
`timeout of 2000ms exceeded` → UI 统一报"安装失败"。

这也解释了"以前能用"：jsDelivr 边缘节点缓存命中时首字节极快，一旦回源就顶到上限。

### 修复（注入式，锚点断言 + 幂等）

| 文件 | 改动 |
| --- | --- |
| `core/pluginManager/index.ts` | `installPluginFromUrl` 的下载请求加 `timeout: 30000`；**运行期请求仍保持 2s** |
| 同上 | 超时单独识别（`ECONNABORTED` 或 message 含 timeout）→ 提示"下载超时，请检查网络后重试" |
| `pluginList.tsx` | 订阅清单（`.json`）拉取同样 `timeout: 30000` |
| `pluginList.tsx` | `text.endsWith(".json")` → `inputUrl.endsWith(".json")`：后缀判断用的是未 trim 的原始输入，而请求用的是 trim 后的 URL，粘贴带换行的链接会被当成插件下载 → 解析失败 |

### 插件代码本身没问题（本地实证）

按 app 的加载方式（`Function(...)` 包裹 + `_require` 注入）在 Node 里跑了一遍订阅源全部 5 个插件：

| 插件 | 结果 |
| --- | --- |
| `xiaoqiu.js` | OK，platform=小秋音乐，ver=0.3.0，11 个方法 |
| `xiaowo.js` | OK，platform=小蜗音乐，ver=0.3.0，12 个方法 |
| `xiaoyun.js` | OK，platform=小芸音乐，ver=0.3.0，13 个方法 |
| `xiaogou.js` | OK，platform=小枸音乐，ver=0.3.0，8 个方法 |
| `xiaomi.js` | OK，platform=小蜜音乐，ver=0.3.0，12 个方法 |

依赖表（`packages`）中 `cheerio / crypto-js / axios / dayjs / big-integer / qs / he / webdav` 齐全。

| # | 验证项 | 结果 |
| --- | --- | --- |
| 44 | `prepare.sh` | **60 项 0 失败**（新增 4 条 timeout / trim 断言） |
| 45 | 二次注入幂等 | 两个文件均 `already present` |
| 46 | `ts.transpileModule` | 0 语法错误 |
| 47 | CI `43022942754` | **成功**（26m04s；工程解析 / Swift / archive 全链路通过） |
| 48 | IPA | 6,962,617 B，SHA-256 `77356a49…`，`verify_ipa.py` VERIFY OK（appex + hermes 递归签名提示正常） |
| 49 | 补丁是否进包 | 新 `main.jsbundle` **6,321,985 B** vs 上一版 **6,321,776 B**（+209 B）；`下载超时，请检查网络后重试` 以 **UTF-16LE** 存在于新包 **1** 次、旧包 **0** 次 |
| 50 | dSYM | app `B85E8C23…`、appex `85A03AA3…`，与包内二进制 UUID 逐一吻合 |

> 说明：Hermes 字节码会把标识符压缩、把数字放进常量池，所以用 `grep "timeout: 30000"`
> 之类的 ASCII 探针在 bundle 上**不可靠**（新旧包都会命中/都不命中）。可靠做法是搜索
> **UTF-16LE 编码的中文字符串字面量**，并比较两个 bundle 的体积差。

---

## 第一批：配置、工程与文档收尾（2026-11-12）

范围来自 `FEATURE_ROADMAP.md` 第 1 批：O0.1（文档 + 产物校验）、O6（CI 缓存 + 语法门禁）、N4（URL scheme）、N5（文件类型导入）、O5（插件生态收尾）。均为源码 / 工程配置 / 文档侧改动，已由提交 `3b78436` 推送并在 CI run `43142605387` 中重建出包（见下方「云端重建」）。

### 改动

| 文件 | 内容 |
| --- | --- |
| `scripts/inject_ios.py` | `read_text_exact()` / `write_text_exact()` 保持 CRLF；`inject_info_plist()` 注入 `CFBundleURLTypes`（`musicfree`）、2 个 `CFBundleDocumentTypes`（`MusicFree audio` / `MusicFree LRC`）与 6 个 `UTImportedTypeDeclarations`；新增 `inject_plugin_platform_env()`（`os` / `platform` → `Platform.OS`，补 `react-native` 导入）与 `inject_network_timeouts()`（`checkUpdate.ts` / `backupSetting.tsx` 裸 `axios.get` → `timeout: 30000` + URL trim） |
| `scripts/verify_adaptation.py` | 新增 scheme / 文档类型 / 插件平台标识 / 超时断言，静态校验 60 → **69 项** |
| `scripts/verify_ipa.py` | 缺 `.appex`、`NSExtensionPointIdentifier` 不是 `com.apple.widgetkit-extension` 均加入 `failed`，不再只打印提示 |
| `scripts/selftest_verify_ipa.py`（新增） | 行为测试：真包必须通过；删掉所有 `/PlugIns/` 条目的假包必须返回非 0 且报 `Widget Extension` |
| `scripts/check_injected_ts.js`（新增） | 对 9 个注入后的 TS/TSX 跑 `ts.transpileModule` 语法检查（不做全量 `tsc`，上游自带类型错误） |
| `scripts/verify_signed_ipa.sh` | 增加「一个 `.appex` 都没有 → 硬失败」，防止签名工具静默丢掉 `PlugIns/`；输出新增 `extensions checked` |
| `.github/workflows/build-ios-unsigned.yml` | 新增脚本语法门禁、`actions/cache`（`~/.npm` + `upstream/ios/Pods`，key 含 lockfile / Podfile / podspec）、注入 TS 语法检查、IPA verifier 行为测试；缓存步骤放在 `prepare.sh` 之后（此时才存在 `upstream/`） |
| `README.md`、`docs/*.html`、`outputs/*.html` | 修正「默认未接线 / 需一次性接线 / 41 项 / 可选增强」等过时表述；签名指南补 `.appex` 签名顺序、扩展描述文件与两份 entitlements（扩展 id `com.musicfree.ios.unsigned.lyrics`） |

### 本地验证结果

| # | 验证项 | 结果 |
| --- | --- | --- |
| 51 | `bash scripts/prepare.sh` | **69 项 0 失败** |
| 52 | 二次重放幂等 | 519 个文件聚合哈希 `ae1308b2…` 两次一致 |
| 53 | `plutil -lint` | app `Info.plist`、`project.pbxproj`、extension `Info.plist` 均 OK |
| 54 | 语法门禁 | `py_compile scripts/*.py`、`node --check`、`bash -n scripts/*.sh` 全通过 |
| 55 | 注入后 TS 语法 | `{"files":9,"failures":0}` |
| 56 | CI workflow YAML | 两个 workflow `YAML.load_file` 通过 |
| 57 | CRLF 保持 | `backupSetting.tsx` 306/306 行仍为 CRLF |
| 58 | plist 注入值 | scheme `['musicfree']`；文档类型 2 个；自定义 UTI 6 个 |
| 59 | `verify_ipa.py` + 行为测试 | 真包 VERIFY OK；删掉 4 个 `PlugIns` 条目的假包被判 `VERIFY FAILED` |
| 60 | `verify_signed_ipa.sh` 新护栏 | 构造无 `.appex` 假包 → 退出码 1，输出 `no PlugIns/*.appex found` |

### 仍待验证

- `musicfree://install/…` 能否从 Safari 唤起 App；「文件」App 分享菜单是否出现 MusicFree（需新 IPA + 真机）。
- CI 缓存的实际加速效果（需一次完整云端构建）。
- `verify_signed_ipa.sh` 的 `set -uo pipefail` 缺 `-e`、对 `embedded.mobileprovision` / entitlements 缺失只给 `[WARN]`（`DEFECT_REVIEW.md` L3），本批未改。
- `DEFECT_REVIEW.md` 的 H3/H4 与 `FEATURE_ROADMAP.md` 第 2 批（灵动岛信息完整化、音频会话、歌词精度）未动。

### 云端重建与产物验收（2026-11-12）

提交 `3b78436` 推到 `main` 后手动触发 `build-ios-unsigned.yml`，run **`43142605387`**，head sha `3b784362ee7b26f632455c4a61f9fc09b7e312cc`，2026-11-12 02:36 UTC → 03:05 UTC，**28m37s，conclusion = success**。全部 15 个步骤通过，其中本批新增的 `Lint adapter scripts`、`Cache npm downloads and CocoaPods`、`Syntax-check injected TypeScript`、`Behaviour-test the IPA verifier` 均为 ✓。

| # | 验收项 | 结果 |
| --- | --- | --- |
| 61 | CI 全步骤 | success；annotation 仅有 Node 20 → Node 24 的 actions 弃用提示与 macOS arm64 排队提示，均不影响构建 |
| 62 | 新 IPA | `outputs/MusicFree-v1.0.0-beta.4-unsigned.ipa`，**6,963,340 B**，SHA-256 `aaace2c405ef967e699e83848a9f5258aea63bb650772d01c63831fe91bcd1a0` |
| 63 | `verify_ipa.py` | VERIFY OK：未签名、含 `main.jsbundle`、4 个启动屏资源、`hermes.framework`、`MusicFreeLiveActivity.appex`（extension point 正确） |
| 64 | verifier 行为测试 | 真包通过；删掉 4 个 `PlugIns` 条目的假包被判 VERIFY FAILED |
| 65 | **第一次实际验收 plist 注入是否进包** | 从 IPA 内解出 `Payload/MusicFree.app/Info.plist`：`CFBundleURLSchemes = ['musicfree']`、`CFBundleDocumentTypes = ['MusicFree audio', 'MusicFree LRC']`、自定义 UTI 6 个（`lrc/flac/ogg/ape/opus/wma`）→ `BATCH1 ARTIFACT CHECK: OK` |
| 66 | dSYM | app `B85E8C23-28A3-371B-8678-F7EFAE87CB46`、appex `85A03AA3-D086-3CCB-8904-8B224BBE0F46`，与包内两个 Mach-O 的 `LC_UUID` 逐一吻合 |
| 67 | 归档 | 旧包备份为 `outputs/MusicFree-v1.0.0-beta.4-unsigned_pre-batch1.ipa`；旧 dSYM 备份为 `outputs/dSYM-pre-batch1/`；云端原始产物留存在 `outputs/cloud-build/batch1/` |

**关于缓存效果（如实记录）**：本次是缓存冷启动，且 runner 有容量排队提示，28m37s 比上一轮 `43022942754` 的 25m55s 更长，**不能据此判断 O6 缓存是否奏效**，需要第二次命中缓存的构建对比。

**仍需真机确认**：Safari 打开 `musicfree://install/…` 能否唤起 App；「文件」App 长按 mp3/lrc 的分享菜单是否出现 MusicFree；含 `.appex` 的包经 Sideloadly / AltStore / ESign 重签后能否正常安装并出现锁屏 / 灵动岛歌词。

---

## 第二批：独立版本号 + 灵动岛播放体验（2026-11-12）

范围来自 `FEATURE_ROADMAP.md` 第 2 批：O0.2 → O1 → N2 → O2；**O3 音频会话按路线图仍单独一批**。用户额外要求「更新一个版本吧，不能总是一个版本号」，因此本批同时把适配版本与上游 tag 解耦为 `ADAPTER_VERSION = 1.1.0` / `ADAPTER_BUILD = 2`。

### 版本机制改动

| 文件 | 内容 |
| --- | --- |
| `ADAPTER_VERSION` / `ADAPTER_BUILD`（新增） | `1.1.0` / `2`，唯一的版本来源 |
| `scripts/bump_version.py`（新增） | `major \| minor \| patch` / `--set X.Y.Z` / `--show`；每次 bump 让 build +1，并打印预期 IPA 名 |
| `scripts/lib.sh` | `read_adapter_version()` / `read_adapter_build()` |
| `scripts/prepare.sh` | 读取并导出 `ADAPTER_VERSION` / `ADAPTER_BUILD`，日志打印适配器版本 |
| `scripts/inject_ios.py` | 新增 `read_version_files()`；`version_from_ref()` 降级为 fallback；`inject_info_plist()` 写 `MusicFreeAdapterVersion` / `MusicFreeUpstreamRef`；`inject_pbxproj()` 用适配版本替换上游 tag 与旧 `BUILD_NUMBER` |
| `upstream/ios/MusicFree/Info.plist`（生成物） | `CFBundleShortVersionString = $(MARKETING_VERSION)`、`CFBundleVersion = $(CURRENT_PROJECT_VERSION)` + 两个 provenance key |
| `upstream/ios/MusicFree.xcodeproj/project.pbxproj`（生成物） | `MARKETING_VERSION = 1.1.0;`、`CURRENT_PROJECT_VERSION = 2;` |
| `scripts/build_unsigned_ipa.sh` | 产物改名为 `MusicFree-v${VERSION}-ios-unsigned.ipa`；调用 `verify_ipa.py --expected-version "${VERSION}"` |
| `scripts/verify_ipa.py` | 新增 `--expected-version`；report 增加 `adapter_version` / `upstream_ref`；`CFBundleShortVersionString` 与 `MusicFreeAdapterVersion` 任一不符即硬失败 |
| `.github/workflows/build-ios-unsigned.yml` | 新增 `Resolve adapter version` step，把 version / build 写入 `$GITHUB_OUTPUT`；job summary 打印版本与预期 artifact 文件名 |
| `.github/workflows/sync-upstream.yml` | Release tag 改为 `ios-v${ADAPTER_VERSION}-${LATEST}`，标题同时标注适配版本与上游 tag |

### 运行时改动（Swift / ObjC / TS 三层）

| 文件 | 内容 |
| --- | --- |
| `overlay/ios/LiveActivity/MusicFreeLyricAttributes.swift` | `ContentState` 成为唯一 UI 状态来源：`title/artist/lyric/translation/previousLyric/nextLyric/isPlaying/duration/elapsed`；attributes 只剩不可变的 `source`；全部 `@available(iOS 16.1, *)` |
| `overlay/ios/LiveActivity/MusicFreeLiveActivityController.swift` | `StatePatch`(Codable) + `Snapshot` + `applyState(_ json:)` 单一入口；主线程派发；250ms 节流；`activities.isEmpty` 才 `request`，否则只 `update`；`action: "stop"` 主动 `end`；`pushType: nil` 保持本地更新；保留旧 `start` / `updateLyric` / `stop` 兼容 |
| `overlay/ios/LiveActivity/MusicFreeLiveActivityWidget.swift` | 从 `context.state` 读真实歌名/歌手；渲染 `isPlaying` 暂停态、上一句 / 当前句 / 翻译 / 下一句；`ProgressView(value: elapsed/duration)` 进度条；私有 subviews / helper 加 `@available(iOS 16.1, *)`；`mmss` 改字符串插值，避免 `String(format:)` 的 `CVarArg` 类型风险 |
| `overlay/ios/LocalPods/MusicFreeNative/MusicFreeNative/MusicFreeLiveActivityModule.m` | 只暴露 `RCT_EXPORT_METHOD(applyState:)`；`start` / `updateLyric` / `stop` 统一构造 JSON patch；`MFDispatch1` / `MFSafeString` / `MFJSON` helpers，全部 `dispatch_get_main_queue()`；删除 `MFDispatch2` 与 legacy fallback，避免两套调用链 |
| `overlay/src/native/liveActivity/index.ios.ts`（新增） | 唯一 Live Activity 状态发布器：`installed` guard 防重复注册；读 `currentMusic` / `currentLyricItem` / `lyricState.lyrics` / `lyric.showTranslation`；4Hz progress 不 1:1 转发，曲目 / 行 / 播放态 / seek 立即发，其余 ~1Hz heartbeat |
| `overlay/src/native/lyricUtil/index.ios.ts` | 不再推歌词文本给 Live Activity，只控制 App 内浮层；`showStatusBarLyric` / `hideStatusBarLyric` 直接发 `{"action":"start"/"stop"}`；**不 import `liveActivity`**，避免 `liveActivity → lyricManager → lyricUtil` 循环依赖 |
| `scripts/inject_ios.py` | `inject_bootstrap_batch2()`：加 `setupLiveActivityBridge` import、`progressUpdateEventInterval: 0.25`、在 `lyricManager.setup()` 后调用；`inject_lyric_manager_guard()`：加 `listenersReady` 防重复注册 |
| `overlay/ios/LiveActivity/README.md` | 重写为 Batch 2 state contract、JSON patch 示例、更新预算表、验证步骤 |
| `scripts/verify_adaptation.py` | 从 69 → **113 项**：版本 semver / build numeric、provenance、`ContentState` 正则结构解析、Controller 幂等与主线程、Widget 不再读 `attributes.title`、不使用 iOS-16-only `timerInterval:` API、RN 桥 / TS 发布器 / bootstrap / lyricManager 注入断言 |
| `scripts/check_injected_ts.js` | 9 → **12 个**文件，新增 `lyricManager.ts`、`liveActivity/index.ios.ts`、`lyricUtil/index.ios.ts` |

### 本地验证结果

| # | 验证项 | 结果 |
| --- | --- | --- |
| 68 | `bash scripts/prepare.sh`（两次） | **113 项 0 失败**，`{"checks":113,"failed":0,"failures":[]}`；日志 `adapter version : 1.1.0 (build 2)` |
| 69 | 二次重放幂等 | 聚合哈希 `dbe0e2f65eba9bdfb66786af49bfaae82d4d10f1` 两次一致，`IDEMPOTENT=True` |
| 70 | 注入后 TS 语法 | `{"files":12,"failures":0}` |
| 71 | Swift 语法 | 3 个文件 `swiftc -parse` 全部 OK |
| 72 | `plutil -lint` | app `Info.plist`、`project.pbxproj`、extension `Info.plist` 均 OK |
| 73 | 语法门禁 | `py_compile` / `node --check` / `bash -n` 全通过 |
| 74 | CI workflow YAML | 两个 workflow `YAML.load_file` 通过 |
| 75 | 版本注入实测 | `MARKETING_VERSION = 1.1.0;`、`CURRENT_PROJECT_VERSION = 2;`、`MusicFreeAdapterVersion = 1.1.0`、`MusicFreeUpstreamRef = v1.0.0-beta.4` |
| 76 | `bump_version.py --show` | `{"adapter_version":"1.1.0","adapter_build":2,"upstream_ref":"v1.0.0-beta.4"}` |
| 77 | **旧包版本门禁（反向测试）** | 第一批 IPA + `--expected-version 1.1.0` → `rc=1`、`VERIFY FAILED: CFBundleShortVersionString is '1.0.0'` / `MusicFreeAdapterVersion is None`，证明旧包不会被当作 v1.1.0 交付 |
| 78 | `selftest_verify_ipa.py` | 真包通过；删掉 `PlugIns/` 的假包仍被判 `VERIFY FAILED` |
| 79 | RN 模块依赖方向 | `liveActivity → lyricManager → lyricUtil` 单向，`lyricUtil` 无 `import ... liveActivity` |
| 80 | 循环依赖 / 兼容路径 | 删除 `MFDispatch2` 与 legacy Swift shim fallback，桥接链路唯一 |

**如实说明的边界**：`swiftc -parse` 只做语法解析，当前工作机只有 CommandLineTools、没有 iOS SDK（已实测 `SDK "iphoneos" cannot be located`），因此 SwiftUI / ActivityKit 的**类型检查与完整编译链接只能由 CI 的 Xcode 16.2 证明**。为降低这类只能在完整 Xcode 下暴露的风险，本批刻意不用 `ProgressView(timerInterval:)` / `Text(timerInterval:)`，进度条改由 1Hz `elapsed` 驱动普通 `ProgressView(value:)`，并给所有引用 availability-gated `ContentState` 的私有 subview / helper 加 `@available(iOS 16.1, *)`。

**仍待真机确认**：切歌后锁屏 / 灵动岛标题与歌手是否刷新、暂停态、翻译与上下句、进度条推进、关闭桌面歌词或播放结束后实时活动是否收起，以及第一批遗留的 `musicfree://` 深链与「文件」App 分享菜单。
