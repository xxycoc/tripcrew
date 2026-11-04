extends Node2D
## A single owner of each actor's motion; jobs expand only when they start.

signal pin_handoff(place: String)

const UPPER := 278.0
const LOWER := 486.0
const MAX_QUEUE := 4
const COLORS := {"planner": Color("e59b53"), "budget": Color("62c794"), "reel_adder": Color("ee8caf"), "you": Color("74b5ee")}
const FRAMES := {"planner": 6, "budget": 0, "reel_adder": 4, "you": 2}

var actor_id := ""
var home := Vector2.ZERO
var hall := Vector2.ZERO
var ladder_x := 0.0
var jobs: Array[Dictionary] = []
var steps: Array[Dictionary] = []
var current_job: Dictionary = {}
var current_step: Dictionary = {}
var elapsed := 0.0
var move_start := Vector2.ZERO
var mode := "idle"
var working := false
var work_requested := false
var room_lit := false
var note := false
var pin := false
var bubble := ""
var bubble_left := 0.0
var facing := 1.0
var animation_time := 0.0
var compressed := false
var completed: Array[String] = []
var sprite: Sprite2D
var textures: Array[Texture2D] = []
var user_actor: Node2D

func setup(id: String, home_point: Vector2, hall_point: Vector2, ladder: float) -> void:
	actor_id = id
	name = id.to_pascal_case()
	home = home_point
	hall = hall_point
	ladder_x = ladder
	position = home
	sprite = Sprite2D.new()
	sprite.name = "KenneyCharacter"
	sprite.position = Vector2(0, -24)
	sprite.scale = Vector2(2, 2)
	for index in [FRAMES[id], FRAMES[id] + 1]:
		textures.append(load("res://assets/kenney/pixel-platformer/Tiles/Characters/tile_%04d.png" % index))
	sprite.texture = textures[0]
	add_child(sprite)

func enqueue(event: Dictionary) -> void:
	jobs.append(event.duplicate(true))
	if jobs.size() > MAX_QUEUE:
		# Catch up to the newest event without changing the actor's position.
		jobs.assign([jobs.back()])
		steps.clear()
		current_step.clear()
		current_job.clear()
		bubble = ""
		bubble_left = 0.0
		compressed = true

func tick(delta: float) -> void:
	animation_time += delta
	bubble_left = maxf(0, bubble_left - delta)
	if bubble_left == 0:
		bubble = ""
	var remaining := delta
	# Consume leftover time so the same event sequence is deterministic at any fps.
	for unused in range(128):
		if current_step.is_empty():
			if steps.is_empty():
				if not current_job.is_empty():
					completed.append(str(current_job.type))
					if completed.size() > 32:
						completed.pop_front()
					current_job.clear()
					compressed = false
				if jobs.is_empty():
					break
				current_job = jobs.pop_front()
				build_job(current_job)
			current_step = steps.pop_front()
			elapsed = 0
			move_start = position
			if current_step.kind == "move":
				mode = "climbing" if not is_equal_approx(position.y, current_step.target.y) else "walking"
				if not is_equal_approx(position.x, current_step.target.x):
					facing = signf(current_step.target.x - position.x)
			elif current_step.kind == "state":
				apply_state(current_step)
				current_step.clear()
				continue
		var duration: float = current_step.duration
		var consumed := minf(remaining, duration - elapsed)
		elapsed += consumed
		remaining -= consumed
		if current_step.kind == "move":
			var t := clampf(elapsed / duration, 0, 1)
			position = move_start.lerp(current_step.target, t * t * (3.0 - 2.0 * t))
		if elapsed >= duration - 0.00001:
			current_step.clear()
		else:
			break
		if remaining <= 0:
			break
	sprite.flip_h = facing < 0
	var walking := mode in ["walking", "climbing"] and not current_step.is_empty()
	sprite.texture = textures[int(animation_time * 8) % 2 if walking else 0]
	sprite.region_enabled = mode in ["working", "watching"]
	sprite.region_rect = Rect2(0, 0, 24, 19)
	sprite.position.y = -25 if mode == "waving" and int(animation_time * 6) % 2 == 0 else -24
	queue_redraw()

func build_job(event: Dictionary) -> void:
	var kind: String = event.type
	match kind:
		"addressed":
			work_requested = true
			route(home)
			state("working")
		"user_message":
			state("walking", "", true)
			route(hall)
			state("idle", event.text, true)
			wait_for(3)
			state("idle")
		"agent_message", "join":
			if kind == "agent_message":
				work_requested = false
			state("idle")
			route(hall)
			state("speaking" if kind == "agent_message" else "waving", str(event.get("text", "")))
			wait_for(3 if kind == "agent_message" else 1)
			route(home)
			state("working" if work_requested else "idle")
		"reel":
			match event.step:
				"fetch_start":
					state("idle")
					route(Vector2(96, LOWER))
					state("away")
				"watching":
					route(Vector2(62, LOWER))
					state("watching", "watching...")
				"identified":
					state("walking", "", false, true)
					route(Vector2(198, LOWER))
					state("handoff", "PIN: " + str(event.get("place", "")), false, true)
					wait_for(3)
					state("idle")
					route(home)
					state("working" if work_requested else "idle")
				"failed":
					state("walking", "?")
					var user_x := user_actor.position.x if user_actor != null else 378.0
					route(Vector2(clampf(user_x - 28, 130, 442), LOWER))
					state("failed", "?")
					wait_for(3)
					state("idle")

func route(target: Vector2) -> void:
	var start := position
	for step in steps:
		if step.kind == "move":
			start = step.target
	if not is_equal_approx(start.y, target.y):
		move_to(Vector2(ladder_x, start.y), start)
		start = Vector2(ladder_x, start.y)
		move_to(Vector2(ladder_x, target.y), start)
		start = Vector2(ladder_x, target.y)
	move_to(target, start)

func move_to(target: Vector2, start: Vector2) -> void:
	if start.distance_to(target) < 0.01:
		return
	var speed := 450.0 if compressed else 155.0
	steps.append({"kind": "move", "target": target, "duration": maxf(0.08, start.distance_to(target) / speed)})

func state(value: String, text := "", has_note := false, has_pin := false) -> void:
	steps.append({"kind": "state", "value": value, "text": text, "note": has_note, "pin": has_pin})

func wait_for(seconds: float) -> void:
	steps.append({"kind": "wait", "duration": minf(seconds, 0.6) if compressed else seconds})

func apply_state(step: Dictionary) -> void:
	mode = step.value
	working = mode == "working"
	if mode == "working":
		room_lit = true
	elif current_job.type == "agent_message":
		room_lit = false
	note = step.note
	pin = step.pin
	bubble = step.text
	bubble_left = INF if mode == "watching" else (0.6 if compressed else 3.0)
	if mode == "handoff":
		pin_handoff.emit(str(current_job.get("place", "")))

func _draw() -> void:
	draw_ellipse_shadow()
	if mode in ["working", "watching"]:
		draw_rect(Rect2(-15, -17, 7, 17), Color("68546e"))
		draw_rect(Rect2(-15, -8, 25, 5), Color("68546e"))
	if note or pin:
		draw_rect(Rect2(13, -32, 13, 16), Color("ffe6a0") if pin else Color("fff9e9"))
		draw_rect(Rect2(16, -29, 7, 2), Color("d36c58") if pin else Color("63809b"))
		draw_rect(Rect2(16, -24, 5, 2), Color("63809b"))
	if mode == "waving":
		draw_rect(Rect2(16, -38 + (int(animation_time * 6) % 2) * 4, 5, 10), COLORS[actor_id])

func draw_ellipse_shadow() -> void:
	draw_rect(Rect2(-15, -3, 30, 4), Color(0.13, 0.12, 0.19, 0.22))
