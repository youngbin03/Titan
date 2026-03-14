#!/bin/bash
# TITAN Signal 초기 설치 스크립트

set -e
echo "🚀 TITAN Signal 설치 시작..."

# Python 버전 확인
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python: $python_version"

# 가상환경 생성
if [ ! -d "venv" ]; then
  echo "📦 가상환경 생성..."
  python3 -m venv venv
fi

# 가상환경 활성화
source venv/bin/activate

# 패키지 설치
echo "📥 의존성 설치..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# spaCy 모델 (선택적)
echo ""
read -p "spaCy 영어 모델 설치 (NER 강화, 약 15MB)? [y/N] " install_spacy
if [[ $install_spacy =~ ^[Yy]$ ]]; then
  python3 -m spacy download en_core_web_sm
  echo "✅ spaCy 모델 설치 완료"
fi

# .env 파일 생성
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚙️  .env 파일 생성됨. API 키를 설정하세요:"
  echo "   ANTHROPIC_API_KEY=sk-ant-..."
  echo "   (Polymarket과 GDELT는 무료라 키 불필요)"
fi

# 출력 디렉토리
mkdir -p output logs

echo ""
echo "✅ 설치 완료!"
echo ""
echo "▶ 실행:"
echo "   source venv/bin/activate"
echo "   python main.py test    # 연결 테스트"
echo "   python main.py run     # 파이프라인 실행"
