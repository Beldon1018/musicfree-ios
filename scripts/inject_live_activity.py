#!/usr/bin/env python3
"""Wire the optional Live Activity Widget Extension into MusicFree.xcodeproj.

Why this exists: `MusicFreeLiveActivityWidget.swift` is the only place Dynamic
Island / Lock Screen lyrics can be rendered (ActivityKit requires a Widget
Extension target — the app process can only start/update/end activities). The
upstream project is a bare RN template with a single app target, so the target
has to be created by editing `project.pbxproj`.

XcodeGen / full project generation would fight the CocoaPods integration, so
this script appends the ~10 missing objects with fixed UUIDs and patches the
exact anchors in the existing sections. Every anchor is asserted: if upstream
reshapes the project file the run fails loudly instead of producing a project
that silently drops the extension (or worse, one that will not build).

Idempotent: presence of the `MusicFreeLiveActivity` target short-circuits.
"""
from __future__ import annotations

import re
from pathlib import Path

# Fixed, collision-free UUIDs (24 hex chars). The AA10 prefix does not appear
# anywhere in the upstream project.
BF_ATTR_APP = "AA10000000000000000000B1"
BF_CTRL_APP = "AA10000000000000000000B2"
BF_WIDGET_EXT = "AA10000000000000000000B3"
BF_ATTR_EXT = "AA10000000000000000000B4"
BF_APPEX = "AA10000000000000000000B5"

FR_ATTR = "AA10000000000000000000F1"
FR_CTRL = "AA10000000000000000000F2"
FR_WIDGET = "AA10000000000000000000F3"
FR_INFO = "AA10000000000000000000F4"
FR_APPEX = "AA10000000000000000000F5"

GROUP = "AA10000000000000000000C1"
TARGET = "AA10000000000000000000D1"
PH_SOURCES = "AA10000000000000000000D2"
PH_FRAMEWORKS = "AA10000000000000000000D3"
PH_RESOURCES = "AA10000000000000000000D4"
PH_EMBED = "AA10000000000000000000D5"
DEP = "AA10000000000000000000D6"
PROXY = "AA10000000000000000000D7"

CONF_DEBUG = "AA10000000000000000000E1"
CONF_RELEASE = "AA10000000000000000000E2"
CONF_LIST = "AA10000000000000000000E3"

PROJECT_OBJECT = "83CBB9F71A601CBA00E9B192"
APP_TARGET = "13B07F861A680F5B00A75B9A"
MAIN_GROUP = "83CBB9F61A601CBA00E9B192"
PRODUCTS_GROUP = "83CBBA001A601CBA00E9B192"

EXT_NAME = "MusicFreeLiveActivity"
EXT_BUNDLE_ID = "com.musicfree.ios.unsigned.lyrics"
EXT_DEPLOYMENT_TARGET = "16.1"

BUILD_FILE_SECTION = """\
\t\t{b_attr_app} /* MusicFreeLyricAttributes.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {f_attr} /* MusicFreeLyricAttributes.swift */; }};
\t\t{b_ctrl} /* MusicFreeLiveActivityController.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {f_ctrl} /* MusicFreeLiveActivityController.swift */; }};
\t\t{b_widget} /* MusicFreeLiveActivityWidget.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {f_widget} /* MusicFreeLiveActivityWidget.swift */; }};
\t\t{b_attr_ext} /* MusicFreeLyricAttributes.swift in Sources */ = {{isa = PBXBuildFile; fileRef = {f_attr} /* MusicFreeLyricAttributes.swift */; }};
\t\t{b_appex} /* MusicFreeLiveActivity.appex in Embed App Extensions */ = {{isa = PBXBuildFile; fileRef = {f_appex} /* MusicFreeLiveActivity.appex */; settings = {{ATTRIBUTES = (RemoveHeadersOnCopy, ); }}; }};
"""

COPY_FILES_SECTION = """\
/* Begin PBXCopyFilesBuildPhase section */
\t\t{ph_embed} /* Embed App Extensions */ = {{
\t\t\tisa = PBXCopyFilesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tdstPath = "";
\t\t\tdstSubfolderSpec = 13;
\t\t\tfiles = (
\t\t\t\t{b_appex} /* MusicFreeLiveActivity.appex in Embed App Extensions */,
\t\t\t);
\t\t\tname = "Embed App Extensions";
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXCopyFilesBuildPhase section */

"""

FILE_REFERENCE_SECTION = """\
\t\t{f_attr} /* MusicFreeLyricAttributes.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; name = MusicFreeLyricAttributes.swift; path = LiveActivity/MusicFreeLyricAttributes.swift; sourceTree = "<group>"; }};
\t\t{f_ctrl} /* MusicFreeLiveActivityController.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; name = MusicFreeLiveActivityController.swift; path = LiveActivity/MusicFreeLiveActivityController.swift; sourceTree = "<group>"; }};
\t\t{f_widget} /* MusicFreeLiveActivityWidget.swift */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; name = MusicFreeLiveActivityWidget.swift; path = LiveActivity/MusicFreeLiveActivityWidget.swift; sourceTree = "<group>"; }};
\t\t{f_info} /* Info.plist */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.xml; name = Info.plist; path = LiveActivity/Info.plist; sourceTree = "<group>"; }};
\t\t{f_appex} /* MusicFreeLiveActivity.appex */ = {{isa = PBXFileReference; explicitFileType = "wrapper.app-extension"; includeInIndex = 0; path = MusicFreeLiveActivity.appex; sourceTree = BUILT_PRODUCTS_DIR; }};
"""

FRAMEWORKS_SECTION = """\
\t\t{ph_frameworks} /* Frameworks */ = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
"""

GROUP_SECTION = """\
\t\t{group} /* MusicFreeLiveActivity */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{f_attr} /* MusicFreeLyricAttributes.swift */,
\t\t\t\t{f_ctrl} /* MusicFreeLiveActivityController.swift */,
\t\t\t\t{f_widget} /* MusicFreeLiveActivityWidget.swift */,
\t\t\t\t{f_info} /* Info.plist */,
\t\t\t);
\t\t\tname = MusicFreeLiveActivity;
\t\t\tsourceTree = "<group>";
\t\t}};
"""

NATIVE_TARGET_SECTION = """\
\t\t{target} /* MusicFreeLiveActivity */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {conf_list} /* Build configuration list for PBXNativeTarget "MusicFreeLiveActivity" */;
\t\t\tbuildPhases = (
\t\t\t\t{ph_sources} /* Sources */,
\t\t\t\t{ph_frameworks} /* Frameworks */,
\t\t\t\t{ph_resources} /* Resources */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t);
\t\t\tname = MusicFreeLiveActivity;
\t\t\tproductName = MusicFreeLiveActivity;
\t\t\tproductReference = {f_appex} /* MusicFreeLiveActivity.appex */;
\t\t\tproductType = "com.apple.product-type.app-extension";
\t\t}};
"""

RESOURCES_SECTION = """\
\t\t{ph_resources} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
"""

SOURCES_SECTION = """\
\t\t{ph_sources} /* Sources */ = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t\t{b_attr_ext} /* MusicFreeLyricAttributes.swift in Sources */,
\t\t\t\t{b_widget} /* MusicFreeLiveActivityWidget.swift in Sources */,
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
"""

TARGET_DEPENDENCY_SECTION = """\
\t\t{dep} /* PBXTargetDependency */ = {{
\t\t\tisa = PBXTargetDependency;
\t\t\ttarget = {target} /* MusicFreeLiveActivity */;
\t\t\ttargetProxy = {proxy} /* PBXContainerItemProxy */;
\t\t}};
"""

CONTAINER_PROXY_SECTION = """\
\t\t{proxy} /* PBXContainerItemProxy */ = {{
\t\t\tisa = PBXContainerItemProxy;
\t\t\tcontainerPortal = {project} /* Project object */;
\t\t\tproxyType = 1;
\t\t\tremoteGlobalIDString = {target};
\t\t\tremoteInfo = MusicFreeLiveActivity;
\t\t}};
"""

BUILD_CONFIG_TEMPLATE = """\
\t\t{conf} /* {name} */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCURRENT_PROJECT_VERSION = 1;
\t\t\t\tINFOPLIST_FILE = LiveActivity/Info.plist;
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = {deployment};
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t"$(inherited)",
\t\t\t\t\t"@executable_path/Frameworks",
\t\t\t\t\t"@executable_path/../../Frameworks",
\t\t\t\t);
\t\t\t\tMARKETING_VERSION = 1.0.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = "{bundle_id}";
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t\tSKIP_INSTALL = YES;
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t\tTARGETED_DEVICE_FAMILY = "1,2";
\t\t\t}};
\t\t\tname = {name};
\t\t}};
"""

CONF_LIST_SECTION = """\
\t\t{conf_list} /* Build configuration list for PBXNativeTarget "MusicFreeLiveActivity" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{conf_debug} /* Debug */,
\t\t\t\t{conf_release} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
"""


def _fmt(template: str) -> str:
    return template.format(
        b_attr_app=BF_ATTR_APP,
        b_ctrl=BF_CTRL_APP,
        b_widget=BF_WIDGET_EXT,
        b_attr_ext=BF_ATTR_EXT,
        b_appex=BF_APPEX,
        f_attr=FR_ATTR,
        f_ctrl=FR_CTRL,
        f_widget=FR_WIDGET,
        f_info=FR_INFO,
        f_appex=FR_APPEX,
        group=GROUP,
        target=TARGET,
        ph_sources=PH_SOURCES,
        ph_frameworks=PH_FRAMEWORKS,
        ph_resources=PH_RESOURCES,
        ph_embed=PH_EMBED,
        dep=DEP,
        proxy=PROXY,
        conf_debug=CONF_DEBUG,
        conf_release=CONF_RELEASE,
        conf_list=CONF_LIST,
        project=PROJECT_OBJECT,
        deployment=EXT_DEPLOYMENT_TARGET,
        bundle_id=EXT_BUNDLE_ID,
    )


def _insert_before(text: str, anchor: str, block: str, label: str) -> str:
    """Insert `block` immediately before `anchor` (which must be unique)."""
    if text.count(anchor) != 1:
        raise RuntimeError(
            f"project.pbxproj: anchor for {label} found {text.count(anchor)} times "
            f"(expected exactly 1) — upstream changed the project layout, "
            f"review inject_live_activity.py manually")
    return text.replace(anchor, block + anchor, 1)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(
            f"project.pbxproj: anchor for {label} found {text.count(old)} times "
            f"(expected exactly 1) — upstream changed the project layout, "
            f"review inject_live_activity.py manually")
    return text.replace(old, new, 1)


def inject(pbxproj: Path) -> list[str]:
    text = pbxproj.read_text(encoding="utf-8")
    if f"/* {EXT_NAME} */ = {{\n\t\t\tisa = PBXNativeTarget;" in text:
        return ["already present"]

    orig = text

    # ---- new objects, one section at a time ------------------------------
    text = _insert_before(text, "/* End PBXBuildFile section */",
                          _fmt(BUILD_FILE_SECTION), "PBXBuildFile")
    # PBXCopyFilesBuildPhase does not exist yet: create the whole section just
    # before PBXFileReference (alphabetical neighbours, Xcode tolerates order).
    text = _insert_before(text, "/* Begin PBXFileReference section */",
                          _fmt(COPY_FILES_SECTION), "PBXCopyFilesBuildPhase")
    text = _insert_before(text, "/* End PBXFileReference section */",
                          _fmt(FILE_REFERENCE_SECTION), "PBXFileReference")
    text = _insert_before(text, "/* End PBXFrameworksBuildPhase section */",
                          _fmt(FRAMEWORKS_SECTION), "PBXFrameworksBuildPhase")
    text = _insert_before(text, "/* End PBXGroup section */",
                          _fmt(GROUP_SECTION), "PBXGroup")
    text = _insert_before(text, "/* End PBXNativeTarget section */",
                          _fmt(NATIVE_TARGET_SECTION), "PBXNativeTarget")
    text = _insert_before(text, "/* End PBXResourcesBuildPhase section */",
                          _fmt(RESOURCES_SECTION), "PBXResourcesBuildPhase")
    text = _insert_before(text, "/* End PBXSourcesBuildPhase section */",
                          _fmt(SOURCES_SECTION), "PBXSourcesBuildPhase")
    text = _insert_before(text, "/* End PBXTargetDependency section */",
                          _fmt(TARGET_DEPENDENCY_SECTION), "PBXTargetDependency")
    text = _insert_before(text, "/* End PBXContainerItemProxy section */",
                          _fmt(CONTAINER_PROXY_SECTION), "PBXContainerItemProxy")
    text = _insert_before(text, "/* End XCBuildConfiguration section */",
                          BUILD_CONFIG_TEMPLATE.format(
                              conf=CONF_DEBUG, name="Debug",
                              deployment=EXT_DEPLOYMENT_TARGET,
                              bundle_id=EXT_BUNDLE_ID)
                          + BUILD_CONFIG_TEMPLATE.format(
                              conf=CONF_RELEASE, name="Release",
                              deployment=EXT_DEPLOYMENT_TARGET,
                              bundle_id=EXT_BUNDLE_ID),
                          "XCBuildConfiguration")
    text = _insert_before(text, "/* End XCConfigurationList section */",
                          _fmt(CONF_LIST_SECTION), "XCConfigurationList")

    # ---- patch the existing objects --------------------------------------
    # 1. app target: embed the .appex into PlugIns
    text = _replace_once(
        text,
        "\t\t\t\tE235C05ADACE081382539298 /* [CP] Copy Pods Resources */,\n\t\t\t);",
        "\t\t\t\tE235C05ADACE081382539298 /* [CP] Copy Pods Resources */,\n"
        f"\t\t\t\t{PH_EMBED} /* Embed App Extensions */,\n\t\t\t);",
        "app target buildPhases")

    # 2. app target: depend on the extension so it is built before the copy
    text = _replace_once(
        text,
        "\t\t\tdependencies = (\n\t\t\t);\n\t\t\tname = MusicFree;",
        f"\t\t\tdependencies = (\n\t\t\t\t{DEP} /* PBXTargetDependency */,\n\t\t\t);\n\t\t\tname = MusicFree;",
        "app target dependencies")

    # 3. app target: compile the attributes + the ActivityKit controller
    text = _replace_once(
        text,
        "\t\t\t\t13B07FC11A68108700A75B9A /* main.m in Sources */,\n\t\t\t);",
        "\t\t\t\t13B07FC11A68108700A75B9A /* main.m in Sources */,\n"
        f"\t\t\t\t{BF_ATTR_APP} /* MusicFreeLyricAttributes.swift in Sources */,\n"
        f"\t\t\t\t{BF_CTRL_APP} /* MusicFreeLiveActivityController.swift in Sources */,\n"
        "\t\t\t);",
        "app target Sources")

    # 4. main group gets the new source group
    text = _replace_once(
        text,
        "\t\t\t\t832341AE1AAA6A7D00B99B32 /* Libraries */,",
        "\t\t\t\t832341AE1AAA6A7D00B99B32 /* Libraries */,\n"
        f"\t\t\t\t{GROUP} /* MusicFreeLiveActivity */,",
        "main group children")

    # 5. Products group gets the .appex
    text = _replace_once(
        text,
        "\t\t\t\t00E356EE1AD99517003FC87E /* MusicFreeTests.xctest */,",
        "\t\t\t\t00E356EE1AD99517003FC87E /* MusicFreeTests.xctest */,\n"
        f"\t\t\t\t{FR_APPEX} /* MusicFreeLiveActivity.appex */,",
        "Products group children")

    # 6. project targets list
    text = _replace_once(
        text,
        f"\t\t\t\t{APP_TARGET} /* MusicFree */,",
        f"\t\t\t\t{APP_TARGET} /* MusicFree */,\n"
        f"\t\t\t\t{TARGET} /* MusicFreeLiveActivity */,",
        "project targets")

    # 7. TargetAttributes: mark the extension target as Xcode-created
    text = _replace_once(
        text,
        f"\t\t\t\t\t{APP_TARGET} = {{\n\t\t\t\t\t\tLastSwiftMigration = 1120;\n\t\t\t\t\t}};",
        f"\t\t\t\t\t{APP_TARGET} = {{\n\t\t\t\t\t\tLastSwiftMigration = 1120;\n\t\t\t\t\t}};\n"
        f"\t\t\t\t\t{TARGET} = {{\n\t\t\t\t\t\tCreatedOnToolsVersion = 16.2;\n\t\t\t\t\t}};",
        "TargetAttributes")

    if text == orig:
        return ["no change"]
    pbxproj.write_text(text, encoding="utf-8")
    return [
        "added Widget Extension target MusicFreeLiveActivity "
        f"({EXT_BUNDLE_ID}, iOS {EXT_DEPLOYMENT_TARGET}+)",
        "compiled MusicFreeLyricAttributes.swift + MusicFreeLiveActivityController.swift "
        "into the app target",
        "embedded the .appex into PlugIns via Embed App Extensions",
    ]


def verify_definitions(pbxproj: Path) -> list[str]:
    """Structural self-check: every referenced UUID must be defined.

    Catches typos in the hand-written objects before a 20-minute CI run.
    """
    text = pbxproj.read_text(encoding="utf-8")
    defined = set(re.findall(r"^\t\t([0-9A-F]{24}) (?:/\*.*?\*/ )?= \{", text, re.M))
    referenced: set[str] = set()
    for match in re.finditer(r"([0-9A-F]{24})", text):
        uid = match.group(1)
        # skip the definition site itself ("<uuid> ... = {")
        tail = text[match.end():match.end() + 40]
        if re.match(r"\s*(?:/\*.*?\*/\s*)?= \{", tail):
            continue
        referenced.add(uid)
    missing = sorted(referenced - defined)
    if missing:
        raise RuntimeError(
            "project.pbxproj references undefined objects: " + ", ".join(missing))
    return []
