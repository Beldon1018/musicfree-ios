# MusicFree iOS Adapter

把官方 [maotoumao/MusicFree](https://github.com/maotoumao/MusicFree)（React Native 0.76.5 / Expo 52）改造成可以构建出**未签名 `.ipa`** 的 iOS 工程，并让上游发新版时自动同步、自动重新出包。

**这不是官方 iOS 版**。官方 README 明确「目前只支持 Android 和 Harmony OS」，从无 IPA 产物。本工程是在官方源码之外加的一层适配，产物需自行重签后安装，且沿用上游 AGPL-3.0 许可。

当前锁定上游版本：`v1.0.0-beta.4`（见 `UPSTREAM_REF`）。

**当前状态（2026-11-10）**：云端 macOS runner 已跑通完整 Release archive；首次出包 run `42845832731`。用户反馈「签名后打开闪退」后追到 Expo SDK 52 的原生启动契约：它在原生阶段硬编码 `UIStoryboard(name: "SplashScreen")`，旧包没有该资源。`f70b008` 生成了 `SplashScreen.storyboard` 并修了 iOS 启动分支；此后又查明 `ibtool: iOS 18.2 Platform Not Installed.` 是 [GitHub `macos-15` runner 镜像缺陷](https://github.com/actions/runner-images/issues/13560)（与 storyboard 内容无关），`5228820` 在 CI 里补 `xcodebuild -downloadPlatform iOS` 并加了快速 `ibtool` 冒烟测试。静态校验 **41 项 0 失败**，修复版产物校验见 `VERIFICATION.md`。产物为 iOS 15.1+ 的 arm64 未签名 IPA，内嵌 `main.jsbundle`；**自签时必须递归签名 `Frameworks/hermes.framework`**，见 [`docs/signing-and-crash-guide.html`](docs/signing-and-crash-guide.html)。

---

## 一、设计：上游零侵入，适配层可重放

```
MusicFree 官方源码 (git tag, 每次重新检出)
        │
        ├── overlay/   新增文件（上游没有）→ 直接覆盖复制，永不冲突
        │              · 3 个 index.ios.ts 平台覆盖
        │              · 本地 Pod：iOS 原生模块（浮层 / ID3 / 覆盖层）+ podspec
        │              · LiveActivity/：灵动岛 Swift 源码（默认未接线，自动降级）
        │              · Podfile.properties.json
        │
        ├── inject_ios.py  幂等注入（内容感知，不依赖固定行号）
        │              · Podfile 挂本地 Pod
        │              · Info.plist 补后台音频 / ATS / 文件共享 / 实时活动
        │              · pbxproj 换 Bundle ID、版本号、启动屏改名为 SplashScreen
        │              · 生成 SplashScreen.storyboard（Expo 原生启动必需）
        │              · bootstrap.ts / index.tsx：iOS 跳过 Android-only 启动调用
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
| `NativeModules.LyricUtil` 为 undefined，启动即崩 | `overlay/src/native/lyricUtil/index.ios.ts`：Metro 平台后缀覆盖，保留 `NativeTextAlignment` 枚举与全部方法，委托本地 Pod 的浮层 + 可选灵动岛联动 |
| `NativeModules.NativeUtils`（bootstrap / 面板 / 抽屉要用） | `index.ios.ts` 覆盖：优先本地 Pod，缺 Pod 时回退纯 JS `Dimensions.get('window')` |
| `NativeModules.Mp3Util`（本地音乐元数据） | `index.ios.ts` 覆盖：优先本地 Pod，缺 Pod 时返回空元数据，保证导入流程不崩 |
| 3 个原生模块没有 iOS 实现 | `ios/LocalPods/MusicFreeNative`：Objective-C 实现的 `NativeUtils` / `Mp3Util` / `LyricUtil` + 可选 Live Activity 桥，用 CocoaPods 链接，**不改 `project.pbxproj` 的源文件列表** |
| `Info.plist` 无后台音频、ATS 限制 | 幂等注入 `UIBackgroundModes=audio`、`NSAllowsArbitraryLoads`、`UIFileSharingEnabled`、`NSSupportsLiveActivities` 等 |
| Expo SDK 52 原生启动硬编码 `UIStoryboard(name: "SplashScreen", bundle: nil)`，上游 RN 模板只有 `LaunchScreen.storyboard`，pod 也不自带 → 找不到就抛异常，真机打开即闪退 | 从上游 storyboard 生成一份最小 `SplashScreen.storyboard`，把 pbxproj 中 7 处文件名引用改为同名，并设 `UILaunchStoryboardName = SplashScreen`；系统启动屏与 Expo 共用一份 `SplashScreen.storyboardc` |
| `macos-15` runner 上 `ibtool` 编译任何 storyboard 都报「iOS 18.2 Platform Not Installed」 | **不是工程问题**：[`actions/runner-images#13560`](https://github.com/actions/runner-images/issues/13560) 证实该镜像移除了旧 Xcode 的 iOS runtime。CI 里先 `xcodebuild -downloadPlatform iOS`，再用 `ibtool --compile` 冒烟测试；`-sdk iphoneos`、精简 storyboard XML 都修不了（run `42853265361`、`42857755459` 已分别复现失败） |
| 上游启动流程在 iOS 上误用 Android API | `bootstrap.ts` 的 Android 权限分支改为 `} else if (Platform.OS === "android") {`，不再调用 `PERMISSIONS.ANDROID.*`；`src/entry/index.tsx` 顶层的 `StatusBar.setBackgroundColor` / `setTranslucent` 同样按平台门控 |
| Bundle ID 是 RN 模板值 | 改为 `com.musicfree.ios.unsigned`；版本号跟随上游 tag |
| Expo 新架构开关不明确 | `ios/Podfile.properties.json` 明确 `newArchEnabled=false` + Hermes |

其余 Android 痕迹（`BackHandler`、已有的 `Platform.OS === "android"` 分支、`react-native-fs`）本身都有 iOS 实现或已有条件分支。上面两处启动路径注入是唯一改写上游文件的地方，都是内容感知的最小条件化；锚点一旦变化，`inject_ios.py` 会明确报错，而不是静默产出一个装上去就崩的包。

> **签名后打开闪退？** 见 [`docs/signing-and-crash-guide.html`](docs/signing-and-crash-guide.html)：区分「IPA 启动链问题」和「自签未递归签名 `hermes.framework`」，含 `codesign` 步骤与崩溃日志定位方法。

### 三个 Android 能力的 iOS 原生替代（不再只是 no-op）

Android 的三项能力在 iOS 上不做「照搬」，而是换成 iOS 自己的形态：

| Android 原能力 | iOS 方案 | 落地位置 | 状态 |
| --- | --- | --- | --- |
| 状态栏 / 悬浮窗歌词 | App 内**可拖动歌词浮层**（透明 UIWindow，非卡片区域触摸穿透） | `LyricUtilModule.m` | 默认启用 |
| 状态栏 / 悬浮窗歌词 | **灵动岛 / 锁屏实时活动**（ActivityKit + Widget Extension） | `overlay/ios/LiveActivity/` | 源码齐备，需一次性接线 |
| 内嵌歌词读取（jaudiotagger `FieldKey.LYRICS`） | AVFoundation 读 ID3v2 `USLT`/`SYLT`、iTunes `©lyr` 帧 | `Mp3UtilModule.m` | 默认启用 |
| ID3 标签写入（改写音频文件） | **应用内元数据覆盖层**：编辑结果存 `Documents/`，读取时与文件标签合并，不碰原始音频 | `Mp3UtilModule.m` | 默认启用 |

补充说明：

- 上游 `plugin.ts` 的 `getLyric()` 在内嵌歌词为空时会回退到同名 `.lrc`，因此**外置歌词一直可用**。
- 上游 TS/UI 层**从未调用** `setMediaTag` / `getMediaTag`（只有接口声明和 Android 原生实现），所以覆盖层刻意做在 Pod 内，让 `getBasicMeta` / `getMediaMeta` / `getLyric` 直接生效，无需改上游源码。
- 本地音乐的标题/艺术家/专辑/时长/封面由 AVFoundation 提供；插件协议、播放、下载、WebDAV 等 JS 层能力不受影响。
- 灵动岛模块通过 `NSClassFromString` 运行时解析 Swift 控制器：**没接 Widget Extension 时自动静默降级**，默认构建完全不受影响。接线步骤见 `overlay/ios/LiveActivity/README.md`。

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

产物在 `build/MusicFree-<tag>-unsigned.ipa`。前置条件：完整 Xcode 16.x + `sudo xcode-select -s /Applications/Xcode.app` + CocoaPods + Node 20。**只有 CommandLineTools 是不够的**（当前这台 Intel Mac 就是这种情况），脚本会明确报错而不是给你一个假包。

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
3. 构建成功 → `publish`：上传 IPA 为 Release `ios-<tag>`，并**提交新的 `UPSTREAM_REF`**，至此完成同步。
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
- **必须递归签名嵌套框架**：包内含 `Payload/MusicFree.app/Frameworks/hermes.framework`。自签工具若只签主程序，dyld 会在启动阶段校验失败并直接杀掉进程，表现就是「打开即闪退」。手机端签名工具需开启「签名 Frameworks / 动态库」；手动 `codesign` 要先签框架再签 `.app`。完整步骤见 [`docs/signing-and-crash-guide.html`](docs/signing-and-crash-guide.html)。
- **`verify_ipa.py` 会拒收缺启动屏的包**：校验器现在检查 `SplashScreen.storyboardc` 是否存在（Expo 原生启动必需），并列出需要递归签名的框架清单。旧包 `7621d109…` 用新校验器会被判定失败。签完包后可再用 `verify_signed_ipa.sh` 确认框架签全了。
- **灵动岛是可选增强**：需要 iOS 16.1+（灵动岛形态还需 iPhone 14 Pro 及以后机型），且必须新增 Widget Extension target。`.appex` 要与 `.app` 一起签，AltStore 支持，手动 `codesign` 需先签 appex 再签 app；自签工具不支持时，直接不加该 target，App 内浮层仍可用，RN 桥会自动静默降级。
- **编译验证状态**：本地做了 41 项静态校验（含 Expo storyboard 名字、精简 storyboard XML、iOS 启动分支断言）。云端 `macos-15` + Xcode 16.2 曾完成一次完整 Release archive 与链接（三个 Objective-C 模块均通过 Clang），但那次是没有 storyboard 的旧包；修复版 IPA 需要 `downloadPlatform` 后的重建来确认。当前工作机没有完整 Xcode，因此**本地无法跑模拟器/真机**，只能做静态校验 + 推到仓库触发 CI；「真机不再闪退」必须由使用者在设备上确认，若仍崩溃需按签名指南导出 `.ips` 崩溃日志。若上游升级后某个第三方 RN 依赖缺 iOS podspec，仍需按日志补 Pod 或换实现。
- **AGPL-3.0**：上游是强传染性许可，本适配层同样受其约束；仓库根目录已放 `LICENSE`（AGPL-3.0 全文，取自上游），分发 IPA 时请一并公开对应源码。
- **不是官方产物**：请勿把它当作 MusicFree 官方 iOS 版对外发布；插件可用性取决于上游音源状态。

---

## 七、目录

```
UPSTREAM_REF                     当前锁定的上游 tag
overlay/                        适配层新增文件（同步时全部重放）
  src/native/*/index.ios.ts      3 个 Metro 平台覆盖
  ios/LocalPods/MusicFreeNative/ iOS 原生模块（LyricUtil / Mp3Util / NativeUtils
                                 + 可选 Live Activity 桥）+ podspec
  ios/LiveActivity/              灵动岛 / 锁屏实时活动 Swift 源码 + 接线说明
  ios/Podfile.properties.json    Expo 构建开关
scripts/
  lib.sh                        公共函数（检出/重置/复制）
  prepare.sh                    一键生成适配后的工程（幂等）
  inject_ios.py                 幂等注入 Podfile / Info.plist / pbxproj
                                + 生成 SplashScreen.storyboard
                                + bootstrap.ts / index.tsx 启动门控
  verify_adaptation.py          无需 Xcode 的静态校验（41 项）
  sync_upstream.py              检测/应用上游新 tag，失败回滚
  build_unsigned_ipa.sh         Release archive → 未签名 IPA
  verify_ipa.py                 校验未签名、含 main.jsbundle、含
                                SplashScreen.storyboardc，并列出需递归签名的框架
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
