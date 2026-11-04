import asyncio

from .events import event

STORY = [
    ("join", {"actor": "you"}),
    ("join", {"actor": "planner"}),
    ("join", {"actor": "budget"}),
    ("join", {"actor": "reel_adder"}),
    ("user_message", {"text": "@planner Add this TikTok food stop to my Osaka day."}),
    ("addressed", {"actor": "planner", "text": "Add this TikTok food stop to my Osaka day."}),
    ("agent_message", {"actor": "planner", "text": "@reel Please identify the food stop."}),
    ("addressed", {"actor": "reel_adder", "text": "Please identify the food stop."}),
    ("reel", {"step": "fetch_start", "platform": "tiktok"}),
    ("reel", {"step": "watching", "platform": "tiktok"}),
    ("reel", {"step": "identified", "platform": "tiktok", "place": "Kushikatsu Daruma, Shinsekai"}),
    ("agent_message", {"actor": "reel_adder", "text": "Kushikatsu Daruma, Shinsekai. Pin sent to Planner."}),
    ("task", {"from": "planner", "to": "budget", "state": "delegated", "summary": "Check the Osaka food budget"}),
    ("task", {"from": "planner", "to": "budget", "state": "accepted", "summary": "Check the Osaka food budget"}),
    ("agent_message", {"actor": "budget", "text": "The food stop fits the budget."}),
    ("task", {"from": "planner", "to": "budget", "state": "finalised", "summary": "Food budget checked"}),
    ("user_message", {"text": "@reel Can you check this Instagram reel too?"}),
    ("addressed", {"actor": "reel_adder", "text": "Can you check this Instagram reel too?"}),
    ("reel", {"step": "fetch_start", "platform": "instagram"}),
    ("reel", {"step": "failed", "platform": "instagram", "reason": "Private reel; please send a screenshot"}),
    ("agent_message", {"actor": "reel_adder", "text": "I could not watch that reel. Please send a screenshot."}),
]


async def play(hub, mapper, interval=1.5):
    await hub.publish(event("switch_on"))
    while True:
        for kind, fields in STORY:
            await asyncio.sleep(interval)
            if kind == "reel":
                items = mapper.reel({"type": kind, **fields})
            else:
                items = [event(kind, **fields)]
                if kind in {"user_message", "agent_message"}:
                    items.append(mapper.board(f"{fields.get('actor', 'you')}: {fields['text']}"))
            await hub.publish_many(items)
