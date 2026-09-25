"""Prove the session log with fixture events. No Nimble and no Liquid yet."""

from __future__ import annotations

from horizon.config import load_config
from horizon.rawtree import RawTree
from horizon.store import SessionLog

FIXTURES = [
    ("observation", "Search: agents lose reliability as the trace grows.", "Result set A"),
    ("observation", "Search: raw page text is what fills the context window.", "Result set B"),
    ("observation", "Search: a retained working state can replace the old prefix.", "Result set C"),
    ("decision", "Keep the goal and the facts; hide the raw search bodies.", "Operator note"),
    ("observation", "Search: compaction has to survive a later read of the timeline.", "Result set D"),
]


def load_key() -> str:
    return load_config()["rawtree_api_key"]


def show(label: str, timeline: dict) -> None:
    state = timeline["working_state"]
    print(f"\n{label}")
    print(f"  visible={timeline['visible_count']}  hidden={timeline['hidden_count']}")
    if state:
        print(f"  goal: {state.get('goal')}")
        print(f"  facts: {len(state.get('facts') or [])}  source: {state.get('source')}")
    for event in timeline["events"]:
        print(f"  #{event['seq']} {event['kind']}: {event['summary']}")


def main() -> None:
    log = SessionLog(RawTree(load_key()))
    session = log.register(
        "research-demo",
        "Show that a supervisor can compact a research trace without losing the goal.",
    )
    agent_id = session["agent_id"]
    print(f"registered {agent_id}")

    for kind, summary, body in FIXTURES:
        log.append_event(agent_id, kind, summary, body)

    show("before compact", log.get_timeline(agent_id))
    result = log.compact(agent_id)
    print(f"\ncompact compacted={result['compacted']} hidden={result['hidden_count']}")
    show("after compact", log.get_timeline(agent_id))

    again = log.compact(agent_id)
    print(f"\nsecond compact compacted={again['compacted']} hidden={again['hidden_count']}")

    log.append_event(agent_id, "observation", "Search: one new result after the checkpoint.", "Result set E")
    show("after one new event", log.get_timeline(agent_id))


if __name__ == "__main__":
    main()
