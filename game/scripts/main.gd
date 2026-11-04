extends Node2D
## Event validation and scene composition. No background agent activity is made up.

const Actor := preload("res://scripts/actor.gd")
const Scenery := preload("res://scripts/scenery.gd")
const AGENTS := ["planner", "budget", "reel_adder"]
const NAMES := {"planner": "Planner", "budget": "Budget", "reel_adder": "Reel Adder", "you": "you"}
const FRAME := Rect2(6, 6, 468, 528)
const BOARD := Rect2(196, 326, 190, 108)
const BOARD_INNER := Rect2(204, 353, 174, 77)
@export var feed_enabled := true
var actors: Dictionary = {}
var switched_on := false
var demo := false
var replay := false
var offline := true
var board_lines: Array[String] = []
var cards: Array[Dictionary] = []
var bubbles: Dictionary = {}
var board_label: Control
var board_rows: Array[Label] = []
var status_label: Label
var scenery: Node2D
var clock := 0.0

func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	scenery = $Building
	scenery.set_script(Scenery)
	scenery.world = self
	var homes := {"planner": Vector2(64, 278), "budget": Vector2(206, 278), "reel_adder": Vector2(346, 278), "you": Vector2(454, 486)}
	var spots := {"planner": Vector2(198, 486), "budget": Vector2(258, 486), "reel_adder": Vector2(322, 486), "you": Vector2(378, 486)}
	var ladders := {"planner": 132.0, "budget": 174.0, "reel_adder": 412.0, "you": 450.0}
	for id in ["planner", "budget", "reel_adder", "you"]:
		var actor := Actor.new()
		actor.setup(id, homes[id], spots[id], ladders[id])
		actor.pin_handoff.connect(func(place: String): add_card("reel_adder", "planner", "PIN: " + place, "identified"))
		$Actors.add_child(actor)
		actors[id] = actor
		var label := make_label($Bubbles, "", Vector2.ZERO, Vector2(184, 0), 12, true)
		label.name = id.to_pascal_case() + "Bubble"
		label.visible = false
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.add_theme_color_override("font_color", Color("302c40"))
		label.add_theme_color_override("font_outline_color", Color("fff9ed"))
		var style := StyleBoxFlat.new()
		style.bg_color = Color("fff9ed")
		style.border_color = Actor.COLORS[id].darkened(0.25)
		style.set_border_width_all(2)
		style.content_margin_left = 7
		style.content_margin_right = 7
		style.content_margin_top = 5
		style.content_margin_bottom = 5
		label.add_theme_stylebox_override("normal", style)
		bubbles[id] = label
	actors.reel_adder.user_actor = actors.you
	build_labels()
	$Feed.event_received.connect(handle_event)
	$Feed.status_changed.connect(func(is_offline: bool, is_replay: bool):
		offline = is_offline
		replay = is_replay
		refresh_status())
	if feed_enabled:
		$Feed.start()
	refresh_status()

func make_label(parent: Node, text: String, at: Vector2, dimensions: Vector2, font_size: int, wrap := false) -> Label:
	var label := Label.new()
	# Set wrapping before text so an unwrapped minimum width cannot enlarge the control.
	if wrap:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	label.text = text
	label.position = at
	label.size = dimensions
	label.add_theme_color_override("font_color", Color("fff6e7"))
	label.add_theme_color_override("font_outline_color", Color("322b3d"))
	label.add_theme_constant_override("outline_size", 2)
	parent.add_child(label)
	label.size = dimensions
	return label

func build_labels() -> void:
	make_label($Labels, "TripCrew", Vector2(18, 22), Vector2(320, 35), 28)
	for i in range(3):
		var id: String = AGENTS[i]
		var x := 22 + 142 * i
		make_label($Labels, NAMES[id], Vector2(x, 121), Vector2(130, 25), 16)
		make_label($Labels, "Codex" if id == "budget" else "Claude Code", Vector2(x + 5, 151), Vector2(114, 20), 11)
	make_label($Labels, "Screening", Vector2(23, 307), Vector2(92, 20), 12)
	make_label($Labels, "Telegram room · TripCrew", Vector2(192, 296), Vector2(239, 23), 14)
	make_label($Labels, "TikTok / IG", Vector2(23, 410), Vector2(90, 20), 11)
	make_label($Labels, "WALL BOARD", Vector2(204, 332), Vector2(176, 18), 10)
	board_label = Control.new()
	board_label.name = "BoardContent"
	board_label.position = BOARD_INNER.position
	board_label.size = BOARD_INNER.size
	board_label.clip_contents = true
	$Labels.add_child(board_label)
	for i in range(6):
		var row := make_label(board_label, "", Vector2(0, i * 12), Vector2(174, 12), 10)
		row.clip_text = true
		row.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		row.add_theme_constant_override("outline_size", 0)
		board_rows.append(row)
	make_label($Labels, "you", Vector2(444, 402), Vector2(35, 20), 12)
	status_label = make_label($Labels, "", Vector2(300, 28), Vector2(167, 50), 11)
	status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

func refresh_status() -> void:
	if status_label == null:
		return
	var status: Array[String] = []
	if replay:
		status.append("REPLAY")
	if demo:
		status.append("DEMO FEED")
	if offline and not replay:
		status.append("relay offline")
	status_label.text = "\n".join(status)

func valid_string(event: Dictionary, key: String) -> bool:
	return event.get(key) is String

func handle_event(event: Dictionary) -> void:
	if event.get("v") != 1 or not valid_string(event, "type"):
		return
	match event.type:
		"hello":
			if event.get("mode") in ["live", "demo"]:
				demo = event.mode == "demo"
				refresh_status()
		"switch_on":
			switched_on = true
		"board":
			if not event.get("lines") is Array:
				return
			board_lines.clear()
			for line in event.lines.slice(0, 6):
				if line is String:
					board_lines.append(line.left(100).replace("\n", " ").replace("\r", " ").replace("\t", " "))
			for i in range(board_rows.size()):
				board_rows[i].text = board_lines[i] if i < board_lines.size() else ""
		"user_message":
			if valid_string(event, "text"):
				actors.you.enqueue({"type": "user_message", "text": short_text(event.text)})
		"addressed", "agent_message", "join":
			if not event.get("actor") in AGENTS:
				return
			if event.type != "join" and not valid_string(event, "text"):
				return
			var job := event.duplicate(true)
			job.text = short_text(str(event.get("text", "")))
			actors[event.actor].enqueue(job)
		"task":
			if event.get("from") in actors and event.get("to") in actors and event.get("state") in ["delegated", "accepted", "finalised"] and valid_string(event, "summary"):
				add_card(event.from, event.to, short_text(event.summary), event.state)
		"reel":
			if event.get("step") in ["fetch_start", "watching", "identified", "failed"]:
				var job := event.duplicate(true)
				job.place = short_text(str(event.get("place", "")))
				actors.reel_adder.enqueue(job)

func short_text(value: String) -> String:
	return value.left(160).replace("\r", " ").replace("\n", " ")

func add_card(from: String, to: String, summary: String, state: String) -> void:
	var label := make_label($Cards, state.to_upper() + "\n" + summary.left(80), Vector2.ZERO, Vector2(100, 0), 11, true)
	label.max_lines_visible = 4
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var style := StyleBoxFlat.new()
	style.bg_color = Color("735539")
	style.border_color = Color("f9dc8c")
	style.set_border_width_all(2)
	style.set_content_margin_all(6)
	label.add_theme_stylebox_override("normal", style)
	var card := {"from": from, "to": to, "summary": summary, "age": 0.0, "label": label, "start": actors[from].position}
	position_card(card)
	cards.append(card)
	if cards.size() > 8:
		cards.pop_front().label.queue_free()

func _process(delta: float) -> void:
	advance(delta)

func advance(delta: float) -> void:
	clock += delta
	for id in actors:
		actors[id].tick(delta)
	for i in range(cards.size() - 1, -1, -1):
		var card: Dictionary = cards[i]
		card.age += delta
		position_card(card)
		if card.age >= 2.5:
			card.label.queue_free()
			cards.remove_at(i)
	position_bubbles()
	scenery.queue_redraw()

func fit_overlay(label: Label, width: float) -> void:
	label.size = Vector2(width, 0)
	label.size = Vector2(width, label.get_combined_minimum_size().y)

func inside_frame(point: Vector2, dimensions: Vector2) -> Vector2:
	return Vector2(clampf(point.x, FRAME.position.x, FRAME.end.x - dimensions.x), clampf(point.y, FRAME.position.y, FRAME.end.y - dimensions.y))

func position_card(card: Dictionary) -> void:
	var label: Label = card.label
	fit_overlay(label, 100)
	var t := clampf(card.age / 1.6, 0, 1)
	var start := card_dock(card.start, label.size)
	var target := card_dock(actors[card.to].position, label.size)
	var clearance := Rect2(BOARD.position - label.size * 0.5 - Vector2(8, 8), BOARD.size + label.size + Vector2(16, 16))
	var path: Array[Vector2] = [start]
	if segment_hits_rect(start, target, clearance):
		# The board leaves room for a full card only on its left, so use that corridor.
		var left := clearance.position.x - 1
		path.append(Vector2(left, start.y))
		path.append(Vector2(left, target.y))
	path.append(target)
	var length := 0.0
	for i in range(1, path.size()):
		length += path[i - 1].distance_to(path[i])
	var remaining := length * smoothstep(0, 1, t)
	var point := target
	for i in range(1, path.size()):
		var distance := path[i - 1].distance_to(path[i])
		if remaining < distance:
			point = path[i - 1].lerp(path[i], remaining / distance)
			break
		remaining -= distance
	label.position = inside_frame(point - label.size * 0.5, label.size)
	label.modulate.a = 1.0 - clampf((card.age - 1.6) / 0.9, 0, 1)

func card_dock(actor_position: Vector2, dimensions: Vector2) -> Vector2:
	var point := actor_position
	if point.y < BOARD.position.y:
		point.y -= 55
	point = inside_frame(point - dimensions * 0.5, dimensions) + dimensions * 0.5
	var clearance := Rect2(BOARD.position - dimensions * 0.5 - Vector2(9, 9), BOARD.size + dimensions + Vector2(18, 18))
	if clearance.has_point(point):
		var candidates := [Vector2(point.x, clearance.position.y - 1), Vector2(point.x, clearance.end.y + 1), Vector2(clearance.position.x - 1, point.y)]
		var best := Vector2(INF, INF)
		for candidate in candidates:
			if not FRAME.encloses(Rect2(candidate - dimensions * 0.5, dimensions)):
				continue
			if candidate.distance_squared_to(point) < best.distance_squared_to(point):
				best = candidate
		point = best
	return point

func segment_hits_rect(a: Vector2, b: Vector2, bounds: Rect2) -> bool:
	if bounds.has_point(a) or bounds.has_point(b):
		return true
	var corners := [bounds.position, Vector2(bounds.end.x, bounds.position.y), bounds.end, Vector2(bounds.position.x, bounds.end.y)]
	for i in range(4):
		if Geometry2D.segment_intersects_segment(a, b, corners[i], corners[(i + 1) % 4]) != null:
			return true
	return false

func bubble_obstacles() -> Array[Rect2]:
	var obstacles: Array[Rect2] = [BOARD.grow(4)]
	for node in $Labels.get_children():
		if node is Label and not node.text.is_empty():
			# Reserve the ink rather than the label's often wider layout box.
			var ink: Vector2 = node.get_theme_font("font").get_multiline_string_size(node.text, HORIZONTAL_ALIGNMENT_LEFT, -1, node.get_theme_font_size("font_size"))
			var at: Vector2 = node.position
			if node.horizontal_alignment == HORIZONTAL_ALIGNMENT_RIGHT:
				at.x += node.size.x - ink.x
			obstacles.append(Rect2(at, ink).grow(3))
	for id in actors:
		obstacles.append(Rect2(actors[id].position - Vector2(23, 48), Vector2(46, 50)).grow(3))
	for card in cards:
		obstacles.append(Rect2(card.label.position, card.label.size).grow(4))
	return obstacles

func position_bubbles() -> void:
	var occupied := bubble_obstacles()
	var speech_start := occupied.size()
	for id in actors:
		var label: Label = bubbles[id]
		label.text = actors[id].bubble
		label.visible = not label.text.is_empty()
		if not label.visible:
			continue
		fit_overlay(label, 184)
		var preferred: Vector2 = actors[id].position - Vector2(label.size.x * 0.5, 56 + label.size.y)
		var xs: Array[float] = [preferred.x, FRAME.position.x, FRAME.end.x - label.size.x]
		var ys: Array[float] = [preferred.y, actors[id].position.y + 8, FRAME.position.y, FRAME.end.y - label.size.y]
		# Every obstacle contributes a flipped/stacked candidate along each edge.
		for obstacle in occupied:
			xs.append(obstacle.position.x - label.size.x - 4)
			xs.append(obstacle.end.x + 4)
			ys.append(obstacle.position.y - label.size.y - 4)
			ys.append(obstacle.end.y + 4)
		var best := inside_frame(preferred, label.size)
		var best_score := INF
		for x in xs:
			for y in ys:
				var at := inside_frame(Vector2(x, y), label.size)
				var bounds := Rect2(at, label.size)
				var overlap := 0.0
				for i in range(occupied.size()):
					var priority := 100.0 if i == 0 or i >= speech_start else 1.0
					overlap += bounds.intersection(occupied[i]).get_area() * priority
				var score := overlap * 1000000.0 + at.distance_squared_to(preferred)
				if score < best_score:
					best_score = score
					best = at
		label.position = best.round()
		occupied.append(Rect2(label.position, label.size).grow(4))
