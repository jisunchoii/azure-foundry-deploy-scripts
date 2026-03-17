"""
Azure AI Foundry — 배포된 모델 삭제 스크립트

실행 방법:
  python delete_models.py            # 대화형 — 삭제할 모델 선택
  python delete_models.py --all      # 전체 삭제 (확인 후)

Windows / macOS / Linux 모두 지원
"""

import json
import os
import shutil
import subprocess
import sys

CONFIG_FILE = ".foundry_config.json"
DELETE_ALL = "--all" in sys.argv
IS_WINDOWS = sys.platform == "win32"


def run_az(args: list, description: str):
    print(f"\n▶ {description}")
    result = subprocess.run(["az"] + args, capture_output=True, text=True, shell=IS_WINDOWS)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"❌ 오류: {result.stderr.strip()}")
        return None
    print(f"✅ {description} — 완료")
    return result.stdout


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ '{CONFIG_FILE}' 파일을 찾을 수 없습니다.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def preflight_check():
    if not shutil.which("az"):
        print("❌ Azure CLI(az)가 설치되어 있지 않습니다.")
        sys.exit(1)
    result = subprocess.run(
        ["az", "account", "show", "--query", "name", "-o", "tsv"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    if result.returncode != 0:
        print("❌ Azure에 로그인되어 있지 않습니다. 'az login'을 먼저 실행하세요.")
        sys.exit(1)
    print(f"✅ Azure 로그인 확인 (구독: {result.stdout.strip()})")


def fetch_deployments(rg: str, account: str) -> list:
    """현재 배포된 모델 목록 조회"""
    print(f"\n▶ 배포된 모델 조회 중...")
    result = subprocess.run(
        ["az", "cognitiveservices", "account", "deployment", "list",
         "--resource-group", rg, "--name", account, "-o", "json"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    if result.returncode != 0:
        print(f"❌ 조회 실패: {result.stderr.strip()}")
        return []

    raw = json.loads(result.stdout)
    deployments = []
    for d in raw:
        props = d.get("properties", {})
        model = props.get("model", {})
        deployments.append({
            "name": d.get("name", ""),
            "model": model.get("name", ""),
            "version": model.get("version", ""),
            "sku": d.get("sku", {}).get("name", ""),
            "status": props.get("provisioningState", ""),
        })

    print(f"✅ {len(deployments)}개 배포 발견")
    return deployments


def select_deployments(deployments: list) -> list:
    """삭제할 배포 선택"""
    if DELETE_ALL:
        return deployments

    print(f"\n📋 삭제할 모델을 선택하세요:\n")
    print(f"   {'#':>3s}  {'배포명':<30s} {'모델':<25s} {'SKU':<20s} {'상태'}")
    print(f"   {'─'*3}  {'─'*30} {'─'*25} {'─'*20} {'─'*12}")
    for i, d in enumerate(deployments, 1):
        print(f"   {i:>3d}  {d['name']:<30s} {d['model']:<25s} {d['sku']:<20s} {d['status']}")
    print(f"\n   A = 전체 선택")
    print()

    while True:
        raw = input("   번호 입력 (콤마/공백 구분, A=전체): ").strip().upper()
        if not raw:
            continue
        if raw == "A":
            return deployments

        selected = []
        tokens = raw.replace(",", " ").split()
        valid = True
        for tok in tokens:
            if not tok.isdigit() or not (1 <= int(tok) <= len(deployments)):
                print(f"   ⚠️  잘못된 입력: {tok}  (1~{len(deployments)} 또는 A)")
                valid = False
                break
            selected.append(deployments[int(tok) - 1])

        if valid and selected:
            names = ", ".join(d["name"] for d in selected)
            print(f"   → 선택됨: {names}")
            return selected


def delete_deployment(rg: str, account: str, name: str):
    run_az([
        "cognitiveservices", "account", "deployment", "delete",
        "--resource-group", rg,
        "--name", account,
        "--deployment-name", name,
    ], f"삭제: {name}")


def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     Azure AI Foundry — 배포된 모델 삭제 스크립트       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    preflight_check()
    config = load_config()
    rg = config["RESOURCE_GROUP"]
    account = config["FOUNDRY_NAME"]

    print(f"\n📌 Foundry: {account}  |  RG: {rg}")

    deployments = fetch_deployments(rg, account)
    if not deployments:
        print("\n✅ 삭제할 배포가 없습니다.")
        return

    selected = select_deployments(deployments)
    if not selected:
        print("⚠️  선택된 모델이 없습니다.")
        return

    # 최종 확인
    print(f"\n⚠️  다음 {len(selected)}개 배포를 삭제합니다:")
    for d in selected:
        print(f"   • {d['name']} ({d['model']}, {d['sku']})")

    answer = input("\n   정말 삭제하시겠습니까? (yes 입력): ").strip().lower()
    if answer != "yes":
        print("   ❌ 취소되었습니다.")
        return

    for d in selected:
        delete_deployment(rg, account, d["name"])

    print(f"\n🎉 {len(selected)}개 모델 배포 삭제 완료!")


if __name__ == "__main__":
    main()
