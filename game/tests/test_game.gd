extends SceneTree

var world: Node2D
var assertions := 0
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, description: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		printerr("FAIL: " + description)

func send(kind: String, fields: Dictionary = {}) -> void:
	var event := {"v": 1, "type": kind, "ts": "2026-11-05T03:12:00Z"}
	event.merge(fields)
	world.handle_event(event)

func advance(seconds: float) -> void:
	for i in range(int(ceil(seconds * 60))):
		world.advance(1.0 / 60)

func fresh() -> void:
	if world != null:
		world.free()
	world = load("res://scenes/main.tscn").instantiate()
	world.feed_enabled = false
	root.add_child(world)
	world.set_process(false)

func run() -> void:
	fresh()
	check(not world.switched_on and world.offline, "starts dim and offline")
	advance(3)
	check(world.actors.planner.position == world.actors.planner.home, "no events invent no activity")
	send("hello", {"mode": "demo"})
	check(world.status_label.text.contains("DEMO FEED"), "demo badge")
	send("hello", {"mode": "live"})
	check(not world.status_label.text.contains("DEMO FEED"), "live clears demo badge")
	send("switch_on")
	check(world.switched_on, "Switch lights hall")
	send("board", {"lines": ["A", "B", "C", "D", "E", "F", "G"]})
	check(world.board_lines.size() == 6 and world.board_rows[0].text == "A" and world.board_rows[5].text == "F", "board keeps six supplied lines in separate fitted rows")
	send("user_message", {"text": "A note from outside"})
	var before: Vector2 = world.actors.you.position
	advance(0.1)
	check(world.actors.you.position.x < before.x and world.actors.you.position.x > 378, "user moves continuously from entrance")
	check(world.actors.you.note, "user carries note")
	advance(1)
	check(world.actors.you.bubble == "A note from outside", "user bubble shows actual text")
	advance(4)
	check(world.actors.you.position == Vector2(378, 486) and world.actors.you.bubble.is_empty(), "user stays after timed bubble")
	for id in world.AGENTS:
		send("addressed", {"actor": id, "text": "Work"})
	advance(0.1)
	for id in world.AGENTS:
		check(world.actors[id].working and world.actors[id].room_lit, id + " works at lit desk")
	advance(7)
	check(world.actors.budget.working, "work persists until response")
	send("agent_message", {"actor": "budget", "text": "Budget checked"})
	advance(2.5)
	check(world.actors.budget.bubble == "Budget checked" and not world.actors.budget.working, "message descends then speaks")
	advance(8)
	check(world.actors.budget.position == world.actors.budget.home and not world.actors.budget.room_lit, "speaker returns home and stops working")
	send("join", {"actor": "planner"})
	advance(2.4)
	check(world.actors.planner.mode == "waving", "join waves in hall")
	advance(6)
	check(world.actors.planner.position == world.actors.planner.home, "join returns")
	check(world.actors.planner.working, "join resumes addressed work until an agent message")
	for state in ["delegated", "accepted", "finalised"]:
		send("task", {"from": "planner", "to": "budget", "state": state, "summary": "Dinner"})
	check(world.cards.size() == 3, "all task states create cards")
	advance(0.8)
	check(world.cards[0].label.position.x > 0, "task card moves")
	advance(3)
	check(world.cards.is_empty(), "task cards finish")
	# Every vertical segment must stay on this actor's actual ladder.
	send("agent_message", {"actor": "planner", "text": "On my way"})
	var actor = world.actors.planner
	var last: Vector2 = actor.position
	for i in range(650):
		world.advance(1.0 / 60)
		check(last.distance_to(actor.position) < 7, "continuous eased motion")
		if absf(last.y - actor.position.y) > 0.001:
			# A frame can finish climbing and begin a horizontal segment.
			check(absf(actor.position.x - actor.ladder_x) < 0.15, "climbs only on ladder")
		last = actor.position
	# Reel sequences can arrive together; each high-level job stays in order.
	fresh()
	send("user_message", {"text": "Check this reel"})
	send("reel", {"step": "fetch_start", "platform": "tiktok"})
	send("reel", {"step": "watching"})
	advance(6)
	actor = world.actors.reel_adder
	check(actor.mode == "watching" and actor.position == Vector2(62, 486), "reel exits red door then watches")
	check(actor.bubble == "watching...", "watching state persists")
	send("reel", {"step": "identified", "place": "Daruma"})
	advance(1.1)
	check(actor.mode == "handoff" and actor.pin and actor.bubble == "PIN: Daruma", "identified pin reaches hall")
	check(world.cards.size() == 1 and world.cards[0].to == "planner", "pin is handed to Planner")
	advance(8)
	check(actor.position == actor.home and not actor.pin, "identified returns home")
	send("reel", {"step": "fetch_start"})
	send("reel", {"step": "watching"})
	send("reel", {"step": "failed", "reason": "No location"})
	advance(7.3)
	check(actor.mode == "failed" and actor.position == Vector2(322, 486) and actor.bubble == "?", "failed comes back beside user with sprite clearance")
	advance(4)
	check(actor.position == Vector2(322, 486), "failed stays with user")
	check(actor.completed.slice(0, 3) == ["reel", "reel", "reel"], "queued reel jobs complete in order")
	# Mid-climb overflow never snaps position or retains an unbounded backlog.
	fresh()
	actor = world.actors.planner
	send("agent_message", {"actor": "planner", "text": "First"})
	advance(0.9)
	before = actor.position
	for i in range(5):
		send("agent_message", {"actor": "planner", "text": "Latest %d" % i})
	check(actor.jobs.size() == 1 and actor.position == before, "overflow collapses pending jobs without teleport")
	advance(0.7)
	check(actor.bubble == "Latest 4", "overflow catches newest text quickly")
	advance(4)
	check(actor.position == actor.home and actor.jobs.is_empty(), "compressed job returns home")
	# Malformed and future events are ignored, rather than crashing the feed.
	for event in [{}, {"v": 2, "type": "switch_on"}, {"v": 1, "type": "future"}, {"v": 1, "type": "addressed", "actor": []}, {"v": 1, "type": "task", "from": [], "to": null}, {"v": 1, "type": "agent_message", "actor": "you", "text": "X"}, {"v": 1, "type": "board", "lines": 5}]:
		world.handle_event(event)
	check(not world.switched_on and actor.jobs.is_empty(), "invalid and unknown events do not change state")
	# Long unbroken text uses smart wrapping and stays within the viewport.
	send("user_message", {"text": "https://example.org/".repeat(12)})
	advance(1)
	await process_frame
	world.advance(0)
	var bubble: Label = world.bubbles.you
	check(bubble.position.x >= 0 and bubble.position.x + bubble.size.x <= 480, "long bubble fits horizontally")
	check(bubble.position.y >= 0 and bubble.position.y + bubble.size.y <= 540, "long bubble fits vertically")
	# Replay runs through the same handler and completes once, without a socket.
	fresh()
	var feed: Node = world.get_node("Feed")
	feed.replay = true
	feed.enabled = true
	feed.set_process(false)
	feed.load_replay("res://dev/sample_events.jsonl")
	check(feed.replay_events.size() == 29, "sample covers every event type and reel step")
	for i in range(4200):
		feed._process(1.0 / 60)
		world.advance(1.0 / 60)
	check(feed.socket == null and feed.replay_index == feed.replay_events.size(), "finite replay uses no socket")
	check(world.switched_on and world.board_lines.size() == 6, "sample drives actual scene")
	check(world.actors.reel_adder.position == Vector2(322, 486), "sample ends in failed-at-user state")
	world.free()
	print("TripCrew event tests: %d assertions, %d failures" % [assertions, failures])
	quit(0 if failures == 0 else 1)
