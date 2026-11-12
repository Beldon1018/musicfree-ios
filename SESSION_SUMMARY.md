# MusicFree iOS 移植项目 · 会话总结

> 覆盖范围：2026-11-10 22:12 → 2026-11-12 08:55（GMT+8）
> 工作区：`/Users/beldon/WorkBuddy AI/2026-11-10-22-12-34/`
> 仓库：`musicfree-ios-build/`（公开仓库 `https://github.com/Beldon1018/musicfree-ios`）
> 基线：`UPSTREAM_REF = v1.0.0-beta.4`，上游 `maotoumao/MusicFree`（RN 0.76.5 + Expo 52，AGPL-3.0）
> 用途：上下文交接 / 后续继续修复时的事实底稿。本文件为叙述性总结，缺陷细节以 `DEFECT_REVIEW.md` 为准，验证证据以 `VERIFICATION.md` 为准。

---

## 一、用户目标与演进

| 阶段 | 用户诉求 | 最终形态 |
| --- | --- | --- |
| 1 | 想要 MusicFree 的 iOS 可用包 | 官方无 iOS 版；先交付第三方「听屿」未签名 IPA + 解析说明，随后转为自建移植 |
| 2 | 「可随上游同步更新」 | 不手改 upstream、不用 `.patch`；改为 `upstream/ 检出 + overlay/ 覆盖层 + 幂等注入脚本 + GitHub Actions` 四层架构 |
| 3 | 「给我一个 iOS 的解决方案，不是必须和原来一样，比如悬浮歌词可以用灵动岛」 | 三项 Android 能力改成 iOS 原生形态（浮层 / Live Activity / ID3 读取与元数据覆盖层） |
| 4 | 真机反馈：自签闪退、键盘遮挡、＋号菜单回归、灵动岛无歌词、插件装不上 | 逐个定位并修复，每次都跑 `prepare.sh` + CI + 产物指纹校验 |
| 5 | 「灵动岛能有什么功能」「检查这个项目的缺陷」 | 能力说明 + 只读缺陷审查报告 `DEFECT_REVIEW.md`（22 项） |

**贯穿始终的约束**：产物是**未签名 IPA**，供用户自签；本机无完整 Xcode，只能用 GitHub Actions（macos-15 / Xcode 16.2）云端编译；所有改动必须能被 `prepare.sh` 确定性重放。

---

## 二、架构与关键决策

```
prepare.sh
   └─ 检出 upstream tag（reset --hard + clean -fd）
   └─ 拷贝 overlay/（3 个 index.ios.ts + LocalPods/MusicFreeNative + LiveActivity Swift）
   └─ inject_ios.py（Podfile / Info.plist / pbxproj / TS 补丁 / 键盘 / 插件超时）
        └─ inject_live_activity.py（Widget Extension target，在 inject_pbxproj 之前调用）
   └─ verify_adaptation.py（60 项静态断言，幂等自检）
build_unsigned_ipa.sh → xcodebuild(CODE_SIGNING_ALLOWED=NO) → verify_ipa.py
sync_upstream.py → 每日检测新 tag → 触发 build → 发 Release
```

- **不改上游源码**：`upstream/` 每次重建，所有适配以注入脚本 + overlay 表达，保证上游升级可重放。
- **注入器带唯一性锚点断言**，锚点不匹配立即抛错，避免静默半注入；二次执行哈希一致。
- **验证器与注入器同源字符串**（该点后来被列为缺陷 L4 · 自证循环）。
- 静态校验项数演进：19 → 35 → 38 → 41 → 42 → 46 → 47 → 56 → **60**。

---

## 三、按时间线的工作记录

### A. 立项与首个可构建版本（11-10）
- 核实官方无 iOS 版（README 仅 Android/Harmony；CI 仅 Gradle；3 个原生模块只有 Kotlin；Issue #564 明确不支持）。本机仅有 CommandLineTools。
- 先交付第三方 IPA `outputs/TingYu-v1.0.2-105-unsigned.ipa`（SHA `2186a871…`）+ 解析说明 HTML，并如实说明非官方、源码未公开。
- 建适配工程并推送公开仓库。`sync_upstream.py` 踩坑：`/releases/latest` 会跳过 `-beta.N` 返回 `v0.6.2`，已改为全量 tag 语义版本取最大值。
- 三次 CI 失败闭环：
  1. `podspec` 里 `s.dependency = 'React-Core'` 赋值写法 → CocoaPods 报错，改方法调用 `s.dependency 'React-Core'`；
  2. `LaunchScreen.storyboard: iOS 18.2 Platform Not Installed.`；
  3. 真正的 ibtool 根因是 **runner 镜像缺陷**（`actions/runner-images#13560`，macos-15 移除旧 Xcode 的 iOS runtime），与 storyboard 内容无关。最终无条件执行 `xcodebuild -downloadPlatform iOS` + 几秒级 ibtool 冒烟测试。
- 首个成功构建 run `42845832731`；产物 7,231,214 B（`7621d109…`），无 `.appex`。

### B. 自签闪退（11-10 → 11-11，重要反转）
- 用户真机「打开即闪退」。推翻「删 storyboard 就能绕过 ibtool」的旧结论：Expo SDK 52 的 `SplashScreenManager` **无条件** `UIStoryboard(name: "SplashScreen")`，找不到就在 RN 挂载前抛异常。
- 修法 `f70b008`：生成精简 `SplashScreen.storyboard`（去 dependencies/device，toolsVersion→22505），plist 设 `UILaunchStoryboardName=SplashScreen`，pbxproj 7 处改名；另修 `bootstrap.ts` 误走 `PERMISSIONS.ANDROID.*` 和 `index.tsx` 顶层 Android-only `StatusBar`。
- 第二类原因：`Frameworks/hermes.framework` 是嵌套动态框架，自签只签主程序 → dyld 在 `main()` 前终止。新增 `scripts/verify_signed_ipa.sh`（实测能抓 `[FAIL] hermes.framework`）。
- 最终修复版 run `42863975900`：7,235,006 B，SHA `15d56628e4b7b7ae4e5e1be93ca67db59e5fc774383774dd2e3b391eab995602`，`expo_splash_screen_present=true`，41/41 + VERIFY OK。

### C. 第二份崩溃（11-11）
- 用户提交 `.ips`（incident `4BA40D8B`，iOS 26.4）：`EXC_BAD_ACCESS` 于 JS 线程，栈为 `strlen(NULL)` ← `std::string(nil UTF8String)` ← `BridgelessNativeModuleProxy::get` ← `TurboModuleBinding::getModule`。
- 根因：App 实际跑在**新架构 / bridgeless**。`Podfile.properties.json` 的 `newArchEnabled:false` 被裸 RN Podfile 忽略；RN 0.76 未设 `RCT_NEW_ARCH_ENABLED` 时默认开新架构。
- 修法 `89c31bb`：`inject_podfile` 在 `platform :ios` 前注入 `ENV['RCT_NEW_ARCH_ENABLED'] = '0'`；`verify_adaptation.py` 42/42。新增 CI 上传 dSYM 步骤（`efdf4ef`），因为每次归档 LC_UUID 都变。
- run `42948604678` 成功：6,934,977 B，SHA `2f556f94…`，dSYM UUID `EEF75C89-…` 与二进制一致；反汇编 `_RCTIsNewArchEnabled` 读 BSS 初值 0 → 返回 NO。
- **认知修正**：`setup_fabric!` 无条件安装 Fabric pods，二进制含 `BridgelessNativeModuleProxy` 符号不代表新架构生效；真正开关是编译宏。

### D. 键盘避让与 ＋ 号菜单回归（11-11）
- 首修 `ab779f3`（46 项）：`panelBase.tsx` 的 KAV 只有 `zIndex`、高度 0，`behavior="height"` 被裁成 0；`dialogs/base` 完全无键盘避让。补全屏 absolute 容器 + `pointerEvents="box-none"`，弹窗卡片移入 `behavior="padding"` 的 KAV。
- 用户反馈「点击＋号，菜单从上面弹出来了，然后直接消失。问题在我选择网络插件的时候，你修改的不对」。
- 根因：`SimpleSelect`（＋ 菜单）未设 `keyboardAvoidBehavior`，走默认 `"position"` 分支，其 children 是**普通流内 0 高 View**；KAV 改成全屏 absolute 后，这个 0 高 View 从屏幕底部跑到顶部。原布局依赖「0 高容器恰好在屏幕底」的巧合。
- 最终修法 `6d30010`：**panelBase 彻底移除 `KeyboardAvoidingView`**，body 放进显式全屏 `<View style={style.kbContainer} pointerEvents="box-none">`，键盘位移叠加到既有 Reanimated transform：
  ```ts
  kbOffset = useSharedValue(0);
  // keyboardWillChangeFrame: overlap = windowHeight - endCoordinates.screenY
  kbOffset.value = withTiming(Math.max(overlap, 0), { duration: 250 });
  // keyboardWillHide: kbOffset.value = withTiming(0, { duration: 250 });
  ```
  用 `screenY` 而非 `height`，因为 iOS 收起键盘会带旧 height 配屏外 screenY，用 height 会导致面板不回落。
- 护栏：验证器断言含 `kbOffset` / `keyboardWillChangeFrame` / 新容器，且**不得再出现** `<KeyboardAvoidingView`（47/47）。`prepare.sh` 因 `listenerSubscription.remove` 锚点空白不匹配失败过一次，按精确行修正。
- CI `42994437080` 成功 20m18s；bundle 含 `kbOffset` 2 处（旧回归版 0 处）；IPA SHA `7e476111…`，dSYM `C13FF666-F650-3B26-808C-1E7855C6CCC3`。

### E. 灵动岛 / 锁屏歌词不显示（11-11）
- 用户「已经能正常运行了 但是没有歌词」→ 澄清后实际是**灵动岛/锁屏歌词不显示**，歌词本身正常。
- 根因：`overlay/ios/LiveActivity/` 三个 Swift 文件**从未编入任何 target**，也没有 Widget Extension → `NSClassFromString(@"MFLiveActivityController") == nil`，`MusicFreeLiveActivityModule.m` 的 start/updateLyric/stop 全部 early-return。典型「源码齐全但没接线」。
- 新增 `scripts/inject_live_activity.py`（由 `inject_ios.py` 在 `inject_pbxproj` **之前**调用），固定 UUID 幂等注入 `project.pbxproj`：
  - `PBXNativeTarget MusicFreeLiveActivity`，bundle id `com.musicfree.ios.unsigned.lyrics`，iOS 16.1，`com.apple.product-type.app-extension`；
  - app Sources 编入 Attributes + Controller；extension Sources 编入 Widget + Attributes；
  - `PBXCopyFilesBuildPhase`（`dstSubfolderSpec=13` → PlugIns）拷 `.appex`；`PBXTargetDependency` / `PBXContainerItemProxy` 保证先建扩展。
- 编译修复：`MusicFreeLyricAttributes.swift` 加 `@available(iOS 16.1, *)`（继承 `ActivityAttributes`，同时被编入部署目标 15.1 的 app target）。
- 验证器增至 56 项；`verify_ipa.py` 报告 `PlugIns/*.appex`。CI `43017023240` 成功 21m52s；`otool -L` 显示扩展链接 ActivityKit/WidgetKit/SwiftUI，主 app 弱链接 ActivityKit；IPA 6,962,546 B（SHA `386ff9b8…`），dSYM app `B85E8C23…` / appex `85A03AA3…`。
- 使用提醒：开启「设置 → 歌词 → 桌面歌词」；自签顺序 framework → appex → .app；扩展 bundle id 必须以 app id 为前缀。

### F. 插件安装失败（11-11）
- 用户给订阅源 `https://fastly.jsdelivr.net/gh/Huibq/keep-alive/Music_Free/myPlugins.json`。
- 排除版本回退：`UPSTREAM_REF` 始终 `v1.0.0-beta.4`；两版 `Info.plist` 逐键相同；两版 JS bundle 仅构建路径字符串不同；包结构只多 `.appex`。
- 根因：`core/pluginManager/plugin.ts:36` 的 `axios.defaults.timeout = 2000`（原为插件运行期节流）被 `installPluginFromUrl` 复用下载插件包。实测冷 TLS 0.96–1.20s，26KB `xiaomi.js` 端到端 1.93s；`Cache-Control: no-cache` + 5 个插件串行下载 → `timeout of 2000ms exceeded`。
- 按 app 的 `Function(...)` + `_require` 方式本地模拟解析订阅源 5 个插件（xiaoqiu/xiaowo/xiaoyun/xiaogou/xiaomi），全部 OK，证明插件代码与依赖表无问题。
- 修法：`installPluginFromUrl` 下载 `timeout: 30000`（运行期仍 2s）；超时识别 `ECONNABORTED`/message 含 timeout → 「下载超时，请检查网络后重试」；`pluginList.tsx` 订阅清单 `.json` 同样 30s；`text.endsWith(".json")` → `inputUrl.endsWith(".json")`，修复带换行 URL 被当插件下载。
- 60 项 0 失败、二次注入幂等、TS 语法 0 错误；CI `43022942754` 成功 26m04s。
- 最终 IPA `outputs/MusicFree-v1.0.0-beta.4-unsigned.ipa`：6,962,617 B，SHA-256 `77356a49475fe61fb0978bc76a2d21129be519f8bc3c93834f12eccba466f531`；dSYM 两个且与二进制 UUID 一致。
- 排障经验：Hermes 字节码 ASCII grep 不可靠，改用 bundle 字节差 + 中文文案 UTF-16LE 指纹；curl 初次 SSL 失败后改多域名 + WebFetch。

### G. 灵动岛能力说明（11-12）
- 当前 `ContentState`：`lyric` / `previousLyric` / `isPlaying`；属性定义有 `title` / `artist`。
- UI：锁屏卡片（音符 + 歌名 + 歌手 + 当前歌词）、展开态（歌名/歌手/歌词/「正在播放」）、紧凑态（音符 + 歌词前 12 字）、最小态（音符）。
- 可扩展：`ProgressView(timerInterval:)` 进度条、播放/上下曲（`Link` 或 iOS 17+ App Intents）、暂停态、上下句歌词、音质标签、收藏、定时关闭；封面图需 App Group / 共享容器 / entitlements。
- 限制：不能滚动歌词、不能自定义循环动画、不能在岛内跑业务逻辑；自签无 APNs（`pushType:nil`），后台音频存活时才能更新；活动最长 8h、锁屏保留最多 4h；状态需远小于 4KB；灵动岛仅 iPhone 14 Pro 及以后。
- **后续更正**：属性定义虽有 `title/artist`，但运行时 `start` 传的是硬编码 `"MusicFree"`，实际永远不显示歌名（见 `DEFECT_REVIEW.md` H3）。

### H. 全项目缺陷审查（11-12）
- 只读审查，未修改任何源码/脚本/交付产物；交付 `musicfree-ios-build/DEFECT_REVIEW.md`。
- 基线 `936c036`，确认 **22 项缺陷：高 5 / 中 8 / 低 9**。

| 编号 | 摘要 |
| --- | --- |
| H1 | `docs/signing-and-crash-guide.html` §3.2 手动自签**漏签 `.appex`**，且仍写「没有 .appex / 未接线」→ 照做会签出装不上的包 |
| H2 | README 与两份 HTML 停留在「灵动岛可选增强 / 必须新增 Widget Extension / 41 项校验」，实际已内置接线且为 60 项 |
| H3 | `overlay/src/native/lyricUtil/index.ios.ts:90` `liveCall("start", "MusicFree", "")` 标题歌手硬编码；ActivityKit attributes 创建后不可变，切歌不刷新 |
| H4 | Swift `start` 非幂等（fire-and-forget end + 立刻 request 新的）；`lyricManager.setup()` 两个监听从不 remove；`BootstrapComponent` 在 `TrackPlayerError` 重跑 `initTrackPlayer()` → 卡片堆叠、歌词事件放大 |
| H5 | `verify_ipa.py` 不把缺 `.appex` 计入 `failed`，只提示仍 `return 0` —— 正是 E 阶段「源码齐全但没接线」能绿灯交付的根因 |
| M1–M8 | 插件 env 硬编码 `os/platform:"android"`；`searchLrc` 设 `keyboardAvoidBehavior="none"` 却有 2 个输入框；`backupSetting.tsx` 未 trim、`checkUpdate.ts` 裸 `axios.get` 仍 2s；`panelBase` 横屏未叠加 `kbOffset`；iPad 分屏/浮动键盘下 `windowHeight - screenY` 算错；Live Activity 模块跨线程数据竞争；`Info.plist` 无 `CFBundleURLTypes`，`musicfree://install/` 是死代码；bundle id 注入正则只匹配模板串且 `n==0` 静默通过 |
| L1–L9 | 「正在播放」硬编码 / `isPlaying` 恒 true / `previousLyric` 恒 nil；`sync_upstream.py` tag 排序；`verify_signed_ipa.sh` 缺 `-e` 且不查 appex；60 项断言与注入器同源构成自证循环、CI 未跑 tsc；`_require` 错误信息笼统；文档目录可被「文件」App 读写；多余的 `NSSupportsLiveActivitiesFrequentUpdates`；CI 硬编码镜像/Xcode/Node 且无缓存；entitlements 示例缺扩展 id |

- 已核查无问题：Widget 四种形态 SwiftUI 写法、`@available` 与部署目标、pbxproj phases/embed/dependency、三个 `index.ios.ts` 方法契约、插件 30s 超时覆盖所有 URL 安装路径、Live Activity 1s 节流、`panelBase` 监听清理、CI 已调用 `verify_ipa.py`。
- 建议顺序：**① 零风险** H1+H2+H5+L9（文档 + 校验器硬失败，不需重新构建）；**② 运行时** H3+H4+M6+L1（需 `prepare.sh` + 一次 CI）；**③ 独立处理** M7/M2/M4/M5/M3/M1；**④ 加固** M8/L2/L3/L4。不建议一次改完 22 项，D 阶段已有「修 A 坏 B」的教训。

---

## 四、当前交付物

> **后续更新（2026-11-12）**：本总结生成后，用户授权「第一批先执行」，已完成 O0.1 / O6 / N4 / N5 / O5，提交 `3b78436` 并由 CI run `43142605387` 重建出包。下表已换成新产物；完整验证记录见 `VERIFICATION.md` 末尾「第一批」与「云端重建与产物验收」两节。上文的阶段 A–H 与缺陷清单保留为历史记录。

| 文件 | 说明 |
| --- | --- |
| `outputs/MusicFree-v1.0.0-beta.4-unsigned.ipa` | 最新未签名包（第一批），6,963,340 B，SHA `aaace2c4…`，含 `.appex` + `musicfree` URL scheme + 音频/`.lrc` 文档类型 |
| `outputs/MusicFree.app.dSYM` + appex dSYM | 与本次 IPA 二进制 UUID 一致，可符号化 |
| `outputs/musicfree-ios-adapter.zip` | 工程源码打包 |
| `outputs/MusicFree-iOS-签名与闪退排查.html`、`MusicFree-iOS-解析与交付说明.html` | 用户向文档 |
| `musicfree-ios-build/VERIFICATION.md` | 全量验证记录（构建 run、指纹、逐项断言） |
| `musicfree-ios-build/DEFECT_REVIEW.md` | 缺陷审查报告（22 项，含证据与建议） |
| `musicfree-ios-build/SESSION_SUMMARY.md` | 本文件 |
| `docs/*.html`、`README.md` | 注：存在 H1/H2 所述过时内容，尚未修复 |

---

## 五、可复用的技术结论

1. RN 0.76 裸 Podfile 不读 `Podfile.properties.json`；新架构默认开，须用 `ENV['RCT_NEW_ARCH_ENABLED']='0'` 关闭。
2. RN 0.76 的 `KeyboardAvoidingView`：`height` 用 `_initialFrameHeight - bottomHeight`，`padding` 加 `paddingBottom`，`bottomHeight` 来自 `_relativeKeyboardHeight` —— **KAV 自身必须占满全屏**才有意义；但把 0 高 KAV 改成全屏会破坏依赖「0 高容器位于底部」的默认 `"position"` 面板。
3. Expo SDK 52 强依赖名为 `SplashScreen` 的 storyboard，删 storyboard 会启动即崩。
4. `macos-15` runner 的 ibtool 报错与 storyboard 内容无关，需 `xcodebuild -downloadPlatform iOS`。
5. `gh run watch` 退出码不可靠，判定 CI 结论要用 `gh api --jq .conclusion`。
6. Hermes bundle 是字节码，ASCII grep 验证注入不可靠；用字节大小差 + UTF-16LE 中文字符串指纹。
7. 自签顺序必须是 **Frameworks → PlugIns/*.appex → .app → 重打包 Payload**；扩展 bundle id 必须以 app id 为前缀。
8. ActivityKit 的 `attributes` 在 `Activity.request` 后不可变，标题/歌手若要随切歌变化必须放进 `ContentState` 或重建活动。
9. 注入式适配的验证盲区：源码存在 ≠ 编入 target ≠ 产物含 `.appex`，必须在**产物侧**做硬失败校验。

---

## 六、当前状态与未决事项（2026-11-12 更新）

> 本节在「总结出来」之后又经历了两批改动，以下为最新状态；`DEFECT_REVIEW.md` 与 `FEATURE_ROADMAP.md` 仍保留各自写作时点的原始基线结论，并在开头/路线图里追加了状态说明。

- **已解决**：首包构建、自签闪退（两类根因）、bridgeless 崩溃、键盘遮挡、＋号菜单回归、灵动岛 Widget Extension 接线、插件下载 2s 超时、灵动岛能力说明、缺陷审查报告、功能路线图。
- **第 1 批已完成并重建出包**（用户「第一批先执行」）：H1/H2/H5/L9 文档与签名修正、O6 CI 缓存与语法门禁、N4 `musicfree://` 深链、N5 音频 / `.lrc` 文件导入、O5 插件平台标识与超时收尾。提交 `3b78436`、文档提交 `9b8f5cf`；CI run `43142605387` 成功；新 IPA `aaace2c405ef967e…`（6,963,340 B）与两份 dSYM 已验收并提升为主交付物；旧包备份为 `*_pre-batch1.ipa`。缓存冷启动 28m37s，**加速效果未证实**。
- **第 2 批已落地（v1.1.0，用户「完成第二批，更新一个版本吧。不能总是一个版本号」）**：O0.2 / O1 / N2 / O2 的源码改造与本地全量验证完成；独立版本机制 `ADAPTER_VERSION = 1.1.0` / `ADAPTER_BUILD = 2`、`bump_version.py`、包内 provenance、`verify_ipa.py --expected-version`、CI / Release tag 解耦均已落地；静态校验 69 → 113 项、注入 TS 检查 9 → 12 个文件、3 个 Swift `swiftc -parse`、二次注入幂等、旧包版本拒收测试全部通过。**O3 音频会话按路线图仍单独一批。**
- **当前进行中**：第二批的文档同步、提交推送、CI 重建与 v1.1.0 产物验收，见 `VERIFICATION.md`「第二批」章节。
- **始终未验证的真机项**：自签后实机行为、浮层歌词与 ID3 解码、后台音频、自动同步「发现新 tag → 构建 → 发 Release」全链路；第一批遗留的深链唤起与「文件」App 分享菜单；**第二批新增的切歌标题/歌手、暂停态、翻译与上下句、进度条、关闭桌面歌词后收起**。
- **工具边界**：本机只有 CommandLineTools，没有 iOS SDK（`SDK "iphoneos" cannot be located`），Swift 只能做语法解析；完整编译链接与真机行为必须由 CI / 使用者确认。

---

## 七、用户消息清单（按时间）

1. iOS 包需求 / 可随上游同步更新 / 三个降级功能追问 / 「不是必须和原来一样，比如悬浮歌词可以用灵动岛」
2. 「ios 签名打开闪退」+ `.ips` 崩溃日志
3. 「继续修复」
4. 插件管理页输入框被键盘盖住
5. 「还是不对。现在点击+号，菜单从上面弹出来了。然后直接消失。问题在我选择网络插件的时候，你修改的不对」
6. 「已经能正常运行了 但是没有歌词」（澄清后为灵动岛歌词）
7. 「上个版本还能用的插件，现在安装失败了」+ 订阅源 `https://fastly.jsdelivr.net/gh/Huibq/keep-alive/Music_Free/myPlugins.json`
8. 「灵动岛能有什么功能」
9. 「检查这个项目的缺陷」
10. 「总结出来」（本文件）
11. 「分析一下目前还能优化和新增的功能」（产出 `FEATURE_ROADMAP.md`）
12. 「第一批先执行」
13. 「完成第二批」
14. 「完成第二批，更新一个版本吧。不能总是一个版本号」（第 2 批的最终指令，明确要求独立版本号）

> 期间多条 `<task-notification>` 为后台 CI/监视任务自动通知，非用户确认，不应视为授权。
