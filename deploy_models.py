"""
Azure AI Foundry — Setup + 모델 배포 통합 스크립트
원본: hijigoo/microsoft-foundry-labs  01-setup.ipynb + 02-models.ipynb

실행 방법:
  python deploy_models.py            # 대화형 — 단계별 확인
  python deploy_models.py --yes      # 비대화형 — 모든 단계 자동 진행

Windows / macOS / Linux 모두 지원
"""

import json
import os
import random
import shutil
import string
import subprocess
import sys
import time

CONFIG_FILE = ".foundry_config.json"
RESOURCE_GROUP = "foundry-code"
PROJECT_NAME = "default-project"
API_VERSION = "2025-04-01-preview"

AUTO_YES = "--yes" in sys.argv or "-y" in sys.argv
IS_WINDOWS = sys.platform == "win32"

# AI Foundry를 지원하는 주요 리전
AVAILABLE_REGIONS = [
    "swedencentral",
    "eastus",
    "eastus2",
    "westus",
    "westus3",
    "northcentralus",
    "southcentralus",
    "westeurope",
    "francecentral",
    "uksouth",
    "japaneast",
    "australiaeast",
    "canadaeast",
    "koreacentral",
    "norwayeast",
]


# ═══════════════════════════════════════════════
#  유틸리티
# ═══════════════════════════════════════════════
def confirm(msg: str) -> bool:
    if AUTO_YES:
        return True
    answer = input(f"\n❓ {msg} (y/n): ").strip().lower()
    return answer in ("y", "yes", "")


def banner(title: str):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


def run_az(args: list, description: str, allow_fail: bool = False):
    """Azure CLI 명령 실행 헬퍼. 성공 시 stdout 반환, 실패 시 None."""
    print(f"\n▶ {description}")
    result = subprocess.run(["az"] + args, capture_output=True, text=True, shell=IS_WINDOWS)

    if result.stdout.strip():
        print(result.stdout.strip())

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "already exists" in stderr.lower() or "conflict" in stderr.lower():
            print("⚠️  이미 존재합니다. 건너뜁니다.")
            return result.stdout
        if "deprecated" in stderr.lower():
            print(f"⚠️  deprecated 모델입니다. 건너뜁니다.")
            return None
        if "marketplace" in stderr.lower():
            print(f"⚠️  Marketplace 구독이 필요한 모델입니다. 건너뜁니다.")
            return None
        if allow_fail:
            print(f"⚠️  {stderr}")
            return None
        print(f"❌ 오류:\n{stderr}")
        return None

    print(f"✅ {description} — 완료")
    return result.stdout


def az_rest(method: str, url: str, body: dict | None = None, description: str = ""):
    """az rest 래퍼"""
    print(f"\n▶ {description}")
    cmd = ["az", "rest", "--method", method, "--url", url]
    if body:
        cmd += ["--body", json.dumps(body)]

    result = subprocess.run(cmd, capture_output=True, text=True, shell=IS_WINDOWS)
    if result.returncode != 0:
        print(f"❌ 실패: {result.stderr.strip()}")
        return None
    print(f"✅ {description} — 완료")
    return json.loads(result.stdout) if result.stdout.strip() else {}


# ═══════════════════════════════════════════════
#  Phase 1: 사전 검증
# ═══════════════════════════════════════════════
def preflight_check():
    banner("Phase 0 · 사전 검증")

    # Azure CLI 설치 확인
    if not shutil.which("az"):
        print("❌ Azure CLI(az)가 설치되어 있지 않습니다.")
        print("   https://learn.microsoft.com/cli/azure/install-azure-cli")
        sys.exit(1)
    print("✅ Azure CLI 설치 확인")

    # 로그인 상태 확인
    result = subprocess.run(
        ["az", "account", "show", "--query", "{sub:name, id:id}", "-o", "json"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    if result.returncode != 0:
        print("❌ Azure에 로그인되어 있지 않습니다.")
        print("   먼저 'az login' 을 실행하세요.")
        sys.exit(1)

    account = json.loads(result.stdout)
    print(f"✅ 로그인 확인  — 구독: {account['sub']}")
    return account["id"]


def select_region() -> str:
    """배포 리전 선택"""
    if AUTO_YES:
        return AVAILABLE_REGIONS[0]

    print("\n📍 배포 리전을 선택하세요:\n")
    for i, r in enumerate(AVAILABLE_REGIONS, 1):
        print(f"   {i:>2d}) {r}")
    print()

    while True:
        raw = input(f"   번호 입력 (기본: 1 — {AVAILABLE_REGIONS[0]}): ").strip()
        if not raw:
            print(f"   → {AVAILABLE_REGIONS[0]}")
            return AVAILABLE_REGIONS[0]
        if raw.isdigit() and 1 <= int(raw) <= len(AVAILABLE_REGIONS):
            selected = AVAILABLE_REGIONS[int(raw) - 1]
            print(f"   → {selected}")
            return selected
        print(f"   ⚠️  1~{len(AVAILABLE_REGIONS)} 사이 번호를 입력하세요.")


# ═══════════════════════════════════════════════
#  Phase 2: Resource Group 생성
# ═══════════════════════════════════════════════
def create_resource_group(location: str):
    banner("Phase 1 · Resource Group 생성")
    run_az([
        "group", "create",
        "--name", RESOURCE_GROUP,
        "--location", location,
        "--output", "table"
    ], f"Resource Group '{RESOURCE_GROUP}' 생성 ({location})")


# ═══════════════════════════════════════════════
#  Phase 3: Foundry (AIServices) 리소스 생성
# ═══════════════════════════════════════════════
def create_foundry_resource(subscription_id: str, location: str):
    banner("Phase 2 · Foundry 리소스 생성")

    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    foundry_name = f"foundry-{suffix}"
    print(f"📌 Foundry Name: {foundry_name}")

    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices/accounts/{foundry_name}"
        f"?api-version={API_VERSION}"
    )
    body = {
        "location": location,
        "kind": "AIServices",
        "sku": {"name": "S0"},
        "identity": {"type": "SystemAssigned"},
        "properties": {
            "customSubDomainName": foundry_name,
            "publicNetworkAccess": "Enabled",
            "allowProjectManagement": True,
            "disableLocalAuth": True,
        },
    }

    info = az_rest("PUT", url, body, f"Foundry '{foundry_name}' 생성 (AIServices)")
    if not info:
        sys.exit(1)

    foundry_id = info.get("id", "")
    props = info.get("properties", {})
    print(f"   allowProjectManagement: {props.get('allowProjectManagement')}")
    print(f"   disableLocalAuth:       {props.get('disableLocalAuth')}")

    return foundry_name, foundry_id


# ═══════════════════════════════════════════════
#  Phase 4: Foundry Project 생성
# ═══════════════════════════════════════════════
def create_foundry_project(foundry_id: str, location: str):
    banner("Phase 3 · Foundry Project 생성")
    print("⏳ Foundry 리소스 안정화 대기 (5초)...")
    time.sleep(5)

    url = (
        f"https://management.azure.com{foundry_id}"
        f"/projects/{PROJECT_NAME}?api-version={API_VERSION}"
    )
    body = {
        "location": location,
        "identity": {"type": "SystemAssigned"},
        "properties": {
            "friendlyName": PROJECT_NAME,
            "description": f"Foundry Project: {PROJECT_NAME}",
        },
    }

    info = az_rest("PUT", url, body, f"Project '{PROJECT_NAME}' 생성")
    if not info:
        sys.exit(1)

    project_id = info.get("id", "")
    print(f"   Project ID: {project_id[:80]}...")
    return project_id


# ═══════════════════════════════════════════════
#  Phase 5: RBAC 역할 할당 (Keyless 인증)
# ═══════════════════════════════════════════════
ROLE_ASSIGNMENTS = [
    {"role": "Cognitive Services OpenAI User", "desc": "모델 호출 (chat, completion, embedding)"},
    {"role": "Cognitive Services User",        "desc": "Cognitive Services 전반"},
]


def assign_roles(foundry_id: str, subscription_id: str):
    banner("Phase 4 · RBAC 역할 할당 (Keyless 인증)")
    print("🔐 API Key 비활성화 → Entra ID(keyless) 인증 사용")
    print("   현재 로그인한 사용자에게 필요한 역할을 할당합니다.\n")

    # 현재 사용자 Object ID 조회
    result = subprocess.run(
        ["az", "ad", "signed-in-user", "show", "--query", "id", "-o", "tsv"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    if result.returncode != 0:
        print("⚠️  사용자 Object ID 조회 실패. 포털에서 수동으로 역할을 할당하세요.")
        return
    user_oid = result.stdout.strip()
    print(f"   사용자 Object ID: {user_oid}")

    for r in ROLE_ASSIGNMENTS:
        run_az([
            "role", "assignment", "create",
            "--assignee", user_oid,
            "--role", r["role"],
            "--scope", foundry_id,
        ], f"역할 할당: {r['role']} — {r['desc']}", allow_fail=True)

    print("\n💡 역할 전파에 최대 5분 소요될 수 있습니다.")


# ═══════════════════════════════════════════════
#  Phase 5-b: Endpoint 조회 & 설정 파일 저장
# ═══════════════════════════════════════════════
def fetch_endpoint_and_save_config(foundry_name: str, foundry_id: str,
                                    project_id: str, subscription_id: str,
                                    location: str):
    banner("Phase 5 · Endpoint 조회 & 설정 저장")

    # Endpoint 조회
    result = subprocess.run(
        ["az", "cognitiveservices", "account", "show",
         "--name", foundry_name, "--resource-group", RESOURCE_GROUP,
         "--query", "properties.endpoint", "-o", "tsv"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    base_endpoint = result.stdout.strip() if result.returncode == 0 else ""
    project_endpoint = base_endpoint.replace(
        ".cognitiveservices.azure.com/",
        ".services.ai.azure.com/"
    ).rstrip("/") + f"/api/projects/{PROJECT_NAME}"

    print(f"   Base Endpoint:    {base_endpoint}")
    print(f"   Project Endpoint: {project_endpoint}")

    # Tenant ID
    tenant_result = subprocess.run(
        ["az", "account", "show", "--query", "tenantId", "-o", "tsv"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    tenant_id = tenant_result.stdout.strip()

    # 설정 파일 저장 (keyless — API Key 없음)
    config = {
        "FOUNDRY_NAME": foundry_name,
        "PROJECT_NAME": PROJECT_NAME,
        "RESOURCE_GROUP": RESOURCE_GROUP,
        "LOCATION": location,
        "AZURE_SUBSCRIPTION_ID": subscription_id,
        "TENANT_ID": tenant_id,
        "FOUNDRY_ID": foundry_id,
        "PROJECT_ID": project_id,
        "AUTH_MODE": "keyless",
        "FOUNDRY_ENDPOINT": project_endpoint,
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ 설정 파일 저장: {os.path.abspath(CONFIG_FILE)}")
    return config


# ═══════════════════════════════════════════════
#  Phase 6: 모델 배포
# ═══════════════════════════════════════════════

def fetch_available_models(location: str) -> list:
    """리전에서 배포 가능한 모델 목록을 Azure CLI로 조회 (SKU 정보 포함)"""
    print(f"\n▶ {location} 리전 — 배포 가능한 모델 조회 중...")
    result = subprocess.run(
        ["az", "cognitiveservices", "model", "list",
         "--location", location, "-o", "json"],
        capture_output=True, text=True, shell=IS_WINDOWS
    )
    if result.returncode != 0:
        print(f"❌ 모델 조회 실패: {result.stderr.strip()}")
        return []

    raw = json.loads(result.stdout)

    # 모델별로 SKU 목록 수집 (같은 모델이 여러 SKU로 나올 수 있음)
    model_map = {}  # key: "name:version" → model dict with skus list
    for entry in raw:
        m = entry.get("model", {})
        name = m.get("name", "")
        version = m.get("version", "")
        fmt = m.get("format", "OpenAI")
        kind = entry.get("kind", "")

        if not name:
            continue

        # OpenAI 포맷만 포함 (Marketplace 3rd-party 모델 제외)
        if fmt != "OpenAI":
            continue

        # deprecated 모델 필터링
        lifecycle = m.get("lifecycleStatus", "").lower()
        deprecation = m.get("deprecation", {})
        if lifecycle in ("deprecated", "retiring"):
            continue
        if deprecation and deprecation.get("fineTune"):
            from datetime import datetime, timezone
            try:
                dep_date = deprecation.get("inference") or deprecation.get("fineTune", "")
                if dep_date and datetime.fromisoformat(dep_date.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                    continue
            except (ValueError, TypeError):
                pass

        key = f"{name}:{version}"

        # SKU 정보 추출
        skus = []
        for sku in (m.get("skus") or []):
            sku_name = sku.get("name", "")
            if sku_name:
                skus.append(sku_name)

        if key in model_map:
            # 기존 항목에 SKU 추가
            for s in skus:
                if s not in model_map[key]["skus"]:
                    model_map[key]["skus"].append(s)
            continue

        # 타입 분류
        if "embedding" in name.lower():
            desc = "Embedding"
        elif "tts" in name.lower() or "whisper" in name.lower():
            desc = "Audio"
        elif "dall-e" in name.lower():
            desc = "Image"
        elif any(k in name.lower() for k in ("gpt", "o1", "o3", "o4")):
            desc = "Language Model"
        else:
            desc = "Other"

        model_map[key] = {
            "deployment": name,
            "model": name,
            "version": version,
            "format": fmt,
            "desc": desc,
            "skus": skus,
        }

    models = sorted(model_map.values(), key=lambda x: x["model"])
    print(f"✅ {len(models)}개 모델 발견")
    return models


def select_models_interactive(models: list) -> list:
    """배포 가능한 모델 목록에서 인터랙티브 선택"""
    if AUTO_YES:
        return models

    print("\n📋 배포할 모델을 선택하세요:\n")
    print(f"   {'#':>3s}  {'모델명':<30s} {'버전':<14s} {'타입':<15s} {'지원 SKU'}")
    print(f"   {'─'*3}  {'─'*30} {'─'*14} {'─'*15} {'─'*30}")
    for i, m in enumerate(models, 1):
        skus_str = ", ".join(m["skus"]) if m["skus"] else "N/A"
        print(f"   {i:>3d}  {m['model']:<30s} {m['version']:<14s} {m['desc']:<15s} {skus_str}")
    print()

    while True:
        raw = input("   번호 입력 (콤마/공백 구분, 예: 1 3 5): ").strip()
        if not raw:
            continue

        selected = []
        tokens = raw.replace(",", " ").split()
        valid = True
        for tok in tokens:
            if not tok.isdigit() or not (1 <= int(tok) <= len(models)):
                print(f"   ⚠️  잘못된 입력: {tok}  (1~{len(models)})")
                valid = False
                break
            selected.append(models[int(tok) - 1])

        if valid and selected:
            names = ", ".join(m["model"] for m in selected)
            print(f"   → 선택됨: {names}")
            return selected


def select_sku_for_model(m: dict) -> str:
    """모델의 지원 SKU 중 하나를 선택. SKU가 1개면 자동 선택."""
    skus = m.get("skus", [])
    if not skus:
        return "GlobalStandard"
    if len(skus) == 1 or AUTO_YES:
        return skus[0]

    print(f"\n   📌 {m['model']} — SKU 선택:")
    for i, s in enumerate(skus, 1):
        print(f"      {i}) {s}")

    while True:
        raw = input(f"      SKU 번호 (기본: 1): ").strip()
        if not raw:
            return skus[0]
        if raw.isdigit() and 1 <= int(raw) <= len(skus):
            return skus[int(raw) - 1]
        print(f"      ⚠️  1~{len(skus)} 사이 번호를 입력하세요.")


def deploy_model(rg: str, account: str, m: dict, sku: str):
    run_az([
        "cognitiveservices", "account", "deployment", "create",
        "--resource-group", rg,
        "--name", account,
        "--deployment-name", m["deployment"],
        "--model-name", m["model"],
        "--model-format", m.get("format", "OpenAI"),
        "--model-version", m["version"],
        "--sku-name", sku,
        "--sku-capacity", "1",
    ], f"모델 배포: {m['deployment']} (SKU: {sku})")


def deploy_all_models(rg: str, account: str, location: str):
    banner("Phase 6 · 모델 배포")

    models = fetch_available_models(location)
    if not models:
        print("⚠️  배포 가능한 모델이 없습니다.")
        return []

    selected = select_models_interactive(models)
    if not selected:
        print("⚠️  선택된 모델이 없습니다. 건너뜁니다.")
        return []

    # 각 모델별 SKU 선택 후 배포
    for m in selected:
        sku = select_sku_for_model(m)
        deploy_model(rg, account, m, sku)

    # 최종 확인
    print()
    run_az([
        "cognitiveservices", "account", "deployment", "list",
        "--resource-group", rg, "--name", account,
        "--query",
        "[].{Name:name, Model:properties.model.name, SKU:sku.name, "
        "Status:properties.provisioningState}",
        "--output", "table"
    ], "배포된 모델 최종 확인")

    return selected


# ═══════════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════════
def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Azure AI Foundry — Setup + 모델 배포 통합 스크립트   ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # ── 기존 설정 파일이 있으면 재사용 여부 확인 ──
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"\n📄 기존 설정 파일 발견: {CONFIG_FILE}")
        print(f"   Foundry: {existing.get('FOUNDRY_NAME')}")
        print(f"   RG:      {existing.get('RESOURCE_GROUP')}")

        if confirm("기존 설정을 재사용하시겠습니까? (n → 새로 생성)"):
            subscription_id = existing.get("AZURE_SUBSCRIPTION_ID", "")
            preflight_check()
            deployed = deploy_all_models(
                existing["RESOURCE_GROUP"],
                existing["FOUNDRY_NAME"],
                existing["LOCATION"],
            )
            print_summary(existing["FOUNDRY_NAME"], deployed or [], existing["LOCATION"])
            return

    # ── Phase 0: 사전 검증 ──
    subscription_id = preflight_check()

    # ── 리전 선택 ──
    location = select_region()

    # ── Phase 1: Resource Group ──
    create_resource_group(location)

    # ── Phase 2: Foundry 리소스 ──
    foundry_name, foundry_id = create_foundry_resource(subscription_id, location)

    # ── Phase 3: Foundry Project ──
    project_id = create_foundry_project(foundry_id, location)

    # ── Phase 4: RBAC 역할 할당 (Keyless 인증) ──
    assign_roles(foundry_id, subscription_id)

    # ── Phase 5: Endpoint + 설정 파일 저장 ──
    config = fetch_endpoint_and_save_config(
        foundry_name, foundry_id, project_id, subscription_id, location
    )

    # ── Phase 6: 모델 배포 ──
    deployed = []
    if confirm("모델 배포를 시작하시겠습니까?"):
        deployed = deploy_all_models(RESOURCE_GROUP, foundry_name, location)

    print_summary(foundry_name, deployed, location)


def print_summary(foundry_name: str, deployed: list = None, location: str = ""):
    if deployed is None:
        deployed = []
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                   🎉  모두 완료!                       ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Foundry : {foundry_name:<45s}║")
    print(f"║  RG      : {RESOURCE_GROUP:<45s}║")
    print(f"║  Location: {location:<45s}║")
    print("╠══════════════════════════════════════════════════════════╣")
    if deployed:
        print("║  배포된 모델:                                          ║")
        for m in deployed:
            line = f"    • {m['deployment']:<28s} ({m['desc']})"
            print(f"║  {line:<54s}║")
    else:
        print("║  배포된 모델: (없음)                                   ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  인증:      Keyless (Entra ID / DefaultAzureCredential) ║")
    print("║  설정 파일: .foundry_config.json                       ║")
    print("║  포털:      https://ai.azure.com                       ║")
    print("╚══════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
