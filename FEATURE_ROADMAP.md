# MusicFree iOS · 功能优化与新增能力分析

> 分析日期：2026-11-12　基线：`936c036` / `UPSTREAM_REF = v1.0.0-beta.4`
> 性质：**只读分析**，未修改任何源码、脚本、工程配置或 IPA。
> 与 `DEFECT_REVIEW.md` 的关系：那一份是「哪里坏了」，本份是「还能往哪走」。缺陷中影响功能体验的部分在此列为 P0 前置项，不重复展开 22 项明细。

---

## 一、结论速览

**投入产出最高的 5 件事**（建议优先做，理由见 §3/§4）：

| 排序 | 事项 | 类型 | 成本 | 用户可感知度 |
| --- | --- | --- | --- | --- |
| 1 | 注入 `CFBundleURLTypes`（`musicfree://`） | 新增 | S | 高：激活已有但完全点不通的插件一键安装 |
| 2 | 灵动岛信息完整化（真实歌名/歌手 + 暂停态 + 切歌不重建） | 优化 | M | 高：目前锁屏卡片永远写着 "MusicFree" |
| 3 | `CFBundleDocumentTypes` 导入音频 / `.lrc` | 新增 | S–M | 高：从「文件」App 直接把歌送进 App |
| 4 | 歌词同步精度 1s → 0.25s | 优化 | S | 中高：歌词不再慢半拍 |
| 5 | iOS 音频会话 / 中断 / 锁屏进度配置 | 优化 | S–M | 高：来电、耳机拔插、锁屏拖进度 |

**一句话判断**：当前包已经「能用」，但 iOS 化程度只完成了一半 —— 上游 Android 导向的配置（播放器 options、插件 env、键盘布局）和「源码已写但系统入口没开」的能力（深链、文件导入）是最大的两块洼地；灵动岛已经接通，但内容还是个空壳。真正需要新写代码的只有灵动岛体验和少数原生入口，其余多是配置级改动。

---

## 二、现状能力盘点（基于代码核实）

| 状态 | 能力 | 证据 / 落点 |
| --- | --- | --- |
| ✅ 已可用 | 插件系统（安装/订阅/更新）、歌单、本地音乐、App 内歌词、下载（前台） | `upstream/src/core/`、`downloader.ts` |
| ✅ 已可用 | App 内可拖动桌面歌词浮层（透明 UIWindow + 触摸穿透） | `LyricUtilModule.m:59-84` |
| ✅ 已可用 | ID3v2 USLT/SYLT、iTunes `©lyr` 内嵌歌词读取；元数据编辑（应用内覆盖层，不改音频二进制） | `Mp3UtilModule.m`，6 个 `RCT_EXPORT_METHOD` 齐全 |
| ✅ 已可用 | 后台音频、锁屏/灵动岛显示**当前一句歌词** | `Info.plist` `UIBackgroundModes=audio`；Widget Swift 四种形态 |
| ✅ 已可用 | 未签名 IPA 自动构建、上游 tag 自动同步、dSYM 上传 | `.github/workflows/`、`sync_upstream.py` |
| ⚠️ 半成品 | 灵动岛：标题/歌手硬编码、`isPlaying` 恒 true、`previousLyric` 恒 nil、无进度/交互、`start` 非幂等 | `lyricUtil/index.ios.ts:90`、`Controller.swift:28-48`、`Widget.swift:59` |
| ⚠️ 半成品 | 锁屏/控制中心：RNTP 已配 capabilities + artwork，但 `updateOptions` 带 Android-only 键 `notificationCapabilities`，`compactCapabilities` 含 iOS 无对应的 `Stop`；`setupPlayer` 只有 `maxCacheSize` + `android:{}`，iOS 音频会话完全默认 | `bootstrap.ts:150-189` |
| ⚠️ 半成品 | 键盘避让：竖屏已修，横屏分支未叠加 `kbOffset`，iPad 分屏算错，`searchLrc` 两个输入框仍被盖 | `DEFECT_REVIEW.md` M2/M4/M5 |
| ⚠️ 半成品 | 歌词精度：`progressUpdateEventInterval: 1`，逐句判定最多滞后 1 秒 | `bootstrap.ts:181` |
| ❌ 缺失 | `CFBundleURLTypes` → `musicfree://install/` 深链、`Linking.getInitialURL()` 全是死代码 | `bootstrap.ts:229`；全仓无 scheme 声明 |
| ❌ 缺失 | `CFBundleDocumentTypes` → 「用 MusicFree 打开」导入 mp3/m4a/flac/lrc | 全仓无声明；目前只能靠「文件」App 手动放进 Documents |
| ❌ 缺失 | 主屏/锁屏小组件、Siri/快捷指令、Spotlight 索引、后台下载、AirPlay 路线选择、iPad 分屏适配 | — |
| ❌ 缺失 | 真 ID3 写入（改写音频文件）、APNs 驱动的 Live Activity 更新 | 见 §5 限制 |

---

## 三、优化项（已有能力，把它做对 / 做完整）

> 评级：**价值** 高/中/低；**成本** S≈配置或单行注入、M≈跨 2–3 层改动、L≈新增原生模块或 target；**风险** 主要看是否可能重演 11-11 的「修 A 坏 B」。

### P0 · 先还债（否则后续功能建在不稳的底座上）

| # | 事项 | 为什么必须先做 | 落点 | 成本 / 风险 |
| --- | --- | --- | --- | --- |
| O0.1 | 文档与产物校验：自签流程漏签 `.appex`、README/两份 HTML 停留在「未接线」、`verify_ipa.py` 缺 `.appex` 不算失败 | 照文档签出的包装不上；扩展再次失效时 CI 仍全绿（11-11 已发生过一次） | `docs/*.html`、`README.md`、`scripts/verify_ipa.py` | S / 低，**不需重新构建** |
| O0.2 | 灵动岛底座：幂等 `start`、`lyricManager.setup()` 监听去重、RN 模块主线程派发 | 播放器错误重试会堆叠卡片、歌词事件放大 N 倍；§4 所有灵动岛新功能会被这个缺陷放大 | `Controller.swift`、`lyricManager.ts:62-103`、`BootstrapComponent.tsx`、`MusicFreeLiveActivityModule.m` | M / 中，**需重建 IPA** |

### P1 · 体验优化

**O1 灵动岛信息完整化（最高价值）**
- 现象：`liveCall("start", "MusicFree", "")` 把标题写死；Widget 却渲染 `context.attributes.title/artist`。ActivityKit 的 `attributes` 在 `request` 后不可变，所以即使传对了，切歌也不会刷新。
- **关键设计建议**：把 `title/artist` 从 `ActivityAttributes` **移到 `ContentState`**，`start` 改为「有活动则 `update`、无活动才 `request`」。一次改动同时解决 H3（标题）、H4（幂等/切歌）两个高危，且不需要重建活动、不会闪。
- 顺势补齐：`isPlaying` 由 `Event.PlaybackState` 驱动（当前 `usePlaybackState` 只是 UI hook，没有事件监听，`isPlaying` 恒 true）；`previousLyric` 接上 `showTranslation`（目前翻译被塞进 `lyric` 的 `\n`，可拆成独立字段让 Widget 显示双行）；播放结束/关闭桌面歌词时主动 `end`，避免杀进程后锁屏残留最后一句最多 4 小时。
- 落点：`MusicFreeLyricAttributes.swift`、`Controller.swift`、`Widget.swift`、`MusicFreeLiveActivityModule.m`（新增 `updatePlayState`/`updateMeta`）、`lyricUtil/index.ios.ts`、`lyricManager.ts`。
- 成本 M / 风险中（跨 Swift + ObjC + TS 三层，必须整批跑 `prepare.sh` + CI + 真机锁屏验证）。

**O2 歌词同步精度**：`bootstrap.ts:181` 的 `progressUpdateEventInterval: 1` 改为 `0.2–0.25`。`lyricManager.ts:87` 已有逐句去重、Controller 有 1s 节流，事件量 ×4 不会打爆 ActivityKit 预算，但需真机观察耗电。成本 S / 风险低。由 `inject_bootstrap` 新增一条幂等补丁实现，不手改 upstream。

**O3 iOS 音频会话与锁屏控制**：`setupPlayer` 目前只有 `maxCacheSize` 与 Android 专属 `android:{}`，iOS 侧全默认；`updateOptions` 的 `notificationCapabilities` 是 Android-only 键，`compactCapabilities` 含 iOS 无对应的 `Capability.Stop`。建议按仓库内 RNTP 版本的实际 API 名（`iosCategory: playback`、`autoHandleInterruptions` 等）补 iOS 分支、`compactCapabilities` 加 `Capability.SeekTo`（锁屏拖进度）、处理来电/耳机拔插/route change。成本 S–M / 风险中（音频行为改变必须真机验证，别和 O1 混在一批）。

**O4 布局适配**：横屏分支叠加 `kbOffset`、iPad 分屏改用窗口坐标换算、`searchLrc` 的 `"none"` 在 iOS 忽略、灵动岛/safe area 避让、动态字体检查。成本 M / 风险中（11-11 回归高发区，单独一批改）。

**O5 插件生态收尾**：`plugin.ts:925,929` 的 `os/platform:"android"` 改 `Platform.OS`；`checkUpdate.ts` / `backupSetting.tsx` 裸 `axios.get` 统一 30s + URL trim；配合 §4 的 N4 让深链真正可用。成本 S / 风险低。

**O6 工程效率（不影响 App 功能，但影响每次迭代速度）**：CI 目前 20–26 分钟且无缓存 → 给 `npm ci`、`Pods/`、DerivedData 加 `actions/cache`；CI 补 `tsc --noEmit` / ESLint（60 项断言全是字符串存在性，且与注入器同源，构成自证循环）；产物侧硬失败（O0.1）；把验证器改成「解析结构」而非「找同一批字符串」。成本 S–M / 风险低。

**O7 App 内浮层歌词**：已有拖动 + 触摸穿透，可低成本补「位置锁定、透明度、双击隐藏、进入后台自动隐藏、与灵动岛独立开关」。落点 `LyricUtilModule.m` + 设置项注入。成本 S / 风险低。

---

## 四、新增功能（iOS 原生能力，上游没有）

> 自签环境是所有新增能力的**第一约束**：凡需要 App Group、推送证书、特殊 entitlement、额外 `.appex` 的方案，都要先确认个人免费证书能否签下来，否则做出来也装不上。

| # | 功能 | 做法与落点 | 价值 | 成本 | 自签风险 |
| --- | --- | --- | --- | --- | --- |
| **N4** | **URL scheme / 深链** | `inject_info_plist()` 注入 `CFBundleURLTypes` → `musicfree`。立即激活 `bootstrap.ts:229` 已写好的插件一键安装、`.js` 安装、本地媒体分支，以及 `Linking.getInitialURL()`。也是 N1 的 `Link` 方案前置 | **高** | **S** | 无 |
| **N5** | **「用 MusicFree 打开」导入音频 / .lrc** | 注入 `CFBundleDocumentTypes` + `UTImportedTypeDeclarations`（mp3/m4a/flac/wav/lrc），系统把文件复制进 `Documents/Inbox`，复用已有 `handleLinkingUrl`。**比 Share Extension 划算得多**：不用第二个 `.appex`、不用 App Group、不增加签名复杂度 | **高** | S–M | 无 |
| **N2** | 灵动岛 / 锁屏进度条 | `ProgressView(timerInterval:)` 或 `Text(timerInterval:)`；`ContentState` 增加 `startDate`/`duration`，seek 时刷新 state。iOS 16.1+ 可用 | 中高 | M | 无 |
| **N1** | 灵动岛交互按钮（播放/暂停/上下曲） | iOS 17+ `Button(intent:)` + App Intents；iOS 16 回退 `Link` 深链（依赖 N4）。**注意**：intent 在扩展进程执行，要触达主 App 播放器需 App Group 或深链唤醒 | 高 | M | **中**：App Group 在免费证书下不可靠 |
| **N3** | 灵动岛 / 锁屏封面 | 方案 A：压缩 JPEG 放 `ContentState`（须挤进 4KB 预算，约 2KB 图）；方案 B：App Group 共享文件 + Widget 读 `UIImage(contentsOfFile:)` | 中 | M | **中**：方案 B 依赖 App Group |
| **N7** | Now Playing / 控制中心增强 | RNTP 已给 artwork 与基础命令；可补 `Capability.Like`/评分、精确 elapsed/rate、`AVRoutePickerView` 的 AirPlay 输出选择、耳机线控细节 | 中 | M | 无 |
| **N6** | 主屏 / 锁屏小组件（WidgetKit 静态） | 最近播放 / 收藏歌单 / 快捷播放入口。**复用已接线的 Widget Extension target**，不新建 `.appex`。读数据依赖 App Group；可先做「不共享数据的纯快捷入口」版本 | 中 | M–L | **中** |
| **N8** | App Intents / Siri / Spotlight / 快捷指令 | App Intents 暴露「播放某歌单」；Core Spotlight 索引本地歌单与歌曲，系统搜索可直达 | 中 | M–L | 低–中 |
| **N9** | 后台下载 | 现状 `downloader.ts` 用 `react-native-fs downloadFile`，App 挂起即停。改为原生 background `URLSessionDownloadTask` + AppDelegate 的 `handleEventsForBackgroundURLSession`，并让 JS 下载器改用该模块 | 中 | **L** | 低，但改动面大 |
| **N10** | iPad / 分屏 / 横屏适配 | 与 O4 合并做；`UISupportedInterfaceOrientations` 已开横屏，但 RN 布局是手机向 | 中 | M | 无 |
| **N11** | 灵动岛独立开关与歌词设置 | 上游设置页只有「桌面歌词」一个总开关；新增「锁屏歌词」「显示翻译」「显示进度」需要注入设置页 TSX | 中 | M | 无 |
| **N12** | 无障碍 / 动态字体 / 本地化 | VoiceOver label、Dynamic Type、跟随系统深色模式 | 中低 | S–M | 无 |
| **N13** | 音频输出与播放细节 | AirPlay / 蓝牙路线、音量归一化、播放速率 | 中低 | M | 无 |

**依赖链**（决定实施顺序）：`N4 → N1(Link 方案)`；`O0.2 + O1 → N2/N3`（进度和封面都要可变的 ContentState）；`App Group 可用性验证 → N1(intent) / N3(方案B) / N6(数据版)`；`N5` 与 `O0.1` 都不改运行时，可同批。

---

## 五、明确不建议 / 平台硬限制

| 事项 | 原因 |
| --- | --- |
| 系统级悬浮歌词窗口（跨 App 覆盖） | iOS 沙盒无 `SYSTEM_ALERT_WINDOW` 等价公开能力，属系统硬限制，只能靠 App 内浮层 + Live Activity 替代（已实现） |
| APNs 驱动的 Live Activity 更新 | 当前 `pushType: nil` 是本地更新，自签无推送证书与服务端；后台音频存活时才能持续刷新，暂停后停在最后一句 |
| CarPlay 音频 App | 需 `com.apple.developer.carplay-audio` entitlement，个人免费证书拿不到 |
| 灵动岛内滚动歌词 / 自定义循环动画 / 跑业务逻辑 | SwiftUI 视图由系统渲染、刷新与动画均受限；状态须远小于 4KB；活动最长 8h、锁屏保留最多 4h |
| 真 ID3 写入（改写音频二进制） | AVFoundation 无写入 API，需自写 ID3v2 帧写入器；**且上游 TS/UI 层根本没有调用 `setMediaTag` 的入口**，做完也点不到。现有「应用内元数据覆盖层」已覆盖用户可见需求 |
| Share Extension 导入文件 | 需要第二个 `.appex` + App Group + 额外签名步骤，成本远高于 `CFBundleDocumentTypes`（N5），收益几乎相同 |
| 灵动岛硬件覆盖 | 仅 iPhone 14 Pro 及以后；锁屏卡片是 iOS 16.1+ 全机型可用，别把这两者混为一谈 |

---

## 六、优先级矩阵（价值 × 成本）

|  | 低成本 | 中成本 | 高成本 |
| --- | --- | --- | --- |
| **高价值** | **立刻做**：N4 深链、N5 文件导入、O2 歌词精度、O6 CI 缓存、O0.1 文档/校验 | **重点投入**：O1 灵动岛完整化、O0.2 底座修复、O3 音频会话、N2 进度条 | — |
| **中价值** | O5 插件收尾、O7 浮层增强、N12 无障碍 | N7 Now Playing、N10 iPad、N11 设置项、N13 音频输出 | N9 后台下载、N6 小组件、N8 Siri/Spotlight |
| **低价值 / 受限** | — | N3 封面（App Group 风险） | N1 App Intents（entitlement 风险）、N14 真 ID3 写入（无 UI 入口） |

---

## 七、建议的三批路线图

> 11-11 已经出现过「修 A 坏 B」的 ＋ 号菜单回归。**每批独立提交、独立跑满 `prepare.sh`（当前 113 项）→ 二次注入幂等 → 一次 CI → 产物指纹 → 真机验证**，不要一次性全改完。

> **执行进度（2026-11-12）**：第 1 批已完成并重建出包（提交 `3b78436`、CI run `43142605387`）；第 2 批源码与本地全量验证已完成，随 v1.1.0 发布，产物与真机结论见 `VERIFICATION.md`。第 3 批未动。

**第 1 批 · 纯配置与工程（风险最低，一次 CI）— 已完成**
- O0.1（文档 + `verify_ipa.py` 硬失败）、O6（CI 缓存 + tsc）、**N4**（URL scheme）、**N5**（文档类型导入）、O5（插件收尾）
- 验证：Safari 打开 `musicfree://install/…` 能唤起 App；「文件」App 分享菜单出现 MusicFree；CI 时长下降；`verify_ipa.py` 对无 `.appex` 的假包返回非 0。
- 结果：前两项真机信号仍待确认；缓存冷启动 28m37s，**加速效果未被证实**；假包拒收已由行为测试证明。

**第 2 批 · 灵动岛与播放体验（需真机）— 源码已执行，随 v1.1.0 发布**
- O0.2 → O1（`title/artist` 移入 ContentState + 幂等 start + 暂停态 + 翻译/上下句 + 结束收起）→ N2（进度条）→ O2（歌词精度）
- 额外纳入：应用户要求把适配版本与上游 tag 解耦（`ADAPTER_VERSION = 1.1.0` / `ADAPTER_BUILD = 2` + `bump_version.py` + `verify_ipa.py --expected-version`）
- O3 音频会话**仍单独再一批**，因为音频行为回归最难自查；本批未动
- 实现路径：`ContentState` 承载全部 UI 状态 → Swift `applyState(_ json:)` 单入口（幂等 start / 主动 stop / 主线程 / 250ms 节流）→ ObjC 桥统一 JSON patch → 新增 RN `liveActivity/index.ios.ts` 状态发布器（4Hz RNTP → ~1Hz ActivityKit 心跳）→ `lyricManager.setup()` 监听去重。进度条用 `ProgressView(value:)` 而非 iOS-16-only `timerInterval:`，以避开本机无 iOS SDK 的类型检查盲区。
- 验证：本地 113 项 0 失败、12 个 TS/TSX 语法、3 个 Swift `swiftc -parse`、二次注入幂等、旧包版本拒收测试；**切歌标题、暂停态、翻译/上下句、进度条、结束收起仍需真机确认**，完整 Xcode 编译结论以 CI 为准。

**第 3 批 · 视自签能力决定**
- 先做一次 entitlement 可用性探针（个人免费证书能否签 App Group）；可行才上 N1(intent) / N3(方案B) / N6(数据版小组件) / N8；否则退回 `Link` 深链、纯快捷入口小组件。
- O4/N10（iPad/横屏）、N7、N9、N12 按用户实际反馈排期。

---

## 八、可验证信号速查

| 事项 | 怎么确认真的做成了 |
| --- | --- |
| N4 | `xcrun simctl openurl booted "musicfree://install/..."` 或 Safari 地址栏；`handleLinkingUrl` 收到 URL |
| N5 | 「文件」App 长按 mp3/lrc → 分享菜单出现 MusicFree；文件出现在 `Documents/Inbox` |
| O1 | 锁屏卡片歌名/歌手随切歌变化；暂停时不再写「正在播放」；连续触发播放错误不堆叠卡片 |
| O2 | 歌词高亮与声音偏差 < 0.3s；`PlaybackProgressUpdated` 频率约 4Hz |
| O3 | 来电结束恢复播放、拔耳机暂停、锁屏可拖动进度、静音键行为符合预期 |
| O6 | CI 从 ~20–26 分钟显著下降；注入的 TS 有类型错误时 CI 直接失败 |
| O0.1 | 故意移除 `.appex` 的假包被 `verify_ipa.py` 判失败 |
