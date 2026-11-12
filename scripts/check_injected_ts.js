#!/usr/bin/env node
/**
 * Syntax-check every TypeScript file that inject_ios.py rewrites.
 *
 * The 60+ assertions in verify_adaptation.py are string-presence checks; they
 * cannot catch a syntactically broken injection. A full `tsc --noEmit` over
 * upstream is not usable here because the upstream tree carries its own
 * pre-existing type errors, so this uses transpileModule (syntax only, no type
 * resolution) on the exact files our injector touches.
 *
 * Usage: node scripts/check_injected_ts.js <path/to/upstream>
 */
const fs = require("fs");
const path = require("path");

const upstream = process.argv[2];
if (!upstream) {
  console.error("usage: check_injected_ts.js <path/to/upstream>");
  process.exit(2);
}

let ts;
try {
  ts = require(path.join(upstream, "node_modules", "typescript"));
} catch (e) {
  // Local runs outside CI have no upstream/node_modules; NODE_PATH can point
  // at a managed typescript install instead.
  ts = require("typescript");
}

const files = [
  "src/entry/bootstrap/bootstrap.ts",
  "src/entry/index.tsx",
  "src/components/panels/base/panelBase.tsx",
  "src/components/dialogs/components/base/index.tsx",
  "src/core/pluginManager/index.ts",
  "src/core/pluginManager/plugin.ts",
  "src/pages/setting/settingTypes/pluginSetting/views/pluginList.tsx",
  "src/pages/setting/settingTypes/backupSetting.tsx",
  "src/utils/checkUpdate.ts",
];

let failures = 0;
for (const rel of files) {
  const file = path.join(upstream, rel);
  if (!fs.existsSync(file)) {
    console.error(`  [FAIL] ${rel} — file missing`);
    failures += 1;
    continue;
  }
  const source = fs.readFileSync(file, "utf8");
  const result = ts.transpileModule(source, {
    fileName: rel,
    reportDiagnostics: true,
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.React,
      allowJs: false,
    },
  });
  const errors = (result.diagnostics || []).filter(
    (d) => d.category === ts.DiagnosticCategory.Error,
  );
  if (errors.length) {
    failures += 1;
    for (const d of errors) {
      const where = d.file && typeof d.start === "number"
        ? d.file.getLineAndCharacterOfPosition(d.start)
        : null;
      const line = where ? ` line ${where.line + 1}` : "";
      console.error(
        `  [FAIL] ${rel}${line}: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`,
      );
    }
  } else {
    console.log(`  [OK] ${rel}`);
  }
}

console.log(JSON.stringify({ files: files.length, failures }));
process.exit(failures ? 1 : 0);
