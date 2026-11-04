extends SceneTree
## Invoke with -- --replay res://dev/sample_events.jsonl, just like the game.

var world: Node2D
var age := 0.0

func _initialize() -> void:
	call_deferred("start")

func start() -> void:
	world = load("res://scenes/main.tscn").instantiate()
	root.add_child(world)

func _process(delta: float) -> bool:
	if world == null:
		return false
	age += delta
	if age > 70:
		var feed: Node = world.get_node("Feed")
		var passed: bool = world.replay and world.status_label.text == "REPLAY\nDEMO FEED" and feed.socket == null and feed.replay_index == 24 and world.actors.reel_adder.position == Vector2(322, 486)
		print("TripCrew replay CLI: %s; events=%d, badges=%s, socket=%s" % ["PASS" if passed else "FAIL", feed.replay_index, world.status_label.text.replace("\n", ", "), str(feed.socket)])
		world.free()
		quit(0 if passed else 1)
	return false
