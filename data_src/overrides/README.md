# 사람이 고친 값 (overrides)

이 폴더의 `*.json`은 파이프라인의 `overrides` 단계가 생성기 결과 **위에** 얹습니다. 초안이나 월드를 다시 만들어도 여기 적은 값은 남습니다.
`_`로 시작하는 파일(`_applied.json`)은 되돌리기 기록이라 직접 고치지 않습니다.

```
python3 tools/overrides.py where 목검                     # 찾기
python3 tools/overrides.py set eq_w1_mokgeom stats.atk 7   # local.json 에 기록 + 적용
python3 tools/overrides.py unset eq_w1_mokgeom stats.atk   # 원래 값으로
python3 tools/overrides.py list
```
주제별로 파일을 나눠도 됩니다(`balance_적.json`, `문구_유산.json` …). 파일 이름 순서로 합칩니다.
자세한 내용: `docs/수정_가이드.md`
