#!/usr/bin/env python3
"""本地构建 + 打补丁（跨平台），生成 build/web 供 netlify-cli 部署。

用法：
    python scripts/build.py
然后：
    netlify deploy --prod --dir=build/web
"""
import io
import os
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "build", "web")
APK = os.path.join(WEB, "tank_battle.apk")
TGZ = os.path.join(WEB, "tank_battle.tar.gz")


def run(cmd):
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def normalize_archive():
    """把 pygbag 可能产出的中文名/连字符名归档统一重命名为 tank_battle。"""
    for src in ("坦克大战.apk", "tank-battle.apk", "坦克大战.tar.gz", "tank-battle.tar.gz"):
        srcp = os.path.join(WEB, src)
        dst = APK if src.endswith(".apk") else TGZ
        if os.path.exists(srcp) and not os.path.exists(dst):
            shutil.move(srcp, dst)


def clean_private():
    """从 tar.gz 内剔除 .workbuddy 记忆与真实存档（避免泄露/体积膨胀）。"""
    if not os.path.exists(TGZ):
        return
    try:
        buf = io.BytesIO()
        with tarfile.open(TGZ, "r:gz") as t:
            kept = skipped = 0
            with tarfile.open(fileobj=buf, mode="w:gz") as out:
                for m in t.getmembers():
                    if m.name.startswith("assets/.workbuddy") or m.name == "assets/save.json":
                        skipped += 1
                        continue
                    out.addfile(m, t.extractfile(m))
                    kept += 1
        with open(TGZ, "wb") as f:
            f.write(buf.getvalue())
        print(f"tar cleanup: kept={kept} skipped={skipped}")
    except Exception as e:
        print("tar cleanup skipped (non-fatal):", repr(e))


def copy_runtime():
    """把 vendor/cdn 拷入 build/web/cdn，使运行时同源自托管。"""
    vendor = os.path.join(ROOT, "vendor", "cdn")
    dest = os.path.join(WEB, "cdn")
    if os.path.isdir(vendor):
        shutil.copytree(vendor, dest, dirs_exist_ok=True)
        print("runtime copied ->", dest)


def main():
    run([sys.executable, "-m", "pygbag", "--build",
         "--app_name", "tank_battle", "--title", "坦克大战", "--can_close", "1", "."])
    normalize_archive()
    clean_private()
    copy_runtime()
    run([sys.executable, "scripts/patch_index.py", os.path.join(WEB, "index.html")])
    print("\n构建完成 ->", WEB)
    print("下一步：netlify deploy --prod --dir=build/web")


if __name__ == "__main__":
    main()
