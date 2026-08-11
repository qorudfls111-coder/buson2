BUSON2 공식 소식 자동 연결 v7.7

포함 파일
- index.html : 업데이트/공지/CM아지트 목록 표시 기능
- news.json : 자동 수집된 데이터 저장
- scripts/scrape_news.py : 공식 홈페이지 게시판 수집기
- .github/workflows/update-news.yml : GitHub Actions 자동 실행 설정

공식 출처
- 업데이트: https://aion2.plaync.com/ko-kr/board/update/list
- 공지: https://aion2.plaync.com/ko-kr/board/notice/list
- CM아지트: https://aion2.plaync.com/ko-kr/board/cm_story/list

동작
1. GitHub Actions가 매시간 17분/47분에 실행
2. 공식 홈페이지 세 게시판을 Chromium으로 확인
3. 최신 게시물 최대 20개를 news.json에 저장
4. 데이터가 바뀌면 자동 commit/push
5. GitHub Pages가 자동 재배포
6. BUSON2 탭에서 제목/날짜/공식 원문 링크 표시

처음 설치 후 Actions 탭에서 'Update AION2 official news'를 수동 실행해 테스트하세요.
공식 사이트 HTML 구조가 변경되면 수집 스크립트도 수정이 필요할 수 있습니다.
