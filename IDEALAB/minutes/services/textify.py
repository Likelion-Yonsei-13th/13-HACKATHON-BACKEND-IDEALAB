# minutes/services/textify.py
def minutes_to_summary_text(m: dict) -> str:
    lines = []
    meta = m.get("meta", {})
    header = []
    if meta.get("date"): header.append(meta["date"])
    if meta.get("time"): header.append(meta["time"])
    if meta.get("location"): header.append(meta["location"])
    if header:
      lines.append(" / ".join(header))
    if meta.get("project"): lines.append(f"[프로젝트] {meta['project']}")
    if meta.get("market_area"): lines.append(f"[상권] {meta['market_area']}")

    if m.get("overall_summary"):
        lines.append("")
        lines.append("■ 전체 요약")
        lines.append(m["overall_summary"])

    if m.get("topics"):
        lines.append("")
        lines.append("■ 주요 토픽")
        for t in m["topics"]:
            owner = f" ({t.get('owner')})" if t.get('owner') else ""
            lines.append(f"- {t.get('topic','')}{owner}: {t.get('summary','')}")

    if m.get("decisions"):
        lines.append("")
        lines.append("■ 결정 사항")
        for d in m["decisions"]:
            r = f" (이유: {d.get('rationale')})" if d.get('rationale') else ""
            lines.append(f"- {d.get('decision','')}{r}")

    if m.get("action_items"):
        lines.append("")
        lines.append("■ 액션 아이템")
        for a in m["action_items"]:
            who = a.get("owner") or "TBD"
            due = a.get("due") or "TBD"
            status = a.get("status") or "Open"
            pri = f" [{a['priority']}]" if a.get("priority") else ""
            lines.append(f"- {who}: {a.get('task','')} (due: {due}, status: {status}){pri}")

    if m.get("next_topics"):
        lines.append("")
        lines.append("■ 다음 회의 안건")
        for nt in m["next_topics"]:
            lines.append(f"- {nt}")

    return "\n".join(lines).strip()
