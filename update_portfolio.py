#!/usr/bin/env python3
"""
블랙 가상포트폴리오 — 마크다운 노트 → portfolio_data.js 자동 변환 스크립트

사용법:
  python update_portfolio.py

가상포트 폴더의 모든 마크다운 파일을 읽어서 최신 포트폴리오 상태를
portfolio_data.js 파일로 출력합니다. HTML 앱이 이 파일을 로드합니다.
"""

import os
import re
import json
import glob
import sys
from datetime import datetime

# Windows CP949 터미널 인코딩 문제 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(SCRIPT_DIR, "portfolio_app.html")
DATA_PLACEHOLDER = "/* __PORTFOLIO_DATA_PLACEHOLDER__ */"


def parse_table(text, header_pattern):
    """마크다운 테이블을 파싱하여 딕셔너리 리스트로 반환"""
    rows = []
    lines = text.split('\n')
    header_idx = None

    for i, line in enumerate(lines):
        if header_pattern in line and '|' in line:
            header_idx = i
            break

    if header_idx is None:
        return rows

    # 헤더 파싱
    header_line = lines[header_idx]
    headers = [h.strip() for h in header_line.split('|') if h.strip()]

    # 데이터 행 파싱 (구분선 건너뛰기)
    for line in lines[header_idx + 2:]:
        if not line.strip() or '|' not in line:
            break
        if line.strip().startswith('|--') or line.strip().startswith('| --'):
            continue
        cells = [c.strip() for c in line.split('|') if c.strip() != '']
        if len(cells) >= 2:
            row = {}
            for j, h in enumerate(headers):
                row[h] = cells[j] if j < len(cells) else ''
            rows.append(row)

    return rows


def parse_price(price_str):
    """가격 문자열을 숫자로 변환"""
    if not price_str or price_str == '—' or price_str == '-':
        return None
    price_str = price_str.replace(',', '').replace('원', '').replace('$', '').strip()
    try:
        return float(price_str)
    except ValueError:
        return None


def parse_pct(pct_str):
    """퍼센트 문자열을 숫자로 변환"""
    if not pct_str or pct_str == '—' or pct_str == '-':
        return None
    pct_str = pct_str.replace('%', '').replace('+', '').strip()
    try:
        return float(pct_str)
    except ValueError:
        return None


def parse_weight(weight_str):
    """비중 문자열을 숫자로 변환 (매도 등 특수 케이스 처리)"""
    if not weight_str:
        return 0
    weight_str = weight_str.strip()
    if weight_str in ['매도', '매도완료', 'sold', '-']:
        return 0
    weight_str = weight_str.replace('%', '').strip()
    try:
        return float(weight_str)
    except ValueError:
        return 0


def get_md_files():
    """가상포트 폴더의 마크다운 파일 목록 (날짜순 정렬)"""
    pattern = os.path.join(SCRIPT_DIR, "*.md")
    files = glob.glob(pattern)
    # 규칙.md 제외, 날짜/주차 파일만
    data_files = []
    EXCLUDE = {'규칙.md', '양식.md', 'PROJECT_CONTEXT.md'}
    for f in files:
        basename = os.path.basename(f)
        if basename in EXCLUDE:
            continue
        data_files.append(f)
    # 파일명 정렬 (주차_일 순서)
    data_files.sort(key=lambda x: os.path.basename(x))
    return data_files


def extract_summary_from_latest(content):
    """최신 노트에서 총 수익률 요약 추출"""
    summary = {
        'totalReturn': 0,
        'totalPnl': 0,
        'unrealizedPnl': 0,
        'realizedPnl': 0,
    }

    # 총 수익률
    m = re.search(r'총 수익률[:\s]*([+\-]?[\d.]+)%', content)
    if m:
        summary['totalReturn'] = float(m.group(1))

    # 총 손익 (형식: "총 손익: +1,210만원" 또는 "총 수익금: +3,496만원")
    m = re.search(r'(?:총 손익|총 수익금)[:\s]*([+\-]?[\d,.]+)만원', content)
    if m:
        summary['totalPnl'] = float(m.group(1).replace(',', '')) * 10000

    # 미실현 (형식: "미실현 +1,868만원" 또는 "미실현 국내: +3,132만원")
    m = re.search(r'미실현[^+\-\n]*([+\-][\d,.]+)만원', content)
    if m:
        summary['unrealizedPnl'] = float(m.group(1).replace(',', '')) * 10000

    # 실현 (형식: "/ 실현 -658만원" 또는 "| 실현: -658만원")
    m = re.search(r'[/·|]\s*실현[:\s]*([+\-]?[\d,.]+)만원', content)
    if m:
        summary['realizedPnl'] = float(m.group(1).replace(',', '')) * 10000
    else:
        # "실현손익" 또는 별도 라인
        m = re.search(r'실현\s*손익[:\s]*([+\-]?[\d,.]+)만원', content)
        if m:
            summary['realizedPnl'] = float(m.group(1).replace(',', '')) * 10000

    return summary


def extract_holdings(content):
    """가상포트 구성 테이블에서 보유 종목 추출"""
    holdings = []
    sold = []

    # 가상포트 구성 테이블 찾기
    table_rows = parse_table(content, '종목명')
    if not table_rows:
        return holdings, sold

    for row in table_rows:
        name = row.get('종목명', '').strip()
        if not name:
            continue

        market = row.get('시장', '').strip()
        weight_raw = row.get('비중', '').strip()
        weight = parse_weight(weight_raw)
        buy_price = parse_price(row.get('매수단가', ''))
        current_price = parse_price(row.get('현재가', ''))
        return_pct = parse_pct(row.get('수익률', ''))
        sell_price = parse_price(row.get('매도단가', ''))

        is_sold = (weight_raw in ['매도', '매도완료', 'sold']) or (sell_price and sell_price > 0)

        # 코드 추론
        code = guess_ticker_code(name)

        # 투자금 계산 (10억 × 비중)
        invest_amt = 1000000000 * (weight / 100) if weight > 0 else 0

        # 평가손익 계산
        pnl = 0
        if return_pct is not None and invest_amt > 0:
            pnl = invest_amt * (return_pct / 100)

        entry = {
            'name': name,
            'code': code,
            'market': market,
            'weight': weight,
            'buyPrice': buy_price or 0,
            'currentPrice': current_price or 0,
            'returnPct': return_pct or 0,
            'pnl': round(pnl),
            'investAmt': round(invest_amt),
            'status': 'sold' if is_sold else 'hold',
        }

        if is_sold:
            entry['sellPrice'] = sell_price or 0
            sold.append(entry)
        else:
            holdings.append(entry)

    return holdings, sold


def guess_ticker_code(name):
    """종목명으로 티커 코드 추론"""
    known = {
        '오킨스전자': '080580', '저스템': '417840', '대덕전자': '008060',
        '태웅': '044490', '케이엠더블유': '032500',
        'NVDA': 'NVDA', 'MU': 'MU', 'AVGO': 'AVGO',
        'MRVL': 'MRVL', 'META': 'META', 'AAPL': 'AAPL',
        'MSFT': 'MSFT', 'AMZN': 'AMZN', 'GOOG': 'GOOG',
        'GOOGL': 'GOOGL', 'TSLA': 'TSLA', 'AMD': 'AMD',
    }
    return known.get(name, name)


def extract_trades(content, filename):
    """매매 결정 섹션에서 거래 내역 추출"""
    trades = []

    # 날짜 추출
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if not date_match:
        # 파일 내용에서 날짜 추출 시도
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', content)
    date = date_match.group(1) if date_match else ''

    # 매도 패턴
    sell_patterns = re.findall(
        r'매도[:\s]*(\S+)\s+전량.*?(?:사유|이유)[:\s]*(.*?)(?:\n|$)',
        content, re.DOTALL
    )
    for ticker, reason in sell_patterns:
        trades.append({
            'date': date,
            'type': 'sell',
            'ticker': ticker.strip(),
            'reason': reason.strip()[:200],
        })

    # 비중 확대 패턴
    add_patterns = re.findall(
        r'비중 확대[:\s]*(\S+).*?(?:사유|이유)[:\s]*(.*?)(?:\n|$)',
        content, re.DOTALL
    )
    for ticker, reason in add_patterns:
        trades.append({
            'date': date,
            'type': 'add',
            'ticker': ticker.strip(),
            'reason': reason.strip()[:200],
        })

    return trades


def extract_analysis(content):
    """3대 축 종합 판단 테이블 추출 (국내 + 미국 모두)"""
    analysis = []

    def extract_signal(text):
        for emoji in ['🟢', '🟡', '🔴']:
            if emoji in text:
                return emoji
        return '—'

    lines = content.split('\n')

    # 신호등 테이블 헤더 위치 전체 수집
    table_starts = []
    for i, line in enumerate(lines):
        if ('펀더' in line) and ('심리' in line) and ('종합' in line) and '|' in line:
            table_starts.append(i)

    for table_start in table_starts:
        # 테이블 위 2~5줄에서 시장 구분 감지 (국내/미국)
        market = 'KR'
        for j in range(max(0, table_start - 5), table_start):
            ctx = lines[j]
            if '미국' in ctx or '🌐' in ctx or 'US' in ctx:
                market = 'US'
                break
            if '국내' in ctx or '🇰🇷' in ctx or 'KR' in ctx:
                market = 'KR'
                break

        # 데이터 행 파싱
        for line in lines[table_start + 2:]:
            if not line.strip() or '|' not in line:
                break
            if set(line.replace('|', '').strip()) <= set('-: '):
                continue
            cells = [c.strip() for c in line.split('|')]
            cells = [c for c in cells if c != '']
            if len(cells) < 4:
                continue

            name = cells[0].strip()
            if not name:
                continue

            analysis.append({
                'name': name,
                'market': market,
                'fundamental': extract_signal(cells[1]) if len(cells) > 1 else '—',
                'chart': extract_signal(cells[2]) if len(cells) > 2 else '—',
                'sentiment': extract_signal(cells[3]) if len(cells) > 3 else '—',
                'total': extract_signal(cells[4]) if len(cells) > 4 else '—',
                'note': cells[4].replace('🟢', '').replace('🟡', '').replace('🔴', '').strip() if len(cells) > 4 else '',
            })

    return analysis


def extract_trade_log_table(all_files_content):
    """모든 노트에서 '## 📝 매매기록' 테이블을 파싱하여 누적 반환"""
    all_logs = []
    seen = set()  # 중복 방지: (날짜, 종목) 키

    for filename, content in all_files_content:
        # 매매기록 섹션 찾기
        m = re.search(r'##\s*📝\s*매매기록\s*\n(.*?)(?=\n##[^#]|\Z)', content, re.DOTALL)
        if not m:
            continue
        section = m.group(1)

        # 테이블 헤더 찾기
        lines = section.split('\n')
        header_idx = None
        for i, line in enumerate(lines):
            if '날짜' in line and '구분' in line and '종목' in line and '|' in line:
                header_idx = i
                break
        if header_idx is None:
            continue

        for line in lines[header_idx + 2:]:
            if not line.strip() or '|' not in line:
                break
            if set(line.replace('|', '').strip()) <= set('-: '):
                continue
            cells = [c.strip() for c in line.split('|')]
            cells = [c for c in cells if c != '']
            if len(cells) < 3:
                continue

            date_val    = cells[0] if len(cells) > 0 else ''
            type_val    = cells[1] if len(cells) > 1 else ''
            ticker_val  = cells[2] if len(cells) > 2 else ''
            content_val = cells[3] if len(cells) > 3 else ''
            pnl_val     = cells[4] if len(cells) > 4 else ''

            key = (date_val, ticker_val)
            if key in seen:
                continue
            seen.add(key)

            all_logs.append({
                'date': date_val,
                'type': type_val,
                'ticker': ticker_val,
                'content': content_val,
                'pnl': pnl_val,
            })

    # 날짜 역순 정렬 (최신순)
    all_logs.sort(key=lambda x: x['date'], reverse=True)
    return all_logs


def extract_black_thoughts(content):
    """블랙의 생각 변화 추출"""
    m = re.search(r'###\s*블랙의 생각[^\n]*\n(.*?)(?=\n##[^#]|\Z)', content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ''


def extract_review(content):
    """복기 섹션 추출"""
    m = re.search(r'###\s*복기[^\n]*\n(.*?)(?=\n###|\Z)', content, re.DOTALL)
    if m:
        text = m.group(1).strip()
        if '아직 없음' not in text:
            return text
    return ''


def extract_priority(content):
    """판단 우선순위 추출"""
    m = re.search(r'###\s*판단 우선순위[^\n]*\n(.*?)(?=\n###|\Z)', content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ''


def extract_trade_decisions(content):
    """국내/미국 매매 결정 상세 추출"""
    decisions = {'kr': '', 'us': ''}

    # 국내 매매 결정
    m = re.search(r'###\s*국내 매매 결정\s*\n(.*?)(?=\n---|\n##[^#]|\Z)', content, re.DOTALL)
    if m:
        decisions['kr'] = m.group(1).strip()

    # 미국 매매 결정
    m = re.search(r'###\s*미국 매매 결정\s*\n(.*?)(?=\n###\s*판단 근거|\n---|\n##[^#]|\Z)', content, re.DOTALL)
    if m:
        decisions['us'] = m.group(1).strip()

    return decisions


def extract_end_comment(content):
    """포트폴리오 종료시 코멘트 전체 추출"""
    m = re.search(r'##\s*포트폴리오 종료시 코멘트\s*\n(.*?)(?=\n##[^#]|\Z)', content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ''


def extract_inception_date(content):
    """포트폴리오 기준일(진입가 날짜) 추출"""
    # "진입가 = 2026-03-13 금요일 종가" 패턴
    m = re.search(r'진입가[^=\n]*=\s*.*?(\d{4}-\d{2}-\d{2})', content)
    if m:
        return m.group(1)
    # "기준일: 2026-03-xx" 패턴
    m = re.search(r'기준일[:\s]*(\d{4}-\d{2}-\d{2})', content)
    if m:
        return m.group(1)
    return None


def extract_daily_returns(all_files_content):
    """일별 수익률 추적 데이터 수집 (코스피/S&P500 포함)"""
    daily = []
    for filename, content in all_files_content:
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', content[:200])
        date = date_match.group(1) if date_match else os.path.basename(filename)

        # 국내 수익률: "국내주식 수익률: +0.22%" 또는 "국내(투자금 대비): +7.96%"
        kr_match = re.search(r'(?:국내 포트|국내주식 수익률|국내\([^)]*\))[:\s]*([+\-]?[\d.]+)%', content)
        # 미국 수익률: "미국주식 수익률: +2.97%" 또는 "미국 부문 합계: 약 +1,022만원 (+1.65% / ...)"
        us_match = re.search(r'(?:미국 포트|미국주식 수익률)[:\s]*([+\-]?[\d.]+)%', content)
        if not us_match:
            us_match = re.search(r'미국 부문 합계[^(]*\(([+\-]?[\d.]+)%', content)
        total_match = re.search(r'총 수익률[:\s]*([+\-]?[\d.]+)%', content)

        # 지수 누적 수익률 파싱
        # 지원 형식: "코스피 누적: +1.14%", "코스피(누적): +1.14%"
        kospi_match = re.search(r'코스피[\s(]*누적[)\s]*[:\s]*([+\-]?[\d.]+)%', content)
        sp500_match = re.search(r'S&?P\s*500[\s(]*누적[)\s]*[:\s]*([+\-]?[\d.]+)%', content, re.IGNORECASE)

        if total_match or kr_match or us_match:
            daily.append({
                'date':  date,
                'total': float(total_match.group(1)) if total_match else None,
                'kr':    float(kr_match.group(1))    if kr_match    else None,
                'us':    float(us_match.group(1))    if us_match    else None,
                'kospi': float(kospi_match.group(1)) if kospi_match else None,
                'sp500': float(sp500_match.group(1)) if sp500_match else None,
            })

    return daily


def main():
    print("🖤 블랙 가상포트폴리오 데이터 업데이트 시작...")

    md_files = get_md_files()
    if not md_files:
        print("⚠️ 마크다운 파일을 찾을 수 없습니다.")
        return

    print(f"📄 {len(md_files)}개 노트 파일 발견")

    # 모든 파일 읽기
    all_content = []
    for f in md_files:
        with open(f, 'r', encoding='utf-8') as fp:
            all_content.append((os.path.basename(f), fp.read()))

    # 최신 파일 (마지막 파일)
    latest_filename, latest_content = all_content[-1]
    print(f"📌 최신 노트: {latest_filename}")

    # 1. 요약 정보 추출
    summary = extract_summary_from_latest(latest_content)

    # 2. 보유 종목 추출
    holdings, sold = extract_holdings(latest_content)
    print(f"💼 보유 종목: {len(holdings)}개, 매도 종목: {len(sold)}개")

    # 3. 거래 내역 수집 (전체 파일 매매기록 테이블에서)
    all_trades = extract_trade_log_table(all_content)

    # 4. 3대 축 분석 추출 (모든 파일에서 최신 것을 찾음)
    analysis = []
    for _, content in reversed(all_content):
        analysis = extract_analysis(content)
        if analysis and analysis[0]['fundamental'] != '—':
            break

    # 5. 블랙의 생각/복기/판단우선순위/매매결정/종료코멘트 추출
    thoughts = extract_black_thoughts(latest_content)
    review = extract_review(latest_content)
    priority = extract_priority(latest_content)
    trade_decisions = extract_trade_decisions(latest_content)
    end_comment = extract_end_comment(latest_content)

    # 6. 일별 수익률 추적
    daily_returns = extract_daily_returns(all_content)

    # 7. 포트폴리오 기준일(시작일) 추출
    inception_date = None
    for _, content in all_content:
        inception_date = extract_inception_date(content)
        if inception_date:
            break

    # 8. 국내/해외 비중 계산
    kr_weight = sum(h['weight'] for h in holdings if h['market'] == 'KR')
    us_weight = sum(h['weight'] for h in holdings if h['market'] == 'US')
    kr_count = sum(1 for h in holdings if h['market'] == 'KR')
    us_count = sum(1 for h in holdings if h['market'] == 'US')

    # 국내/해외 수익률
    kr_return = None
    us_return = None
    kr_match = re.search(r'(?:국내 포트|국내주식 수익률|국내\([^)]*\))[:\s]*([+\-]?[\d.]+)%', latest_content)
    us_match = re.search(r'(?:미국 포트|미국주식 수익률)[:\s]*([+\-]?[\d.]+)%', latest_content)
    if not us_match:
        us_match = re.search(r'미국 부문 합계[^(]*\(([+\-]?[\d.]+)%', latest_content)
    if kr_match:
        kr_return = float(kr_match.group(1))
    if us_match:
        us_return = float(us_match.group(1))

    # 최고/최저 수익 종목
    best = max(holdings, key=lambda h: h['returnPct']) if holdings else None
    worst = min(holdings, key=lambda h: h['returnPct']) if holdings else None

    # JS 데이터 파일 생성
    portfolio_data = {
        'lastUpdated': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'latestNote': latest_filename,
        'inceptionDate': inception_date or '2026-03-13',
        'totalAsset': 1000000000,
        'summary': summary,
        'krWeight': kr_weight,
        'usWeight': us_weight,
        'krCount': kr_count,
        'usCount': us_count,
        'krReturn': kr_return,
        'usReturn': us_return,
        'holdings': holdings,
        'sold': sold,
        'trades': all_trades,
        'tradeLog': all_trades,
        'analysis': analysis,
        'thoughts': thoughts,
        'review': review,
        'priority': priority,
        'tradeDecisions': trade_decisions,
        'endComment': end_comment,
        'dailyReturns': daily_returns,
        'best': {'name': best['name'], 'returnPct': best['returnPct'], 'pnl': best['pnl']} if best else None,
        'worst': {'name': worst['name'], 'returnPct': worst['returnPct'], 'pnl': worst['pnl']} if worst else None,
    }

    # HTML 파일 내 데이터 교체
    data_js = f"const PORTFOLIO_DATA = {json.dumps(portfolio_data, ensure_ascii=False, indent=2)};"

    with open(HTML_FILE, 'r', encoding='utf-8') as fp:
        html_content = fp.read()

    # 기존 데이터 블록 교체 (마커 사이의 내용을 교체)
    start_marker = "// === DATA_START ==="
    end_marker = "// === DATA_END ==="

    start_idx = html_content.find(start_marker)
    end_idx = html_content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("⚠️ HTML 파일에서 데이터 마커를 찾을 수 없습니다.")
        return

    new_html = (
        html_content[:start_idx]
        + start_marker + "\n"
        + data_js + "\n"
        + html_content[end_idx:]
    )

    with open(HTML_FILE, 'w', encoding='utf-8') as fp:
        fp.write(new_html)

    print(f"✅ portfolio_app.html 업데이트 완료!")
    print(f"   총 수익률: {summary['totalReturn']:+.2f}%")
    print(f"   보유: {len(holdings)}종목 | 매도: {len(sold)}종목")
    print(f"   국내 {kr_weight}% ({kr_count}종목) / 해외 {us_weight}% ({us_count}종목)")


if __name__ == '__main__':
    main()
