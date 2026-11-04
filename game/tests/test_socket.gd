extends SceneTree
## Local fixture, not the external Switch/Telegram relay. Uses the real Feed node.

var server := TCPServer.new()
var peer: WebSocketPeer
var world: Node2D
var age := 0.0
var phase := 0
var sent := false
var connections := 0
var closed_at := 0.0
var failures := 0

func _initialize() -> void:
	call_deferred("start")

func start() -> void:
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)

func fail(message: String) -> void:
	printerr("FAIL: " + message)
	failures += 1
	finish()

func finish() -> void:
	if peer != null:
		peer.close()
	server.stop()
	world.free()
	print("TripCrew socket test: %d connections, %d failures (%.2f s)" % [connections, failures, age])
	quit(0 if failures == 0 else 1)

func _process(delta: float) -> bool:
	if world == null:
		return false
	age += delta
	if age > 10:
		fail("socket test timed out in phase %d" % phase)
		return false
	if phase == 0 and age > 0.3:
		if not world.offline or world.switched_on:
			fail("absent relay must be offline with no made-up Switch event")
			return false
		var error := server.listen(8770, "127.0.0.1")
		if error != OK:
			fail("fixture port 8770 unavailable: %d" % error)
			return false
		phase = 1
	if server.is_connection_available():
		peer = WebSocketPeer.new()
		peer.accept_stream(server.take_connection())
		connections += 1
		sent = false
	if peer != null:
		peer.poll()
		if peer.get_ready_state() == WebSocketPeer.STATE_OPEN and not sent:
			peer.send_text("not JSON")
			peer.send_text(JSON.stringify({"v": 1, "type": "hello", "mode": "demo"}))
			peer.send_text(JSON.stringify({"v": 1, "type": "switch_on"}))
			peer.send_text(JSON.stringify({"v": 1, "type": "board", "lines": ["Socket connection %d" % connections]}))
			sent = true
	if phase == 1 and world.board_lines == ["Socket connection 1"]:
		if world.offline or not world.demo or not world.switched_on:
			fail("real WebSocket packets did not update the scene")
			return false
		peer.close()
		closed_at = age
		phase = 2
	if phase == 2 and world.offline:
		if not world.status_label.text.contains("relay offline"):
			fail("offline status is missing")
			return false
		phase = 3
	if phase == 3 and world.board_lines == ["Socket connection 2"]:
		if age - closed_at < 1.8 or world.offline:
			fail("reconnect must wait about two seconds and clear offline")
			return false
		finish()
	return false
