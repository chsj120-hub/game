# 대화·서사 수정본 넣는 곳

이 폴더의 `*.json` 은 `tools/gen_story.py` 가 초안(`../drafts/`) 위에 **파일 이름 순서대로 깊은 병합**합니다.
초안을 몇 번 다시 만들어도 여기 적은 내용은 그대로 남습니다.

- 새로 고칠 서사 꺼내기: `python3 tools/story_tool.py edit q_cp_chakho` → `promotion.json`·`recruit.json` 같은 종류별 파일이 생깁니다.
- 엑셀로 고치기: `story_tool.py export` → 엑셀 수정 → `story_tool.py import docs/대화_서사.xlsx` → `xlsx_import.json` 에 바뀐 칸만 기록됩니다.
- 반영·검사: `python3 tools/story_tool.py check`

작은 예 (착호갑사 영입 두 번째 장면의 두 번째 대사만 바꾸기):

```json
{
 "narratives": {
  "quest:q_cp_chakho": {
   "status": "final",
   "steps": {"1": {"lines": {"1": {"who": "cp_chakho", "text": "호랑이 셋을 잡아 오면 함께 가겠소."}}}}
  }
 }
}
```

자세한 규칙은 `docs/대화_서사_편집_가이드.md`.
