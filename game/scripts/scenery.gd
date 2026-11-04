extends Node2D
## The selected B composition, rebuilt for a 480 x 540 portrait frame.

var world: Node2D
var metal: Texture2D = preload("res://assets/kenney/pixel-platformer-industrial-expansion/Tiles/tile_0000.png")
var grass: Texture2D = preload("res://assets/kenney/pixel-platformer/Tiles/tile_0000.png")
var crate: Texture2D = preload("res://assets/kenney/pixel-platformer/Tiles/tile_0026.png")

func rect(x: float, y: float, w: float, h: float, color: String) -> void:
	draw_rect(Rect2(x, y, w, h), Color(color))

func _draw() -> void:
	if world == null:
		return
	rect(0, 0, 480, 540, "88cde4")
	rect(0, 318, 480, 173, "a1d9e7")
	cloud(326, 90)
	cloud(427, 182)
	# Exterior silhouette and a warm, clearly cut-open shell.
	rect(8, 108, 430, 390, "503a36")
	rect(6, 102, 434, 9, "775146")
	rect(16, 113, 418, 165, "f4d5b6")
	room(16, 113, 134, 165, "f2d5b8", "edccac")
	room(158, 113, 134, 165, "d7e7c4", "d1dfbd")
	room(300, 113, 130, 165, "f2ccdf", "eac1d5")
	for x in [150, 292]:
		rect(x, 111, 8, 168, "67483b")
	for i in range(3):
		var id: String = world.AGENTS[i]
		var x := 22 + i * 142
		var accent: Color = world.actors[id].COLORS[id]
		draw_rect(Rect2(x - 2, 120, 127, 27), accent.darkened(0.28))
		rect(x + 2, 151, 114, 19, "4c4449")
		rect(x + 8, 253, 62, 8, "886042")
		rect(x + 12, 261, 5, 17, "694936")
		rect(x + 60, 261, 5, 17, "694936")
		rect(x + 22, 214, 38, 31, "41404c")
		var lit: bool = world.actors[id].working
		var glow := accent.lightened(0.3) if lit else Color("596570")
		if lit and int(world.clock * 5) % 3 == 0:
			glow = glow.lightened(0.25)
		draw_rect(Rect2(x + 26, 218, 30, 23), glow)
		rect(x + 39, 245, 5, 8, "41404c")
		rect(x + 9, 250, 15, 3, "b7a187")
		draw_rect(Rect2(x + 105, 181, 9, 9), accent if world.actors[id].room_lit else Color("86776c"))
		if not world.actors[id].room_lit:
			draw_rect(Rect2(16 + i * 142, 174, 134 if i < 2 else 130, 104), Color(0.14, 0.12, 0.19, 0.08))
	room(16, 294, 96, 192, "302b45", "342e4a")
	room(120, 294, 310, 192, "f2e3c9", "ecdcbe")
	for x in range(12, 438, 18):
		draw_texture_rect(metal, Rect2(x, 278, 18, 16), false, Color("b68f76"))
		draw_texture_rect(metal, Rect2(x, 486, 18, 12), false, Color("a37a5a"))
	rect(112, 294, 8, 128, "67483b")
	rect(112, 422, 8, 64, "a43644")
	# Door leaves open only after the real Switch connection event.
	if world.switched_on:
		rect(112, 422, 4, 64, "e76a62")
		rect(116, 422, 4, 64, "482e39")
	else:
		rect(109, 422, 14, 64, "ac3b49")
		rect(112, 430, 8, 40, "c74c57")
	rect(112, 451, 3, 3, "ffe2a2")
	for x in [132, 174, 412]:
		ladder(x)
	# Board stays clear of all three ladder routes.
	rect(196, 326, 190, 108, "99774c")
	rect(200, 330, 182, 100, "344a50")
	rect(202, 349, 178, 1, "68817c")
	# Screening room: dark until a watching event arrives.
	rect(27, 341, 75, 59, "171e31")
	var watching: bool = world.actors.reel_adder.mode == "watching"
	rect(31, 345, 67, 50, ["e76298", "64d8d6", "c8b8f0"][int(world.clock * 6) % 3] if watching else "243147")
	if watching:
		rect(45, 352, 31, 34, "232c42")
		rect(49, 358, 23, 20, "f6d6a5")
	rect(42, 476, 37, 6, "77547a")
	rect(222, 456, 114, 9, "926b4b")
	rect(228, 465, 7, 21, "694936")
	rect(322, 465, 7, 21, "694936")
	rect(243, 450, 25, 6, "ffedbc")
	rect(294, 444, 9, 12, "73a9c0")
	draw_texture_rect(crate, Rect2(20, 468, 18, 18), false)
	# Exterior entrance is cut away on the right.
	rect(430, 294, 8, 128, "67483b")
	if not world.switched_on:
		rect(430, 422, 8, 64, "8a5c46")
	else:
		rect(430, 422, 3, 64, "aa7954")
	rect(442, 427, 28, 3, "6c6058")
	rect(463, 425, 7, 7, "6c6058")
	for x in range(0, 480, 18):
		draw_texture_rect(grass, Rect2(x, 498, 18, 18), false)
	rect(0, 516, 480, 24, "735840")
	if not world.switched_on:
		draw_rect(Rect2(120, 294, 310, 192), Color(0.11, 0.14, 0.22, 0.5))

func room(x: int, y: int, w: int, h: int, first: String, second: String) -> void:
	rect(x, y, w, h, first)
	for cy in range(y, y + h, 18):
		for cx in range(x, x + w, 18):
			if ((cx - x) / 18 + (cy - y) / 18) % 2 == 0:
				rect(cx, cy, mini(18, x + w - cx), mini(18, y + h - cy), second)

func ladder(x: float) -> void:
	rect(x - 7, 279, 3, 207, "a67950")
	rect(x + 5, 279, 3, 207, "a67950")
	for y in range(285, 486, 12):
		rect(x - 4, y, 9, 3, "c49565")

func cloud(x: float, y: float) -> void:
	rect(x, y, 44, 10, "d9eff1")
	rect(x + 8, y - 7, 23, 7, "d9eff1")
