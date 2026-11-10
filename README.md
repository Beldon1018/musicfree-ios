# MusicFree iOS Adapter

把官方 [maotoumao/MusicFree](https://github.com/maotoumao/MusicFree)（React Native 0.76.5 / Expo 52）改造成可以构建出**未签名 `.ipa`** 的 iOS 工程，并让上游发新版时自动同步、自动重新出包。

**这不是官方 iOS 版**。官方 README 明确「目前只支持 Android 和 Harmony OS」，从无 IPA 产物。本工程是在官方源码之外加的一层适配，产物需自行重签后安装，且沿用上游 AGPL-3.0 许可。

当前锁定上游版本：`v1.0.0-beta.4`（见 `UPSTREAM_REF`）。

---

## 一、设计：上游零侵入，适配层可重放

```
MusicFree 官方源码 (git tag, 每次重新检出)
        │
        ├── overlay/   新增文件（上游没有）→ 直接覆盖复制，永不冲突
        │              · 3 个 index.ios.ts 平台覆盖
        │              · 本地 Pod：iOS 原生模块 + podspec
        │              · Podfile.properties.json
        │
        ├── inject_ios.py  幂等注入（内容感知，不依赖固定行号）
        │              · Podfile 挂本地 Pod
        │              · Info.plist 补后台音频 / ATS / 文件共享
        │              · pbxproj 换 Bundle ID 与版本号
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
| `NativeModules.LyricUtil` 为 undefined，启动即崩 | `overlay/src/native/lyricUtil/index.ios.ts`：Metro 平台后缀覆盖，保留 `NativeTextAlignment` 枚举与全部方法，全部 no-op |
| `NativeModules.NativeUtils`（bootstrap / 面板 / 抽屉要用） | `index.ios.ts` 覆盖：优先本地 Pod，缺 Pod 时回退纯 JS `Dimensions.get('window')` |
| `NativeModules.Mp3Util`（本地音乐元数据） | `index.ios.ts` 覆盖：优先本地 Pod，缺 Pod 时返回空元数据，保证导入流程不崩 |
| 3 个原生模块没有 iOS 实现 | `ios/LocalPods/MusicFreeNative`：Objective-C 实现的 `NativeUtils` / `Mp3Util`，用 CocoaPods 链接，**不改 `project.pbxproj` 的源文件列表** |
| `Info.plist` 无后台音频、ATS 限制 | 幂等注入 `UIBackgroundModes=audio`、`NSAllowsArbitraryLoads`、`UIFileSharingEnabled` 等 |
| Bundle ID 是 RN 模板值 | 改为 `com.musicfree.ios.unsigned`；版本号跟随上游 tag |
| Expo 新架构开关不明确 | `ios/Podfile.properties.json` 明确 `newArchEnabled=false` + Hermes |

其余 Android 痕迹（`BackHandler`、`Platform.OS === "android"` 分支、`react-native-fs`）本身都有 iOS 实现或已有条件分支，不需要改上游源码。

**功能差异（iOS 端降级项）**：状态栏悬浮歌词（iOS 无该能力）、ID3 标签写入、内嵌歌词读取。本地音乐的标题/艺术家/专辑/时长/封面由 AVFoundation 提供。插件协议、播放、下载、WebDAV 等 JS 层能力不受影响。

---

## 三、快速开始

### 路径 A：云端构建（推荐，本机不需要 Xcode）

```bash
cd musicfree-ios-build
bash scripts/bootstrap_github.sh musicfree-ios private   # 或 public
gh run list --repo <你的用户名>/musicfree-ios --workflow build-ios-unsigned.yml
gh run download --repo <你的用户名>/musicfree-ios -n unsigned-ipa
```

公开仓库的 macOS runner 免费；私有仓库按 10 倍费率消耗 Actions 分钟数，一个 RN 工程约 20–40 分钟/次。`bootstrap_github.sh` 会建仓库、推送代码、触发第一次构建。

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
- **编译验证的边界**：这套适配层在本地做了完整的静态校验（平台覆盖完整性、Pod 接线、plist 能力、pbxproj bundle 阶段、产物签名结构），但**构建用的 `xcodebuild` 必须在装有完整 Xcode 的 macOS 上跑**。当前工作机没有 Xcode，所以第一次云端构建是真正的验证点；若某个第三方 RN 依赖缺 iOS podspec，需要按日志补 Pod 或换实现。
- **AGPL-3.0**：上游是强传染性许可，本适配层同样受其约束；仓库根目录已放 `LICENSE`（AGPL-3.0 全文，取自上游），分发 IPA 时请一并公开对应源码。
- **不是官方产物**：请勿把它当作 MusicFree 官方 iOS 版对外发布；插件可用性取决于上游音源状态。

---

## 七、目录

```
UPSTREAM_REF                     当前锁定的上游 tag
overlay/                        适配层新增文件（同步时全部重放）
  src/native/*/index.ios.ts      3 个 Metro 平台覆盖
  ios/LocalPods/MusicFreeNative/ iOS 原生模块 + podspec
  ios/Podfile.properties.json    Expo 构建开关
scripts/
  lib.sh                        公共函数（检出/重置/复制）
  prepare.sh                    一键生成适配后的工程（幂等）
  inject_ios.py                 幂等注入 Podfile / Info.plist / pbxproj
  verify_adaptation.py          无需 Xcode 的静态校验
  sync_upstream.py              检测/应用上游新 tag，失败回滚
  build_unsigned_ipa.sh         Release archive → 未签名 IPA
  verify_ipa.py                 校验产物未签名且含 main.jsbundle
  bootstrap_github.sh           一键建仓推送并触发首次构建
.github/workflows/
  build-ios-unsigned.yml        macOS 云端构建（可被复用）
  sync-upstream.yml             每日同步 + 发 Release + 失败告警
upstream/                       脚本生成的上游检出（.gitignore 忽略）
build/                          构建产物（.gitignore 忽略）
```
