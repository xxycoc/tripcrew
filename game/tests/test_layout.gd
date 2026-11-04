extends SceneTree
## Geometry regressions, including the frame an event is received and deferred Label layout.

var world: Node2D
var assertions := 0
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, description: String) -> void:
	assertions += 1
	if not ok:
		failures += 1
		if failures <= 30:
			printerr("FAIL: " + description)

func fresh() -> void:
	if world != null:
		world.free()
	world = load("res://scenes/main.tscn").instantiate()
	world.feed_enabled = false
	root.add_child(world)
	world.set_process(false)

func send(kind: String, fields: Dictionary) -> void:
	var event := {"v": 1, "type": kind}
	event.merge(fields)
	world.handle_event(event)

func check_overlays(frame: int) -> void:
	var viewport := Rect2(0, 0, 480, 540)
	var board := Rect2(196, 326, 190, 108)
	var visible: Array[Rect2] = []
	for id in world.actors:
		var bubble: Label = world.bubbles[id]
		if not bubble.visible:
			continue
		var bounds := Rect2(bubble.position, bubble.size)
		check(viewport.encloses(bounds), "frame %d: %s bubble inside frame" % [frame, id])
		check(not board.intersects(bounds), "frame %d: %s bubble clears board" % [frame, id])
		for other in visible:
			check(not bounds.intersects(other), "frame %d: bubbles do not overlap" % frame)
		visible.append(bounds)
		for obstacle in world.bubble_obstacles():
			check(not bounds.intersects(obstacle), "frame %d: %s bubble clears text, cards and faces" % [frame, id])
	for card in world.cards:
		var bounds := Rect2(card.label.position, card.label.size)
		check(viewport.encloses(bounds), "frame %d: whole card inside frame" % frame)
		check(not bounds.intersects(board), "frame %d: card clears board" % frame)
		check(bounds.position.y > 80, "frame %d: card never flashes over title" % frame)
		for label in world.get_node("Labels").get_children():
			if label is Label and not label.text.is_empty():
				var ink: Vector2 = label.get_theme_font("font").get_multiline_string_size(label.text, HORIZONTAL_ALIGNMENT_LEFT, -1, label.get_theme_font_size("font_size"))
				var at: Vector2 = label.position
				if label.horizontal_alignment == HORIZONTAL_ALIGNMENT_RIGHT:
					at.x += label.size.x - ink.x
				check(not bounds.intersects(Rect2(at, ink).grow(2)), "frame %d: card clears %s" % [frame, label.text])

func run() -> void:
	fresh()
	check(world.actors.you.position.x + 26 <= 480, "idle user and carried note fit at entrance")
	for label in world.get_node("Labels").get_children():
		if label is Label:
			check(not label.text.contains("YOUR AI CREW") and not label.text.contains("ONE CHAT"), "invented taglines removed")
	var lines := ["W".repeat(100), "Dinner: 2,000 yen", "Line\nbreak", "4", "5", "6", "7"]
	send("board", {"lines": lines})
	await process_frame
	check(world.board_rows.size() == 6 and world.board_lines.size() == 6, "board limits supplied rows")
	check(world.board_rows[2].text == "Line break", "embedded newlines cannot create extra rows")
	check(world.board_label.clip_contents, "board clips all child ink to its inner rectangle")
	for row in world.board_rows:
		check(Rect2(Vector2.ZERO, world.board_label.size).encloses(Rect2(row.position, row.size)), "whole board row fits inside board: %s %s within %s" % [row.position, row.size, world.board_label.size])
		check(row.clip_text and row.text_overrun_behavior == TextServer.OVERRUN_TRIM_ELLIPSIS, "each board row ellipsizes independently")
	# A newly received card must already be attached to its source before another advance.
	world.actors.reel_adder.position = Vector2(322, 486)
	send("task", {"from": "reel_adder", "to": "planner", "state": "accepted", "summary": "W".repeat(80)})
	var card: Dictionary = world.cards[0]
	check(card.start == Vector2(322, 486), "card captures source's actual position")
	check(card.label.position.distance_to(card.start) < 140, "card positioned at source immediately")
	check_overlays(-1)
	var first: Vector2 = card.label.position
	world.advance(0.8)
	check(card.label.position.distance_to(first) > 20, "card travels toward recipient")
	world.advance(0.9)
	check(card.label.modulate.a > 0 and card.label.modulate.a < 1, "card fades after reaching recipient")
	world.advance(0.9)
	check(world.cards.is_empty(), "faded card removed")
	# Long bubbles and simultaneous ordinary messages use the actual layout controls.
	for id in world.actors:
		world.actors[id].bubble = "A message from " + id
		world.actors[id].bubble_left = INF
	world.advance(0)
	await process_frame
	check_overlays(-2)
	fresh()
	send("user_message", {"text": "W".repeat(160)})
	world.advance(1)
	await process_frame
	var long_bubble: Label = world.bubbles.you
	check(Rect2(0, 0, 480, 540).encloses(Rect2(long_bubble.position, long_bubble.size)), "long smart-wrapped text stays fully inside frame")
	check(not Rect2(196, 326, 190, 108).intersects(Rect2(long_bubble.position, long_bubble.size)), "long bubble also leaves the board readable")
	# Match parent-before-Feed process order in the real scene, including immediate event frames.
	fresh()
	var feed: Node = world.get_node("Feed")
	feed.replay = true
	feed.enabled = true
	feed.set_process(false)
	feed.load_replay("res://dev/sample_events.jsonl")
	for frame in range(280):
		world.advance(0.25)
		feed._process(0.25)
		await process_frame
		check_overlays(frame)
	check(feed.replay_index == 29, "layout replay covers all events, including failure after 52 seconds")
	check(world.actors.you.position.distance_to(world.actors.reel_adder.position) >= 50, "final characters stand beside each other without overlap")
	world.free()
	print("TripCrew layout tests: %d assertions, %d failures" % [assertions, failures])
	quit(0 if failures == 0 else 1)
