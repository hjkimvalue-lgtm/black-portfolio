#!/usr/bin/env python3
"""
블랙 가상포트폴리오 — 자동 감시 & GitHub 동기화 스크립트

MD 파일이 변경되면 자동으로:
  1. update_portfolio.py 실행 (HTML 데이터 갱신)
  2. GitHub에 자동 푸시 (어디서든 접속 가능)

실행: python watch_and_sync.py
종료: Ctrl+C
"""

import os
import time
import subprocess
import sys
from pathlib import Path

# watchdog 없으면 자동 설치
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("📦 watchdog 설치 중...")
    subprocess.run([sys.executable, "-m", "pip", "install", "watchdog"], check=True)
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

SCRIPT_DIR = Path(__file__).parent
DEBOUNCE_SEC = 5  # 마지막 변경 후 N초 뒤에 실행 (연속 저장 대응)
EXCLUDE_FILES = {'규칙.md', '양식.md', 'PROJECT_CONTEXT.md'}


class PortfolioHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_modified = 0
        self.pending = False

    def _trigger(self, path_str):
        path = Path(path_str)
        if path.suffix.lower() != '.md':
            return
        if path.name in EXCLUDE_FILES:
            return
        print(f"\n📝 변경 감지: {path.name}")
        self.last_modified = time.time()
        self.pending = True

    def on_modified(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._trigger(event.src_path)


def run_update():
    """update_portfolio.py 실행 후 GitHub 자동 푸시"""
    print("🔄 포트폴리오 업데이트 중...")

    # 1. update_portfolio.py 실행
    result = subprocess.run(
        [sys.executable, "update_portfolio.py"],
        cwd=SCRIPT_DIR,
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"⚠️ 업데이트 오류:\n{result.stderr}")
        return

    # 2. git 변경사항 확인
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=SCRIPT_DIR, capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    if not status.stdout.strip():
        print("ℹ️  변경 없음 — GitHub 푸시 생략")
        return

    # 3. git add → commit → push
    subprocess.run(
        ["git", "add", "portfolio_app.html"],
        cwd=SCRIPT_DIR
    )
    ts = time.strftime('%Y-%m-%d %H:%M')
    subprocess.run(
        ["git", "commit", "-m", f"auto: {ts}"],
        cwd=SCRIPT_DIR, capture_output=True
    )
    push = subprocess.run(
        ["git", "push"],
        cwd=SCRIPT_DIR, capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    if push.returncode == 0:
        print(f"✅ GitHub 업로드 완료! — {ts}")
        print(f"🌐 반영까지 약 1~2분 소요됩니다.")
    else:
        print(f"⚠️ GitHub 푸시 실패:\n{push.stderr}")
        print("💡 git 인증 설정을 확인해주세요.")


def main():
    print("=" * 55)
    print("  🖤 블랙 포트폴리오 자동 감시 & GitHub 동기화")
    print("=" * 55)
    print(f"📂 감시 폴더: {SCRIPT_DIR}")
    print(f"⏱️  대기 시간: MD 저장 후 {DEBOUNCE_SEC}초")
    print("📌 MD 노트 저장 → 자동 업데이트 → GitHub 자동 업로드")
    print("🛑 종료하려면 이 창에서 Ctrl+C")
    print("-" * 55)

    handler = PortfolioHandler()
    observer = Observer()
    observer.schedule(handler, str(SCRIPT_DIR), recursive=False)
    observer.start()

    print("👀 감시 중...")

    try:
        while True:
            time.sleep(1)
            if handler.pending and (time.time() - handler.last_modified) >= DEBOUNCE_SEC:
                handler.pending = False
                run_update()
    except KeyboardInterrupt:
        print("\n🛑 자동 동기화 종료")
        observer.stop()
    observer.join()


if __name__ == '__main__':
    main()
