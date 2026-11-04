extends Node2D
## Event validation and scene composition. No background agent activity is made up.

const Actor := preload("res://scripts/actor.gd")
const Scenery := preload("res://scripts/scenery.gd")
const AGENTS := ["planner", "budget", "reel_adder"]
const NAMES := {"planner": "Planner", "budget": "Budget", "reel_adder": "Reel Adder", "you": "you"}
@export var feed_enabled := true
var actors: Dictionary = {}
var switched_on := false
var demo := false
var replay := false
var offline := true
var board_lines: Array[String] = []
var cards: Array[Dictionary] = []
var bubbles: Dictionary = {}
var board_label: Label
var status_label: Label
var scenery: Node2D
var clock := 0.0

func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	scenery = $Building
	scenery.set_script(Scenery)
	scenery.world = self
	var homes := {"planner": Vector2(64, 278), "budget": Vector2(206, 278), "reel_adder": Vector2(346, 278), "you": Vector2(470, 486)}
	var spots := {"planner": Vector2(198, 486), "budget": Vector2(258, 486), "reel_adder": Vector2(322, 486), "you": Vector2(378, 486)}
	var ladders := {"planner": 132.0, "budget": 174.0, "reel_adder": 412.0, "you": 450.0}
	for id in ["planner", "budget", "reel_adder", "you"]:
		var actor := Actor.new()
		actor.setup(id, homes[id], spots[id], ladders[id])
		actor.pin_handoff.connect(func(place: String): add_card("reel_adder", "planner", "PIN: " + place, "identified"))
		$Actors.add_child(actor)
		actors[id] = actor
		var label := make_label($Bubbles, "", Vector2.ZERO, Vector2(184, 0), 12)
		label.name = id.to_pascal_case() + "Bubble"
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

func make_label(parent: Node, text: String, at: Vector2, dimensions: Vector2, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.position = at
	label.size = dimensions
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("fff6e7"))
	label.add_theme_color_override("font_outline_color", Color("322b3d"))
	label.add_theme_constant_override("outline_size", 2)
	parent.add_child(label)
	return label

func build_labels() -> void:
	make_label($Labels, "TripCrew", Vector2(18, 22), Vector2(320, 35), 28)
	make_label($Labels, "YOUR AI CREW, TOGETHER", Vector2(20, 58), Vector2(330, 20), 11)
	for i in range(3):
		var id: String = AGENTS[i]
		var x := 22 + 142 * i
		make_label($Labels, NAMES[id], Vector2(x, 121), Vector2(130, 25), 16)
		make_label($Labels, "Codex" if id == "budget" else "Claude Code", Vector2(x + 5, 151), Vector2(114, 20), 11)
	make_label($Labels, "Screening", Vector2(23, 307), Vector2(92, 20), 12)
	make_label($Labels, "Telegram room · TripCrew", Vector2(192, 296), Vector2(239, 23), 14)
	make_label($Labels, "TikTok / IG", Vector2(23, 410), Vector2(90, 20), 11)
	make_label($Labels, "WALL BOARD", Vector2(204, 332), Vector2(176, 18), 10)
	board_label = make_label($Labels, "", Vector2(204, 353), Vector2(174, 77), 11)
	board_label.clip_text = true
	board_label.add_theme_constant_override("line_spacing", -2)
	make_label($Labels, "you", Vector2(444, 402), Vector2(35, 20), 12)
	make_label($Labels, "ONE CHAT. A WHOLE CREW.", Vector2(128, 514), Vector2(315, 20), 11)
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
					board_lines.append(line.left(100))
			board_label.text = "\n".join(board_lines)
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
	var label := make_label($Cards, state.to_upper() + "\n" + summary.left(80), Vector2.ZERO, Vector2(156, 0), 11)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var style := StyleBoxFlat.new()
	style.bg_color = Color("735539")
	style.border_color = Color("f9dc8c")
	style.set_border_width_all(2)
	style.set_content_margin_all(6)
	label.add_theme_stylebox_override("normal", style)
	cards.append({"from": from, "to": to, "summary": summary, "age": 0.0, "label": label})
	if cards.size() > 8:
		cards.pop_front().label.queue_free()

func _process(delta: float) -> void:
	advance(delta)

func advance(delta: float) -> void:
	clock += delta
	for id in actors:
		actors[id].tick(delta)
		var label: Label = bubbles[id]
		label.text = actors[id].bubble
		label.visible = not label.text.is_empty()
		label.size = Vector2(184, 0)
		label.position = Vector2(clampf(actors[id].position.x - 92, 6, 290), clampf(actors[id].position.y - 65 - label.get_combined_minimum_size().y, 84, 450))
	for i in range(cards.size() - 1, -1, -1):
		var card: Dictionary = cards[i]
		card.age += delta
		var t := clampf(card.age / 1.6, 0, 1)
		var from: Vector2 = actors[card.from].position + Vector2(0, -55)
		var to: Vector2 = actors[card.to].position + Vector2(0, -55)
		var point := from.lerp(to, t * t * (3 - 2 * t)) + Vector2(0, -sin(t * PI) * 25)
		card.label.position = Vector2(clampf(point.x - 78, 6, 318), clampf(point.y - 40, 84, 430))
		if card.age >= 2.5:
			card.label.queue_free()
			cards.remove_at(i)
	scenery.queue_redraw()
