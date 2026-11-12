# MusicFree iOS 移植项目 · 缺陷审查报告

审查日期：2026-11-12
审查基线：`936c036`（`docs: record the plugin-install timeout fix and its verification`），`UPSTREAM_REF = v1.0.0-beta.4`
审查范围：`scripts/`（注入器、验证器、构建脚本）、`.github/workflows/`、`overlay/`（Swift / ObjC / TS 覆盖层）、`upstream/src/` 注入后的 TS、`upstream/ios/` 注入后的工程配置、`README.md` / `VERIFICATION.md` / `docs/*.html`

> **本次为只读审查，未修改任何源码、脚本、工程配置或交付产物。** 所有结论均标注了文件与行号；无法从文件内容证实的一律不列入。

---

## 一、结论摘要

项目整体工程质量不错：注入器带唯一性锚点断言、幂等、失败即抛错；`prepare.sh → inject → verify → xcodebuild → verify_ipa` 链路完整；CI 已能稳定产出含 `.appex` 的未签名 IPA。

本次共确认 **22 项缺陷**，其中 **5 项高危**、**8 项中危**、**9 项低危**。高危项集中在两类：

1. **文档与产物脱节**：Widget Extension 接线后，README 和两份 HTML 指南仍按「未接线」写，其中手动签名流程**漏签 `.appex`**，照着做会签出装不上的包。
2. **灵动岛功能的运行时缺陷**：歌名/歌手被硬编码、`start` 非幂等且伴随监听重复注册，以及产物校验器不把「缺 `.appex`」当作失败——后者正是上一轮「源码齐全但没接进工程」能一路绿灯交付的根因。

| 级别 | 数量 | 分布 |
| --- | --- | --- |
| 高 | 5 | 文档/签名 2、运行时 2、验证盲区 1 |
| 中 | 8 | JS 运行时 5、配置 2、构建脚本 1 |
| 低 | 9 | 死代码 2、校验/兼容性 4、CI/文档 3 |

---

## 二、高危（建议优先处理）

### H1 — 手动自签流程漏签 `.appex`，且文档仍声称包内没有扩展

**位置**：`docs/signing-and-crash-guide.html` §3.2、§检查表

**证据**：§3.2 的 codesign 脚本只有两步签名：

```bash
# 2. 逐个签嵌套 framework
find MusicFree.app/Frameworks -type d -name "*.framework" ... codesign ...
# 3. 再签整个 .app
codesign --force --sign "$IDENTITY" --entitlements "$ENT" ... MusicFree.app
```

全文没有 `PlugIns/*.appex` 的任何签名命令；entitlements 示例里也只有 `TEAMID.com.musicfree.ios.unsigned`，没有扩展的 `TEAMID.com.musicfree.ios.unsigned.lyrics`。同一文档的检查表还写着：

> `Extension 无 / 没有 .appex，灵动岛只是源码预留，未接线，不参与本次启动`

但自 `8459a40` 起，IPA 里已经有 `Payload/MusicFree.app/PlugIns/MusicFreeLiveActivity.appex`（见 `VERIFICATION.md` 第 39 项实证）。

**影响**：用户按文档操作，第 4 步 `codesign --verify --deep --strict MusicFree.app` 会因扩展未签名而失败；即使跳过自检，iOS 也会拒绝安装带未签名 `.appex` 的包。文档没有给出修复命令，用户会卡死在这里。

**建议**：在步骤 2 与 3 之间插入「先签 appex」一步，使用独立的 entitlements（`application-identifier` 用扩展 bundle id），并更新检查表与 entitlements 示例。顺序必须是 **framework → appex → .app → 重打包 Payload/**。

---

### H2 — README 与两份 HTML 指南整体停留在「灵动岛未接线」时代

**位置**：`README.md`（3 处）、`docs/signing-and-crash-guide.html`、`docs/ios-native-alternatives.html`

**证据**：

| 文件 | 过时尚未更新的表述 |
| --- | --- |
| `README.md` | 「**灵动岛是可选增强**……且必须新增 Widget Extension target」「自签工具不支持时，直接不加该 target」 |
| `README.md` | 「本地做了 **41 项**静态校验」（出现 2 次，实际 `verify_adaptation.py` 已是 **60 项**） |
| `README.md` | 「云端……曾完成一次完整 Release archive……但那次是**没有 storyboard 的旧包**；修复版 IPA 需要……」——实际已连续成功构建多次（`42994437080`、`43017023240`、`43022942754`） |
| `docs/ios-native-alternatives.html` | 「灵动岛现状……包内**没有 `.appex`**；需接线 Widget Extension 后重新构建才会启动」 |
| `docs/signing-and-crash-guide.html` | 见 H1 |

**影响**：用户会被误导成「当前包没有灵动岛」，或按旧建议去手工加 target（与 `inject_live_activity.py` 的固定 UUID 冲突，可能把工程改坏）。校验项数、构建状态的陈旧数字也削弱了 `VERIFICATION.md` 的可信度。

**建议**：把三份文档统一改为「扩展已内置接线，由 `inject_live_activity.py` 幂等注入；产物含 `.appex`；自签必须先签扩展」，校验项数改为 60，构建状态指向最近一次成功的 run。

---

### H3 — 灵动岛永远显示 "MusicFree"，歌名和歌手从不传入

**位置**：`overlay/src/native/lyricUtil/index.ios.ts:90`；`overlay/ios/LiveActivity/MusicFreeLiveActivityWidget.swift:20-26,41-48`

**证据**：JS 侧启动 Live Activity 时传的是常量：

```ts
showStatusBarLyric: async (initLyric, config) => {
    await pick("showStatusBarLyric")(initLyric, config);
    liveCall("start", "MusicFree", "");          // ← 标题/歌手硬编码
    if (initLyric) { liveCall("updateLyric", initLyric); }
},
```

而 Widget 确实在渲染这两个字段：

```swift
Text(context.attributes.title)   // 锁屏卡片
Text(context.attributes.artist)
Label(context.attributes.title, systemImage: "music.note")  // 展开态 leading
Text(context.attributes.artist)                             // 展开态 trailing
```

`lyricManager.ts:69` 虽然把 `${musicItem.title} - ${musicItem.artist}` 传给了 `setStatusBarLyricText`，但那走的是 `updateLyric`（只改 `ContentState.lyric`），**不会改 attributes**。ActivityKit 的 attributes 在 `Activity.request` 后不可变，所以切歌也不会刷新标题。

**影响**：锁屏卡片和灵动岛展开态左上/右上永远显示 "MusicFree" 和空白；切歌时标题不更新。这是用户能直接看到的功能缺失。

> 更正：上一轮我回答「灵动岛能有什么功能」时说「属性里是歌名和歌手」——属性定义里确实有，但运行时**从未被正确赋值**，此处以本报告为准。

**建议**：`lyricManager.setup()` 的 `CurrentMusicChanged` 回调里，把 `musicItem.title/artist` 通过一个新的 `start(title, artist)` 调用重建 Activity（或用 `activity.update` 配合可变的 `ContentState` 字段）；JS 侧不要再传常量。配合 H4 一起改成「复用现有 activity，切歌只更新 state」。

---

### H4 — Live Activity `start` 非幂等，叠加 `lyricManager.setup()` 监听重复注册

**位置**：`overlay/ios/LiveActivity/MusicFreeLiveActivityController.swift:31-43`；`upstream/src/core/lyricManager.ts:60-103`；`upstream/src/entry/bootstrap/BootstrapComponent.tsx:36-44`

**证据**：Swift 侧每次 `start` 都先 fire-and-forget 结束旧的，紧接着**再 request 一个新的**：

```swift
for activity in Activity<MusicFreeLyricAttributes>.activities {
    Task { await activity.end(dismissalPolicy: .immediate) }   // 不等待
}
_ = try Activity.request(attributes: attributes, contentState: state, pushType: nil)
```

没有「已存在则复用」的分支。JS 侧 `lyricManager.setup()` 每次调用都注册两个监听且**从不 remove**：

```ts
this.trackPlayer.on(TrackPlayerEvents.CurrentMusicChanged, ...);
RNTrackPlayer.addEventListener(Event.PlaybackProgressUpdated, ...);
if (this.appConfig.getConfig("lyric.showStatusBarLyric")) {
    LyricUtil.showStatusBarLyric("MusicFree", ...);   // → liveCall("start") → 新建 Activity
}
```

而 `BootstrapComponent.tsx` 在 `bootstrapState === "TrackPlayerError"` 时会再次 `initTrackPlayer()`（`bootstrap.ts:150` 内会调 `lyricManager.setup()`）。

**影响**：每次播放器错误重试，歌词监听就多一份，`PlaybackProgressUpdated` 回调被触发 N 倍，`start` 也多调一次 → 锁屏堆叠多张实时活动卡片、歌词事件放大、灵动岛反复重建闪烁。Android 上 `showStatusBarLyric` 是覆盖窗口，重复调用基本幂等，所以上游从未暴露；iOS + ActivityKit 把这个差异放大成了真实 bug。

**建议**：
1. Swift `start` 先检查 `Activity.activities`：非空则只 `update` 现有 state，不 `request`；确需重建时用 `await` 串行化 `end` 再 `request`。
2. `lyricManager.setup()` 加幂等标志，保存订阅句柄并在 cleanup 中 `remove()`；或把 Live Activity 的生命周期从 `setup` 挪到独立的、只初始化一次的模块。

---

### H5 — `verify_ipa.py` 不把「缺 `.appex`」判为失败，产物侧存在验证盲区

**位置**：`scripts/verify_ipa.py:96-118`

**证据**：`failed` 数组只收集四类失败（已签名、缺 `main.jsbundle`、缺 Mach-O、缺启动屏资源），`appex` 仅在函数末尾作为**提示**输出：

```python
if appex:
    print("RESIGN NOTE: ...")
    print("LIVE ACTIVITY: present — ...")
else:
    print("LIVE ACTIVITY: no PlugIns/*.appex in this ipa — Dynamic Island / "
          "Lock Screen lyrics will not appear")   # ← 仍然 return 0
return 0
```

**影响**：`build_unsigned_ipa.sh:92` 会调用本脚本作为构建最后一道关卡，CI 也依赖它。如果 Widget Extension target 再次失效（上游改 pbxproj、注入锚点失配、Embed phase 丢失），产物里没有 `.appex`，**校验器依然打印 `VERIFY OK`、CI 全绿**。这正是上一轮「三个 Swift 文件都在、但从未被编译」能一路交付到用户手上的原因——当时是靠用户反馈才发现的。

**建议**：把 `if not appex: failed.append("Widget Extension (.appex) missing — Dynamic Island / Lock Screen lyrics disabled")` 加入硬失败列表；同时校验 `app_extension_point_ids` 是否为 `com.apple.widgetkit-extension`。

---

## 三、中危

| # | 位置 | 现象与证据 | 影响 / 建议 |
| --- | --- | --- | --- |
| M1 | `upstream/src/core/pluginManager/plugin.ts:925,929` | 注入给插件的 `env` / `process` 硬编码 `os: "android"`、`platform: "android"` | iOS 上插件读到错误平台身份，可能选错 UA / 路径 / 接口分支。当前订阅源 5 个插件（`xiaoqiu/xiaowo/xiaoyun/xiaogou/xiaomi`）实测均未读这两个字段，故暂未爆发，但属于移植语义错误。建议改用 `Platform.OS`。 |
| M2 | `upstream/src/pages/setting/settingTypes/pluginSetting/views/../searchLrc/index.tsx:40`；`scripts/inject_ios.py:509` | `searchLrc` 设 `keyboardAvoidBehavior="none"` 且含 **2 个 `TextInput`**；注入的键盘 effect 首行 `if (keyboardAvoidBehavior === "none" || Platform.OS !== "ios") return;`，render 里 `"none"` 分支也不套 `kbContainer` | iOS 不会像 Android 那样 resize 窗口，搜索歌词面板的输入框会被键盘直接盖住。建议 iOS 上忽略 `"none"`（或只对确实无输入面板跳过）。 |
| M3 | `upstream/src/pages/setting/settingTypes/backupSetting.tsx:118-120`；`upstream/src/utils/checkUpdate.ts:24` | `const url = text.trim();` 之后却用 `axios.get(text)`（未 trim 原文）；两处均为裸 `axios.get`，继承 `plugin.ts:36` 的 `axios.defaults.timeout = 2000` | 备份恢复 URL 带尾随换行必失败（与已修的 `pluginList.tsx` 同类遗漏）；版本检查 / 备份导入在慢网络下 2 秒超时。建议改用 `url` 并统一加 `timeout: 30000`。 |
| M4 | `upstream/src/components/panels/base/panelBase.tsx:155-164` | 横屏分支只有 `{ translateX: ... }`，**没有叠加 `- kbOffset.value`**；`kbOffset` 仅在竖屏 `translateY` 分支生效 | 横屏/侧滑面板带输入框时键盘避让完全失效。建议两个分支都叠加 `kbOffset`。 |
| M5 | `upstream/src/components/panels/base/panelBase.tsx:128-131` | `windowHeight - endCoordinates.screenY`：`screenY` 是屏幕绝对坐标，`Dimensions.get("window").height` 是 app 窗口高 | iPad 分屏（窗口 origin.y ≠ 0）、浮动键盘、旋转屏下会算错，面板抬过头或抬不动。另外 `keyboardWillHide` 已把 `kbOffset` 归零，代码注释里「用 height 会残留所以必须用 screenY」的理由并不成立。建议用 `endCoordinates.height` 配合窗口坐标换算，并监听尺寸变化重算。 |
| M6 | `overlay/ios/LocalPods/MusicFreeNative/MusicFreeNative/MusicFreeLiveActivityModule.m:24-74`；`MusicFreeLiveActivityController.swift:17-19` | 该 RN 模块没有 `methodQueue`、没有 `dispatch_async(main)`；Swift 侧 `static var lastLyric/lastUpdate` 从 RN 后台队列读写无同步。同 pod 的 `LyricUtilModule.m` 含 5 处 `dispatch`/主线程派发 | ActivityKit 调用与静态节流状态存在跨线程数据竞争，`ActivityAuthorizationInfo().areActivitiesEnabled` 在后台线程读取也不稳妥。建议在 module 侧统一 `dispatch_async(dispatch_get_main_queue(), ...)`，Swift 状态加 `@MainActor` 或串行队列保护。 |
| M7 | `upstream/ios/MusicFree/Info.plist`；`upstream/src/entry/bootstrap/bootstrap.ts:229` | 全仓库无 `CFBundleURLTypes` / `CFBundleURLSchemes`；但 `bootstrap.ts` 有 `url.startsWith("musicfree://install/")` 分支，并注册了 `Linking.addEventListener("url")` 和 `getInitialURL()` | 系统不会把 `musicfree://` 路由到 App，插件一键安装深链（及 `.js` / 本地媒体分支）在 iOS 上是死代码。建议在 `inject_info_plist()` 注入 scheme `musicfree`。 |
| M8 | `scripts/inject_ios.py:160-166`；`scripts/verify_adaptation.py:106` | bundle id 替换正则只匹配 `org\.reactjs\.native\.example`，且 `if n:` 才记录 change——`n == 0` 时**静默通过**；验证器只断言该字符串「不出现」，不检查实际值 | 上游一旦更换模板 bundle id，注入器不替换、验证器却照样通过，产出的 IPA 会带着别人的 id。建议改为「匹配任意 `PRODUCT_BUNDLE_IDENTIFIER` 值并强制写成 `BUNDLE_ID`」+ `n == 0` 抛错，验证器改为断言 `== "com.musicfree.ios.unsigned"`。 |

---

## 四、低危

| # | 位置 | 说明 |
| --- | --- | --- |
| L1 | `MusicFreeLiveActivityWidget.swift:59`；`MusicFreeLyricAttributes.swift` | `Text("正在播放")` 硬编码，`ContentState.isPlaying` 恒传 `true`、`previousLyric` 恒传 `nil` 且 Widget 从不读取 → 暂停时仍显示「正在播放」，上一句/下一句歌词字段是死代码。 |
| L2 | `scripts/sync_upstream.py:26-33` | `tag_key()` 只在匹配 `-beta.N` 时给 beta 序号，其余预发布后缀（`-rc.1`、`-alpha`）会被当成稳定版 `beta=999`，排在 `v1.0.0-beta.N` 之前，可能把 `--apply` 指向非预期的 tag。当前上游只有 beta，属潜在风险。 |
| L3 | `scripts/verify_signed_ipa.sh:1` | `set -uo pipefail` 缺少 `-e`；`Frameworks` 遍历不含 `PlugIns/*.appex/Frameworks`；entitlements 只检查 `.app`，扩展的 entitlements / profile 完全未查，缺失时仅 `[WARN]` 不 FAIL。 |
| L4 | `scripts/verify_adaptation.py` 全文；CI workflow | 60 项断言全是「字符串存在/不存在」，且注入器的幂等判断用的是**同一批字符串**（如 `kbOffset.value`、`keyboardWillChangeFrame`），构成自证循环；CI 未跑 `tsc` / ESLint / 单测，注入的 TS 若有类型或语义错误要等运行时才暴露。 |
| L5 | `upstream/src/core/pluginManager/plugin.ts:_require` | `let pkg = packages[packageName]; pkg.default = pkg;` 对白名单外的包名会抛 `TypeError`，被 `mountPlugin` 吞成笼统的 `CannotParse`，用户无从得知缺哪个依赖。 |
| L6 | `upstream/src/constants/pathConst.ts:4-14` + `Info.plist` | 插件源码、`mmkv`、`data` 全放在 `DocumentDirectoryPath` 下，而 `UIFileSharingEnabled` / `LSSupportsOpeningDocumentsInPlace` 均为 `true` → 「文件」App 可读写插件代码、iCloud/iTunes 备份体积膨胀。（路径拼接与缓存清理本身无问题，插件不会丢。） |
| L7 | `scripts/inject_ios.py:140-147` | `NSSupportsLiveActivitiesFrequentUpdates = true` 对 `pushType: nil` 的纯本地更新是多余键，且容易被误读成「可以高频 update」。 |
| L8 | `.github/workflows/build-ios-unsigned.yml:31,43,66` | 硬编码 `macos-15` / Xcode `16.2` / node `20`，runner 镜像退役或默认工具链升级时会失效；全程无 `actions/cache` 缓存 npm / Pods / DerivedData，单次构建 20–26 分钟。 |
| L9 | `docs/signing-and-crash-guide.html` entitlements 示例 | 只有 app 的 `application-identifier`，没有扩展 id，与 H1 配套缺失。 |

---

## 五、已核查且未发现问题的方向

为避免误报，以下方向逐项检查后确认正常：

- **Widget SwiftUI 各形态**：`compactLeading/compactTrailing/minimal/expanded(leading/trailing/center/bottom)/lockScreen` 写法合法；未使用 `Link` / `Button(intent:)` / `Text(timerInterval:)` / `ProgressView`，不存在 iOS 版本可用性问题。
- **`@available` 与部署目标**：`MusicFreeLyricAttributes.swift` 的 `@available(iOS 16.1, *)` 与 app target 15.1 / extension 16.1 一致；主 App 对 `ActivityKit` 为 weak 链接，低版本可启动。
- **pbxproj 注入**：`inject_live_activity.py` 的 Sources / Frameworks / Resources phase、`dstSubfolderSpec = 13`(PlugIns)、target dependency、Debug/Release 双配置、`MARKETING_VERSION` 同步、共享 scheme 均齐；13 处 `_insert_before` 都带唯一性断言，`verify_definitions()` 会自检所有 24-hex 引用有定义对象。
- **ObjC RN 桥接**：`RCT_EXPORT_MODULE(MusicFreeLiveActivity)`、无扩展时 `NSClassFromString` 返回 nil 的静默 noop、`dispatch_once` 类缓存、NSString 类型校验均正确（线程问题另见 M6）。
- **iOS 覆盖模块契约**：`overlay/src/native/` 三个 `index.ios.ts` 与 upstream 调用契约一致，`ILyricUtil`(9) / `IMp3Util`(6) / `INativeUtils`(4) 方法在 `.m` 中全部导出，`getWindowDimensions` 用 `RCT_EXPORT_BLOCKING_SYNCHRONOUS_METHOD` 保持同步语义；无其它裸 `NativeModules.X` 引用。
- **插件下载超时覆盖**：所有 URL 安装路径（网络 / 订阅 / 批量更新 / 自动更新 / 深链）最终都汇入已加 30s 的 `installPluginFromUrl`；本地文件安装走 `readFile` 不经网络，无遗漏。
- **Live Activity 更新预算**：Swift `updateLyric` 有 1s 节流 + 去重，JS 侧逐句去重，不会打爆 ActivityKit 预算。
- **`panelBase` 监听清理**：`addListener` 均在 cleanup 中 `remove()`，无泄漏；`snapPoint` / `kbOffset` 是两个独立 shared value 合成，与滑入 transform 无优先级冲突。
- **CI 构建链**：`build_unsigned_ipa.sh` 已调用 `verify_ipa.py`（不是缺失）；dSYM 上传覆盖 app 与 extension 两个 bundle；签名禁用参数齐全。

---

## 六、建议的修复顺序

1. **零风险、立即做**：H1 + H2（文档/签名流程）+ H5（把 `.appex` 缺失变成硬失败）+ L9。纯文档与校验器改动，不触碰运行时代码，不需要重新构建 IPA。
2. **小改动、需要重新构建**：H3 + H4 + M6（灵动岛歌名、幂等 start、主线程）+ L1（暂停态）。集中在 `lyricManager.ts`、`lyricUtil/index.ios.ts`、两个 Swift/ObjC 文件，改完需跑 `prepare.sh` 与一次 CI。
3. **独立处理**：M7（URL scheme）、M2/M4/M5（键盘避让三连）、M3（备份/更新超时）、M1（平台身份）。
4. **加固**：M8（bundle id 注入与断言）、L2/L3/L4（同步排序、签名校验、CI 加 tsc）。

> 建议不要一次性把 22 项全改完：H4 和 M2/M4/M5 都涉及面板/歌词生命周期，上一轮已经出现过「修 A 弄坏 B」的回归（见 `VERIFICATION.md` 追加验证）。分批改动、每批跑满 `prepare.sh` + CI + 产物指纹校验更稳妥。
