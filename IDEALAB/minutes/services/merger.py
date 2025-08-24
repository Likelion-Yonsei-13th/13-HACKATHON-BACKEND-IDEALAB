from typing import Dict, Any, List, Tuple
import re

def _norm_owner(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or "").strip().lower())

def _norm_task(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or "").strip().lower())

def merge_minutes(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    out = {**old}

    for k in ["meta", "overall_summary"]:
        out[k] = new.get(k, old.get(k))

    def merge_str_list(a: List[str], b: List[str]) -> List[str]:
        s = set(a)
        for x in b:
            if x not in s:
                a.append(x); s.add(x)
        return a

    def merge_obj_list_key(a: List[dict], b: List[dict], key: str) -> List[dict]:
        seen = set([d.get(key, "") for d in a])
        for x in b:
            if x.get(key, "") not in seen:
                a.append(x); seen.add(x.get(key, ""))
        return a

    out["topics"] = merge_obj_list_key(old.get("topics", []), new.get("topics", []), "summary")
    out["decisions"] = merge_obj_list_key(old.get("decisions", []), new.get("decisions", []), "decision")
    out["next_topics"] = merge_str_list(old.get("next_topics", []), new.get("next_topics", []))
    out["risks"] = merge_obj_list_key(old.get("risks", []), new.get("risks", []), "risk")
    out["dependencies"] = merge_str_list(old.get("dependencies", []), new.get("dependencies", []))

    def key_of(ai: dict) -> tuple[str, str]:
        return (_norm_owner(ai.get("owner")), _norm_task(ai.get("task")))

    def better(old_ai: dict, new_ai: dict) -> dict:
        nd, od = new_ai.get("due") or "TBD", old_ai.get("due") or "TBD"
        pick_due = nd if (nd != "TBD" and (od == "TBD" or len(nd) >= len(od))) else od
        ordmap = {"Done":3, "Blocked":2, "Open":1}
        ns, os = new_ai.get("status", "Open"), old_ai.get("status", "Open")
        pick_status = ns if ordmap.get(ns,1) >= ordmap.get(os,1) else os
        pmap = {"High":3,"Medium":2,"Low":1}
        np, op = new_ai.get("priority"), old_ai.get("priority")
        pick_prio = np if (np and pmap.get(np,0) >= pmap.get(op or "",0)) else op
        out = {**old_ai, **new_ai}
        out["due"] = pick_due
        out["status"] = pick_status
        if pick_prio: out["priority"] = pick_prio
        return out

    merged, index = [], {}
    for ai in old.get("action_items", []):
        k = key_of(ai); index[k] = len(merged); merged.append(ai)
    for ai in new.get("action_items", []):
        k = key_of(ai)
        if k in index:
            i = index[k]; merged[i] = better(merged[i], ai)
        else:
            index[k] = len(merged); merged.append(ai)

    out["action_items"] = merged
    return out
