# MusicFree iOS Adapter

把官方 [maotoumao/MusicFree](https://github.com/maotoumao/MusicFree)（React Native 0.76.5 / Expo 52）改造成可以构建出**未签名 `.ipa`** 的 iOS 工程，并让上游发新版时自动同步、自动重新出包。

**这不是官方 iOS 版**。官方 README 明确「目前只支持 Android 和 Harmony OS」，从无 IPA 产物。本工程是在官方源码之外加的一层适配，产物需自行重签后安装，且沿用上游 AGPL-3.0 许可。

当前锁定上游版本：`v1.0.0-beta.4`（见 `UPSTREAM_REF`）；**适配层独立版本号 `1.1.0`（build `2`）**，见 `ADAPTER_VERSION` / `ADAPTER_BUILD`。上游 tag 只决定代码来源，不再决定 App 版本、build number、IPA 文件名或 Release tag —— 否则每轮适配改动都还得叫 `1.0.0` / `v1.0.0-beta.4`，分不清「上游没变、适配变了」的情况。

**当前状态（2026-11-12，第二批 v1.1.0 已重建出包）**：适配层第二批（灵动岛信息完整化、幂等生命周期、歌词精度）已完成源码改造、本地全量校验与**云端完整编译**。提交 `51c06fa` → CI run `43164883366`（22m23s，22 步全绿），产物 `outputs/MusicFree-v1.1.0-ios-unsigned.ipa`，6,980,457 B，SHA-256 `5aa12af1…1c8a5ecb`（完整值见 `VERIFICATION.md`）。`verify_ipa.py --expected-version 1.1.0` 已 VERIFY OK，旧包因版本不符会被拒收。第一批的 `MusicFree-v1.0.0-beta.4-unsigned.ipa`（SHA `aaace2c4…`）已备份为 `*_pre-batch2.ipa`。

已验收产物为 iOS 15.1+、arm64、未签名、内嵌 `main.jsbundle`，含 `SplashScreen.storyboardc`、`musicfree` URL scheme、音频 / `.lrc` 文档类型、`MusicFreeAdapterVersion = 1.1.0` / `MusicFreeUpstreamRef = v1.0.0-beta.4`，并**内嵌 `PlugIns/MusicFreeLiveActivity.appex`** —— 灵动岛 / 锁屏歌词已由 `scripts/inject_live_activity.py` 自动接线，不再是「源码预留」。`verify_ipa.py` 现在对缺 `.appex` 或 extension point 错误的包直接判失败，并有行为测试兜底。

两类历史启动故障已修复：① Expo SDK 52 原生启动硬编码 `UIStoryboard(name: "SplashScreen")`，旧包缺该资源；② [GitHub `macos-15` runner 镜像缺陷](https://github.com/actions/runner-images/issues/13560) 导致 `ibtool` 报 `iOS 18.2 Platform Not Installed.`（与 storyboard 内容无关）。CI 里无条件执行 `xcodebuild -downloadPlatform iOS` 并加 `ibtool` 冒烟测试。

**自签时必须递归签名 `Frameworks/hermes.framework`，且先签 `PlugIns/*.appex`、再签 `.app`**；漏签扩展不会让 App 闪退，但会让灵动岛静默失效或安装被拒。见 [`docs/signing-and-crash-guide.html`](docs/signing-and-crash-guide.html)。完整记录见 `VERIFICATION.md`。

> **第一批改动已完成并重建出包**：`musicfree://` URL scheme、音频与 `.lrc` 的文件导入、插件沙盒平台标识与网络超时收尾、CI 缓存与语法门禁、产物校验加固、签名文档修正，提交 `3b78436`。`prepare.sh` 当时为 **69 项 0 失败**，CI run `43142605387` 全步骤通过（含脚本语法、注入 TS 语法、`ibtool` 冒烟、archive、verifier 行为测试）；新包的 `Info.plist` 已实测带 `musicfree` scheme、2 个文档类型与 6 个自定义 UTI。**深链唤起与「文件」App 分享菜单仍需真机确认**。旧包 `77356a49…` 已备份为 `outputs/MusicFree-v1.0.0-beta.4-unsigned_pre-batch1.ipa`。

> **第二批已落地并解耦版本（v1.1.0）**：`ADAPTER_VERSION = 1.1.0` / `ADAPTER_BUILD = 2`，`MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` 与 `CFBundleShortVersionString` / `CFBundleVersion` 全部由它们生成；IPA 内另写 `MusicFreeAdapterVersion` / `MusicFreeUpstreamRef` 两个 provenance key，`bump_version.py` 负责后续升版。改动覆盖 O0.2 / O1 / N2 / O2：所有 UI 状态移入 `ContentState`，`start` 幂等（已有活动只 `update`）、`stop` 主动收起、`lyricManager.setup()` 监听去重；锁屏 / 灵动岛显示真实歌名歌手、暂停态、翻译与上下句、进度条；RNTP 4Hz 进度事件经 ~1Hz 心跳与 Swift 250ms 节流后才写入 ActivityKit。O3（音频会话）按路线图仍单独一批。`prepare.sh` 现为 **113 项 0 失败**，注入后 **12 个** TS/TSX 语法检查、3 个 Swift `swiftc -parse`、二次注入幂等、旧包版本拒收测试均通过。**上述灵动岛行为仍需真机确认**。云端重建：提交 `51c06fa` → CI run `43164883366`（22m23s，22 步全绿，含 Xcode 16.2 对第二批 Swift / ObjC 改动的完整编译链接；缓存命中 primary key，比第一批冷启动 28m37s 快约 6 分钟）。产物 6,980,457 B，SHA-256 `5aa12af1963b4ad2d0093496a988fafd2c77695a14901728aa15864e1c8a5ecb`；两份 dSYM 的 UUID `2AA98472-E134-3E9E-933F-9D9D03285AE2` / `EB845396-A0C4-3E0E-9BC7-86DEE998D74F` 与包内 Mach-O 的 `LC_UUID` 逐一吻合。详见 `VERIFICATION.md`。

---

## 一、设计：上游零侵入，适配层可重放

```
MusicFree 官方源码 (git tag, 每次重新检出)
        │
        ├── overlay/   新增文件（上游没有）→ 直接覆盖复制，永不冲突
        │              · 3 个原生模块 index.ios.ts 平台覆盖
        │                + 1 个 Live Activity 状态发布器
        │              · 本地 Pod：iOS 原生模块（浮层 / ID3 / 覆盖层）+ podspec
        │              · LiveActivity/：灵动岛 / 锁屏实时活动 Swift 源码
        │                （inject_live_activity.py 自动接线 → .appex 进包）
        │              · Podfile.properties.json
        │
        ├── inject_ios.py  幂等注入（内容感知，不依赖固定行号）
        │              · Podfile 挂本地 Pod、关新架构（RCT_NEW_ARCH_ENABLED=0）
        │              · Info.plist 补后台音频 / ATS / 文件共享 / 实时活动
        │                / musicfree:// scheme / 音频与 .lrc 文档类型
        │              · pbxproj 换 Bundle ID、按 ADAPTER_VERSION / ADAPTER_BUILD
        │                写版本号、启动屏改名为 SplashScreen
        │              · 生成 SplashScreen.storyboard（Expo 原生启动必需）
        │              · bootstrap.ts / index.tsx：iOS 跳过 Android-only 启动调用
        │              · plugin.ts / checkUpdate.ts / backupSetting.tsx：
        │                插件沙盒标识改 Platform.OS、下载/检查/恢复请求 30s 超时
        │              · 调用 inject_live_activity.py 接好 Widget Extension
        │
        └── scripts/   prepare → verify → build → verify_ipa
                       sync_upstream.py（检测新 tag、失败自动回滚）
                       .github/workflows（macOS runner 云端构建 + 每日同步）
```

关键取舍：**不用 `.patch` 文件改上游源码**。上游以后改 `Podfile` / `Info.plist` / `pbxproj` 时，固定上下文的补丁必然失效；而「新增文件 + 幂等注入」每次重新检出后重放一遍即可，冲突面几乎为零。这也是「后续能同步更新」能落地的原因。

`prepare.sh` 是幂等的：先 `git reset --hard` + `git clean -fd` 把上游恢复干净，再重新复制 overlay、重新注入、重新校验。跑几次结果都一样。

---

## 二、它具体修了什么

上游 `ios/` 只是 RN 模板骨架；业务依赖的 3 个自定义原生模块只有 Kotlin 实现。iOS 上 `NativeModules.X` 为 `undefined`，其中状态栏歌词模块在**模块加载时**就会读属性直接崩溃。

| 上游阻塞点 | 适配方式 |
| --- | --- |
| `NativeModules.LyricUtil` 为 undefined，启动即崩 | `overlay/src/native/lyricUtil/index.ios.ts`：Metro 平台后缀覆盖，保留 `NativeTextAlignment` 枚举与全部方法，委托本地 Pod 的浮层 + 灵动岛联动 |
| `NativeModules.NativeUtils`（bootstrap / 面板 / 抽屉要用） | `index.ios.ts` 覆盖：优先本地 Pod，缺 Pod 时回退纯 JS `Dimensions.get('window')` |
| `NativeModules.Mp3Util`（本地音乐元数据） | `index.ios.ts` 覆盖：优先本地 Pod，缺 Pod 时返回空元数据，保证导入流程不崩 |
| 3 个原生模块没有 iOS 实现 | `ios/LocalPods/MusicFreeNative`：Objective-C 实现的 `NativeUtils` / `Mp3Util` / `LyricUtil` + Live Activity RN 桥，用 CocoaPods 链接（Pod 本身不改 pbxproj 源文件列表；**Swift Widget Extension 由 `inject_live_activity.py` 单独注入 target**） |
| `Info.plist` 无后台音频、ATS 限制，也没有 iOS 系统入口 | 幂等注入 `UIBackgroundModes=audio`、`NSAllowsArbitraryLoads`、`UIFileSharingEnabled`、`NSSupportsLiveActivities`、`CFBundleURLTypes`（`musicfree`）、`CFBundleDocumentTypes` + `UTImportedTypeDeclarations`（音频与 `.lrc`） |
| Expo SDK 52 原生启动硬编码 `UIStoryboard(name: "SplashScreen", bundle: nil)`，上游 RN 模板只有 `LaunchScreen.storyboard`，pod 也不自带 → 找不到就抛异常，真机打开即闪退 | 从上游 storyboard 生成一份最小 `SplashScreen.storyboard`，把 pbxproj 中 7 处文件名引用改为同名，并设 `UILaunchStoryboardName = SplashScreen`；系统启动屏与 Expo 共用一份 `SplashScreen.storyboardc` |
| `macos-15` runner 上 `ibtool` 编译任何 storyboard 都报「iOS 18.2 Platform Not Installed」 | **不是工程问题**：[`actions/runner-images#13560`](https://github.com/actions/runner-images/issues/13560) 证实该镜像移除了旧 Xcode 的 iOS runtime。CI 里先 `xcodebuild -downloadPlatform iOS`，再用 `ibtool --compile` 冒烟测试；`-sdk iphoneos`、精简 storyboard XML 都修不了（run `42853265361`、`42857755459` 已分别复现失败） |
| 上游启动流程在 iOS 上误用 Android API | `bootstrap.ts` 的 Android 权限分支改为 `} else if (Platform.OS === "android") {`，不再调用 `PERMISSIONS.ANDROID.*`；`src/entry/index.tsx` 顶层的 `StatusBar.setBackgroundColor` / `setTranslucent` 同样按平台门控 |
| Bundle ID 是 RN 模板值、版本恒为 1.0.0 | 改为 `com.musicfree.ios.unsigned`；`MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` 由 `ADAPTER_VERSION` / `ADAPTER_BUILD` 生成，`Info.plist` 另写 provenance key，**与上游 tag 解耦** |
| RN 0.76 默认开新架构 / bridgeless，真机第二份 `.ips` 显示启动崩溃 | `ios/Podfile.properties.json` 写 `newArchEnabled=false` + Hermes，**并且** `inject_ios.py` 往 `Podfile` 注入 `ENV['RCT_NEW_ARCH_ENABLED'] = '0'` —— Expo 会忽略 properties 文件，必须两处都设 |
| 插件沙盒把运行环境谎报成 Android、下载/检查/恢复请求继承 2s 全局超时 | `plugin.ts` 的 `os` / `platform` 改 `Platform.OS`；`pluginManager/index.ts`、`pluginList.tsx`、`checkUpdate.ts`、`backupSetting.tsx` 给下载类请求独立 `timeout: 30000`，运行期请求仍保持 2s 节流 |

其余 Android 痕迹（`BackHandler`、已有的 `Platform.OS === "android"` 分支、`react-native-fs`）本身都有 iOS 实现或已有条件分支。所有对上游文件的改写都集中在 `inject_ios.py` 中，按**内容锚点**做最小条件化，覆盖 `Podfile` / `Info.plist` / `project.pbxproj` / `bootstrap.ts` / `index.tsx` / `plugin.ts` / `checkUpdate.ts` / `backupSetting.tsx` 等；`prepare.sh` 每轮从干净 tag 重放一次。锚点一旦变化，注入器会明确报错，而不是静默产出一个装上去就崩的包。`verify_adaptation.py`（113 项）、`check_injected_ts.js`（注入后 12 个 TS/TSX 语法）、`selftest_verify_ipa.py`（产物行为）与 `verify_ipa.py --expected-version`（版本硬校验）是对应的四道护栏。

> **签名后打开闪退 / 灵动岛没歌词？** 见 [`docs/signing-and-crash-guide.html`](docs/signing-and-crash-guide.html)：区分「IPA 启动链问题」「自签未递归签名 `hermes.framework`」「`.appex` 漏签」，含完整 `codesign` 顺序、两份 entitlements 与崩溃日志定位方法。

### 三个 Android 能力的 iOS 原生替代（不再只是 no-op）

Android 的三项能力在 iOS 上不做「照搬」，而是换成 iOS 自己的形态：

| Android 原能力 | iOS 方案 | 落地位置 | 状态 |
| --- | --- | --- | --- |
| 状态栏 / 悬浮窗歌词 | App 内**可拖动歌词浮层**（透明 UIWindow，非卡片区域触摸穿透） | `LyricUtilModule.m` | 默认启用 |
| 状态栏 / 悬浮窗歌词 | **灵动岛 / 锁屏实时活动**（ActivityKit + Widget Extension） | `overlay/ios/LiveActivity/` + `inject_live_activity.py` | 已自动接线，随包产出 `.appex` |
| 内嵌歌词读取（jaudiotagger `FieldKey.LYRICS`） | AVFoundation 读 ID3v2 `USLT`/`SYLT`、iTunes `©lyr` 帧 | `Mp3UtilModule.m` | 默认启用 |
| ID3 标签写入（改写音频文件） | **应用内元数据覆盖层**：编辑结果存 `Documents/`，读取时与文件标签合并，不碰原始音频 | `Mp3UtilModule.m` | 默认启用 |

补充说明：

- 上游 `plugin.ts` 的 `getLyric()` 在内嵌歌词为空时会回退到同名 `.lrc`，因此**外置歌词一直可用**。
- 上游 TS/UI 层**从未调用** `setMediaTag` / `getMediaTag`（只有接口声明和 Android 原生实现），所以覆盖层刻意做在 Pod 内，让 `getBasicMeta` / `getMediaMeta` / `getLyric` 直接生效，无需改上游源码。
- 本地音乐的标题/艺术家/专辑/时长/封面由 AVFoundation 提供；插件协议、播放、下载、WebDAV 等 JS 层能力不受影响。
- 灵动岛模块通过 `NSClassFromString` 运行时解析 Swift 控制器。这条降级路径**仍然保留但已不是默认状态**：`prepare.sh` 每轮会调用 `scripts/inject_live_activity.py`，把 Swift 源码、Widget Extension target 与 `PlugIns` 拷贝阶段写回重新检出的 `project.pbxproj`（因为 `upstream/` 每次都会被 `git clean`，接线必须可重放）。`verify_ipa.py` 会拒收没有 `.appex` 的产物，防止再次静默回退。说明见 `overlay/ios/LiveActivity/README.md`。

### 本轮新增的 iOS 系统入口（第一批）

上游代码里已经写好了处理能力，但工程配置一直没开；这批只补配置，不动业务逻辑：

| 能力 | 注入内容 | 激活的上游代码 | 状态 |
| --- | --- | --- | --- |
| 插件一键安装深链 | `CFBundleURLTypes` → `musicfree` | `bootstrap.ts` 的 `musicfree://install/…`、`.js` 安装、本地媒体分支，以及 `Linking.getInitialURL()` | 已进包，待真机确认 |
| 从「文件」App 导入歌曲 / 歌词 | `CFBundleDocumentTypes` + `UTImportedTypeDeclarations`（`public.audio`、`public.mp3`、`public.mpeg-4-audio`、`wav` 与自定义 `flac/ogg/ape/opus/wma/lrc`） | 系统把文件复制进 `Documents/Inbox` 后复用既有 `handleLinkingUrl` | 已进包，待真机确认 |
| 插件沙盒平台身份 | `plugin.ts` 的 `os` / `process.platform` 由硬编码 `"android"` 改为 `Platform.OS`，并补 `react-native` 导入 | 依赖平台字段判断行为的插件 | 已注入 + 静态断言 |
| 网络超时收尾 | `checkUpdate.ts`、`backupSetting.tsx` 的裸 `axios.get` 加 `timeout: 30000`、URL trim；插件运行期请求仍保持 2s 节流 | 版本检查、备份恢复 | 已注入 + 静态断言 |

`backupSetting.tsx` 是上游少见的 CRLF 文件，注入器为此改用 `read_text_exact()` / `write_text_exact()`，避免整文件换行风格被改写。

### 第二批：独立版本号 + 灵动岛播放体验（v1.1.0）

**版本号不再等于上游 tag。** `UPSTREAM_REF` 只负责「检出哪个上游版本」；App 对外版本由适配层自己的两个文件决定：

| 载体 | 值 / 来源 | 说明 |
| --- | --- | --- |
| `ADAPTER_VERSION` | `1.1.0` | `MARKETING_VERSION` → `CFBundleShortVersionString`、IPA 文件名、Release tag |
| `ADAPTER_BUILD` | `2` | `CURRENT_PROJECT_VERSION` → `CFBundleVersion`，每次 bump 自动 +1 |
| `UPSTREAM_REF` | `v1.0.0-beta.4` | 只写入 `MusicFreeUpstreamRef`，作为包内溯源信息 |
| `MusicFreeAdapterVersion` / `MusicFreeUpstreamRef` | 注入进 `Info.plist` | 解包即可知道「哪份适配 + 哪份上游」，不必靠文件名猜 |

```bash
python3 scripts/bump_version.py --show              # 查看当前版本
python3 scripts/bump_version.py patch               # 1.1.0 → 1.1.1，build +1
python3 scripts/bump_version.py --set 1.2.0         # 直接指定
```

`build_unsigned_ipa.sh` 会用 `--expected-version "${VERSION}"` 校验产物：三个 plist/pbxproj 值不一致就判失败。实测把第一批的旧包喂给 `--expected-version 1.1.0` 会返回 `VERIFY FAILED`（`CFBundleShortVersionString is '1.0.0'`、`MusicFreeAdapterVersion is None`），所以旧包不会被误交付为新版本。

**灵动岛 / 锁屏实时活动这轮从「能显示」做到「显示对」。** 根因是 `ActivityAttributes` 在 `request` 之后不可变，早期把 `title` / `artist` 放在 attributes 里，切歌时标题永远是写死的 `"MusicFree"`；`start` 每次重建活动又会堆叠卡片。

| 改动 | 做法 | 解决 |
| --- | --- | --- |
| 状态契约 | `title/artist/lyric/translation/previousLyric/nextLyric/isPlaying/duration/elapsed` 全部放进 `ContentState`，attributes 只留 `source` | 切歌、暂停、翻译、进度都能 `update` 刷新 |
| 幂等生命周期 | Swift 控制器 `applyState(_ json:)` 单一入口：有活动则 `update`、无活动才 `request`；`stop` 主动 `end`；主线程派发 + 250ms 节流 | 不再堆叠卡片 / 反复闪烁 / 后台线程碰 UI |
| RN 桥 | ObjC 只暴露 `applyState:`，`start` / `updateLyric` / `stop` 都拼成 JSON patch 走同一条链 | 消除两套调用路径 |
| 状态发布器 | 新增 `overlay/src/native/liveActivity/index.ios.ts`：module-scoped `installed` guard，读 `currentMusic` / `currentLyricItem` / `lyricState.lyrics` / 翻译开关 | 真实歌名歌手、翻译与上下句、`isPlaying` 暂停态 |
| 更新频率 | `progressUpdateEventInterval: 0.25`（4Hz）→ 曲目/行/播放态/seek 立即发，其余 ~1Hz 心跳 → Swift 250ms 节流 → ActivityKit | 歌词更贴声音，又不撞 4KB 状态预算与更新预算 |
| 进度条 | SwiftUI `ProgressView(value: elapsed/duration)`；刻意不用 iOS 16-only 的 `timerInterval:` | 本机无 iOS SDK 也能做语法门禁，CI 里不引入类型检查风险 |
| 监听去重 | `inject_lyric_manager_guard()` 给 `lyricManager.setup()` 加 `listenersReady` | 播放器错误重试不再 N 倍触发歌词事件 |
| 依赖方向 | `lyricUtil` 不 import `liveActivity`，直接发 `{"action":"start"/"stop"}` | 避免 `liveActivity → lyricManager → lyricUtil` 循环依赖 |

进度条刻意用「1Hz 推 `elapsed` + 普通 `ProgressView(value:)`」而不是 `ProgressView(timerInterval:)`：后者是 iOS 16 专属 API，当前工作机只有 CommandLineTools、没有 iOS SDK，`swiftc -parse` 无法验证其类型可用性，交给 CI 赌一次编译不划算。设计细节见 `overlay/ios/LiveActivity/README.md`。

详见 [`docs/ios-native-alternatives.html`](docs/ios-native-alternatives.html)（完整方案、系统/自签限制、产物校验与实施顺序）。

---

## 三、快速开始

### 路径 A：云端构建（推荐，本机不需要 Xcode）

```bash
cd musicfree-ios-build
bash scripts/bootstrap_github.sh musicfree-ios private   # 或 public
gh run list --repo <你的用户名>/musicfree-ios --workflow build-ios-unsigned.yml
gh run download --repo <你的用户名>/musicfree-ios -n unsigned-ipa
```

公开仓库的 macOS runner 免费；私有仓库按 10 倍费率消耗 Actions 分钟数，一个 RN 工程约 20 分钟/次。`bootstrap_github.sh` 会建仓库、推送代码、触发第一次构建。这条路已在 `Beldon1018/musicfree-ios` 上跑通：首次成功出包是 run `42845832731`；之后根据「签名后闪退」反馈做了启动链修复并重建，过程与产物见 `VERIFICATION.md`。

### 路径 B：本地构建（需要完整 Xcode）

```bash
bash scripts/prepare.sh                 # 检出上游 + 重放适配层 + 静态校验
bash scripts/build_unsigned_ipa.sh      # npm ci → pod install → Release archive → 未签名 IPA
```

产物在 `build/MusicFree-v${ADAPTER_VERSION}-ios-unsigned.ipa`（当前为 `MusicFree-v1.1.0-ios-unsigned.ipa`）。`bump_version.py` 升版后，文件名、App 版本、build number 与 Release tag 会一起变化，不再与上游 tag 混用。前置条件：完整 Xcode 16.x + `sudo xcode-select -s /Applications/Xcode.app` + CocoaPods + Node 20。**只有 CommandLineTools 是不够的**（当前这台 Intel Mac 就是这种情况），脚本会明确报错而不是给你一个假包。

国内网络可给脚本传镜像：

```bash
MUSICFREE_UPSTREAM_REPO=https://gh-proxy.com/https://github.com/maotoumao/MusicFree.git \
  bash scripts/prepare.sh
```

### 路径 C：手动同步上游

```bash
python3 scripts/sync_upstream.py --check                     # 只看有没有新版
python3 scripts/sync_upstream.py --apply                     # 升到最新 tag 并重放适配层
python3 scripts/sync_upstream.py --apply --ref v0.6.2        # 锁定某个 tag
```

`--apply` 会先跑 `prepare.sh` 的完整校验，**失败时自动把 `UPSTREAM_REF` 回滚**并打印需要人工处理的点，不会留下一个指向「适配不了的版本」的仓库状态。

---

## 四、自动同步是怎么闭环的

`.github/workflows/sync-upstream.yml` 每天 03:23 UTC 执行：

1. `check`（Ubuntu）：调 GitHub API 取最新 release tag，与 `UPSTREAM_REF` 比较。API 限流时自动回退到 `git ls-remote --tags`。
2. 有新版 → 调用 `build-ios-unsigned.yml`（`macos-15` + Xcode 16.2），把新 tag 传进去重新检出、重放适配层、出包。
3. 构建成功 → `publish`：上传 IPA 为 Release `ios-v${ADAPTER_VERSION}-<upstream-tag>`（当前 `ios-v1.1.0-v1.0.0-beta.4`），标题同时标注适配版本与上游 tag，并**提交新的 `UPSTREAM_REF`**，至此完成同步。
4. 构建失败 → **不 bump `UPSTREAM_REF`**，自动开一个 issue 附上 run 链接和排查提示。

也可以从 Actions 页面手动触发，指定任意一个上游 tag 单独构建。

---

## 五、上游大改版时需要人工看什么

自动校验（`verify_adaptation.py`）会扫描上游 JS 里所有 `NativeModules.X` 引用，一旦出现**新的** Android-only 原生模块就会报 `no uncovered native modules` 失败，不会静默出一个装上去就崩的包。届时需要：

1. 在 `overlay/src/native/<模块>/index.ios.ts` 加一个同名平台覆盖（照抄现有三个的写法）；
2. 若该模块需要真实能力，在 `overlay/ios/LocalPods/MusicFreeNative/` 加对应 Objective-C 实现；
3. 若上游改了 `Podfile` 结构导致注入锚点 `target 'MusicFree' do` 消失，`inject_ios.py` 会给出明确报错，按新结构改锚点即可；
4. 若 RN / Expo 升级，`build-ios-unsigned.yml` 里固定的 Xcode 版本可能需要跟着调。

`prepare.sh` 每次都从干净的 tag 重新构建，所以人工改动**只应该发生在 `overlay/` / `scripts/` / workflows 里**，不要直接编辑 `upstream/` —— 那会在下次 prepare 时被清掉。

---

## 六、限制与风险，如实说明

- **未签名**：产物需 Sideloadly / AltStore / ESign 自签；免费 Apple ID 通常 7 天一签。Bundle ID `com.musicfree.ios.unsigned`，最低系统由上游 `IPHONEOS_DEPLOYMENT_TARGET = 15.1` 决定。
- **必须递归签名嵌套框架与扩展**：包内含 `Payload/MusicFree.app/Frameworks/hermes.framework` 和 `Payload/MusicFree.app/PlugIns/MusicFreeLiveActivity.appex`。只签主程序时，前者会让 dyld 在启动阶段杀掉进程（「打开即闪退」），后者会让安装被拒或灵动岛静默失效。手机端签名工具需开启「签名 Frameworks / 动态库」**和「签名 App Extension」**；手动 `codesign` 顺序为 `frameworks → .appex → .app`，且扩展 id `com.musicfree.ios.unsigned.lyrics` 必须是主 id 的子前缀。完整步骤与两份 entitlements 见 [`docs/signing-and-crash-guide.html`](docs/signing-and-crash-guide.html)。
- **`verify_ipa.py` 会拒收不完整的包**：缺 `SplashScreen.storyboardc`（Expo 原生启动必需）、缺 `.appex`、或 `NSExtensionPointIdentifier` 不是 `com.apple.widgetkit-extension`，现在都直接判失败；`scripts/selftest_verify_ipa.py` 会用「故意删掉 `PlugIns/` 的假包必须被拒收」做行为验证，避免注入器与验证器的字符串自证循环。签完包后再用 `verify_signed_ipa.sh` 确认框架、扩展、deep 签名三项齐全。
- **灵动岛已不是可选项**：要求 iOS 16.1+（灵动岛形态还需 iPhone 14 Pro 及以后机型），锁屏卡片在 16.1+ 全机型可用。Widget Extension target 已自动接线、随包产出，**不要为了省事把 `.appex` 删掉**。用户在系统设置里关闭「实时活动」时控制器会安静跳过，这是预期行为。
- **编译验证状态**：本地 `prepare.sh` 现为 **113 项静态校验 0 失败**，另有注入后 12 个 TS/TSX 的语法检查、3 个 Swift 文件的 `swiftc -parse`、Python/Node/bash 语法门禁、`plutil -lint`、二次注入幂等与旧包版本拒收测试。注意 `swiftc -parse` 只做语法解析，**不能替代完整 iOS SDK 下的类型检查与编译链接**；第二批 Swift 改动的最终编译结论以 CI 为准。云端 `macos-15` + Xcode 16.2 已完成多次完整 Release archive，三个 Objective-C 模块与 Swift 实时活动源码均通过编译链接；**第二批重写的三份 Swift 源码、JSON patch 桥与 RN 状态发布器已在 run `43164883366` 中通过完整编译链接**，本地 `swiftc -parse` 的类型检查盲区至此已由 CI 覆盖；CI 里先 `xcodebuild -downloadPlatform iOS` 再加 `ibtool` 冒烟测试以绕开 runner 镜像缺陷。当前工作机没有完整 Xcode，因此**本地无法跑模拟器/真机**，只能做静态校验 + 推到仓库触发 CI；「真机不再闪退」「深链与文件导入可用」「灵动岛显示歌词」都必须由使用者在设备上确认；**第二批新增的切歌标题/歌手刷新、暂停态、翻译与上下句、进度条、关闭桌面歌词后收起，同样全部待真机验证**，若仍崩溃需按签名指南导出 `.ips` 崩溃日志。若上游升级后某个第三方 RN 依赖缺 iOS podspec，仍需按日志补 Pod 或换实现。
- **AGPL-3.0**：上游是强传染性许可，本适配层同样受其约束；仓库根目录已放 `LICENSE`（AGPL-3.0 全文，取自上游），分发 IPA 时请一并公开对应源码。
- **不是官方产物**：请勿把它当作 MusicFree 官方 iOS 版对外发布；插件可用性取决于上游音源状态。

---

## 七、目录

```
UPSTREAM_REF                     当前锁定的上游 tag（只决定代码来源）
ADAPTER_VERSION                  适配层对外版本（当前 1.1.0）
ADAPTER_BUILD                    适配层 build number（当前 2）
overlay/                        适配层新增文件（同步时全部重放）
  src/native/*/index.ios.ts      3 个 Metro 原生模块平台覆盖
  src/native/liveActivity/       第二批新增：Live Activity 状态发布器
                                 （RNTP 事件 → JSON patch → native）
  ios/LocalPods/MusicFreeNative/ iOS 原生模块（LyricUtil / Mp3Util / NativeUtils
                                 + Live Activity RN 桥）+ podspec
  ios/LiveActivity/              灵动岛 / 锁屏实时活动 Swift 源码 + 接线说明
                                 （脚本自动接线，已随包产出 .appex）
  ios/Podfile.properties.json    Expo 构建开关
scripts/
  lib.sh                        公共函数（检出/重置/复制/读版本文件）
  prepare.sh                    一键生成适配后的工程（幂等）
  inject_ios.py                 幂等注入 Podfile / Info.plist / pbxproj
                                + URL scheme / 文档类型 / 插件平台标识 / 超时
                                + 版本号与 provenance / 第二批 bootstrap 注入
                                + lyricManager 监听去重
                                + 生成 SplashScreen.storyboard
                                + bootstrap.ts / index.tsx 启动门控
  inject_live_activity.py       幂等创建 Widget Extension target 与 PlugIns 拷贝阶段
  bump_version.py               升 ADAPTER_VERSION / ADAPTER_BUILD（build 自动 +1）
  verify_adaptation.py          无需 Xcode 的静态校验（113 项）
  check_injected_ts.js          注入后 TS/TSX 语法检查（12 个文件，CI 门禁）
  sync_upstream.py              检测/应用上游新 tag，失败回滚
  build_unsigned_ipa.sh         Release archive → MusicFree-v<版本>-ios-unsigned.ipa
  verify_ipa.py                 校验未签名、含 main.jsbundle / storyboardc /
                                .appex、版本号与 provenance 匹配
  selftest_verify_ipa.py        verifier 行为测试：无 .appex 的假包必须被拒收
  verify_signed_ipa.sh          签完包后自检：框架 / extension / deep 签名
  bootstrap_github.sh           一键建仓推送并触发首次构建
docs/
  ios-native-alternatives.html  三项能力的 iOS 原生替代方案
  signing-and-crash-guide.html  自签步骤与启动闪退排查
.github/workflows/
  build-ios-unsigned.yml        macOS 云端构建（可被复用）
  sync-upstream.yml             每日同步 + 发 Release + 失败告警
upstream/                       脚本生成的上游检出（.gitignore 忽略）
build/                          构建产物（.gitignore 忽略）
```
