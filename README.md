# Azure AI Foundry — Deploy Scripts

Azure AI Foundry 리소스 생성부터 모델 배포까지 한 번에 실행하는 CLI 스크립트입니다.

> 원본 노트북: [hijigoo/microsoft-foundry-labs](https://github.com/hijigoo/microsoft-foundry-labs) (`01-setup.ipynb` + `02-models.ipynb`)

## 주요 기능

| 스크립트 | 설명 |
|----------|------|
| `deploy_models.py` | Foundry 리소스 생성 → 프로젝트 생성 → RBAC 할당 → 모델 배포 |
| `delete_models.py` | 배포된 모델 선택 삭제 |

### deploy_models.py 실행 흐름

```
Phase 0  사전 검증 (Azure CLI 설치·로그인 확인)
         리전 선택 (인터랙티브)
Phase 1  Resource Group 생성
Phase 2  Foundry (AIServices) 리소스 생성
Phase 3  Foundry Project 생성
Phase 4  RBAC 역할 할당 (Keyless / Entra ID 인증)
Phase 5  Endpoint 조회 & .foundry_config.json 저장
Phase 6  모델 배포 (인터랙티브 선택 + SKU 선택)
```

### 인터랙티브 선택

- **리전**: swedencentral, eastus, koreacentral 등 15개 주요 리전에서 선택
- **모델**: 선택한 리전에서 **실제 배포 가능한 모델**을 Azure CLI로 조회하여 표시
- **SKU**: 모델별 지원 SKU (GlobalStandard, Standard, DataZoneStandard 등) 표시 및 선택
- Deprecated / 3rd-party Marketplace 모델은 자동 필터링

## 사전 요구사항

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) 설치
- `az login` 완료
- Python 3.10+

## 사용법

### 배포

```bash
# 대화형 — 리전·모델·SKU 단계별 선택
python deploy_models.py

# 비대화형 — 기본값으로 자동 진행 (swedencentral, 전체 모델)
python deploy_models.py --yes
```

### 삭제

```bash
# 대화형 — 삭제할 모델 선택
python delete_models.py

# 전체 삭제 (확인 후)
python delete_models.py --all
```

## 커스터마이징

### 프로젝트 이름 변경

`deploy_models.py` 상단의 상수를 수정하세요:

```python
# deploy_models.py 22행
PROJECT_NAME = "default-project"     # ← 원하는 이름으로 변경
```

변경 후 스크립트를 다시 실행하면 새 이름으로 프로젝트가 생성됩니다.

> ⚠️ 이미 생성된 프로젝트의 이름은 변경할 수 없습니다. 새 이름으로 재생성해야 합니다.

### Resource Group 이름 변경

```python
# deploy_models.py 21행
RESOURCE_GROUP = "foundry-code"      # ← 원하는 이름으로 변경
```

### 리전 목록 커스터마이징

기본 제공 리전 외에 추가하려면 `AVAILABLE_REGIONS` 리스트를 수정하세요:

```python
# deploy_models.py 27행
AVAILABLE_REGIONS = [
    "swedencentral",
    "eastus",
    "koreacentral",    # ← 이미 포함됨
    "southeastasia",   # ← 추가 예시
    ...
]
```

## 인증 방식

**Keyless (Entra ID)** 인증만 사용합니다. API Key는 비활성화(`disableLocalAuth: true`)됩니다.

스크립트가 자동으로 현재 사용자에게 아래 역할을 할당합니다:
- `Cognitive Services OpenAI User`
- `Cognitive Services User`

이후 SDK에서는 `DefaultAzureCredential()`로 인증합니다:

```python
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

credential = DefaultAzureCredential()
client = AIProjectClient(endpoint=config["FOUNDRY_ENDPOINT"], credential=credential)
```

## 설정 파일

`.foundry_config.json`이 작업 디렉터리에 생성되며, 이후 노트북/스크립트에서 참조합니다:

```json
{
  "FOUNDRY_NAME": "foundry-xxxxxx",
  "PROJECT_NAME": "default-project",
  "RESOURCE_GROUP": "foundry-code",
  "LOCATION": "swedencentral",
  "AUTH_MODE": "keyless",
  "FOUNDRY_ENDPOINT": "https://foundry-xxxxxx.services.ai.azure.com/api/projects/default-project"
}
```

## 크로스플랫폼

Windows, macOS, Linux 모두 지원합니다.

## License

MIT
