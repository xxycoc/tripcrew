extends Node
## Transport only. Replay is opt-in, finite, and never opens a socket.

signal event_received(event: Dictionary)
signal status_changed(offline: bool, replay: bool)

const URL := "ws://127.0.0.1:8770"
var socket: WebSocketPeer
var reconnect_in := 0.0
var replay := false
var replay_events: Array[Dictionary] = []
var replay_elapsed := 0.0
var replay_index := 0
var enabled := false
var offline := true

func start() -> void:
	enabled = true
	var args := OS.get_cmdline_user_args()
	var index := args.find("--replay")
	if index >= 0:
		replay = true
		if index + 1 >= args.size():
			push_error("--replay requires a JSONL resource path")
		else:
			load_replay(args[index + 1])
		offline = false
	status_changed.emit(offline, replay)

func load_replay(path: String) -> void:
	replay_events.clear()
	replay_index = 0
	replay_elapsed = 0
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("Cannot open replay: " + path)
		return
	var previous := 0.0
	while not file.eof_reached():
		var line := file.get_line().strip_edges()
		if line.is_empty():
			continue
		var parsed := JSON.new()
		if parsed.parse(line) != OK or not parsed.data is Dictionary:
			push_warning("Skipping invalid replay JSON")
			continue
		var event: Dictionary = parsed.data
		var at = event.get("at", previous + 2.0)
		if not (at is float or at is int) or not is_finite(float(at)):
			continue
		event["at"] = maxf(previous, float(at))
		previous = event.at
		replay_events.append(event)

func _process(delta: float) -> void:
	if not enabled:
		return
	if replay:
		replay_elapsed += delta
		while replay_index < replay_events.size() and replay_events[replay_index].at <= replay_elapsed:
			event_received.emit(replay_events[replay_index])
			replay_index += 1
		return
	if socket == null:
		reconnect_in -= delta
		if reconnect_in <= 0:
			socket = WebSocketPeer.new()
			var error := socket.connect_to_url(URL)
			if error != OK:
				disconnect_socket()
		return
	socket.poll()
	match socket.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if offline:
				offline = false
				status_changed.emit(false, false)
			while socket.get_available_packet_count() > 0:
				var packet := socket.get_packet()
				if not socket.was_string_packet():
					continue
				var parsed := JSON.new()
				if parsed.parse(packet.get_string_from_utf8()) == OK and parsed.data is Dictionary:
					event_received.emit(parsed.data)
		WebSocketPeer.STATE_CLOSED:
			disconnect_socket()

func disconnect_socket() -> void:
	socket = null
	reconnect_in = 2.0
	if not offline:
		offline = true
		status_changed.emit(true, false)
